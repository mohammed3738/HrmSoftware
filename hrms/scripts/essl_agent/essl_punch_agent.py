#!/usr/bin/env python
"""eSSL punch agent -- runs on the WINDOWS server, next to eTimeTrackLite.

Why the traffic goes this way
-----------------------------
The HRMS runs on an Ubuntu server on a different network, with no route to
this machine's SQL Server. Only RDP is published from here, so nothing can
be pulled in from outside. This script therefore runs *here*: it reads
dbo.DeviceLogs over a local connection and POSTs the punches out to the
HRMS over HTTPS. Only outbound 443 is needed, and SQL Server stays closed.

Nothing is created to make this work
------------------------------------
No new database, no new SQL login, no schema change on the eSSL side. The
agent only ever runs SELECTs (see the SQL at the bottom of this file), and
it connects one of two ways:

  Windows Authentication (the default, and the one to prefer)
      SQL Server trusts whichever Windows account the Scheduled Task runs
      as. No password is stored anywhere on disk.

  The credentials eTimeTrackLite itself already uses
      eTimeTrackLite stores them in its own Settings.txt, next to the web
      app. This agent reads that file to discover the server name, the
      database and the login automatically, so there is almost nothing to
      configure. On this installation that file says SQL Server
      Authentication as user "essl" -- an existing login, which the agent
      reuses rather than asking anyone to add one.

Several HRMS targets at once
----------------------------
Each [hrms:<name>] section in the ini is somewhere to push to, with its own
token and its own resume point. That is what a staged rollout needs: point
it at a development PC first, add the Ubuntu staging site next, add
production last, and turn the earlier ones off as you go. A target that is
down or refusing the token is skipped and retried next run -- it never holds
up the others, and it never loses punches, because a target's resume point
only moves after it has accepted them.

Install
-------
See ESSL_INTEGRATION_GUIDE.txt in the repository root. In short:

    py -m pip install pyodbc requests
    copy essl_agent.ini.example essl_agent.ini   (then edit it)
    py essl_punch_agent.py --test
    py essl_punch_agent.py --since 2026-01-01    (one-off backfill)

then register it as a Scheduled Task running every 30 minutes.

Usage
-----
    py essl_punch_agent.py                 normal run (what the task calls)
    py essl_punch_agent.py --test          check SQL + every target, send nothing
    py essl_punch_agent.py --since DATE    re-read from a date, ignoring state
    py essl_punch_agent.py --days N        re-read the last N days
    py essl_punch_agent.py --dry-run       read and report, POST nothing
    py essl_punch_agent.py --target NAME   only this target (repeatable)
    py essl_punch_agent.py --show-config   print what it resolved, then stop
"""
import argparse
import configparser
import datetime
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "essl_agent.ini")
STATE_PATH = os.path.join(HERE, "essl_agent_state.json")
LOG_PATH = os.path.join(HERE, "essl_agent.log")

AGENT_DEFAULTS = {
    "essl_settings_file": "",
    "sql_server": "",
    "sql_database": "",
    "sql_driver": "ODBC Driver 17 for SQL Server",
    "sql_auth": "windows",          # "windows" or "sql"
    "sql_user": "",
    "sql_password": "",
    # dbo.DeviceLogs is a staging buffer eTimeTrackLite empties as it
    # archives into DeviceLogs_<month>_<year>. Off by default: punches live
    # in the monthly tables, and on a tidy installation the buffer is always
    # empty. buffer_row_count() warns if that ever stops being true.
    "read_devicelogs_buffer": "no",
    "overlap_minutes": "180",
    "batch_size": "2000",
    "first_run_days": "30",
    "timeout_seconds": "120",
    "agent_name": "essl-windows-agent",
}

TARGET_DEFAULTS = {
    "url": "",
    "token": "",
    "enabled": "yes",
    "verify_tls": "yes",
}

# Where eTimeTrackLite's own Settings.txt usually sits. Checked in order,
# and only used when essl_settings_file is not set explicitly.
SETTINGS_GUESSES = (
    r"C:\inetpub\wwwroot\iclock\Settings.txt",
    r"C:\inetpub\wwwroot\eTimeTrackLiteWeb\iclock\Settings.txt",
    r"C:\Program Files (x86)\eSSL\eTimeTrackLite\Settings.txt",
    r"C:\Program Files\eSSL\eTimeTrackLite\Settings.txt",
    os.path.join(HERE, "Settings.txt"),
)


# ── logging ──────────────────────────────────────────────────────────────

class Log:
    """Deliberately tiny: a Scheduled Task has nowhere to show stdout, so
    everything goes to a size-rotated file as well, and this runs unattended
    for years with nobody cleaning up a log directory."""

    def __init__(self):
        self._handle = None

    def open(self):
        try:
            if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > 2_000_000:
                backup = LOG_PATH + ".1"
                if os.path.exists(backup):
                    os.remove(backup)
                os.replace(LOG_PATH, backup)
            self._handle = open(LOG_PATH, "a", encoding="utf-8")
        except OSError:
            self._handle = None  # a read-only folder must not stop the sync

    def __call__(self, message, *args):
        line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {message % args if args else message}"
        print(line)
        if self._handle is not None:
            self._handle.write(line + "\n")
            self._handle.flush()


log = Log()


def as_bool(value):
    return str(value).strip().lower() in ("1", "true", "yes", "on")


# ── configuration ────────────────────────────────────────────────────────

class Target:
    """One HRMS to push to."""

    def __init__(self, name, values):
        self.name = name
        self.url = values["url"].rstrip("/")
        self.token = values["token"]
        self.enabled = as_bool(values["enabled"])
        self.verify_tls = as_bool(values["verify_tls"])

    def __repr__(self):
        return f"<Target {self.name} {self.url}>"


