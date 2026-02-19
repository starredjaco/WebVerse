import os, time, base64, sqlite3, hashlib
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify, render_template, redirect, make_response
import jwt, random

app = Flask(__name__)

ALLOWED_ORIGINS = {
    "http://portal.orbitdesk.local",
    "https://portal.orbitdesk.local",
    "http://orbitdesk.local",
    "https://orbitdesk.local",
}

def _corsify(resp):
    origin = request.headers.get("Origin")
    if origin in ALLOWED_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
        resp.headers["Access-Control-Allow-Credentials"] = "true"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        resp.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    return resp

@app.after_request
def after(resp):
    return _corsify(resp)

@app.before_request
def handle_preflight():
    # Handle CORS preflight for ALL routes so browser fetch() from portal doesn't fail.
    if request.method == "OPTIONS":
        return _corsify(make_response("", 204))

LAB_DOMAIN = os.getenv("LAB_DOMAIN", "orbitdesk.local")
DB_PATH = os.getenv("DB_PATH", "/data/orbitdesk.db")
AUTH_SECRET = os.getenv("AUTH_SECRET", "0rB1tD35kSecretAuthSign1ngK3y!")

# Public team directory for marketing site (intentionally leaks employee IDs for the lab chain).
# IMPORTANT: Only employees are exposed here (not admin/ops).
TEAM_PROFILES_BY_EMAIL = {
    "ella.reed@orbitdesk.local": {
        "title": "Customer Success",
        "short_bio": "Onboards new customers, fixes rough edges, and makes sure teams actually adopt the portal.",
        "description": "Ella helps teams roll out OrbitDesk without the usual friction — faster onboarding, fewer tickets, and smoother handoffs.",
        "what_they_do": "Runs onboarding calls, builds rollout plans, and translates customer feedback into clear action items for product and engineering.",
        "personal": "Outside of work, Ella is a trail runner and amateur photographer who loves finding quiet coffee shops in every new city.",
        "why_they_love_it": "OrbitDesk moves fast without breaking trust — she loves shipping small improvements that customers feel immediately.",
        "how_they_found_us": "Found OrbitDesk through a former teammate who swore by the product during a high-pressure client migration.",
        "photo_url": "/static/team/ella.jpg",
    },
    "michael.chan@orbitdesk.local": {
        "title": "Solutions Engineer",
        "short_bio": "Helps customers integrate OrbitDesk with their existing workflows and gets tricky edge-cases unstuck.",
        "description": "Michael bridges product and engineering — he can speak API, dashboards, and rollout strategy in the same sentence.",
        "what_they_do": "Builds proof-of-concepts, validates integrations, and helps customers model their document workflows cleanly.",
        "personal": "Michael is into mechanical keyboards and chess puzzles, and he’s always tinkering with home lab automation.",
        "why_they_love_it": "He likes solving real problems with real constraints — and the team treats reliability like a feature.",
        "how_they_found_us": "He met the founders while helping a client clean up a messy portal migration and stayed for the mission.",
        "photo_url": "/static/team/michael.jpg",
    },
}

# Only this seeded employee is allowed to be reset (in addition to user-created accounts)
ALLOW_RESET_SEEDED_EMAIL = "ella.reed@orbitdesk.local"

