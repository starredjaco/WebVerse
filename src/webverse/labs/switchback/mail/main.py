from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

LAB_DOMAIN = os.getenv("LAB_DOMAIN", "switchback.local")
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret")

DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "switchback_mail")
DB_USER = os.getenv("DB_USER", "wv_mail")
DB_PASSWORD = os.getenv("DB_PASSWORD", "wv_mail_pass")

app = FastAPI(title="Switchback Mail", docs_url=None, redoc_url=None)

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def _render(request: Request, template: str, ctx: dict[str, Any], status_code: int = 200):
    base = {"request": request, "lab_domain": LAB_DOMAIN}
    base.update(ctx)
    return templates.TemplateResponse(template, base, status_code=status_code)

def _hash(pw: str) -> str:
    salt = "mail-salt"
    return hashlib.sha256((salt + pw).encode()).hexdigest()


def _connect():
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=DictCursor,
        autocommit=True,
        charset="utf8mb4",
        use_unicode=True,
    )

def _wait_for_db() -> None:
    last_err: Exception | None = None
    for _ in range(60):
        try:
            conn = _connect()
            conn.close()
            return
        except Exception as e:  # pragma: no cover
            last_err = e
            time.sleep(1)
    raise RuntimeError(f"database not ready: {last_err}")


@app.on_event("startup")
def startup() -> None:
    _wait_for_db()


def _get_active_workspace_id(request: Request) -> int:
    ws = request.session.get("workspace_id")
    if ws is None:
        return 1
    try:
        return int(ws)
    except Exception:
        return 1

def _get_workspace(conn, ws_id: int) -> dict[str, Any]:
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM mail_workspaces WHERE id=%s LIMIT 1", (ws_id,))
    row = cur.fetchone()
    return dict(row) if row else {"id": ws_id, "name": "Unknown"}


def get_current_user(request: Request):
    """Authenticate and resolve active user.

    Intended chain bug (tenant/workspace mix-up):

    If the authenticated email doesn't exist inside the selected workspace,
    the app falls back to the first user in that workspace.

    This simulates a migration "convenience" feature that confuses identity
    and workspace context.
    """
    email = request.session.get("email")
    if not email:
        return None

    ws_id = _get_active_workspace_id(request)

    conn = _connect()
    cur = conn.cursor()

    cur.execute(
        "SELECT id, email, workspace_id FROM mail_users WHERE email=%s AND workspace_id=%s LIMIT 1",
        (email, ws_id),
    )
    user = cur.fetchone()

    if user is None:
        cur.execute(
            "SELECT id, email, workspace_id FROM mail_users WHERE workspace_id=%s ORDER BY id ASC LIMIT 1",
            (ws_id,),
        )
        user = cur.fetchone()

    conn.close()
    return dict(user) if user else None


def require_auth(request: Request):
    return get_current_user(request)

@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
    return _render(
        request,
        "login.html",
        {"title": "Sign in", "error": None},
    )


@app.post("/login")
def login_post(request: Request, email: str = Form(...), password: str = Form(...)):
    conn = _connect()
    cur = conn.cursor()

    cur.execute("SELECT email, password_hash, workspace_id FROM mail_users WHERE email=%s LIMIT 1", (email.strip().lower(),))
    row = cur.fetchone()
    conn.close()

    if not row or row["password_hash"] != _hash(password):
        return _render(
            request,
            "login.html",
            {"title": "Sign in", "error": "Invalid credentials"},
            status_code=401,
        )

    request.session["email"] = row["email"]
    request.session["workspace_id"] = int(row["workspace_id"])
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.post("/switch-workspace")
def switch_workspace(request: Request, workspace_id: int = Form(...)):
    request.session["workspace_id"] = int(workspace_id)
    return RedirectResponse("/", status_code=303)