class Config:
    def __init__(self, agent, targets):
        self.agent = agent
        self.targets = targets

    def __getitem__(self, key):
        return self.agent[key]

    @property
    def uses_sql_login(self):
        return self.agent["sql_auth"].strip().lower() in ("sql", "sqlserver", "sql server")


def read_essl_settings(path):
    """eTimeTrackLite's own Settings.txt, as a dict.

    The file is six bare lines, in this order, with no keys:

        MS SQL Server              database type
        WIN-5E3312PVO5J\\SQLEXPRESS  server / instance
        eTimetracklite1            database
        Sql Server Authentication  auth mode
        essl                       login name
        rKWYgQrTCGc=               password, obfuscated by eTimeTrackLite

    The password cannot be read back out of it -- it is scrambled with a key
    held inside eTimeTrackLiteLibrary.dll -- so only the first five lines are
    useful here. That is still every value that is easy to get wrong by hand:
    the instance name, the database's exact spelling, and whether eSSL is
    using Windows or SQL authentication. Run eTimeTrackDatabaseSettings.exe
    (shipped beside this file) to see or re-set the password itself.
    """
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as handle:
            lines = [line.strip() for line in handle.read().splitlines()]
    except OSError:
        return {}

    lines = [line for line in lines if line]
    if len(lines) < 3:
        return {}

    found = {
        "db_type": lines[0],
        "sql_server": lines[1],
        "sql_database": lines[2],
    }
    if len(lines) >= 4:
        found["auth_mode"] = lines[3]
        found["sql_auth"] = "sql" if "sql" in lines[3].lower() else "windows"
    if len(lines) >= 5:
        found["sql_user"] = lines[4]
    if len(lines) >= 6:
        # Kept only so the agent can recognise it if somebody pastes it into
        # sql_password, which cannot work -- see _check_sql_config. It is
        # never used as a credential and never printed.
        found["_raw_password"] = lines[5]
    return found


def _check_sql_config(agent):
    """Reject a configuration that cannot work, before anything tries to use
    it.

    Specifically the mix-up this file used to invite: a SQL Server instance
    name typed into sql_database. SQL Server's own answer to that is
    "Cannot open database "SERVER\\INSTANCE" requested by the login. The
    login failed. (4060)", followed by a login failure for good measure --
    which reads like an authentication problem and sends people off checking
    accounts and passwords instead of looking at one wrong line.
    """
    server = agent["sql_server"].strip()
    database = agent["sql_database"].strip()
    discovered = agent.get("_discovered") or {}
    suggestion = discovered.get("sql_database") or "eTimetracklite1"

    def fail(problem):
        raise SystemExit(
            f"{CONFIG_PATH}\n"
            f"\n"
            f"{problem}\n"
            f"\n"
            f"sql_database is the name of a DATABASE inside SQL Server --\n"
            f"here that is {suggestion!r}. sql_server is the machine and\n"
            f"instance it lives on, such as '.\\SQLEXPRESS' or\n"
            f"'WIN-5E3312PVO5J\\SQLEXPRESS'.\n"
            f"\n"
            f"Fix it with either:\n"
            f"    sql_database = {suggestion}\n"
            f"or leave it blank and let the agent read it from\n"
            f"eTimeTrackLite's own Settings.txt:\n"
            f"    sql_database =\n"
            f"\n"
            f"Then check it with:  py essl_punch_agent.py --show-config"
        )

    if not database:
        fail("sql_database is empty, so there is no database to open.")

    # An instance name, a UNC path or a drive letter is never a database name.
    # Quoted plainly rather than with !r: repr() doubles the backslashes,
    # and a message about a wrong backslashed value should not itself print
    # a different number of them than the file contains.
    if "\\" in database or "/" in database:
        fail(f'sql_database is set to "{database}", which is a SQL Server '
             f"instance name, not a database name.")

    if database.lower() == server.lower():
        fail(f'sql_server and sql_database are both set to "{database}". '
             f"They are different things.")

    # The password in Settings.txt is scrambled and useless as a password;
    # pasting it in produces a plain "Login failed" that looks like the
    # account is wrong rather than the value.
    password = agent["sql_password"].strip()
    if password and password == (discovered.get("_raw_password") or "").strip():
        raise SystemExit(
            f"{CONFIG_PATH}\n"
            f"\n"
            f"sql_password is the scrambled string copied out of "
            f"eTimeTrackLite's\n"
            f"Settings.txt. That value is not the password -- it is encrypted "
            f"with a\n"
            f"key held inside eTimeTrackLiteLibrary.dll and cannot be used to "
            f"log in.\n"
            f"\n"
            f"Either run eTimeTrackDatabaseSettings.exe (beside "
            f"eTimeTrackLite) to see\n"
            f"or re-set the real password for that login, or use Windows "
            f"Authentication\n"
            f"and store no password at all:\n"
            f"    sql_auth = windows\n"
            f"    sql_password ="
        )


def discover_settings_file(explicit):
    if explicit:
        return explicit if os.path.exists(explicit) else None
    for candidate in SETTINGS_GUESSES:
        if os.path.exists(candidate):
            return candidate
    return None


