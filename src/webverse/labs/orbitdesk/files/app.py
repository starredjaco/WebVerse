import os, time, hmac, hashlib, sqlite3
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template, send_file

app = Flask(__name__)

LAB_DOMAIN = os.getenv("LAB_DOMAIN", "orbitdesk.local")
DB_PATH = os.getenv("DB_PATH", "/data/orbitdesk.db")
FILES_SIGNING_SECRET = os.getenv("FILES_SIGNING_SECRET", "0rB1tD35kSup3rSecretFileSign1ngK3y!")
AUTH_SECRET = os.getenv("AUTH_SECRET", "0rB1tD35kSecretAuthSign1ngK3y!")

# CORS (portal <-> API subdomains). Keeps the lab usable in-browser.
ALLOWED_ORIGINS = {
    f"http://portal.{LAB_DOMAIN}",
    f"http://{LAB_DOMAIN}",
    f"http://marketing.{LAB_DOMAIN}",
}

def _cors_headers():
    origin = request.headers.get("Origin")
    if origin in ALLOWED_ORIGINS:
        return {
            "Access-Control-Allow-Origin": origin,
            "Vary": "Origin",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Documents-Key",
            "Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
        }
    return {}

@app.before_request
def _handle_options():
    if request.method == "OPTIONS":
        return ("", 204, _cors_headers())

@app.after_request
def _add_cors(resp):
    for k,v in _cors_headers().items():
        resp.headers[k]=v
    return resp

OPS_BASE_URL = os.getenv("OPS_BASE_URL", f"http://ops.{LAB_DOMAIN}")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "dev-internal")

STORAGE_ROOT = "/data/storage"

# Block direct DB exfil via traversal (return same 404 as missing files).
DB_ABS_PATH = os.path.normpath(DB_PATH)
DB_BASENAMES_BLOCKLIST = {
    os.path.basename(DB_ABS_PATH),
    os.path.basename(DB_ABS_PATH) + "-journal",
    os.path.basename(DB_ABS_PATH) + "-wal",
    os.path.basename(DB_ABS_PATH) + "-shm",
}

# Config location is controlled via environment variables (defaults preserved).
CONFIG_DIR = os.getenv("ORBITDESK_CONFIG_DIR", "/srv/orbitdesk/config")
CONFIG_PATH = os.getenv("ORBITDESK_CONFIG_PATH", f"{CONFIG_DIR}/service.env")

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def init_db():
    c = db()
    cur = c.cursor()
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
    c.commit()
    c.close()

def ensure_config():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_PATH):
        content = "\n".join([
            "SERVICE=files",
            f"LAB_DOMAIN={LAB_DOMAIN}",
            f"AUTH_SECRET={AUTH_SECRET}",
            f"FILES_SIGNING_SECRET={FILES_SIGNING_SECRET}",
            f"OPS_BASE_URL={OPS_BASE_URL}",
            f"INTERNAL_API_KEY={INTERNAL_API_KEY}",
            "NOTES=Sandbox configuration for internal debugging. Do not commit secrets."
        ]) + "\n"
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(content)
        # readable in the sandbox (misconfiguration)
        os.chmod(CONFIG_PATH, 0o644)

def ensure_storage_seed():
    os.makedirs(STORAGE_ROOT, exist_ok=True)
    # Keep storage in sync with any docs present in the shared DB.
    #
    # The auth service seeds rows into `documents`, and the portal UI expects
    # downloads to work. If the files container starts first, this will become
    # consistent as soon as the docs exist.
    try:
        c = db()
        rows = c.execute("SELECT project_id, filename, file_id FROM documents").fetchall()
        c.close()
    except Exception:
        rows = []

    # Always ensure at least one believable seeded doc exists (safe even if DB is empty).
    if not rows:
        rows = [{"project_id": "PRJ-1001", "filename": "Q4-reconciliation.pdf", "file_id": "projects/PRJ-1001/finance/Q4-reconciliation.pdf"}]

    # Intentionally seeded .env for the lab chain (downloadable via fileId=./.env)
    # This is NOT the real service.env; it only reveals where config lives.
    try:
        env_path = os.path.join(STORAGE_ROOT, ".env")
        os.makedirs(STORAGE_ROOT, exist_ok=True)
        if not os.path.exists(env_path):
            with open(env_path, "w", encoding="utf-8") as f:
                f.write('CONFIG_DIR = "/srv/orbitdesk/config"\n')
                f.write('CONFIG_PATH = f"{CONFIG_DIR}/service.env"\n')
    except Exception:
        pass

    for r in rows:
        # sqlite Row supports dict-style access
        file_id = (r["file_id"] if hasattr(r, "keys") else r.get("file_id") if isinstance(r, dict) else "").strip()
        if not file_id:
            continue
        # Only seed believable project files (avoid creating files for traversal payloads).
        if not file_id.startswith("projects/"):
            continue

        abs_path = os.path.normpath(os.path.join(STORAGE_ROOT, file_id))
        # Prevent escaping the storage root when seeding.
        if not abs_path.startswith(os.path.normpath(STORAGE_ROOT) + os.sep):
            continue

        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        if os.path.exists(abs_path):
            continue

        project_id = (r["project_id"] if hasattr(r, "keys") else r.get("project_id") if isinstance(r, dict) else "").strip()
        filename = (r["filename"] if hasattr(r, "keys") else r.get("filename") if isinstance(r, dict) else "").strip()
        title = f"{project_id} • {filename}".encode()

        # Create a believable PDF-like text artifact.
        with open(abs_path, "wb") as f:
            f.write(b"%PDF-1.4\n% OrbitDesk export\n\n")
            f.write(title + b"\n\n")
            f.write(b"Generated document placeholder for the OrbitDesk sandbox.\n")
            f.write(b"(For internal distribution only)\n")
            f.write(b"\n%%EOF\n")

        # Lab artifact: allow players to use fileId=./.env to retrieve a "developer note"
        # that hints at where the real config is stored.
        env_hint_path = os.path.join(STORAGE_ROOT, ".env")
        if not os.path.exists(env_hint_path):
            with open(env_hint_path, "w", encoding="utf-8") as f:
                f.write('CONFIG_DIR = "/srv/orbitdesk/config"\n')
                f.write('CONFIG_PATH = f"{CONFIG_DIR}/service.env"\n')
    

