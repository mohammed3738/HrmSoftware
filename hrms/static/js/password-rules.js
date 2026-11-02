/* Live password checklist and show/hide toggles.
 *
 * Used by the change-password and reset-password pages. Two jobs:
 *
 * 1. Turn each rule in #password-rules red -> green as the user types.
 *    The rules come from the server (templates/auth/_password_rules.html
 *    emits them with json_script, from website/utils/password_rules.py),
 *    so this file never decides what the policy is -- change
 *    PASSWORD_MIN_LENGTH and the number here follows. Rules the browser
 *    cannot judge, like the 20,000-word common-password list, arrive with
 *    mode "server" and are left neutral rather than guessed at.
 *
 * 2. Wire every [data-password-toggle] button to the field it names.
 *
 * Nothing here gates submission: the server validates regardless, and a
 * checklist that disabled the button would lock out anyone whose password
 * only the server can approve.
 */
(function () {
  "use strict";

  function setupToggles() {
    document.querySelectorAll("[data-password-toggle]").forEach(function (button) {
      var field = document.getElementById(button.getAttribute("data-password-toggle"));
      if (!field) return;
      var icon = button.querySelector("i");
      button.addEventListener("click", function () {
        var hidden = field.type === "password";
        field.type = hidden ? "text" : "password";
        button.setAttribute("aria-pressed", hidden ? "true" : "false");
        button.setAttribute("aria-label", hidden ? "Hide password" : "Show password");
        if (icon) {
          icon.className = hidden ? "ri-eye-line" : "ri-eye-off-line";
        }
      });
    });
  }

  function evaluate(rule, password, confirmation) {
    switch (rule.id) {
      case "min_length":
        return password.length >= rule.min_length;
      case "not_numeric":
        // Django's NumericPasswordValidator rejects an all-digit password.
        // An empty box is not a pass -- it would show green before the
        // user has typed anything.
        return password.length > 0 && !/^\d+$/.test(password);
      case "match":
        return password.length > 0 && password === confirmation;
      default:
        return null; // judged on the server
    }
  }

  function setupChecklist() {
    var data = document.getElementById("password-rules-data");
    var container = document.getElementById("password-rules");
    var newPassword = document.getElementById("id_new_password1");
    if (!data || !container || !newPassword) return;

    var rules;
    try {
      rules = JSON.parse(data.textContent);
    } catch (e) {
      return; // leave the server-rendered list as it is
    }

    var confirmation = document.getElementById("id_new_password2");
    var status = document.getElementById("password-rules-status");
    var byId = {};
    container.querySelectorAll(".password-rule").forEach(function (item) {
      byId[item.getAttribute("data-rule")] = item;
    });

    function refresh() {
      var password = newPassword.value;
      var confirmValue = confirmation ? confirmation.value : "";
      var met = 0;
      var live = 0;

      rules.forEach(function (rule) {
        var item = byId[rule.id];
        if (!item || item.getAttribute("data-mode") !== "live") return;
        live += 1;
        var ok = evaluate(rule, password, confirmValue);
        if (ok) met += 1;
        item.classList.toggle("text-success", !!ok);
        item.classList.toggle("text-danger", !ok);
        var icon = item.querySelector(".password-rule-icon");
        if (icon) {
          icon.className = "password-rule-icon " +
            (ok ? "ri-checkbox-circle-line" : "ri-close-circle-line");
        }
      });

      if (status) {
        status.textContent = password.length
          ? met + " of " + live + " password requirements met"
          : "";
      }
    }

    newPassword.addEventListener("input", refresh);
    if (confirmation) confirmation.addEventListener("input", refresh);
    // A redisplayed form arrives with the boxes already filled.
    refresh();
  }

  function init() {
    setupToggles();
    setupChecklist();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