def load_config(require_targets=True):
    if not os.path.exists(CONFIG_PATH):
        raise SystemExit(
            f"Missing {CONFIG_PATH}.\n"
            "Copy essl_agent.ini.example to essl_agent.ini and fill it in."
        )

    parser = configparser.ConfigParser()
    # utf-8-sig, not utf-8: Notepad and PowerShell both like to save a BOM,
    # and configparser reads one as part of the first section header and then
    # claims the file has no sections at all.
    parser.read(CONFIG_PATH, encoding="utf-8-sig")

    agent = dict(AGENT_DEFAULTS)
    if parser.has_section("agent"):
        agent.update({k: v.strip() for k, v in parser.items("agent")})

    # eTimeTrackLite's own settings fill in anything left blank. Explicit ini
    # values always win -- discovery is a convenience, not an override.
    settings_path = discover_settings_file(agent["essl_settings_file"])
    agent["_settings_file_used"] = settings_path or ""
    if settings_path:
        discovered = read_essl_settings(settings_path)
        agent["_discovered"] = discovered
        for key in ("sql_server", "sql_database", "sql_user"):
            if not agent[key] and discovered.get(key):
                agent[key] = discovered[key]
        # Only adopt the discovered auth mode if the ini did not state one.
        if not parser.has_option("agent", "sql_auth") and discovered.get("sql_auth"):
            agent["sql_auth"] = discovered["sql_auth"]
    else:
        agent["_discovered"] = {}

    if not agent["sql_server"]:
        agent["sql_server"] = r".\SQLEXPRESS"
    if not agent["sql_database"]:
        agent["sql_database"] = "etimetracklite1"

    _check_sql_config(agent)

    targets = []
    for section in parser.sections():
        if not section.lower().startswith("hrms:"):
            continue
        values = dict(TARGET_DEFAULTS)
        values.update({k: v.strip() for k, v in parser.items(section)})
        name = section.split(":", 1)[1].strip() or "unnamed"
        if not values["url"]:
            raise SystemExit(f"[{section}] has no url.")
        if not values["token"]:
            raise SystemExit(f"[{section}] has no token.")
        targets.append(Target(name, values))

    # Backwards compatibility with the first version of this agent, which had
    # a single hrms_url/sync_token pair in [agent].
    if parser.has_option("agent", "hrms_url"):
        legacy = {
            "url": parser.get("agent", "hrms_url").strip(),
            "token": parser.get("agent", "sync_token", fallback="").strip(),
            "enabled": "yes",
            "verify_tls": parser.get("agent", "verify_tls", fallback="yes").strip(),
        }
        if legacy["url"] and not any(t.url == legacy["url"].rstrip("/") for t in targets):
            targets.append(Target("default", legacy))

    if require_targets and not targets:
        raise SystemExit(
            f"{CONFIG_PATH} defines no HRMS to push to.\n"
            "Add a section like:\n\n"
            "    [hrms:production]\n"
            "    url = https://hrms.zacoinfotech.com\n"
            "    token = <the BIOMETRIC_SYNC_TOKEN from hrms/.env>\n"
        )
    return Config(agent, targets)


def describe_config(config):
    lines = [
        f"Config file        : {CONFIG_PATH}",
        f"eSSL Settings.txt  : {config.agent['_settings_file_used'] or '(not found -- using ini values only)'}",
    ]
    discovered = config.agent.get("_discovered") or {}
    if discovered:
        lines.append(f"  discovered       : server={discovered.get('sql_server')!r} "
                     f"database={discovered.get('sql_database')!r} "
                     f"auth={discovered.get('auth_mode')!r} user={discovered.get('sql_user')!r}")
    lines += [
        f"SQL Server         : {config['sql_server']}",
        f"Database           : {config['sql_database']}",
        f"ODBC driver        : {config['sql_driver']}",
        f"Authentication     : " + (
            f"SQL login {config['sql_user']!r}" + ("" if config["sql_password"] else "  [NO PASSWORD SET]")
            if config.uses_sql_login else "Windows (no password stored)"
        ),
        f"Punch tables       : " + (
            "monthly DeviceLogs_<month>_<year> + dbo.DeviceLogs buffer"
            if as_bool(config["read_devicelogs_buffer"])
            else "monthly DeviceLogs_<month>_<year> only"),
        f"Overlap            : {config['overlap_minutes']} minutes",
        "Targets            :",
    ]
    for target in config.targets:
        lines.append(f"  [{'on ' if target.enabled else 'off'}] {target.name:<18} {target.url}"
                     + ("" if target.verify_tls else "   (TLS verification OFF)"))
    return "\n".join(lines)


# ── reading punches out of eTimeTrackLite ────────────────────────────────

# Only ever a SELECT. The LEFT JOIN turns the device's own UserId into the
# EmployeeCode HR recognises; it is a LEFT join on purpose, so a punch from
# somebody since deleted from eTimeTrackLite is still sent rather than lost.
# eTimeTrackLite keeps punches in TWO places, and reading only one of them
# is the difference between working and silently finding nothing:
#
#   dbo.DeviceLogs                 a buffer for punches just downloaded from
#                                  the devices. Emptied as they are archived,
#                                  so on a tidy installation it is often
#                                  completely empty.
#   dbo.DeviceLogs_<month>_<year>  one table per month, e.g.
#                                  DeviceLogs_10_2026, where the punches
#                                  actually live. Their primary key is
#                                  (UserId, LogDate) -- the punch identity --
#                                  which is what marks them as the real store
#                                  rather than a loose copy.
#
# So every read covers dbo.DeviceLogs plus the monthly tables the window
# touches. A month with no table yet is simply skipped, and a punch present
# in both places is sent twice and de-duplicated by the HRMS, which keys on
# (UserId, LogDate) exactly as these tables do.

MONTH_TABLE_RE = re.compile(r"^DeviceLogs(_\d{1,2}_\d{4})?$", re.I)

# One branch of the UNION. The column list is spelled out because the monthly
# tables are not byte-identical to dbo.DeviceLogs -- they carry an UpdateFlag
# it lacks, and Direction is a different width -- so SELECT * would not line
# up across them.
PUNCH_BRANCH_SQL = """
        SELECT  l.UserId, l.LogDate, l.DeviceId,
                COALESCE(l.Direction, l.AttDirection) AS PunchDirection,
                l.DeviceLogId
        FROM    dbo.[{table}] AS l
        WHERE   l.LogDate >= ? AND l.LogDate < ?
"""