@app.before_request
def _boot():
    init_db()
    ensure_config()
    ensure_storage_seed()

@app.get("/")
def home():
    return render_template("index.html", lab_domain=LAB_DOMAIN)

@app.get("/health")
def health():
    return "ok\n", 200, {"Content-Type":"text/plain"}

def _doc_key():
    # Accept either header name (what you'd see in internal integrations)
    # or a bearer-like token for convenience.
    key = request.headers.get("X-Documents-Key") or ""
    if key:
        return key.strip()
    auth = request.headers.get("Authorization","")
    if auth.startswith("Bearer "):
        return auth.split(" ",1)[1].strip()
    return ""

def _project_for_key(key: str):
    c = db()
    row = c.execute("SELECT project_id FROM project_secrets WHERE documents_api_key=?", (key,)).fetchone()
    c.close()
    return row["project_id"] if row else None

def _sign(ts: int) -> str:
    # NOTE: signature intentionally only binds timestamp (not file_id).
    mac = hmac.new(FILES_SIGNING_SECRET.encode(), str(ts).encode(), hashlib.sha256).hexdigest()
    return mac[:16]

@app.get("/api/v1/list")
def list_docs():
    key = _doc_key()
    if not key:
        return jsonify({"error":"Missing document key"}), 401
    project = request.args.get("project","").strip()
    project_for_key = _project_for_key(key)
    if not project_for_key:
        return jsonify({"error":"Invalid document key"}), 403
    if project and project != project_for_key:
        return jsonify({"items":[]})
    c = db()
    rows = c.execute("SELECT id,filename,file_id,created_at FROM documents WHERE project_id=? ORDER BY id", (project_for_key,)).fetchall()
    c.close()
    return jsonify({"items":[{"id": r["id"], "filename": r["filename"], "fileId": r["file_id"], "createdAt": r["created_at"]} for r in rows]})

@app.post("/api/v1/share")
def share():
    key = _doc_key()
    if not key:
        return jsonify({"error":"Missing document key"}), 401
    project_for_key = _project_for_key(key)
    if not project_for_key:
        return jsonify({"error":"Invalid document key"}), 403
    data = request.get_json(force=True, silent=True) or {}
    file_id = (data.get("fileId") or "").strip()
    if not file_id:
        return jsonify({"error":"Missing fileId"}), 400
    c = db()
    row = c.execute("SELECT file_id FROM documents WHERE project_id=? AND file_id=?", (project_for_key, file_id)).fetchone()
    c.close()
    if not row:
        return jsonify({"error":"Not found"}), 404
    ts = int(time.time())
    sig = _sign(ts)
    url = f"http://files.{LAB_DOMAIN}/api/v1/download?fileId={file_id}&ts={ts}&sig={sig}"
    return jsonify({"url": url, "expiresIn": 86400})

@app.get("/api/v1/download")
def download():
    file_id = (request.args.get("fileId") or "").strip()
    ts = request.args.get("ts","").strip()
    sig = request.args.get("sig","").strip()
    if not file_id or not ts or not sig:
        return jsonify({"error":"Missing parameters"}), 400
    try:
        ts_i = int(ts)
    except Exception:
        return jsonify({"error":"Bad timestamp"}), 400
    if sig != _sign(ts_i):
        return jsonify({"error":"Invalid signature"}), 403
    # Accept links up to 24 hours old (simple policy)
    if abs(int(time.time()) - ts_i) > 86400:
        return jsonify({"error":"Link expired"}), 403

    # Vulnerable join (path traversal). Used by the lab chain to read internal config.
    path = os.path.normpath(os.path.join(STORAGE_ROOT, file_id))

    # If traversal resolves to the SQLite DB (or sidecar files), pretend it doesn't exist.
    # This keeps the response indistinguishable from a normal missing-file 404.
    try:
        base = os.path.basename(path)
        if os.path.normpath(path) == DB_ABS_PATH or base in DB_BASENAMES_BLOCKLIST:
            return jsonify({"error":"Not found"}), 404
    except Exception:
        pass

    if not os.path.exists(path) or os.path.isdir(path):
        return jsonify({"error":"Not found"}), 404
    return send_file(path, as_attachment=True, download_name=os.path.basename(path))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
