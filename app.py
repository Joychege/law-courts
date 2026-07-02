"""
Githunguri Law Courts — Visitor Attendance Register
-----------------------------------------------------
A small Flask application backed by a SQLite database.

Run locally:
    pip install -r requirements.txt
    python app.py

Then open:
    http://127.0.0.1:5000            -> visitor entry form
    http://127.0.0.1:5000/admin      -> admin login (see ADMIN_PASSWORD below)
"""

import csv
import io
import os
import shutil
import sqlite3
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, request, render_template, redirect,
    url_for, session, send_file, flash
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# ---------------------------------------------------------------------------
# CONFIGURATION — change these before real use
# ---------------------------------------------------------------------------
# Secret key used to sign session cookies. Use a long random string in
# production, e.g. generate one with: python -c "import secrets; print(secrets.token_hex(32))"
app.secret_key = "change-this-secret-key-before-deploying"

# The plain-text password below is only used once, at startup, to build a
# hash. Change the string, restart the app, and staff will log in with the
# new password. The plain text is never stored anywhere.
ADMIN_PASSWORD_HASH = generate_password_hash("Githunguri@2026")

# Admin is automatically logged out after this many minutes of inactivity.
app.permanent_session_lifetime = timedelta(minutes=20)

DB_PATH = "attendance.db"
BACKUP_DIR = "backups"
RECORDS_PER_PAGE = 25

# Login lockout settings — protects the admin password against guessing.
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 5
_login_state = {"attempts": 0, "locked_until": None}


# ---------------------------------------------------------------------------
# DATABASE HELPERS
# ---------------------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS visitors (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            phone       TEXT NOT NULL DEFAULT '',
            host        TEXT NOT NULL DEFAULT '',
            visit_date  TEXT NOT NULL,
            visit_time  TEXT NOT NULL,
            time_out    TEXT,
            purpose     TEXT NOT NULL,
            signature   TEXT NOT NULL,   -- base64 PNG data URL from the signature pad
            created_at  TEXT NOT NULL
        )
    """)
    # Migration safety net: if attendance.db was created by an earlier
    # version of this app, add any columns it's missing.
    existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(visitors)").fetchall()}
    for col, ddl in [
        ("phone", "ALTER TABLE visitors ADD COLUMN phone TEXT NOT NULL DEFAULT ''"),
        ("host", "ALTER TABLE visitors ADD COLUMN host TEXT NOT NULL DEFAULT ''"),
        ("time_out", "ALTER TABLE visitors ADD COLUMN time_out TEXT"),
    ]:
        if col not in existing_cols:
            conn.execute(ddl)
    conn.commit()
    conn.close()


def backup_db():
    """Create a timestamped copy of the database in backups/. Returns the path, or None if there's nothing to back up yet."""
    if not os.path.exists(DB_PATH):
        return None
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    dest = os.path.join(BACKUP_DIR, f"attendance-{timestamp}.db")
    shutil.copy2(DB_PATH, dest)
    return dest


def maybe_auto_backup():
    """Create at most one automatic backup per calendar day, the first time an admin visits that day."""
    if not os.path.exists(DB_PATH):
        return
    os.makedirs(BACKUP_DIR, exist_ok=True)
    today_prefix = f"attendance-{datetime.now().strftime('%Y-%m-%d')}"
    already_today = any(f.startswith(today_prefix) for f in os.listdir(BACKUP_DIR))
    if not already_today:
        backup_db()


def list_backups():
    if not os.path.isdir(BACKUP_DIR):
        return []
    return sorted(os.listdir(BACKUP_DIR), reverse=True)


# ---------------------------------------------------------------------------
# LOGIN LOCKOUT HELPERS
# ---------------------------------------------------------------------------
def is_locked_out():
    locked_until = _login_state["locked_until"]
    return locked_until is not None and datetime.now() < locked_until