# Simple in-memory rate limit (per email) for reset requests
_rl = {}

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    c = db()
    cur = c.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        created_at TEXT NOT NULL
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS mail_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        to_email TEXT NOT NULL,
        subject TEXT NOT NULL,
        body TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")

    # Track the most recently generated reset token per user.
    # Only the latest token is valid; generating a new one invalidates the previous.
    cur.execute("""CREATE TABLE IF NOT EXISTS password_reset_tokens(
        user_id INTEGER PRIMARY KEY,
        token TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")

    # Shared tables used across services (created here to avoid order dependence)
    cur.execute("""CREATE TABLE IF NOT EXISTS projects(
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        owner_id INTEGER NOT NULL,
        created_at TEXT NOT NULL
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS project_members(
        project_id TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        member_role TEXT NOT NULL DEFAULT 'member',
        PRIMARY KEY(project_id,user_id)
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS project_secrets(
        project_id TEXT PRIMARY KEY,
        documents_api_key TEXT NOT NULL
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS documents(
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        filename TEXT NOT NULL,
        file_id TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS contacts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    c.commit()
    c.close()

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def seed_if_empty():
    c = db()
    cur = c.cursor()
    # Always ensure seeded identities exist (DB may persist across runs).
    users = [
        ("it.admin@orbitdesk.local", "IT Admin", sha256("OrbitDesk!2026"), "admin"),
        ("ella.reed@orbitdesk.local", "Ella Reed", sha256("Welcome2026!"), "employee"),
        ("michael.chan@orbitdesk.local", "Michael Chan", sha256("Welcome2026!"), "employee"),
    ]
    for email, name, ph, role in users:
        cur.execute(
            "INSERT OR IGNORE INTO users(email,name,password_hash,role,created_at) VALUES(?,?,?,?,?)",
            (email, name, ph, role, now_iso()),
        )
    c.commit()

    # Seed baseline projects and docs (idempotent)
    row = cur.execute("SELECT id FROM users WHERE email='it.admin@orbitdesk.local'").fetchone()
    if not row:
        c.close()
        return
    admin_id = row["id"]
    ella_id = cur.execute("SELECT id FROM users WHERE email='ella.reed@orbitdesk.local'").fetchone()["id"]

    def new_docs_key():
        return "dok_live_" + hashlib.sha256(os.urandom(16)).hexdigest()[:20]

    projects = [
        ("PRJ-1001", "Executive Briefings", admin_id),
        ("PRJ-1002", "Client Onboarding Templates", admin_id),
    ]
    for pid, name, owner in projects:
        cur.execute("INSERT OR IGNORE INTO projects(id,name,owner_id,created_at) VALUES(?,?,?,?)", (pid, name, owner, now_iso()))
        cur.execute("INSERT OR IGNORE INTO project_members(project_id,user_id,member_role) VALUES(?,?,?)", (pid, owner, "owner"))
        cur.execute("INSERT OR IGNORE INTO project_secrets(project_id,documents_api_key) VALUES(?,?)", (pid, new_docs_key()))

    # Give Ella access to the employee-facing workspace so the portal has a project to load.
    cur.execute(
        "INSERT OR IGNORE INTO project_members(project_id,user_id,member_role) VALUES(?,?,?)", ("PRJ-1002", ella_id, "member")
    )

    # A doc in PRJ-1001 (used later in the chain)
    cur.execute(
        "INSERT OR IGNORE INTO documents(id,project_id,filename,file_id,created_at) VALUES(?,?,?,?,?)",
        ("DOC-9001", "PRJ-1001", "Q4-reconciliation.pdf", "projects/PRJ-1001/finance/Q4-reconciliation.pdf", now_iso()),
    )
    # A normal doc in PRJ-1002 (so Ella sees something on /app/documents)
    cur.execute("INSERT OR IGNORE INTO documents(id,project_id,filename,file_id,created_at) VALUES(?,?,?,?,?)", ("DOC-9002","PRJ-1002","onboarding-checklist.pdf","projects/PRJ-1002/templates/onboarding-checklist.pdf", now_iso()))
    c.commit()
    c.close()

def reset_blocked_role(role: str) -> bool:
    r = (role or "").strip().lower()
    return r in ("admin", "ops")

def can_issue_reset_for_user(user_row) -> bool:
    """
    Reset policy for this lab:
      - Block ANY admin/ops accounts.
      - Allow ONLY:
          * user-created accounts (role == 'user')
          * the seeded employee ella.reed@orbitdesk.local
    Enforced both at reset request-time and confirm-time.
    """
    if not user_row:
        return False
    role = (user_row["role"] or "").strip().lower()
    email = (user_row["email"] or "").strip().lower()
    if reset_blocked_role(role):
        return False
    return (role == "user") or (email == ALLOW_RESET_SEEDED_EMAIL)

def issue_token(user_row):
    payload = {
        "sub": str(user_row["id"]),
        "email": user_row["email"],
        "name": user_row["name"],
        "role": user_row["role"],
        "scopes": "portal:read projects:read" + (" ops:admin ops:write" if user_row["role"] == "admin" else ""),
        "iat": int(time.time()),
        "iss": "orbitdesk-auth"
    }
    return jwt.encode(payload, AUTH_SECRET, algorithm="HS256")

def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")

def b64url_decode(s: str) -> bytes:
    pad = "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode((s + pad).encode())

def store_latest_reset_token(user_id: int, token: str):
    c = db()
    c.execute(
        "INSERT OR REPLACE INTO password_reset_tokens(user_id, token, created_at) VALUES(?,?,?)",
        (user_id, token, now_iso()),
    )
    c.commit()
    c.close()

def latest_reset_token_for_user(user_id: int):
    c = db()
    row = c.execute(
        "SELECT token FROM password_reset_tokens WHERE user_id=?",
        (user_id,),
    ).fetchone()
    c.close()
    return row["token"] if row else None

def consume_reset_token(user_id: int):
    c = db()
    c.execute("DELETE FROM password_reset_tokens WHERE user_id=?", (user_id,))
    c.commit()
    c.close()

def make_reset_token(user_id: int) -> str:
    # Intentionally weak "token":
    #   base64url( "{uid}:{base64(date)}:{rand_1_to_50}" )
    # Designed to be reversible/guessable for an educational lab.
    date_str = datetime.now(timezone.utc).strftime("%m/%d/%Y")
    date_b64 = base64.b64encode(date_str.encode()).decode()
    r = random.randint(1, 50)
    token_raw = f"{user_id}:{date_b64}:{r}".encode()
    return b64url_encode(token_raw)

def parse_reset_token(token: str):
    raw = b64url_decode(token).decode(errors="ignore")
    parts = raw.split(":")
    if len(parts) != 3:
        return None
    try:
        uid = int(parts[0])
    except Exception:
        return None

    # Third field must be an integer 1..50 (adds "noise" but still forgeable)
    try:
        r = int(parts[2])
    except Exception:
        return None
    if r < 1 or r > 50:
        return None

    # Decode embedded date and require it to be "today" (UTC) with a small drift window.
    try:
        embedded_date = base64.b64decode(parts[1].encode()).decode(errors="ignore")
    except Exception:
        return None

    today = datetime.now(timezone.utc).strftime("%m/%d/%Y")
    # Small drift window to avoid timezone edge-cases during local play.
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%m/%d/%Y")
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%m/%d/%Y")

    if embedded_date not in (yesterday, today, tomorrow):
        return None
    return uid

def _get_bearer_token():
    h = request.headers.get("Authorization", "")
    if not h:
        return None
    if not h.lower().startswith("bearer "):
        return None
    return h.split(" ", 1)[1].strip() or None

def require_user():
    """
    Delivery logs are available to all authenticated users,
    but users may only access logs for THEIR OWN email.
    """
    token = _get_bearer_token()
    if not token:
        return None, (jsonify({"error": "Unauthorized"}), 401)
    try:
        payload = jwt.decode(token, AUTH_SECRET, algorithms=["HS256"])
    except Exception:
        return None, (jsonify({"error": "Unauthorized"}), 401)

    email = (payload.get("email") or "").strip().lower()
    if not email:
        # If your JWT doesn't include email, swap to lookup by sub/user_id here.
        return None, (jsonify({"error": "Unauthorized"}), 401)
    return payload, None

def log_mail(to_email: str, subject: str, body: str):
    c = db()
    c.execute("INSERT INTO mail_log(to_email,subject,body,created_at) VALUES(?,?,?,?)", (to_email,subject,body,now_iso()))
    c.commit()
    c.close()

def rate_limited(email: str) -> bool:
    # 2 reset emails per 60 seconds per recipient
    now = int(time.time())
    window = 60
    bucket = _rl.get(email, [])
    bucket = [t for t in bucket if (now - t) < window]
    if len(bucket) >= 2:
        _rl[email] = bucket
        return True
    bucket.append(now)
    _rl[email] = bucket
    return False

# --- Public: Marketing (intentionally exposes employee IDs for the lab chain) ---

@app.get("/api/v1/public/team")
def public_team_list():
    c = db()
    rows = c.execute(
        "SELECT id,email,name,role FROM users WHERE role='employee' ORDER BY id"
    ).fetchall()
    c.close()

    items = []
    for r in rows:
        email = (r["email"] or "").strip().lower()
        profile = TEAM_PROFILES_BY_EMAIL.get(email)
        if not profile:
            continue
        items.append({
            "id": r["id"],
            "name": r["name"],
            "title": profile["title"],
            "short_bio": profile["short_bio"],
            "photo_url": profile["photo_url"],
        })
    return jsonify({"items": items})

@app.get("/api/v1/public/team/<int:user_id>")
def public_team_member(user_id: int):
    c = db()
    r = c.execute(
        "SELECT id,email,name,role FROM users WHERE id=?",
        (user_id,),
    ).fetchone()
    c.close()
    if not r:
        return jsonify({"error": "Not found"}), 404
    if (r["role"] or "").strip().lower() != "employee":
        return jsonify({"error": "Not found"}), 404
    email = (r["email"] or "").strip().lower()
    profile = TEAM_PROFILES_BY_EMAIL.get(email)
    if not profile:
        return jsonify({"error": "Not found"}), 404
    return jsonify({
        "id": r["id"],
        "name": r["name"],
        "title": profile["title"],
        "description": profile["description"],
        "what_they_do": profile["what_they_do"],
        "personal": profile["personal"],
        "why_they_love_it": profile["why_they_love_it"],
        "how_they_found_us": profile["how_they_found_us"],
        "photo_url": profile["photo_url"],
    })

@app.before_request
def _boot():
    init_db()
    seed_if_empty()

@app.get("/")
def home():
    return render_template("index.html", lab_domain=LAB_DOMAIN, title="OrbitDesk Identity")

@app.get("/reset")
def reset_get():
    return render_template("reset.html", lab_domain=LAB_DOMAIN, notice=None, notice_kind="")

@app.post("/reset")
def reset_post():
    email = (request.form.get("email") or "").strip().lower()
    if not email:
        return render_template("reset.html", lab_domain=LAB_DOMAIN, notice="Enter an email address.", notice_kind="bad")
    if rate_limited(email):
        return render_template("reset.html", lab_domain=LAB_DOMAIN, notice="Too many requests. Try again in a minute.", notice_kind="bad")
    c = db()
    row = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    c.close()
    # Always return success (avoid account enumeration), but only log mail if user exists.
    if row:
        # Do NOT issue reset tokens for privileged accounts (admin/ops).
        if not reset_blocked_role(row["role"]) and can_issue_reset_for_user(row):
            uid = int(row["id"])
            token = make_reset_token(uid)
            store_latest_reset_token(uid, token)
            link = f"http://auth.{LAB_DOMAIN}/reset/confirm?token={token}"
            body = f"Reset your OrbitDesk password\n\nIf you requested a reset, click:\n{link}\n\nIf you didn't request this, you can ignore this message."
            log_mail(email, "OrbitDesk password reset", body)
    return render_template("reset.html", lab_domain=LAB_DOMAIN, notice="If the account exists, a reset email has been sent.", notice_kind="ok")

@app.get("/reset/confirm")
def confirm_get():
    token = request.args.get("token","")
    if not token:
        return jsonify({"error": "invalid token"}), 500
    uid = parse_reset_token(token)
    if not uid:
        return jsonify({"error": "invalid token"}), 500

    # Enforce privileged-account block again at confirmation time (prevents forged tokens).
    c = db()
    row = c.execute("SELECT email, role FROM users WHERE id=?", (uid,)).fetchone()
    c.close()
    if (not row) or reset_blocked_role(row["role"]) or (not can_issue_reset_for_user(row)):
        return jsonify({"error": "invalid token"}), 500

    # Only accept the most recently generated token for this user.
    latest = latest_reset_token_for_user(uid)
    if (not latest) or (latest != token):
        return jsonify({"error": "invalid token"}), 500
    return render_template("confirm.html", lab_domain=LAB_DOMAIN, token=token, error=None, ok=None)

@app.post("/reset/confirm")
def confirm_post():
    token = request.form.get("token","")
    pw = request.form.get("password","")
    uid = parse_reset_token(token)
    if not uid:
        return jsonify({"error": "invalid token"}), 500
    if len(pw) < 8:
        return render_template("confirm.html", lab_domain=LAB_DOMAIN, token=token, error="Password must be at least 8 characters.", ok=None)

    # Enforce privileged-account block again at confirmation time (prevents forged tokens).
    c = db()
    row = c.execute("SELECT email, role FROM users WHERE id=?", (uid,)).fetchone()
    if (not row) or reset_blocked_role(row["role"]) or (not can_issue_reset_for_user(row)):
        c.close()
        return jsonify({"error": "invalid token"}), 500

    # Only accept the most recently generated token for this user.
    latest = latest_reset_token_for_user(uid)
    if (not latest) or (latest != token):
        c.close()
        return jsonify({"error": "invalid token"}), 500

    c.execute("UPDATE users SET password_hash=? WHERE id=?", (sha256(pw), uid))
    c.commit()
    c.close()
    # One-time use: consume token after successful reset.
    consume_reset_token(uid)
    return render_template("confirm.html", lab_domain=LAB_DOMAIN, token=token, error=None, ok="Password updated. You can sign in now.")

@app.get("/delivery/logs")
def delivery_logs():
    user, err = require_user()
    if err:
        return err

    # Enforce per-user visibility: only show messages delivered to this user's email.
    my_email = (user.get("email") or "").strip().lower()

    c = db()
    items = c.execute(
        "SELECT * FROM mail_log WHERE lower(to_email)=? ORDER BY id DESC LIMIT 25",
        (my_email,)
    ).fetchall()
    c.close()
    items = [dict(x) for x in items]
    return render_template("logs.html", lab_domain=LAB_DOMAIN, items=items, title="Delivery logs • OrbitDesk Identity")

# JSON API for the portal
@app.post("/api/v1/auth/register")
def api_register():
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    name = (data.get("name") or "").strip() or "User"
    pw = data.get("password") or ""
    if not email or "@" not in email:
        return jsonify({"error":"Enter a valid email."}), 400
    if len(pw) < 8:
        return jsonify({"error":"Password must be at least 8 characters."}), 400
    c = db()
    try:
        c.execute("INSERT INTO users(email,name,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                  (email,name,sha256(pw),"user",now_iso()))
        c.commit()
    except sqlite3.IntegrityError:
        c.close()
        return jsonify({"error":"Email is already in use."}), 409
    # auto-create a personal project (realistic for SaaS onboarding)
    uid = c.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()["id"]
    # next project ID
    row = c.execute("SELECT id FROM projects ORDER BY id DESC LIMIT 1").fetchone()
    next_num = 1003
    if row and row["id"].startswith("PRJ-"):
        try:
            next_num = int(row["id"].split("-")[1]) + 1
        except Exception:
            next_num = 1003
    pid = f"PRJ-{next_num}"
    c.execute("INSERT OR IGNORE INTO projects(id,name,owner_id,created_at) VALUES(?,?,?,?)",
              (pid,f"{name.split(' ')[0]}'s Workspace",uid,now_iso()))
    c.execute("INSERT OR IGNORE INTO project_members(project_id,user_id,member_role) VALUES(?,?,?)",
              (pid,uid,"owner"))
    # project-scoped documents key
    dok = "dok_live_" + hashlib.sha256(os.urandom(16)).hexdigest()[:20]
    c.execute("INSERT OR IGNORE INTO project_secrets(project_id,documents_api_key) VALUES(?,?)", (pid,dok))
    c.commit()
    c.close()
    return jsonify({"ok": True})

@app.post("/api/v1/auth/login")
def api_login():
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    pw = data.get("password") or ""
    c = db()
    row = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    c.close()
    if not row or row["password_hash"] != sha256(pw):
        return jsonify({"error":"Invalid email or password."}), 401
    token = issue_token(row)
    return jsonify({"token": token})

# CORS for browser-based portal calls
@app.after_request
def cors(resp):
    origin = request.headers.get("Origin")
    allowed = {f"http://portal.{LAB_DOMAIN}", f"http://{LAB_DOMAIN}"}
    if origin in allowed:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
        resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp

@app.route("/api/<path:_any>", methods=["OPTIONS"])
def options_any(_any):
    return ("", 204)

@app.get("/delivery")
def delivery_redirect():
    # Normalize trailing slash
    return ("", 302, {"Location": "/delivery/"})

@app.get("/delivery/")
def delivery_empty():
    # Intentionally blank endpoint (200 with no content)
    return ("", 200)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
