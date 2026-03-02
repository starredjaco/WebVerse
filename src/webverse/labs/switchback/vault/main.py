from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime, timedelta
from typing import Any

import secrets
import pymysql
from pymysql.cursors import DictCursor
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, BaseLoader
from starlette.middleware.sessions import SessionMiddleware

LAB_DOMAIN = os.getenv("LAB_DOMAIN", "switchback.local")
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret")

DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "switchback_vault")
DB_USER = os.getenv("DB_USER", "wv_vault")
DB_PASSWORD = os.getenv("DB_PASSWORD", "wv_vault_pass")

TOTP_DB_NAME = os.getenv("TOTP_DB_NAME", "switchback_totp")

FLAG = os.getenv("FLAG", "WEBVERSE{dev-flag-not-set}")

app = FastAPI(title="Switchback Vault", docs_url=None, redoc_url=None)

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def _hash(pw: str) -> str:
	salt = "vault-salt"
	return hashlib.sha256((salt + pw).encode()).hexdigest()

def _render(request: Request, template: str, ctx: dict[str, Any], status_code: int = 200):
	base = {"request": request, "lab_domain": LAB_DOMAIN}
	base.update(ctx)
	return templates.TemplateResponse(template, base, status_code=status_code)


def _connect_vault():
	return pymysql.connect(
		host=DB_HOST,
		port=DB_PORT,
		user=DB_USER,
		password=DB_PASSWORD,
		database=DB_NAME,
		cursorclass=DictCursor,
		autocommit=True,
	)


def _connect_totp():
	return pymysql.connect(
		host=DB_HOST,
		port=DB_PORT,
		user=DB_USER,
		password=DB_PASSWORD,
		database=TOTP_DB_NAME,
		cursorclass=DictCursor,
		autocommit=True,
	)

def _issue_mfa_code(email: str, request: Request | None = None) -> None:
	# New random code each successful password login; overwrites any previous.
	code = f"{secrets.randbelow(1_000_000):06d}"
	now = datetime.utcnow()
	exp = now + timedelta(minutes=5)

	conn = _connect_totp()
	cur = conn.cursor()
	cur.execute(
		"""
		REPLACE INTO mfa_challenges(email, code, created_at, expires_at)
		VALUES (%s,%s,%s,%s)
		""",
		(
			email,
			code,
			now.strftime("%Y-%m-%d %H:%M:%S"),
			exp.strftime("%Y-%m-%d %H:%M:%S"),
		),
	)
	conn.close()
	_audit(email, "MFA_CHALLENGE_ISSUED", "vault", request)


def _wait_for_db() -> None:
	last_err: Exception | None = None
	for _ in range(60):
		try:
			c1 = _connect_vault()
			c1.close()
			c2 = _connect_totp()
			c2.close()
			return
		except Exception as e:  # pragma: no cover
			last_err = e
			time.sleep(1)
	raise RuntimeError(f"database not ready: {last_err}")


@app.on_event("startup")
def startup() -> None:
	_wait_for_db()

def _client_ip(request: Request) -> str:
	# Nginx sets X-Real-IP
	ip = request.headers.get("x-real-ip") or request.client.host
	return ip or "unknown"