def lockout_message():
    remaining = int((_login_state["locked_until"] - datetime.now()).total_seconds() // 60) + 1
    return f"Too many failed attempts. Try again in about {remaining} minute(s)."


def register_failed_login():
    _login_state["attempts"] += 1
    if _login_state["attempts"] >= MAX_LOGIN_ATTEMPTS:
        _login_state["locked_until"] = datetime.now() + timedelta(minutes=LOCKOUT_MINUTES)
        return f"Too many failed attempts. The admin login is locked for {LOCKOUT_MINUTES} minutes."
    remaining_attempts = MAX_LOGIN_ATTEMPTS - _login_state["attempts"]
    return f"Incorrect password. {remaining_attempts} attempt(s) remaining before lockout."


def register_successful_login():
    _login_state["attempts"] = 0
    _login_state["locked_until"] = None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped


# ---------------------------------------------------------------------------
# PUBLIC ROUTES — visitor entry
# ---------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    now = datetime.now()
    return render_template(
        "index.html",
        active="entry",
        today=now.strftime("%Y-%m-%d"),
        now=now.strftime("%H:%M"),
    )


@app.route("/submit", methods=["POST"])
def submit():
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    host = request.form.get("host", "").strip()
    visit_date = request.form.get("date", "").strip()
    visit_time = request.form.get("time", "").strip()
    purpose = request.form.get("purpose", "").strip()
    other = request.form.get("other", "").strip()
    signature = request.form.get("signature", "").strip()

    if purpose == "Other" and other:
        purpose = other

    now = datetime.now()

    if not (name and phone and host and visit_date and visit_time and purpose and signature):
        flash("Please complete every field and sign before submitting.", "error")
        return render_template(
            "index.html", active="entry",
            today=now.strftime("%Y-%m-%d"), now=now.strftime("%H:%M")
        )

    conn = get_db()
    cur = conn.execute(
        """INSERT INTO visitors (name, phone, host, visit_date, visit_time, purpose, signature, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, phone, host, visit_date, visit_time, purpose, signature, now.isoformat()),
    )
    conn.commit()
    entry_id = cur.lastrowid
    conn.close()

    return render_template(
        "index.html",
        active="entry",
        today=now.strftime("%Y-%m-%d"),
        now=now.strftime("%H:%M"),
        confirmed=True,
        entry_id=entry_id,
        name=name,
        visit_date=visit_date,
        visit_time=visit_time,
    )


# ---------------------------------------------------------------------------
# ADMIN ROUTES — password protected
# ---------------------------------------------------------------------------
@app.route("/admin", methods=["GET"])
def admin_login():
    if session.get("is_admin"):
        return redirect(url_for("admin_records"))
    error = lockout_message() if is_locked_out() else None
    return render_template("admin_login.html", active="admin", error=error)


@app.route("/admin/login", methods=["POST"])
def admin_login_post():
    if is_locked_out():
        return render_template("admin_login.html", active="admin", error=lockout_message())

    password = request.form.get("password", "")
    if check_password_hash(ADMIN_PASSWORD_HASH, password):
        register_successful_login()
        session.permanent = True
        session["is_admin"] = True
        return redirect(url_for("admin_records"))

    error = register_failed_login()
    return render_template("admin_login.html", active="admin", error=error)


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("admin_login"))


@app.route("/admin/records", methods=["GET"])
@login_required
def admin_records():
    maybe_auto_backup()

    search = request.args.get("q", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    try:
        page = max(int(request.args.get("page", 1)), 1)
    except ValueError:
        page = 1

    where_clauses = []
    params = []
    if search:
        like = f"%{search}%"
        where_clauses.append("(name LIKE ? OR purpose LIKE ? OR host LIKE ?)")
        params += [like, like, like]
    if date_from:
        where_clauses.append("visit_date >= ?")
        params.append(date_from)
    if date_to:
        where_clauses.append("visit_date <= ?")
        params.append(date_to)
    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    conn = get_db()
    total_filtered = conn.execute(f"SELECT COUNT(*) FROM visitors {where_sql}", params).fetchone()[0]
    total_pages = max((total_filtered + RECORDS_PER_PAGE - 1) // RECORDS_PER_PAGE, 1)
    page = min(page, total_pages)
    offset = (page - 1) * RECORDS_PER_PAGE

    rows = conn.execute(
        f"SELECT * FROM visitors {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?",
        params + [RECORDS_PER_PAGE, offset]
    ).fetchall()
    total = conn.execute("SELECT COUNT(*) FROM visitors").fetchone()[0]
    conn.close()

    return render_template(
        "admin_records.html", active="admin", subactive="records",
        rows=rows, total=total, total_filtered=total_filtered,
        search=search, date_from=date_from, date_to=date_to,
        page=page, total_pages=total_pages,
    )


@app.route("/admin/checkout/<int:entry_id>", methods=["POST"])
@login_required
def admin_checkout(entry_id):
    conn = get_db()
    conn.execute(
        "UPDATE visitors SET time_out = ? WHERE id = ?",
        (datetime.now().strftime("%H:%M"), entry_id)
    )
    conn.commit()
    conn.close()
    flash("Visitor checked out.", "success")
    return redirect(request.referrer or url_for("admin_records"))


@app.route("/admin/delete/<int:entry_id>", methods=["POST"])
@login_required
def admin_delete(entry_id):
    conn = get_db()
    conn.execute("DELETE FROM visitors WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()
    flash("Entry deleted.", "success")
    return redirect(request.referrer or url_for("admin_records"))


@app.route("/admin/export", methods=["GET"])
@login_required
def admin_export():
    conn = get_db()
    rows = conn.execute(
        "SELECT id, name, phone, host, visit_date, visit_time, time_out, purpose, created_at "
        "FROM visitors ORDER BY id DESC"
    ).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Entry No.", "Name", "Phone / ID", "Visiting", "Date", "Time In", "Time Out", "Purpose", "Recorded At"])
    for r in rows:
        writer.writerow([
            r["id"], r["name"], r["phone"], r["host"], r["visit_date"],
            r["visit_time"], r["time_out"] or "", r["purpose"], r["created_at"]
        ])

    mem = io.BytesIO(output.getvalue().encode("utf-8"))
    filename = f"githunguri-courts-register-{datetime.now().strftime('%Y-%m-%d')}.csv"
    return send_file(mem, mimetype="text/csv", as_attachment=True, download_name=filename)


@app.route("/admin/backup", methods=["POST"])
@login_required
def admin_backup_now():
    path = backup_db()
    if path:
        flash(f"Backup created: {os.path.basename(path)}", "success")
    else:
        flash("Nothing to back up yet — no records exist.", "error")
    return redirect(request.referrer or url_for("admin_stats"))


@app.route("/admin/stats", methods=["GET"])
@login_required
def admin_stats():
    maybe_auto_backup()

    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM visitors").fetchone()[0]

    today_str = datetime.now().strftime("%Y-%m-%d")
    today_count = conn.execute(
        "SELECT COUNT(*) FROM visitors WHERE visit_date = ?", (today_str,)
    ).fetchone()[0]

    week_start = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")
    week_count = conn.execute(
        "SELECT COUNT(*) FROM visitors WHERE visit_date >= ?", (week_start,)
    ).fetchone()[0]

    month_start = datetime.now().strftime("%Y-%m-01")
    month_count = conn.execute(
        "SELECT COUNT(*) FROM visitors WHERE visit_date >= ?", (month_start,)
    ).fetchone()[0]

    currently_in = conn.execute(
        "SELECT COUNT(*) FROM visitors WHERE time_out IS NULL OR time_out = ''"
    ).fetchone()[0]

    by_purpose = conn.execute(
        "SELECT purpose, COUNT(*) AS c FROM visitors GROUP BY purpose ORDER BY c DESC"
    ).fetchall()
    conn.close()

    max_count = max((r["c"] for r in by_purpose), default=0)
    backups = list_backups()

    return render_template(
        "admin_stats.html", active="admin", subactive="stats",
        total=total, today_count=today_count, week_count=week_count,
        month_count=month_count, currently_in=currently_in,
        by_purpose=by_purpose, max_count=max_count,
        last_backup=(backups[0] if backups else None),
        backup_count=len(backups),
    )


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
