# Githunguri Law Courts — Visitor Attendance Register

A visitor attendance register with a Python (Flask) backend and a SQLite
database, so every entry is safely stored on disk in a real database file
rather than in the browser.

## What's inside

```
githunguri_register/
├── app.py                     # Flask app + database logic
├── requirements.txt
├── attendance.db               # created automatically on first run
├── backups/                    # daily database backups, created automatically
├── templates/
│   ├── base.html               # shared header, nav, footer — used by every page
│   ├── index.html              # visitor entry form
│   ├── admin_login.html        # admin password screen
│   ├── admin_records.html      # admin records table, search, filters
│   ├── admin_stats.html        # admin visit statistics
│   └── _admin_subnav.html      # shared Records / Statistics tabs
└── static/
    └── style.css                # one stylesheet shared by every page
```

## Setup

1. Make sure Python 3.9+ is installed.
2. Open a terminal in this folder and install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Run the app:

   ```bash
   python app.py
   ```

4. Open your browser to:

   - **Visitor entry:** http://127.0.0.1:5000
   - **Admin login:** http://127.0.0.1:5000/admin

The first time you run it, `attendance.db` is created automatically in the
same folder — that's where every visitor record is stored.

## What visitors fill in

- Full name
- Phone number / National ID
- Person or office they're visiting
- Date and time in
- Purpose of visit
- Signature (drawn on screen)

**Time out is recorded separately, by staff.** A visitor can't know their own
departure time when they sign in, so instead each row in the admin records
table has a **Check Out** button — click it when the visitor leaves, and it
stamps the current time. Until then, the row shows an **In** status.

## Admin password

The default password is:

```
Githunguri@2026
```

**To change it:** open `app.py`, find this line near the top:

```python
ADMIN_PASSWORD_HASH = generate_password_hash("Githunguri@2026")
```

replace `"Githunguri@2026"` with your new password, save the file, and
restart the app. The password is stored as a one-way hash in memory — the
plain text itself is never saved anywhere.

## What the admin can do

Once logged in at `/admin`, staff can:

- **Records tab** — view every visit, search by name/purpose/host, filter by
  date range, page through results 25 at a time, check visitors out, delete
  a mistaken entry, and export everything to CSV
- **Statistics tab** — see totals for today / this week / this month /
  all time, how many visitors are currently on site, and a breakdown of
  visits by purpose
- **Backups** — a backup of `attendance.db` is created automatically once
  per day the first time an admin opens the records or statistics page; a
  **Backup Now** button is also available any time on the Statistics page

## Security features

- **Login lockout** — after 5 incorrect password attempts, the admin login
  locks for 5 minutes, even if the correct password is entered during that
  window
- **Session timeout** — admins are automatically logged out after 20 minutes
  of inactivity (change this via `app.permanent_session_lifetime` in
  `app.py`)

## Backing up or moving the records

Everything lives in `attendance.db`, a standard SQLite file, plus dated
copies in `backups/`. To restore from a backup, stop the app, replace
`attendance.db` with the backup file you want, and restart. To inspect the
database directly:

```bash
sqlite3 attendance.db "SELECT * FROM visitors;"
```

## Before using this for real visitors

- **Change the admin password** (see above) and keep `app.py` private.
- **Change `app.secret_key`** in `app.py` to a random string, e.g.:

  ```bash
  python -c "import secrets; print(secrets.token_hex(32))"
  ```

- **Run it on a proper server** for anything beyond a single office machine —
  the built-in `python app.py` server is fine for one computer, but for a
  shared network, run it behind a production server such as `gunicorn` or
  `waitress`, ideally with HTTPS.
- **Copy `backups/` off the machine periodically** (a USB drive, network
  share, or cloud folder) — automatic backups protect against a corrupted
  database, but not against the whole computer being lost or damaged.