def _audit(actor_email: str, action: str, target: str, request: Request | None = None):
	ip = _client_ip(request) if request else "unknown"
	conn = _connect_vault()
	cur = conn.cursor()
	cur.execute(
		"INSERT INTO vault_audit_events(actor_email, action, target, ip, created_at) VALUES (%s,%s,%s,%s,%s)",
		(actor_email, action, target, ip, datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")),
	)
	conn.close()


def _current_email(request: Request) -> str | None:
	return request.session.get("email")


def _require_auth(request: Request) -> str | None:
	return _current_email(request)

@app.get("/healthz")
def healthz():
	return {"ok": True}


@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
	return _render(
		request,
		"login.html",
		{"title": "Sign in", "error": None, "user": None},
	)


@app.post("/login")
def login_post(request: Request, email: str = Form(...), password: str = Form(...)):
	email = email.strip().lower()

	conn = _connect_vault()
	cur = conn.cursor()
	cur.execute("SELECT email, password_hash FROM vault_users WHERE email=%s LIMIT 1", (email,))

	row = cur.fetchone()
	conn.close()

	if not row or row["password_hash"] != _hash(password):
		# don't leak details
		return _render(
			request,
			"login.html",
			{"title": "Sign in", "error": "Invalid credentials", "user": None},
			status_code=401,
		)

	request.session.clear()
	request.session["preauth_email"] = row["email"]
	_audit(row["email"], "LOGIN_OK", "vault", request)
	_issue_mfa_code(row["email"], request)
	return RedirectResponse("/mfa", status_code=303)


@app.get("/mfa", response_class=HTMLResponse)
def mfa_get(request: Request):
	if not request.session.get("preauth_email"):
		return RedirectResponse("/login", status_code=303)
	return _render(
		request,
		"mfa.html",
		{"title": "MFA", "error": None, "user": None},
	)


@app.post("/mfa", response_class=HTMLResponse)
def mfa_post(request: Request, code: str = Form(...)):
    email = request.session.get("preauth_email")
    if not email:
        return RedirectResponse("/login", status_code=303)

    code = (code or "").strip()
    if len(code) != 6 or not code.isdigit():
        return _render(
            request,
            "mfa.html",
            {"title": "MFA", "error": "Invalid code", "user": None},
            status_code=401,
        )

    conn = _connect_totp()
    cur = conn.cursor()
    cur.execute(
        "SELECT code, expires_at FROM mfa_challenges WHERE email=%s LIMIT 1",
        (email,),
    )
    row = cur.fetchone()

    if not row:
        conn.close()
        return _render(
            request,
            "mfa.html",
            {"title": "MFA", "error": "Invalid code", "user": None},
            status_code=401,
        )

    exp = row["expires_at"]
    if isinstance(exp, str):
        try:
            exp = datetime.fromisoformat(exp.replace(" ", "T"))
        except Exception:
            exp = None

    if exp is not None and datetime.utcnow() > exp:
        cur.execute("DELETE FROM mfa_challenges WHERE email=%s", (email,))
        conn.close()
        return _render(
            request,
            "mfa.html",
            {"title": "MFA", "error": "Code expired. Please sign in again.", "user": None},
            status_code=401,
        )

    if code != str(row["code"]):
        conn.close()
        return _render(
            request,
            "mfa.html",
            {"title": "MFA", "error": "Invalid code", "user": None},
            status_code=401,
        )

    # Success: invalidate one-time code
    cur.execute("DELETE FROM mfa_challenges WHERE email=%s", (email,))
    conn.close()

    request.session.pop("preauth_email", None)
    request.session["email"] = email
    _audit(email, "MFA_OK", "vault", request)
    return RedirectResponse("/", status_code=303)


@app.get("/logout")
def logout(request: Request):
	request.session.clear()
	return RedirectResponse("/login", status_code=303)

@app.get("/policies", response_class=HTMLResponse)
def policies(request: Request):
	email = _require_auth(request)
	if not email:
		return RedirectResponse("/login", status_code=303)

	return _render(
		request,
		"policies.html",
		{"title": "Policies", "email": email},
	)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, q: str | None = None):
	email = _require_auth(request)
	if not email:
		return RedirectResponse("/login", status_code=303)

	conn = _connect_vault()
	cur = conn.cursor()

	if q:
		qv = f"%{q.strip()}%"
		cur.execute(
			"""
			SELECT id, name, created_at, tags, expires_at
			FROM secrets
			WHERE owner_email=%s AND (name LIKE %s OR tags LIKE %s)
			ORDER BY id DESC
			""",
			(email, qv, qv),
		)
	else:
		cur.execute(
			"SELECT id, name, created_at, tags, expires_at FROM secrets WHERE owner_email=%s ORDER BY id DESC",
			(email,),
		)

	secrets = [dict(r) for r in cur.fetchall()]

	cur.execute(
		"SELECT id, actor_email, action, target, ip, created_at FROM vault_audit_events WHERE actor_email=%s ORDER BY id DESC LIMIT 20",
		(email,),
	)

	audit = [dict(r) for r in cur.fetchall()]
	conn.close()

	return _render(
		request,
		"dashboard.html",
		{"title": "Vault", "email": email, "secrets": secrets, "audit": audit, "q": q or ""},
	)


