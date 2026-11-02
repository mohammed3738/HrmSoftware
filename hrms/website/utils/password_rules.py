"""The password rules, in one place, derived from what the server enforces.

The change-password and reset-password pages show a live checklist that
turns green as a password satisfies each rule. The obvious way to build
that is to hard-code "at least 8 characters" in the template -- and then
PASSWORD_MIN_LENGTH changes, or a validator is switched off, and the
checklist quietly lies to the user about what will be accepted.

So the list is read off settings.AUTH_PASSWORD_VALIDATORS instead. Turning
a validator off removes its line from the checklist; changing
PASSWORD_MIN_LENGTH changes the number shown.

Not every rule can be judged in the browser:

* "at least N characters" and "not entirely numeric" are arithmetic, so
  they are checked as the user types (mode "live").
* "not a commonly used password" is a 20,000-word list, and "not too
  similar to your name" needs the account's own attributes. Shipping
  either to the page would be a lot of bytes to tell an attacker nothing
  they could not learn by guessing, so these are listed with mode
  "server": shown so the user knows the rule exists, judged on submit.

website/tests/test_password_rules.py checks this list against the
validators actually configured, in both directions.
"""
from django.conf import settings

#: Validator path -> how to present it. Keys are the tail of the dotted
#: path, so a custom validator with the same class name still matches.
_KNOWN = {
    "MinimumLengthValidator": "min_length",
    "NumericPasswordValidator": "not_numeric",
    "CommonPasswordValidator": "not_common",
    "UserAttributeSimilarityValidator": "not_similar",
}


def _configured():
    """The active validators as (kind, options) pairs, in declared order."""
    for entry in settings.AUTH_PASSWORD_VALIDATORS:
        name = entry.get("NAME", "").rsplit(".", 1)[-1]
        kind = _KNOWN.get(name)
        if kind:
            yield kind, entry.get("OPTIONS", {})


def password_rules():
    """The checklist, as plain dicts ready to be serialised to the page.

    `mode` is "live" when the browser can judge the rule as the user
    types, and "server" when it is only known on submit.
    """
    rules = []
    for kind, options in _configured():
        if kind == "min_length":
            minimum = options.get("min_length", 8)
            rules.append({
                "id": "min_length",
                "label": f"At least {minimum} characters",
                "mode": "live",
                "min_length": minimum,
            })
        elif kind == "not_numeric":
            rules.append({
                "id": "not_numeric",
                "label": "Not only numbers",
                "mode": "live",
            })
        elif kind == "not_common":
            rules.append({
                "id": "not_common",
                "label": "Not a commonly used password",
                "mode": "server",
            })
        elif kind == "not_similar":
            rules.append({
                "id": "not_similar",
                "label": "Not too similar to your name or username",
                "mode": "server",
            })

    # Not a validator -- the form's own confirm-field check. Listed last
    # because it is the one people actually get wrong.
    rules.append({
        "id": "match",
        "label": "Both passwords match",
        "mode": "live",
    })
    return rules
