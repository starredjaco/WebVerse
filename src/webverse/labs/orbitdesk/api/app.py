import os, time, sqlite3, json, re, random, hashlib
from datetime import datetime, timezone
from flask import Flask, request, jsonify
import jwt
import requests
from ariadne import QueryType, make_executable_schema, graphql_sync

# Ariadne removed PLAYGROUND_HTML in newer versions.
# Keep this lab compatible across Ariadne releases.
try:
    from ariadne.constants import PLAYGROUND_HTML  # older Ariadne
except Exception:
    PLAYGROUND_HTML = None
    try:
        from ariadne.explorer import ExplorerPlayground
        PLAYGROUND_HTML = ExplorerPlayground(title="OrbitDesk GraphQL").html(None)
    except Exception:
        PLAYGROUND_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>OrbitDesk GraphQL</title></head>
<body style="font-family:system-ui;padding:24px">
  <h2>OrbitDesk GraphQL</h2>
  <p>Use <strong>POST</strong> requests at <code>/graphql</code>.</p>
</body></html>"""

app = Flask(__name__)

LAB_DOMAIN = os.getenv("LAB_DOMAIN", "orbitdesk.local")
DB_PATH = os.getenv("DB_PATH", "/data/orbitdesk.db")
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
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
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

INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "dev-internal")

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def now_iso():
    return datetime.now(timezone.utc).isoformat()

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
    cur.execute("""CREATE TABLE IF NOT EXISTS tasks(
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    priority TEXT NOT NULL DEFAULT 'normal',
    created_by INTEGER NOT NULL,
    assignee_email TEXT,
    due_date TEXT,
    created_at TEXT NOT NULL
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS timeline_updates(
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        created_by INTEGER NOT NULL,
        created_at TEXT NOT NULL
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS project_invites(
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        email TEXT NOT NULL,
        invited_by INTEGER NOT NULL,
        token TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        accepted INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS activity_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT NOT NULL,
        actor_id INTEGER,
        action TEXT NOT NULL,
        meta TEXT,
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

def seed_if_empty():
    c = db()
    cur = c.cursor()
    cur.execute("SELECT COUNT(*) AS n FROM users")
    if cur.fetchone()["n"] == 0:
        # If auth hasn't seeded yet, keep the environment stable.
        cur.execute("INSERT INTO users(email,name,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                    ("it.admin@orbitdesk.local","IT Admin","", "admin", now_iso()))
        c.commit()
    # Ensure docs exist
    cur.execute("SELECT COUNT(*) AS n FROM documents")
    if cur.fetchone()["n"] == 0:
        # Create minimal baseline rows; the Files service will create the actual files.
        cur.execute("INSERT OR IGNORE INTO documents(id,project_id,filename,file_id,created_at) VALUES(?,?,?,?,?)",
                    ("DOC-9001","PRJ-1001","Q4-reconciliation.pdf","projects/PRJ-1001/finance/Q4-reconciliation.pdf", now_iso()))
        c.commit()
    c.close()

def decode_token():
    auth = request.headers.get("Authorization","")
    if not auth.startswith("Bearer "):
        return None
    token = auth.split(" ",1)[1].strip()
    try:
        return jwt.decode(token, AUTH_SECRET, algorithms=["HS256"], options={"require": ["iat","iss"]})
    except Exception:
        return None

def require_auth():
    claims = decode_token()
    if not claims:
        return None, (jsonify({"error":"Unauthorized"}), 401)
    return claims, None

def _role(claims):
    return (claims.get("role") or "").strip().lower()

def is_employee_or_admin(claims) -> bool:
    # Lab policy:
    # - "user" accounts are customers and should NOT be able to access GraphQL / project documents.
    # - only internal accounts can: employee + admin
    return _role(claims) in ("employee", "admin")

def require_admin(claims):
    if (claims.get("role") == "admin") or ("ops:admin" in (claims.get("scopes") or "")):
        return True
    return False

def is_member(project_id: str, user_id: int) -> bool:
    c = db()
    row = c.execute("SELECT 1 FROM project_members WHERE project_id=? AND user_id=?", (project_id,user_id)).fetchone()
    c.close()
    return bool(row)

def is_owner(project_id: str, user_id: int) -> bool:
    c = db()
    row = c.execute("SELECT 1 FROM projects WHERE id=? AND owner_id=?", (project_id,user_id)).fetchone()
    c.close()
    return bool(row)

def log_activity(project_id: str, actor_id: int | None, action: str, meta: dict | None = None):
    try:
        c = db()
        c.execute("INSERT INTO activity_log(project_id,actor_id,action,meta,created_at) VALUES(?,?,?,?,?)",
                  (project_id, actor_id, action, json.dumps(meta or {}), now_iso()))
        c.commit()
        c.close()
    except Exception:
        pass

def new_id(prefix: str):
    # deterministic-ish but unique enough for local labs
    return f"{prefix}-{int(time.time()*1000)}"

@app.before_request
def _boot():
    init_db()
    seed_if_empty()

@app.get("/health")
def health():
    return "ok\n", 200, {"Content-Type":"text/plain"}

@app.get("/api/v1/me")
def me():
    claims, err = require_auth()
    if err: return err
    return jsonify({"id": claims.get("sub"), "email": claims.get("email"), "role": claims.get("role"), "name": claims.get("name")})

# --- Projects (REST) ---
@app.get("/api/v1/projects")
def projects_list():
    claims, err = require_auth()
    if err: return err
    uid = int(claims["sub"])
    c = db()
    rows = c.execute("""SELECT p.id,p.name,p.owner_id,p.created_at
                        FROM projects p
                        JOIN project_members m ON m.project_id=p.id
                        WHERE m.user_id=?
                        ORDER BY p.created_at DESC""", (uid,)).fetchall()
    c.close()
    items = []
    for r in rows:
        owner = _user_from_id(int(r["owner_id"]))
        items.append({"id": r["id"], "name": r["name"], "owner": owner, "createdAt": r["created_at"]})
    return jsonify({"items": items})

@app.post("/api/v1/projects")
def projects_create():
    claims, err = require_auth()
    if err: return err
    uid = int(claims["sub"])
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name or len(name) > 80:
        return jsonify({"error":"Invalid project name"}), 400
    project_id = data.get("id")
    if project_id:
        project_id = (str(project_id).strip()[:32]).upper()
        if not re.fullmatch(r"[A-Z0-9\-]{6,32}", project_id or ""):
            return jsonify({"error":"Invalid project id"}), 400
    else:
        project_id = f"PRJ-{random.randint(2000,9999)}"
    docs_key = "docs_" + hashlib.sha256(f"{project_id}:{AUTH_SECRET}".encode()).hexdigest()[:24]
    c = db()
    # ensure unique id
    exists = c.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone()
    if exists:
        c.close()
        return jsonify({"error":"Project id already exists"}), 409
    c.execute("INSERT INTO projects(id,name,owner_id,created_at) VALUES(?,?,?,?)", (project_id,name,uid,now_iso()))
    c.execute("INSERT INTO project_members(project_id,user_id,member_role) VALUES(?,?,?)", (project_id,uid,"owner"))
    c.execute("INSERT OR REPLACE INTO project_secrets(project_id,documents_api_key) VALUES(?,?)", (project_id, docs_key))
    c.commit()
    c.close()
    log_activity(project_id, uid, "project.created", {"name": name})
    return jsonify({"ok": True, "project": {"id": project_id, "name": name}})

@app.get("/api/v1/projects/<project_id>")
def project_get(project_id):
    claims, err = require_auth()
    if err: return err
    uid = int(claims["sub"])
    if not is_member(project_id, uid):
        return jsonify({"error":"Not found"}), 404
    c = db()
    p = c.execute("SELECT id,name,owner_id,created_at FROM projects WHERE id=?", (project_id,)).fetchone()
    c.close()
    if not p: return jsonify({"error":"Not found"}), 404
    owner = _user_from_id(int(p["owner_id"]))
    return jsonify({"project": {"id": p["id"], "name": p["name"], "owner": owner, "createdAt": p["created_at"]}})

@app.patch("/api/v1/projects/<project_id>")
def project_update(project_id):
    claims, err = require_auth()
    if err: return err
    uid = int(claims["sub"])
    if not is_owner(project_id, uid) and not require_admin(claims):
        return jsonify({"error":"Forbidden"}), 403
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name or len(name) > 80:
        return jsonify({"error":"Invalid project name"}), 400
    c = db()
    c.execute("UPDATE projects SET name=? WHERE id=?", (name, project_id))
    c.commit()
    c.close()
    log_activity(project_id, uid, "project.renamed", {"name": name})
    return jsonify({"ok": True})

@app.get("/api/v1/projects/<project_id>/members")
def project_members_list(project_id):
    claims, err = require_auth()
    if err: return err
    uid = int(claims["sub"])
    if not is_member(project_id, uid):
        return jsonify({"error":"Not found"}), 404
    c = db()
    rows = c.execute("""SELECT u.id,u.email,u.name,u.role,m.member_role
                        FROM project_members m JOIN users u ON u.id=m.user_id
                        WHERE m.project_id=?
                        ORDER BY m.member_role DESC, u.email ASC""", (project_id,)).fetchall()
    c.close()
    return jsonify({"items":[{"id": str(r["id"]), "email": r["email"], "name": r["name"], "role": r["role"], "memberRole": r["member_role"]} for r in rows]})

@app.post("/api/v1/projects/<project_id>/members")
def project_member_invite(project_id):
    claims, err = require_auth()
    if err: return err
    uid = int(claims["sub"])
    if not is_owner(project_id, uid) and not require_admin(claims):
        return jsonify({"error":"Forbidden"}), 403
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    role = (data.get("memberRole") or "member").strip().lower()
    if role not in ["member","viewer"]:
        role = "member"
    if not re.fullmatch(r"[^@\s]{1,64}@[A-Za-z0-9\-\.]{3,160}", email or ""):
        return jsonify({"error":"Invalid email"}), 400
    c = db()
    user = c.execute("SELECT id FROM users WHERE lower(email)=?", (email,)).fetchone()
    if user:
        # direct add if user exists (keeps UX simple)
        c.execute("INSERT OR IGNORE INTO project_members(project_id,user_id,member_role) VALUES(?,?,?)", (project_id, int(user["id"]), role))
        c.commit()
        c.close()
        log_activity(project_id, uid, "member.added", {"email": email, "memberRole": role})
        return jsonify({"ok": True, "status": "added"})
    # otherwise store invite token (not vulnerable, random)
    token = hashlib.sha256(f"{email}:{project_id}:{time.time()}:{AUTH_SECRET}".encode()).hexdigest()
    inv_id = new_id("INV")
    expires_at = datetime.now(timezone.utc).timestamp() + (60*60*24*3)
    expires_iso = datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat()
    c.execute("INSERT INTO project_invites(id,project_id,email,invited_by,token,expires_at,accepted,created_at) VALUES(?,?,?,?,?,?,0,?)",
              (inv_id, project_id, email, uid, token, expires_iso, now_iso()))
    c.commit()
    c.close()
    log_activity(project_id, uid, "invite.created", {"email": email})
    return jsonify({"ok": True, "status": "invited"})

@app.get("/api/v1/projects/<project_id>/activity")
def project_activity(project_id):
    claims, err = require_auth()
    if err: return err
    uid = int(claims["sub"])
    if not is_member(project_id, uid):
        return jsonify({"error":"Not found"}), 404
    limit = min(int(request.args.get("limit") or "20"), 50)
    c = db()
    rows = c.execute("SELECT id,actor_id,action,meta,created_at FROM activity_log WHERE project_id=? ORDER BY id DESC LIMIT ?",
                     (project_id, limit)).fetchall()
    c.close()
    items=[]
    for r in rows:
        actor = _user_from_id(int(r["actor_id"])) if r["actor_id"] else None
        meta = {}
        try: meta = json.loads(r["meta"] or "{}")
        except Exception: meta = {}
        items.append({"id": r["id"], "actor": actor, "action": r["action"], "meta": meta, "createdAt": r["created_at"]})
    return jsonify({"items": items})

@app.get("/api/v1/projects/<project_id>/tasks")
def tasks_list(project_id):
    claims, err = require_auth()
    if err: return err
    uid = int(claims["sub"])
    if not is_member(project_id, uid):
        return jsonify({"error":"Not found"}), 404
    c = db()
    rows = c.execute("SELECT id,title,status,priority,assignee_email,due_date,created_at FROM tasks WHERE project_id=? ORDER BY created_at DESC",
                     (project_id,)).fetchall()
    c.close()
    return jsonify({"items":[dict(id=r["id"], title=r["title"], status=r["status"], priority=r["priority"],
                                 assigneeEmail=r["assignee_email"], dueDate=r["due_date"], createdAt=r["created_at"]) for r in rows]})

@app.post("/api/v1/projects/<project_id>/tasks")
def tasks_create(project_id):
    claims, err = require_auth()
    if err: return err
    uid = int(claims["sub"])
    if not is_member(project_id, uid):
        return jsonify({"error":"Not found"}), 404
    data = request.get_json(force=True, silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title or len(title) > 120:
        return jsonify({"error":"Invalid title"}), 400
    priority = (data.get("priority") or "normal").strip().lower()
    if priority not in ["low","normal","high","urgent"]:
        priority = "normal"
    due = (data.get("dueDate") or "").strip()
    if due and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", due):
        return jsonify({"error":"Invalid dueDate"}), 400
    task_id = new_id("TSK")
    c = db()
    c.execute("INSERT INTO tasks(id,project_id,title,status,priority,created_by,assignee_email,due_date,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
              (task_id, project_id, title, "open", priority, uid, None, due or None, now_iso()))
    c.commit()
    c.close()
    log_activity(project_id, uid, "task.created", {"id": task_id, "title": title})
    return jsonify({"ok": True, "task": {"id": task_id}})

@app.patch("/api/v1/projects/<project_id>/tasks/<task_id>")
def tasks_update(project_id, task_id):
    claims, err = require_auth()
    if err: return err
    uid = int(claims["sub"])
    if not is_member(project_id, uid):
        return jsonify({"error":"Not found"}), 404
    data = request.get_json(force=True, silent=True) or {}
    fields = {}
    if "status" in data:
        st = (data.get("status") or "").strip().lower()
        if st not in ["open","in_progress","blocked","done"]:
            return jsonify({"error":"Invalid status"}), 400
        fields["status"]=st
    if "priority" in data:
        pr=(data.get("priority") or "").strip().lower()
        if pr not in ["low","normal","high","urgent"]:
            return jsonify({"error":"Invalid priority"}), 400
        fields["priority"]=pr
    if "assigneeEmail" in data:
        ae=(data.get("assigneeEmail") or "").strip().lower()
        if ae and not re.fullmatch(r"[^@\s]{1,64}@[A-Za-z0-9\-\.]{3,160}", ae):
            return jsonify({"error":"Invalid assigneeEmail"}), 400
        fields["assignee_email"]=ae or None
    if "dueDate" in data:
        due=(data.get("dueDate") or "").strip()
        if due and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", due):
            return jsonify({"error":"Invalid dueDate"}), 400
        fields["due_date"]=due or None
    if not fields:
        return jsonify({"ok": True})
    sets=", ".join([f"{k}=?" for k in fields.keys()])
    vals=list(fields.values())+[project_id, task_id]
    c=db()
    row=c.execute("SELECT 1 FROM tasks WHERE project_id=? AND id=?", (project_id, task_id)).fetchone()
    if not row:
        c.close()
        return jsonify({"error":"Not found"}), 404
    c.execute(f"UPDATE tasks SET {sets} WHERE project_id=? AND id=?", vals)
    c.commit()
    c.close()
    log_activity(project_id, uid, "task.updated", {"id": task_id, "fields": list(fields.keys())})
    return jsonify({"ok": True})

@app.get("/api/v1/projects/<project_id>/updates")
def updates_list(project_id):
    claims, err = require_auth()
    if err: return err
    uid = int(claims["sub"])
    if not is_member(project_id, uid):
        return jsonify({"error":"Not found"}), 404
    c=db()
    rows=c.execute("SELECT id,title,body,created_by,created_at FROM timeline_updates WHERE project_id=? ORDER BY created_at DESC", (project_id,)).fetchall()
    c.close()
    items=[]
    for r in rows:
        actor=_user_from_id(int(r["created_by"]))
        items.append({"id": r["id"], "title": r["title"], "body": r["body"], "createdBy": actor, "createdAt": r["created_at"]})
    return jsonify({"items": items})

@app.post("/api/v1/projects/<project_id>/updates")
def updates_create(project_id):
    claims, err = require_auth()
    if err: return err
    uid=int(claims["sub"])
    if not is_member(project_id, uid):
        return jsonify({"error":"Not found"}), 404
    data=request.get_json(force=True, silent=True) or {}
    title=(data.get("title") or "").strip()
    body=(data.get("body") or "").strip()
    if not title or len(title)>120 or not body or len(body)>5000:
        return jsonify({"error":"Invalid update"}), 400
    up_id=new_id("UPD")
    c=db()
    c.execute("INSERT INTO timeline_updates(id,project_id,title,body,created_by,created_at) VALUES(?,?,?,?,?,?)",
              (up_id, project_id, title, body, uid, now_iso()))
    c.commit(); c.close()
    log_activity(project_id, uid, "update.posted", {"id": up_id, "title": title})
    return jsonify({"ok": True, "update": {"id": up_id}})

@app.get("/api/v1/directory")
def directory():
    claims, err = require_auth()
    if err: return err
    q = (request.args.get("query") or "").strip().lower()
    if len(q) < 2:
        return jsonify({"items":[]})
    c = db()
    rows = c.execute("SELECT id,email,name,role FROM users WHERE email LIKE ? OR name LIKE ? ORDER BY id LIMIT 10", (f"%{q}%", f"%{q}%",)).fetchall()
    c.close()
    return jsonify({"items":[{"id": r["id"], "email": r["email"], "name": r["name"], "role": r["role"]} for r in rows]})

@app.post("/api/v1/contact")
def contact():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()[:120]
    email = (data.get("email") or "").strip()[:160]
    message = (data.get("message") or "").strip()[:4000]
    if not name or not email or not message:
        return jsonify({"error":"Missing fields"}), 400
    c = db()
    c.execute("INSERT INTO contacts(name,email,message,created_at) VALUES(?,?,?,?)", (name,email,message,now_iso()))
    c.commit()
    c.close()
    return jsonify({"ok": True})

# --- GraphQL ---
type_defs = """
    type Query {
      me: User!
      myProjects: [Project!]!
      project(id: ID!): Project
      documents(projectId: ID!): [Document!]!
    }

    type User {
      id: ID!
      email: String!
      name: String!
      role: String!
    }

    type Project {
      id: ID!
      name: String!
      owner: User!
      documentsApiKey: String!
    }

    type Document {
      id: ID!
      filename: String!
      fileId: String!
      createdAt: String!
    }
"""

query = QueryType()

def _user_from_id(user_id: int):
    c = db()
    row = c.execute("SELECT id,email,name,role FROM users WHERE id=?", (user_id,)).fetchone()
    c.close()
    if not row: return None
    return {"id": str(row["id"]), "email": row["email"], "name": row["name"], "role": row["role"]}

@query.field("me")
def resolve_me(*_):
    claims = decode_token() or {}
    return _user_from_id(int(claims.get("sub","0")))

@query.field("myProjects")
def resolve_my_projects(*_):
    claims, err = require_auth()
    if err: raise Exception("Unauthorized")
    if not is_employee_or_admin(claims):
        # customer accounts should not have access to internal project/workspace directory
        raise Exception("Forbidden")

    uid = int(claims["sub"])
    c = db()
    rows = c.execute("""SELECT p.id,p.name,p.owner_id
                        FROM projects p
                        JOIN project_members m ON m.project_id=p.id
                        WHERE m.user_id=?
                        ORDER BY p.id""", (uid,)).fetchall()
    c.close()
    out = []
    for r in rows:
        owner = _user_from_id(int(r["owner_id"]))
        out.append({"id": r["id"], "name": r["name"], "owner": owner})
    return out

@query.field("project")
def resolve_project(*_, id):
    claims, err = require_auth()
    if err: raise Exception("Unauthorized")
    if not is_employee_or_admin(claims):
        raise Exception("Forbidden")
    # NOTE: This resolver is intentionally lenient in the lab environment.
    # Real implementations must enforce project membership.
    c = db()
    proj = c.execute("SELECT id,name,owner_id FROM projects WHERE id=?", (id,)).fetchone()
    if not proj:
        c.close()
        return None
    secret = c.execute("SELECT documents_api_key FROM project_secrets WHERE project_id=?", (id,)).fetchone()
    c.close()
    owner = _user_from_id(int(proj["owner_id"]))
    return {"id": proj["id"], "name": proj["name"], "owner": owner, "documentsApiKey": secret["documents_api_key"] if secret else ""}

@query.field("documents")
def resolve_documents(*_, projectId):
    claims, err = require_auth()
    if err: raise Exception("Unauthorized")
    # Documents are internal-only: employees + admins only
    if not is_employee_or_admin(claims):
        raise Exception("Forbidden")
    uid = int(claims["sub"])
    # This one is properly checked (contrast helps the app feel real).
    c = db()
    m = c.execute("SELECT 1 FROM project_members WHERE project_id=? AND user_id=?", (projectId,uid)).fetchone()
    if not m:
        c.close()
        return []
    rows = c.execute("SELECT id,filename,file_id,created_at FROM documents WHERE project_id=? ORDER BY id", (projectId,)).fetchall()
    c.close()
    return [{"id": r["id"], "filename": r["filename"], "fileId": r["file_id"], "createdAt": r["created_at"]} for r in rows]

schema = make_executable_schema(type_defs, query)

@app.route("/graphql", methods=["GET"])
def graphql_playground():
    claims, err = require_auth()
    if err: return err
    if not is_employee_or_admin(claims):
        return jsonify({"error": "Forbidden"}), 403
    return PLAYGROUND_HTML, 200

@app.route("/graphql", methods=["POST"])
def graphql_server():
    claims, err = require_auth()
    if err: return err
    # Restrict GraphQL entirely to internal accounts (employee/admin).
    if not is_employee_or_admin(claims):
        return jsonify({"error": "Forbidden"}), 403
    data = request.get_json(force=True, silent=True) or {}
    success, result = graphql_sync(schema, data, context_value={"claims": claims}, debug=False)
    status = 200 if success else 400
    return jsonify(result), status

# --- Integrations (admin) ---
def _is_internal_hostname(url: str) -> bool:
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        host = ""
    if not host:
        return False
    # treat *.LAB_DOMAIN (and LAB_DOMAIN itself) as "internal"
    return host == LAB_DOMAIN.lower() or host.endswith("." + LAB_DOMAIN.lower())

def _sanitize_outgoing_headers(h: dict) -> dict:
    # Keep user-supplied headers for realism, but block ones that would break
    # internal trust checks or let the user spoof internal routing metadata.
    out = {}
    for k, v in (h or {}).items():
        if not isinstance(k, str):
            continue
        lk = k.strip().lower()
        if lk in ("host", "x-real-ip", "x-forwarded-host", "x-internal-request", "content-length"):
            continue
        out[k] = v
    return out

@app.post("/api/v2/integrations/test")
def integrations_test():
    claims, err = require_auth()
    if err: return err
    if not require_admin(claims):
        return jsonify({"error":"Forbidden"}), 403

    body = request.get_json(force=True, silent=True) or {}
    url = (body.get("url") or "").strip()
    method = (body.get("method") or "GET").upper()
    headers = _sanitize_outgoing_headers(body.get("headers") or {})
    data = body.get("body") or ""

    if not url.startswith("http://") and not url.startswith("https://"):
        return jsonify({"error":"URL must be http(s)."}), 400
    if method not in ["GET","POST","PUT","DELETE","PATCH"]:
        return jsonify({"error":"Unsupported method"}), 400
    if len(url) > 400:
        return jsonify({"error":"URL too long"}), 400

    # Best-effort safety: block metadata IPs (still leaves plenty of internal surface in a lab)
    blocked = ["169.254.169.254", "metadata.google.internal"]
    if any(b in url for b in blocked):
        return jsonify({"error":"Destination blocked by policy"}), 400

    # Internal trust shim:
    # ops service requires:
    #   - src IP from bridge subnet (handled by docker network)
    #   - X-Internal-Request: 1
    #   - X-Forwarded-Host ends with .LAB_DOMAIN
    # Also, ops prefers X-Real-IP over remote_addr, so NEVER forward client X-Real-IP.
    if _is_internal_hostname(url):
        headers["X-Internal-Request"] = "1"
        headers["X-Forwarded-Host"] = f"api.{LAB_DOMAIN}"
        # Ensure we do not accidentally pass through a client-provided X-Real-IP
        headers.pop("X-Real-IP", None)

    # Requests will follow redirects in real life; here we keep it simple.
    try:
        r = requests.request(
            method,
            url,
            headers=headers,
            data=data.encode() if isinstance(data, str) else data,
            timeout=3,
            allow_redirects=False,
        )
        text = r.text
        if len(text) > 5000:
            text = text[:5000] + "\n…(truncated)…"
        return jsonify({
            "requested": {"method": method, "url": url},
            "status": r.status_code,
            "headers": dict(list(r.headers.items())[:20]),
            "body": text
        })
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 502

# CORS for the portal's browser fetches
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

@app.route("/<path:_any>", methods=["OPTIONS"])
def options_any(_any):
    return ("", 204)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