@app.get("/secrets/new", response_class=HTMLResponse)
def new_secret_get(request: Request):
	email = _require_auth(request)
	if not email:
		return RedirectResponse("/login", status_code=303)
	return _render(
		request,
		"new_secret.html",
		{"title": "New secret", "email": email, "error": None},
	)

def _parse_dt(val: str | None) -> str | None:
	if not val:
		return None
	val = val.strip()
	if not val:
		return None
	# Accept YYYY-MM-DD or YYYY-MM-DDTHH:MM
	try:
		if "T" in val:
			dt = datetime.fromisoformat(val)
		else:
			dt = datetime.fromisoformat(val + "T00:00")
		return dt.strftime("%Y-%m-%d %H:%M:%S")
	except Exception:
		return None


@app.post("/secrets/new")
def new_secret_post(
	request: Request,
	name: str = Form(...),
	value: str = Form(...),
	description: str = Form(""),
	tags: str = Form(""),
	expires_at: str = Form(""),
):
	email = _require_auth(request)
	if not email:
		return RedirectResponse("/login", status_code=303)

	if len(name) > 120:
		return _render(
			request,
			"new_secret.html",
			{"title": "New secret", "email": email, "error": "Name too long"},
			status_code=400,
		)

	exp = _parse_dt(expires_at)

	conn = _connect_vault()
	cur = conn.cursor()
	cur.execute(
		"""
		INSERT INTO secrets(owner_email, name, value, description, tags, expires_at, created_at)
		VALUES (%s,%s,%s,%s,%s,%s,%s)
		""",
		(
			email,
			name,
			value,
			(description or "")[:800],
			(tags or "")[:255],
			exp,
			datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
		),
	)
	new_id = cur.lastrowid
	conn.close()

	_audit(email, "SECRET_CREATED", f"secret:{new_id}", request)
	return RedirectResponse(f"/secrets/{new_id}", status_code=303)


@app.get("/secrets/{secret_id}", response_class=HTMLResponse)
def view_secret(request: Request, secret_id: int):
	email = _require_auth(request)
	if not email:
		return RedirectResponse("/login", status_code=303)

	conn = _connect_vault()
	cur = conn.cursor()
	cur.execute(
		"""
		SELECT id, owner_email, name, value, description, tags, expires_at, created_at, last_viewed_at
		FROM secrets
		WHERE id=%s LIMIT 1
		""",
		(secret_id,),
	)
	row = cur.fetchone()

	if not row or row["owner_email"] != email:
		conn.close()
		return RedirectResponse("/", status_code=303)

	# Update last_viewed_at
	cur.execute(
		"UPDATE secrets SET last_viewed_at=%s WHERE id=%s",
		(datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), secret_id),
	)

	conn.close()

	secret = dict(row)

	# Intentionally unsafe: secret name is rendered as a template (SSTI).
	# The intended payloads are the common Jinja2 SSTI chains (PayloadsAllTheThings)
	# that reach os.environ.
	j2 = Environment(loader=BaseLoader())
	rendered_name = j2.from_string(secret["name"]).render()

	_audit(email, "SECRET_VIEWED", f"secret:{secret_id}", request)

	return _render(
		request,
		"view_secret.html",
		{
			"title": f"Secret {secret_id}",
			"lab_domain": LAB_DOMAIN,
			"email": email,
			"secret": secret,
			"rendered_name": rendered_name,
		},
	)

@app.get("/secrets/{secret_id}/value", response_class=JSONResponse)
def secret_value(request: Request, secret_id: int):
	email = _require_auth(request)
	if not email:
		return JSONResponse({"ok": False}, status_code=401)

	conn = _connect_vault()
	cur = conn.cursor()
	cur.execute("SELECT owner_email, value FROM secrets WHERE id=%s LIMIT 1", (secret_id,))
	row = cur.fetchone()
	conn.close()

	if not row or row["owner_email"] != email:
		return JSONResponse({"ok": False}, status_code=404)

	return JSONResponse({"ok": True, "value": row["value"]})


@app.exception_handler(404)
def not_found(request: Request, exc: Exception):
	return _render(request, "error.html", {"title": "Not found", "code": 404, "email": _current_email(request)}, status_code=404)


@app.exception_handler(500)
def server_error(request: Request, exc: Exception):
	return _render(request, "error.html", {"title": "Error", "code": 500, "email": _current_email(request)}, status_code=500)