PUNCH_SQL_TEMPLATE = """
    SELECT  p.UserId,
            e.EmployeeCode,
            e.EmployeeName,
            p.LogDate,
            p.DeviceId,
            p.PunchDirection,
            p.DeviceLogId
    FROM    ({branches}
    ) AS p
    LEFT JOIN dbo.Employees AS e ON e.EmployeeCodeInDevice = p.UserId
    ORDER BY p.LogDate, p.UserId
"""


def month_table_names(since, until):
    """DeviceLogs_<month>_<year> names covering the window, inclusive."""
    names = []
    year, month = since.year, since.month
    while (year, month) <= (until.year, until.month):
        names.append(f"DeviceLogs_{month}_{year}")
        month += 1
        if month > 12:
            month, year = 1, year + 1
    return names


def _punch_tables_present(cursor):
    """{lowercased name: actual name} for every real punch table.

    Names come from the server rather than being interpolated blindly, and
    are then re-checked against MONTH_TABLE_RE, so nothing but a genuine
    DeviceLogs table can reach the query text.
    """
    cursor.execute(
        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_SCHEMA = 'dbo' AND TABLE_TYPE = 'BASE TABLE' "
        "AND (TABLE_NAME = 'DeviceLogs' OR TABLE_NAME LIKE 'DeviceLogs[_]%')"
    )
    present = {row[0] for row in cursor.fetchall() if MONTH_TABLE_RE.match(row[0])}
    return {name.lower(): name for name in present}


def existing_punch_tables(cursor, since, until, include_buffer=False):
    """The tables to read for this window, in the order to read them.

    By default only the monthly DeviceLogs_<month>_<year> tables, which is
    where eTimeTrackLite actually keeps punches. dbo.DeviceLogs is included
    only when include_buffer is true -- see read_devicelogs_buffer in the
    ini, and buffer_row_count() for the safety net that notices if skipping
    it ever starts costing anything.
    """
    lowered = _punch_tables_present(cursor)

    tables = []
    if include_buffer and "devicelogs" in lowered:
        tables.append(lowered["devicelogs"])
    for wanted in month_table_names(since, until):
        actual = lowered.get(wanted.lower())
        if actual:
            tables.append(actual)
    return tables


def month_tables_exist(cursor):
    """True when this database has any monthly table at all. Distinguishes
    "that month simply has no punches" (fine) from "this is the wrong
    database" (not fine)."""
    return any(name != "devicelogs" for name in _punch_tables_present(cursor))


def buffer_row_count(cursor):
    """How many punches are sitting in dbo.DeviceLogs unarchived, or None if
    that table does not exist.

    Checked on every run while the buffer is being skipped. It is normally
    0, and a COUNT on an empty table costs nothing -- but if eTimeTrackLite
    ever starts leaving punches there, skipping it would quietly lose them,
    and that must not pass unnoticed.
    """
    if "devicelogs" not in _punch_tables_present(cursor):
        return None
    cursor.execute("SELECT COUNT(*) FROM dbo.DeviceLogs")
    return cursor.fetchone()[0]


def connection_string(config):
    parts = [
        f"DRIVER={{{config['sql_driver']}}}",
        f"SERVER={config['sql_server']}",
        f"DATABASE={config['sql_database']}",
        # The local instance uses a self-signed certificate; driver 18
        # encrypts by default and would otherwise refuse it.
        "TrustServerCertificate=yes",
    ]
    if config.uses_sql_login:
        parts.append(f"UID={config['sql_user']}")
        parts.append(f"PWD={config['sql_password']}")
    else:
        parts.append("Trusted_Connection=yes")
    return ";".join(parts)


def fetch_punches(config, since, until):
    try:
        import pyodbc
    except ImportError:
        # --test says this nicely, but a scheduled run must too: its log is
        # the only place anyone will see it, and a bare traceback there sends
        # people looking for a code bug rather than a missing package.
        raise RuntimeError(
            "pyodbc is not installed, so the eSSL database cannot be read. Fix with:\n"
            "    py -m pip install pyodbc\n"
            "It also needs the Microsoft ODBC Driver for SQL Server -- guide section 5.1."
        )

    log("Reading punches from %s to %s", since, until)
    punches = []
    with pyodbc.connect(connection_string(config), timeout=30) as connection:
        cursor = connection.cursor()

        include_buffer = as_bool(config["read_devicelogs_buffer"])
        tables = existing_punch_tables(cursor, since, until, include_buffer)

        if not include_buffer:
            # Skipping the buffer must never be the reason a punch is lost.
            stranded = buffer_row_count(cursor)
            if stranded:
                log("WARNING: dbo.DeviceLogs holds %d punch(es) that have not been "
                    "archived yet, and read_devicelogs_buffer = no, so they are "
                    "being skipped.", stranded)
                log("         If this keeps happening, set read_devicelogs_buffer = yes "
                    "in %s.", CONFIG_PATH)

        if not tables:
            if not month_tables_exist(cursor):
                raise RuntimeError(
                    "This database has no DeviceLogs_<month>_<year> table at all, so "
                    "there is nowhere for punches to be. Check sql_database -- "
                    "'py essl_punch_agent.py --show-config' shows what it resolved to."
                )
            # The database is right; this window just predates or postdates
            # the months that exist. Not an error.
            log("No monthly table covers %s to %s -- nothing to read.", since, until)
            return []

        log("Reading from: %s", ", ".join(tables))

        branches = "\n        UNION ALL".join(
            PUNCH_BRANCH_SQL.format(table=table) for table in tables)
        sql = PUNCH_SQL_TEMPLATE.format(branches=branches)
        params = []
        for _ in tables:
            params.extend((since, until))

        cursor.execute(sql, *params)
        for row in cursor.fetchall():
            if row.LogDate is None:
                continue
            punches.append({
                "device_user_id": str(row.UserId or "").strip(),
                "employee_code": str(row.EmployeeCode or "").strip(),
                "employee_name": str(row.EmployeeName or "").strip(),
                "punch_date": row.LogDate.date().isoformat(),
                "punch_time": row.LogDate.time().replace(microsecond=0).isoformat(),
                "device_id": row.DeviceId,
                "direction": str(row.PunchDirection or "").strip(),
                "source_log_id": row.DeviceLogId,
            })
    log("Read %d punch(es)", len(punches))
    return punches