@app.get("/", response_class=HTMLResponse)
def inbox(
    request: Request,
    mailbox: int | None = None,
    folder: str = "inbox",
    q: str | None = None,
):
    user = require_auth(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    ws_id = _get_active_workspace_id(request)
    conn = _connect()
    cur = conn.cursor()

    ws = _get_workspace(conn, ws_id)

    cur.execute("SELECT id, name FROM mail_workspaces ORDER BY id ASC")
    workspaces = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT id, email FROM mail_users WHERE workspace_id=%s ORDER BY email ASC", (ws_id,))
    mailboxes = [dict(r) for r in cur.fetchall()]

    # Mailbox selection is constrained to the active workspace.
    mailbox_id = mailbox if mailbox is not None else user["id"]
    cur.execute(
        "SELECT id, email, workspace_id FROM mail_users WHERE id=%s LIMIT 1",
        (mailbox_id,),
    )

    mailbox_row = cur.fetchone()
    if not mailbox_row or int(mailbox_row["workspace_id"]) != int(ws_id):
        mailbox_id = user["id"]
        cur.execute("SELECT id, email, workspace_id FROM mail_users WHERE id=%s LIMIT 1", (mailbox_id,))
        mailbox_row = cur.fetchone()

    mailbox_obj = dict(mailbox_row) if mailbox_row else {"id": user["id"], "email": user["email"]}

    # Folder filter
    folder = (folder or "inbox").lower()
    allowed_folders = {"inbox", "sent", "archive", "starred"}
    if folder not in allowed_folders:
        folder = "inbox"

    params: list[Any] = [mailbox_obj["id"]]
    where = "mailbox_user_id=%s"

    if folder == "starred":
        where += " AND is_starred=1"
    else:
        where += " AND folder=%s"
        params.append(folder)

    if q:
        qv = f"%{q.strip()}%"
        where += " AND (sender LIKE %s OR recipient LIKE %s OR subject LIKE %s OR body LIKE %s)"
        params.extend([qv, qv, qv, qv])

    cur.execute(
        f"SELECT id, sender, recipient, subject, body, created_at, is_read, is_starred, folder "
        f"FROM mail_messages WHERE {where} ORDER BY id DESC",
        tuple(params),
    )
    messages = [dict(r) for r in cur.fetchall()]

    # Unread counts by folder for sidebar
    cur.execute(
        "SELECT folder, COUNT(*) AS c FROM mail_messages WHERE mailbox_user_id=%s AND is_read=0 GROUP BY folder",
        (mailbox_obj["id"],),
    )
    unread_map = {r["folder"]: int(r["c"]) for r in cur.fetchall()}
    cur.execute(
        "SELECT COUNT(*) AS c FROM mail_messages WHERE mailbox_user_id=%s AND is_read=0 AND is_starred=1",
        (mailbox_obj["id"],),
    )
    starred_unread = int(cur.fetchone()["c"])

    conn.close()

    return _render(
        request,
        "inbox.html",
        {
            "title": "Mail",
            "lab_domain": LAB_DOMAIN,
            "user": user,
            "workspace": ws,
            "workspaces": workspaces,
            "mailboxes": mailboxes,
            "mailbox": mailbox_obj,
            "messages": messages,
            "folder": folder,
            "q": q or "",
            "unread": unread_map,
            "starred_unread": starred_unread,
        },
    )


@app.get("/message/{msg_id}", response_class=HTMLResponse)
def view_message(request: Request, msg_id: int):
    user = require_auth(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    ws_id = _get_active_workspace_id(request)

    conn = _connect()
    cur = conn.cursor()

    # Constrain message access to the active workspace.
    cur.execute(
        """
        SELECT m.id, m.mailbox_user_id, m.sender, m.recipient, m.subject, m.body, m.created_at, m.is_read, m.is_starred, m.folder
        FROM mail_messages m
        JOIN mail_users u ON m.mailbox_user_id = u.id
        WHERE m.id=%s AND u.workspace_id=%s
        LIMIT 1
        """,
        (msg_id, ws_id),
    )
    msg = cur.fetchone()

    if not msg:
        conn.close()
        return RedirectResponse("/", status_code=303)

    # Mark as read
    if int(msg.get("is_read", 0)) == 0:
        cur.execute("UPDATE mail_messages SET is_read=1 WHERE id=%s", (msg_id,))
        msg["is_read"] = 1

    ws = _get_workspace(conn, ws_id)

    conn.close()

    return _render(
        request,
        "message.html",
        {"title": "Message", "user": user, "workspace": ws, "msg": dict(msg)},
    )

@app.post("/message/{msg_id}/star")
def toggle_star(request: Request, msg_id: int):
    user = require_auth(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    ws_id = _get_active_workspace_id(request)

    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT m.id, m.is_starred
        FROM mail_messages m
        JOIN mail_users u ON m.mailbox_user_id=u.id
        WHERE m.id=%s AND u.workspace_id=%s
        LIMIT 1
        """,
        (msg_id, ws_id),
    )
    row = cur.fetchone()
    if row:
        new_val = 0 if int(row["is_starred"]) == 1 else 1
        cur.execute("UPDATE mail_messages SET is_starred=%s WHERE id=%s", (new_val, msg_id))
    conn.close()
    return RedirectResponse(f"/message/{msg_id}", status_code=303)


@app.get("/compose", response_class=HTMLResponse)
def compose_get(request: Request):
    user = require_auth(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    ws_id = _get_active_workspace_id(request)
    conn = _connect()
    ws = _get_workspace(conn, ws_id)
    conn.close()

    return _render(
        request,
        "compose.html",
        {"title": "Compose", "user": user, "workspace": ws, "error": None, "success": None},
     )


@app.post("/compose", response_class=HTMLResponse)
def compose_post(
    request: Request,
    to: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
):
    user = require_auth(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    ws_id = _get_active_workspace_id(request)
    conn = _connect()
    ws = _get_workspace(conn, ws_id)
    cur = conn.cursor()

    recipient = (to or "").strip().lower()
    if "@" not in recipient:
        conn.close()
        return _render(request, "compose.html", {"title":"Compose","user":user,"workspace":ws,"error":"Invalid recipient.","success":None}, status_code=400)

    domain = recipient.split("@", 1)[1]
    if not (domain == LAB_DOMAIN or domain.endswith("." + LAB_DOMAIN)):
        conn.close()
        return _render(
            request,
            "compose.html",
            {
                "title": "Compose",
                "user": user,
                "workspace": ws,
                "error": "Recipient must be an internal address.",
                "success": None,
            },
            status_code=400,
        )

    # Look up recipient mailbox
    cur.execute("SELECT id FROM mail_users WHERE email=%s LIMIT 1", (recipient,))
    rec = cur.fetchone()

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    # Sender 'Sent' copy
    cur.execute(
        """
        INSERT INTO mail_messages(mailbox_user_id, sender, recipient, subject, body, created_at, folder, is_read, is_starred)
        VALUES (%s, %s, %s, %s, %s, %s, 'sent', 1, 0)
        """,
        (user["id"], user["email"], recipient, subject.strip()[:255], body, now),
    )

    if rec:
        cur.execute(
            """
            INSERT INTO mail_messages(mailbox_user_id, sender, recipient, subject, body, created_at, folder, is_read, is_starred)
            VALUES (%s, %s, %s, %s, %s, %s, 'inbox', 0, 0)
            """,
            (int(rec["id"]), user["email"], recipient, subject.strip()[:255], body, now),
        )

    conn.close()

    return _render(
        request,
        "compose.html",
        {"title": "Compose", "user": user, "workspace": ws, "error": None, "success": "Message queued."},
    )


@app.get("/directory", response_class=HTMLResponse)
def directory(request: Request):
    user = require_auth(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    ws_id = _get_active_workspace_id(request)
    conn = _connect()
    ws = _get_workspace(conn, ws_id)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, email FROM mail_users WHERE workspace_id=%s ORDER BY email ASC",
        (ws_id,),
    )
    users = [dict(r) for r in cur.fetchall()]
    conn.close()

    return _render(request, "directory.html", {"title": "Directory", "user": user, "workspace": ws, "users": users})


@app.get("/settings", response_class=HTMLResponse)
def settings(request: Request):
    user = require_auth(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    ws_id = _get_active_workspace_id(request)
    conn = _connect()
    ws = _get_workspace(conn, ws_id)
    conn.close()

    return _render(request, "settings.html", {"title": "Settings", "user": user, "workspace": ws})


@app.exception_handler(404)
def not_found(request: Request, exc: Exception):
    return _render(request, "error.html", {"title": "Not found", "code": 404}, status_code=404)


@app.exception_handler(500)
def server_error(request: Request, exc: Exception):
    return _render(request, "error.html", {"title": "Error", "code": 500}, status_code=500)