# ── talking to an HRMS ───────────────────────────────────────────────────

def post_batch(config, target, batch):
    import requests

    response = requests.post(
        f"{target.url}/api/biometric/punches/",
        data=json.dumps({"device": config["agent_name"], "punches": batch}),
        headers={"Content-Type": "application/json", "X-HRMS-Sync-Token": target.token},
        timeout=int(config["timeout_seconds"]),
        verify=target.verify_tls,
    )
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:300]}")
    return response.json()


def target_status(config, target):
    import requests

    response = requests.get(
        f"{target.url}/api/biometric/status/",
        headers={"X-HRMS-Sync-Token": target.token},
        timeout=int(config["timeout_seconds"]),
        verify=target.verify_tls,
    )
    response.raise_for_status()
    return response.json()


# ── state ────────────────────────────────────────────────────────────────

def read_state():
    try:
        with open(STATE_PATH, encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, ValueError):
        return {"targets": {}}
    state.setdefault("targets", {})
    # The first version of this agent kept one global resume point. Treat it
    # as every target's starting point so an upgrade does not re-send months.
    legacy = state.pop("last_punch_sent", None)
    if legacy and not state["targets"]:
        state["targets"]["default"] = {"last_punch_sent": legacy}
    return state


def write_state(state):
    # Written to a temp file and moved into place, so a run killed halfway
    # cannot leave a truncated state file that resets the agent.
    temp = STATE_PATH + ".tmp"
    try:
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, sort_keys=True)
        os.replace(temp, STATE_PATH)
    except OSError as exc:
        log("WARNING: could not write the state file (%s). The next run will "
            "re-read a wider window, which is safe but slower.", exc)


# ── the run ──────────────────────────────────────────────────────────────

def target_window_start(config, target, state, args, now):
    """Where this target should resume from."""
    if args.since:
        return datetime.datetime.combine(args.since, datetime.time.min)
    if args.days:
        return now - datetime.timedelta(days=args.days)

    saved = (state["targets"].get(target.name) or {}).get("last_punch_sent")
    if saved:
        try:
            return datetime.datetime.fromisoformat(saved) - datetime.timedelta(
                minutes=int(config["overlap_minutes"]))
        except ValueError:
            log("Target %s has an unreadable resume point (%r); ignoring it.", target.name, saved)

    # No usable state: ask that HRMS how far it has got, rather than
    # re-sending months of history for nothing.
    try:
        status = target_status(config, target)
        if status.get("latest_punch_date"):
            resume = datetime.datetime.fromisoformat(status["latest_punch_date"])
            log("Target %s: no local state; resuming from its newest punch date %s",
                target.name, resume.date())
            return resume - datetime.timedelta(days=1)
    except Exception as exc:
        log("Target %s: could not ask where to resume (%s); using first_run_days.",
            target.name, exc)

    return now - datetime.timedelta(days=int(config["first_run_days"]))


def send_to_target(config, target, punches, state, batch_size):
    """Push this target's slice. Returns True when everything landed.

    A failure here is deliberately not fatal and deliberately does not move
    the target's resume point: the next run re-reads the same window and
    sends it again, so nothing is lost and no other target is affected.
    """
    if not punches:
        log("Target %s: nothing new.", target.name)
        return True

    totals = {"stored": 0, "created": 0, "updated": 0, "skipped": 0}
    entry = state["targets"].setdefault(target.name, {})
    newest = entry.get("last_punch_sent")

    for start in range(0, len(punches), batch_size):
        batch = punches[start:start + batch_size]
        for attempt in (1, 2, 3):
            try:
                result = post_batch(config, target, batch)
                break
            except Exception as exc:
                if attempt == 3:
                    log("Target %s: batch %d-%d FAILED after 3 attempts: %s",
                        target.name, start + 1, start + len(batch), exc)
                    # The scheduled run's log is the only place anyone sees
                    # this, so it gets the same explanation --test gives.
                    for line in explain_http_error(exc, target):
                        log("    %s", line)
                    entry["last_run_result"] = f"failed: {exc}"
                    entry["last_run_at"] = datetime.datetime.now().isoformat(timespec="seconds")
                    return False
                wait = attempt * 15
                log("Target %s: batch %d-%d failed (%s); retrying in %ds",
                    target.name, start + 1, start + len(batch), exc, wait)
                time.sleep(wait)

        for key, field in (("stored", "stored"), ("created", "attendance_created"),
                           ("updated", "attendance_updated"), ("skipped", "attendance_skipped")):
            totals[key] += result.get(field, 0)
        if result.get("message"):
            log("Target %s says: %s", target.name, result["message"])

        batch_newest = f"{batch[-1]['punch_date']}T{batch[-1]['punch_time']}"
        if newest is None or batch_newest > newest:
            newest = batch_newest

        log("Target %s: sent %d-%d of %d  (%d new, %d day(s) created, %d updated)",
            target.name, start + 1, start + len(batch), len(punches),
            result.get("stored", 0), result.get("attendance_created", 0),
            result.get("attendance_updated", 0))

    entry["last_punch_sent"] = newest
    entry["last_run_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    entry["last_run_result"] = "ok"
    log("Target %s: done -- %d new punch(es), %d day(s) created, %d updated, %d left alone.",
        target.name, totals["stored"], totals["created"], totals["updated"], totals["skipped"])
    return True


def run(config, args):
    state = read_state()
    now = datetime.datetime.now().replace(microsecond=0)
    until = now + datetime.timedelta(minutes=1)  # include a punch from this very minute

    chosen = [t for t in config.targets if t.enabled]
    if args.target:
        wanted = {name.lower() for name in args.target}
        chosen = [t for t in config.targets if t.name.lower() in wanted]
        missing = wanted - {t.name.lower() for t in chosen}
        if missing:
            raise SystemExit(f"No such target: {', '.join(sorted(missing))}")
    if not chosen:
        log("No enabled targets -- nothing to do. Set enabled = yes on at least one [hrms:*].")
        return 0

    windows = {t.name: target_window_start(config, t, state, args, now) for t in chosen}
    # One SQL read covers every target: the earliest resume point wins, and
    # each target is then given only the slice it has not seen.
    punches = fetch_punches(config, min(windows.values()), until)

    if args.dry_run:
        for target in chosen:
            slice_ = [p for p in punches
                      if f"{p['punch_date']}T{p['punch_time']}" >= windows[target.name].isoformat()]
            log("Dry run: target %s would receive %d punch(es) from %s",
                target.name, len(slice_), windows[target.name])
        return 0

    batch_size = max(1, int(config["batch_size"]))
    failures = []
    for target in chosen:
        cutoff = windows[target.name].isoformat()
        slice_ = [p for p in punches if f"{p['punch_date']}T{p['punch_time']}" >= cutoff]
        if not send_to_target(config, target, slice_, state, batch_size):
            failures.append(target.name)
        write_state(state)  # after each target, so one failure cannot lose another's progress

    if failures:
        log("Finished with failures: %s. They will be retried next run; no punches are lost.",
            ", ".join(failures))
        return 1
    log("All targets up to date.")
    return 0


# ── turning driver errors into something actionable ──────────────────────

def explain_sql_error(exc, config):
    """Plain-language follow-up lines for a pyodbc failure.

    SQL Server's own wording is actively misleading for the two mistakes
    people actually make. A wrong database name reports a LOGIN failure
    (error 4060 arrives wrapped in 18456), so the obvious reading -- "my
    account is wrong" -- sends you checking accounts for an hour. This
    turns each known code into the one line that fixes it.
    """
    text = str(exc)
    lines = []

    if "4060" in text or "Cannot open database" in text:
        lines.append("-> SQL Server could not open the database named in sql_database.")
        lines.append(f'   sql_database is currently "{config["sql_database"]}".')
        discovered = (config.agent.get("_discovered") or {}).get("sql_database")
        if discovered:
            lines.append(f'   eTimeTrackLite\'s own Settings.txt says it should be "{discovered}".')
        lines.append("   Note the 'Login failed' alongside this is a CONSEQUENCE of that, not")
        lines.append("   a separate problem -- the account is probably fine.")
        return lines

    if "18456" in text or "Login failed for user" in text:
        if config.uses_sql_login:
            lines.append(f"-> SQL Server rejected the login {config['sql_user']!r}.")
            lines.append("   Check sql_password. The value in eTimeTrackLite's Settings.txt is")
            lines.append("   scrambled and will not work -- run eTimeTrackDatabaseSettings.exe")
            lines.append("   to see or re-set the real one.")
        else:
            lines.append("-> SQL Server rejected the Windows account this is running as.")
            lines.append("   Run `whoami` to see which that is. Do not create a login for it:")
            lines.append("   either run as the account you use with SSMS, or switch to the")
            lines.append("   login eTimeTrackLite already uses:")
            lines.append("       sql_auth = sql")
            lines.append(f"       sql_user = {config['sql_user'] or 'essl'}")
            lines.append("       sql_password = <from eTimeTrackDatabaseSettings.exe>")
        return lines

    if "18452" in text or "not associated with a trusted" in text:
        lines.append("-> The server is in SQL-authentication-only mode, so Windows")
        lines.append("   Authentication cannot be used. Set sql_auth = sql.")
        return lines

    if "08001" in text or "server was not found" in text.lower():
        lines.append(f"-> Could not reach the instance {config['sql_server']!r}.")
        lines.append("   Try .\\SQLEXPRESS, localhost\\SQLEXPRESS, or the full computer name.")
        lines.append("   Check the service is up:  Get-Service | Where-Object Name -like 'MSSQL*'")
        return lines

    if "IM002" in text or "Data source name not found" in text:
        lines.append(f"-> The ODBC driver {config['sql_driver']!r} is not installed under that")
        lines.append("   exact name. See what is:  py -c \"import pyodbc; print(pyodbc.drivers())\"")
        return lines

    if "SSL" in text or "certificate" in text.lower():
        lines.append("-> A TLS problem with the local instance. Driver 18 encrypts by default;")
        lines.append("   the agent already sends TrustServerCertificate=yes, so if this")
        lines.append("   persists try the 17 driver instead.")
        return lines

    lines.append("-> Not a failure this agent recognises. ESSL_INTEGRATION_GUIDE.txt part 12")
    lines.append("   lists the known ones.")
    return lines


def explain_http_error(exc, target):
    """Plain-language follow-up lines for a failed call to an HRMS."""
    text = str(exc)
    status = None
    response = getattr(exc, "response", None)
    if response is not None:
        status = response.status_code
    else:
        for code in (400, 401, 403, 404, 413, 500, 502, 503):
            if f"{code} Client Error" in text or f"{code} Server Error" in text:
                status = code
                break

    if status == 400:
        return [
            "-> 400 is almost always DJANGO_ALLOWED_HOSTS, not the token.",
            f"   That server has to list the host from this url ({target.url}).",
            "   In its hrms/.env add the address, for example:",
            "       DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,192.168.1.86",
            "   then restart it (runserver, or gunicorn on a server).",
        ]
    if status == 401:
        return [
            "-> The token does not match BIOMETRIC_SYNC_TOKEN in that server's",
            "   hrms/.env. Each environment has its own; check you are not still",
            "   using the previous stage's. Restart the server after editing .env.",
        ]
    if status == 404:
        return [
            "-> That HRMS does not have the endpoint: the code is not deployed there,",
            "   or the service was not restarted after deploying.",
        ]
    if status == 413:
        return [
            "-> The batch was too large for the web server. Lower batch_size, or raise",
            "   client_max_body_size in that site's nginx config.",
        ]
    if status in (500, 502, 503):
        return [
            "-> The HRMS itself errored. Check its logs:",
            "       sudo journalctl -u hrms-prod-gunicorn -n 50 --no-pager",
        ]
    if "resolve" in text.lower() or "NameResolution" in text:
        return [
            "-> DNS could not resolve that hostname. Check the url for a typo, and that",
            "   the name exists from this machine:  Resolve-DnsName <host>",
        ]
    if "timed out" in text.lower() or "timeout" in text.lower():
        return [
            "-> Network, not the HRMS. Check it is reachable from here:",
            f"       Test-NetConnection -ComputerName <host> -Port 443",
        ]
    if "CERTIFICATE_VERIFY_FAILED" in text or "SSLError" in text:
        return [
            "-> The HTTPS certificate is self-signed or does not match the hostname.",
            "   Fix the certificate. verify_tls = no is a stopgap, not a fix, and only",
            "   acceptable for plain http on a trusted LAN.",
        ]
    return [
        "-> Not a failure this agent recognises. ESSL_INTEGRATION_GUIDE.txt part 12",
        "   lists the known ones.",
    ]


def _print_todays_punches(config, today, include_buffer):
    """Every punch recorded today, per employee, as --test's last word on
    whether the feed is actually alive.

    The row counts above prove the tables have history in them. This proves
    the devices are working NOW, which is the question somebody standing at
    the server actually has. Opened on its own connection so a failure here
    cannot spoil the checks that already passed.
    """
    import pyodbc

    print("-" * 70)
    print(f"TODAY'S PUNCHES  ({today})")
    print("-" * 70)
    try:
        with pyodbc.connect(connection_string(config), timeout=30) as connection:
            cursor = connection.cursor()
            tables = existing_punch_tables(cursor, today, today, include_buffer)
            if not tables:
                print("No table covers today, so there is nothing to show.")
                print("If eTimeTrackLite has not created this month's table yet, it will")
                print("appear with the month's first punch.")
                return

            branches = "\n        UNION ALL".join(
                PUNCH_BRANCH_SQL.format(table=table) for table in tables)
            params = []
            for _ in tables:
                params.extend((today, today + datetime.timedelta(days=1)))
            cursor.execute(PUNCH_SQL_TEMPLATE.format(branches=branches), *params)
            rows = cursor.fetchall()
    except Exception as exc:
        print(f"[warn] Could not list today's punches: {exc}")
        return

    if not rows:
        print("NO PUNCHES AT ALL TODAY.")
        print("Before office hours that is normal. During them it means the devices")
        print("are not reaching eTimeTrackLite -- check them there, not here.")
        return

    people = {}
    per_device = {}
    for row in rows:
        key = (str(row.EmployeeCode or "").strip() or f"?{row.UserId}",
               (row.EmployeeName or "").strip())
        people.setdefault(key, []).append(row.LogDate.strftime("%H:%M"))
        per_device[row.DeviceId] = per_device.get(row.DeviceId, 0) + 1

    print(f"{len(rows)} punch(es) from {len(people)} employee(s), "
          f"newest {max(r.LogDate for r in rows).strftime('%H:%M:%S')}")
    print()
    # Sorted numerically where the codes are numbers, which they are here.
    def sort_key(item):
        code = item[0][0]
        return (0, int(code)) if code.isdigit() else (1, code)

    # A chatty reader can log a dozen punches for one person, so the list
    # wraps -- in whole times per line, never mid-value, which a plain
    # character slice would do ("17:1" / "8, 17:19").
    PER_LINE = 7
    for (code, name), times in sorted(people.items(), key=sort_key):
        for offset in range(0, len(times), PER_LINE):
            chunk = ", ".join(times[offset:offset + PER_LINE])
            if offset == 0:
                print(f"  {code:<8} {name[:24]:<24} {len(times):>2}  {chunk}")
            else:
                print(f"  {'':<8} {'':<24} {'':>2}  {chunk}")

    print()
    print("  per device:  " + "   ".join(
        f"device {device}: {count}" for device, count in sorted(
            per_device.items(), key=lambda kv: (kv[0] is None, kv[0]))))
    print("  A device missing from that list recorded nothing today.")


# ── self-test ────────────────────────────────────────────────────────────

def self_test(config):
    """Check both ends before anybody schedules this. Reads a little, writes
    nothing, sends nothing."""
    print(describe_config(config))
    print()
    ok = True

    try:
        import pyodbc
    except ImportError:
        print("[FAIL] pyodbc is not installed.    py -m pip install pyodbc")
        return 1
    print("[ ok ] pyodbc importable")

    drivers = pyodbc.drivers()
    if config["sql_driver"] not in drivers:
        print(f"[FAIL] ODBC driver {config['sql_driver']!r} not installed.")
        print(f"       Installed: {drivers or '(none)'}")
        print("       Install 'Microsoft ODBC Driver 17/18 for SQL Server', then put the")
        print("       exact name above into sql_driver.")
        ok = False
    else:
        print(f"[ ok ] ODBC driver {config['sql_driver']!r} present")

    try:
        import requests  # noqa: F401
        print("[ ok ] requests importable")
    except ImportError:
        print("[FAIL] requests is not installed.  py -m pip install requests")
        return 1

    if config.uses_sql_login and not config["sql_password"]:
        print(f"[FAIL] sql_auth = sql but sql_password is empty.")
        print(f"       eTimeTrackLite connects as {config['sql_user']!r}. Either put that")
        print("       login's password in sql_password (run eTimeTrackDatabaseSettings.exe")
        print("       to see it), or set sql_auth = windows to use Windows Authentication")
        print("       and store no password at all.")
        ok = False
    elif ok:
        try:
            today = datetime.date.today()
            # A year back is enough to prove the feed is alive without
            # counting all hundred-odd archive tables.
            window_start = datetime.date(today.year - 1, today.month, 1)

            with pyodbc.connect(connection_string(config), timeout=15) as connection:
                cursor = connection.cursor()
                cursor.execute("SELECT SUSER_NAME(), DB_NAME()")
                login, database = cursor.fetchone()
                cursor.execute("SELECT COUNT(*) FROM dbo.Employees WHERE RecordStatus = 1")
                employees = cursor.fetchone()[0]

                cursor.execute(
                    "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
                    "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME LIKE 'DeviceLogs[_]%'")
                archive_count = cursor.fetchone()[0]

                include_buffer = as_bool(config["read_devicelogs_buffer"])
                stranded = None if include_buffer else buffer_row_count(cursor)

                per_table = []
                for table in existing_punch_tables(cursor, window_start, today,
                                                   include_buffer):
                    cursor.execute(
                        f"SELECT COUNT(*), MIN(LogDate), MAX(LogDate) FROM dbo.[{table}]")
                    count, oldest, newest = cursor.fetchone()
                    per_table.append((table, count, oldest, newest))

            print(f"[ ok ] Connected as {login!r} to {database!r}")
            print(f"       {employees} active employee(s) in eTimeTrackLite")
            print(f"       {archive_count} monthly table(s) exist; reading "
                  + ("the monthly tables and dbo.DeviceLogs" if include_buffer
                     else "the monthly tables only"))

            total = sum(row[1] for row in per_table)
            dated = [row for row in per_table if row[3] is not None]
            newest_overall = max((row[3] for row in dated), default=None)

            print(f"       {total} punch(es) in the last 12 months, newest {newest_overall}")
            for table, count, oldest, newest in per_table:
                if count:
                    print(f"         {table:<24} {count:>8}  {oldest} .. {newest}")

            if stranded:
                print(f"[warn] dbo.DeviceLogs holds {stranded} punch(es) not yet archived,")
                print("       and read_devicelogs_buffer = no, so they are being skipped.")
                print("       They will be picked up once eTimeTrackLite archives them. If")
                print("       this persists, set read_devicelogs_buffer = yes.")

            if not total:
                print("[warn] No punches anywhere in the last 12 months.")
                print("       The connection is fine, so this is eTimeTrackLite's data, not")
                print("       the agent. Check in eTimeTrackLite that the devices are")
                print("       downloading, and that this is the database they write to.")
            elif newest_overall is not None:
                behind = (datetime.datetime.now() - newest_overall).days
                if behind >= 2:
                    print(f"[warn] The newest punch is {behind} days old. The agent will send")
                    print("       what is there, but eTimeTrackLite may not be collecting from")
                    print("       the devices any more.")

            print()
            _print_todays_punches(config, today, include_buffer)
        except Exception as exc:
            print(f"[FAIL] Cannot read dbo.DeviceLogs")
            print(f"       {exc}")
            for line in explain_sql_error(exc, config):
                print(f"       {line}")
            ok = False

    print()
    for target in config.targets:
        label = f"{target.name} ({target.url})"
        if not target.enabled:
            print(f"[skip] {label} -- enabled = no")
            continue
        try:
            status = target_status(config, target)
            print(f"[ ok ] {label}")
            print(f"       token accepted; server date {status.get('server_date')}, "
                  f"newest punch held {status.get('latest_punch_date')}")
        except Exception as exc:
            print(f"[FAIL] {label}")
            print(f"       {exc}")
            for line in explain_http_error(exc, target):
                print(f"       {line}")
            ok = False

    print()
    print("All good -- safe to schedule." if ok else "Fix the FAIL lines above before scheduling.")
    return 0 if ok else 1


def main():
    parser = argparse.ArgumentParser(description="Push eSSL punches to one or more HRMS servers.")
    parser.add_argument("--test", action="store_true",
                        help="Check SQL Server and every enabled target, send nothing.")
    parser.add_argument("--show-config", action="store_true",
                        help="Print the resolved configuration and stop.")
    parser.add_argument("--since", type=datetime.date.fromisoformat, metavar="YYYY-MM-DD",
                        help="Read from this date instead of resuming, for a backfill.")
    parser.add_argument("--days", type=int, help="Read the last N days instead of resuming.")
    parser.add_argument("--target", action="append",
                        help="Only this target, even if disabled. Repeatable.")
    parser.add_argument("--dry-run", action="store_true", help="Read and report, POST nothing.")
    args = parser.parse_args()

    if args.since and args.days:
        raise SystemExit("Give either --since or --days, not both.")

    config = load_config(require_targets=not args.show_config)
    if args.show_config:
        print(describe_config(config))
        return 0
    if args.test:
        return self_test(config)

    log.open()
    try:
        return run(config, args)
    except SystemExit:
        raise
    except Exception as exc:
        log("Agent run FAILED: %s", exc)
        import traceback
        log(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())
