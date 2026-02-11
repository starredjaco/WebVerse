from __future__ import annotations

import json
import os
import secrets
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import jwt
import requests
from ariadne import QueryType, gql, make_executable_schema
from ariadne.graphql import graphql_sync
from flask import Flask, Response, make_response, redirect, render_template, request

APP = Flask(__name__)
APP.secret_key = os.getenv("FLASK_SECRET", "qs-dev-" + secrets.token_hex(12))

LAB_DOMAIN = os.getenv("LAB_DOMAIN", "quartershift.local")
DB_PATH = os.getenv("DB_PATH", "/data/quartershift.db")
JWT_SECRET = os.getenv("JWT_SECRET", "QuarterShift_Dev_Secret_2026")
FLAG = os.getenv("FLAG", "WEBVERSE{house_edge_meets_cache_edge}")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'player',
            reset_code TEXT,
            created_ts INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tournaments (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT NOT NULL,
            season TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS leaderboard (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            score INTEGER NOT NULL,
            ts INTEGER NOT NULL
        )
        """
    )
    conn.commit()

    if int(conn.execute("SELECT COUNT(*) AS n FROM tournaments").fetchone()["n"]) == 0:
        conn.execute(
            "INSERT INTO tournaments (id, name, status, season) VALUES (?,?,?,?)",
            (101, "Midnight Split", "LIVE", "Q1-2026"),
        )
        conn.execute(
            "INSERT INTO tournaments (id, name, status, season) VALUES (?,?,?,?)",
            (102, "Quarter Burn", "SCHEDULED", "Q1-2026"),
        )
        conn.commit()

    if int(conn.execute("SELECT COUNT(*) AS n FROM leaderboard").fetchone()["n"]) == 0:
        seed = [
            ("crankshaft", 9150),
            ("riverslot", 8740),
            ("dealers_choice", 8410),
            ("pitboss", 8020),
            ("split_ace", 7900),
            ("driftstack", 7410),
            ("coldshoe", 7150),
            ("doubletap", 6990),
            ("chipcount", 6540),
            ("sidebet", 6020),
        ]
        now = int(time.time())
        for u, s in seed:
            conn.execute("INSERT INTO leaderboard (username, score, ts) VALUES (?,?,?)", (u, s, now))
        conn.commit()

    # Seed a moderator account within a fuzzable 0-10k id window.
    row = conn.execute("SELECT id, reset_code FROM users WHERE email = ?", ("moderator@quartershift.local",)).fetchone()
    if row is None:
        existing = int(conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"])
        if existing < 20:
            for i in range(20 - existing):
                email = f"seed{i}@quartershift.local"
                try:
                    conn.execute(
                        "INSERT INTO users (username,email,password,role,created_ts) VALUES (?,?,?,?,?)",
                        (f"seed{i}", email, secrets.token_hex(8), "player", int(time.time())),
                    )
                except Exception:
                    pass
            conn.commit()

        conn.execute(
            "INSERT INTO users (username,email,password,role,reset_code,created_ts) VALUES (?,?,?,?,?,?)",
            ("tournament_mod", "moderator@quartershift.local", secrets.token_hex(16), "moderator", None, int(time.time())),
        )
        conn.commit()

    row = conn.execute("SELECT id, reset_code FROM users WHERE email = ?", ("moderator@quartershift.local",)).fetchone()
    if row and not row["reset_code"]:
        code = f"QS-{int(row['id']):04d}-{secrets.randbelow(9000)+1000}"
        conn.execute("UPDATE users SET reset_code = ? WHERE id = ?", (code, int(row["id"])))
        conn.commit()

    conn.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%b %d %Y %I:%M%p UTC")


def surface_from_host(host: str) -> str:
    host = (host or "").split(":")[0].lower()
    if host == LAB_DOMAIN:
        return "marketing"
    if host.endswith("." + LAB_DOMAIN):
        sub = host[: -(len(LAB_DOMAIN) + 1)]
        if sub in {"portal", "games", "scores", "auth", "ops", "dashboard"}:
            return sub
    return "marketing"


def _get_token_from_request() -> Optional[str]:
    tok = request.cookies.get("qs_token")
    if tok:
        return tok
    authz = request.headers.get("Authorization", "")
    if authz.lower().startswith("bearer "):
        return authz.split(" ", 1)[1].strip()
    return None


def auth_decode(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        return None


def auth_encode(payload: Dict[str, Any]) -> str:
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def current_user() -> Optional[Dict[str, Any]]:
    tok = _get_token_from_request()
    if not tok:
        return None
    return auth_decode(tok)


def set_auth_cookie(resp: Response, token: str) -> Response:
    # IMPORTANT: share auth across subdomains (portal/games/dashboard/scores)
    resp.set_cookie(
        "qs_token",
        token,
        httponly=True,
        samesite="Lax",
        path="/",
        domain=f".{LAB_DOMAIN}",
    )
    return resp


def clear_auth_cookie(resp: Response) -> Response:
    resp.set_cookie("qs_token", "", expires=0, path="/", domain=f".{LAB_DOMAIN}")
    return resp


@dataclass
class CacheEntry:
    body: bytes
    status: int
    headers: Dict[str, str]
    created: float


_CACHE: Dict[str, CacheEntry] = {}
_CACHE_TTL_S = 45
_CACHE_MAX = 256


def cache_key() -> str:
    host = (request.host or "").split(":")[0].lower()
    path = request.full_path
    return f"{host}::{request.method}::{path}"


def cache_get(k: str) -> Optional[CacheEntry]:
    ent = _CACHE.get(k)
    if not ent:
        return None
    if (time.time() - ent.created) > _CACHE_TTL_S:
        _CACHE.pop(k, None)
        return None
    return ent


def cache_set(k: str, ent: CacheEntry) -> None:
    if len(_CACHE) >= _CACHE_MAX:
        oldest = sorted(_CACHE.items(), key=lambda kv: kv[1].created)[: max(1, _CACHE_MAX // 8)]
        for kk, _ in oldest:
            _CACHE.pop(kk, None)
    _CACHE[k] = ent


def db_get_user_by_email(email: str) -> Optional[sqlite3.Row]:
    conn = connect()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
    conn.close()
    return row


def db_get_user_by_id(uid: int) -> Optional[sqlite3.Row]:
    conn = connect()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (int(uid),)).fetchone()
    conn.close()
    return row


def db_create_user(username: str, email: str, password: str) -> Tuple[bool, str]:
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO users (username,email,password,role,created_ts) VALUES (?,?,?,?,?)",
            (username.strip(), email.strip().lower(), password, "player", int(time.time())),
        )
        conn.commit()
        return True, ""
    except Exception:
        return False, "Account already exists."
    finally:
        conn.close()


def db_set_reset_code(email: str, code: str) -> None:
    conn = connect()
    conn.execute("UPDATE users SET reset_code = ? WHERE email = ?", (code, email.strip().lower()))
    conn.commit()
    conn.close()


def db_reset_password(email: str, code: str, new_password: str) -> bool:
    conn = connect()
    row = conn.execute("SELECT reset_code FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
    if not row:
        conn.close()
        return False
    if (row["reset_code"] or "") != (code or ""):
        conn.close()
        return False
    conn.execute("UPDATE users SET password = ?, reset_code = NULL WHERE email = ?", (new_password, email.strip().lower()))
    conn.commit()
    conn.close()
    return True


def auth_api_json(payload: Dict[str, Any], status: int = 200) -> Response:
    r = make_response(json.dumps(payload), status)
    r.headers["Content-Type"] = "application/json"
    return r


type_defs = gql(
    """
    type LeaderRow {
      rank: Int!
      username: String!
      score: Int!
    }

    type Tournament {
      id: Int!
      name: String!
      status: String!
      season: String!
    }

    type Moderator {
      id: Int!
      email: String!
      displayName: String!
      resetCode: String
    }

    type Query {
      leaderboardTop(limit: Int = 10): [LeaderRow!]!
      tournament(id: Int!): Tournament
      moderator(id: Int!): Moderator
    }
"""
)

query = QueryType()


def _is_kiosk_client() -> bool:
    return (request.headers.get("X-Client", "").strip().lower() == "kiosk")


@query.field("leaderboardTop")
def resolve_leaderboard(*_, limit: int = 10):
    conn = connect()
    rows = conn.execute("SELECT username, score FROM leaderboard ORDER BY score DESC, ts DESC LIMIT ?", (int(limit),)).fetchall()
    conn.close()
    out = []
    rank = 1
    for r in rows:
        out.append({"rank": rank, "username": r["username"], "score": int(r["score"])})
        rank += 1
    return out


@query.field("tournament")
def resolve_tournament(*_, id: int):
    conn = connect()
    row = conn.execute("SELECT * FROM tournaments WHERE id = ?", (int(id),)).fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)


@query.field("moderator")
def resolve_moderator(*_, id: int):
    if not _is_kiosk_client():
        return None
    row = db_get_user_by_id(int(id))
    if not row or row["role"] != "moderator":
        return None
    return {
        "id": int(row["id"]),
        "email": row["email"],
        "displayName": row["username"],
        "resetCode": row["reset_code"],
    }


schema = make_executable_schema(type_defs, query)


def ops_internal_only() -> bool:
    ra = (request.remote_addr or "")
    return ra in {"127.0.0.1", "::1"}

def marketing_home_override() -> Response:
    """
    Stealth behavior:
    If someone hits internal-only surfaces from a non-internal IP,
    serve the normal marketing homepage so subdomain fuzzing can't
    distinguish ops via status/size/body differences.
    """
    return make_response(
        render_template(
            "marketing.html",
            title="Quarter Shift",
            surf="marketing",
            domain=LAB_DOMAIN,
            user=current_user(),
            logout_url="/logout",
            year=datetime.utcnow().year,
        ),
        200,
    )


def ops_decode_jwt(token: str) -> Optional[Dict[str, Any]]:
    try:
        header = jwt.get_unverified_header(token)
    except Exception:
        return None
    alg = (header.get("alg") or "").lower()

    # Vulnerability: accepts alg=none
    if alg == "none":
        try:
            return jwt.decode(token, options={"verify_signature": False, "verify_aud": False})
        except Exception:
            return None

    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        return None


def ops_current() -> Optional[Dict[str, Any]]:
    tok = _get_token_from_request()
    if not tok:
        return None
    return ops_decode_jwt(tok)


def ops_require_admin() -> bool:
    u = ops_current()
    if not u:
        return False
    return u.get("role") in {"admin","moderator"}


@APP.route("/static/<path:fname>")
def static_files(fname: str):
    return APP.send_static_file(fname)


@APP.route("/logout")
def logout():
    resp = redirect(f"http://{LAB_DOMAIN}/")
    return clear_auth_cookie(resp)


@APP.route("/")
def root():
    surf = surface_from_host(request.host)
    u = current_user()

    if surf == "marketing":
        return render_template(
            "marketing.html",
            title="Quarter Shift",
            surf="marketing",
            domain=LAB_DOMAIN,
            user=u,
            logout_url="/logout",
            year=datetime.utcnow().year,
        )

    if surf == "portal":
        if u:
            return redirect(f"http://games.{LAB_DOMAIN}/")
        return redirect("/login")

    if surf == "games":
        if not u:
            return redirect(f"http://portal.{LAB_DOMAIN}/login")
        return render_template(
            "games.html",
            title="Games",
            surf="games",
            domain=LAB_DOMAIN,
            user=u,
            logout_url="/logout",
            year=datetime.utcnow().year,
        )

    if surf == "dashboard":
        if not u:
            return redirect(f"http://portal.{LAB_DOMAIN}/login")
        if u.get("role") != "moderator":
            return redirect(f"http://games.{LAB_DOMAIN}/")
        return render_template(
            "dashboard.html",
            title="Moderator Console",
            surf="dashboard",
            domain=LAB_DOMAIN,
            user=u,
            logout_url="/logout",
            year=datetime.utcnow().year,
        )

    if surf == "ops":
        if not ops_internal_only():
            return marketing_home_override()
        if not ops_require_admin():
            return render_template("ops_denied.html", title="Ops", surf="ops", domain=LAB_DOMAIN, user=None, logout_url="/logout", year=datetime.utcnow().year), 403
        return render_template(
            "ops_home.html",
            title="Ops Backoffice",
            surf="ops",
            domain=LAB_DOMAIN,
            user=ops_current(),
            logout_url="/logout",
            year=datetime.utcnow().year,
        )

    if surf == "scores":
        return redirect("/graphql")

    if surf == "auth":
        return auth_api_json({"ok": True, "service": "auth", "ts": now_iso()})

    return render_template("marketing.html", title="Quarter Shift", surf="marketing", domain=LAB_DOMAIN, user=u, logout_url="/logout", year=datetime.utcnow().year)


@APP.route("/about")
def about():
    surf = surface_from_host(request.host)
    if surf != "marketing":
        return redirect(f"http://{LAB_DOMAIN}/about")
    return render_template("about.html", title="About", surf="marketing", domain=LAB_DOMAIN, user=current_user(), logout_url="/logout", year=datetime.utcnow().year)


@APP.route("/play")
def play_now():
    u = current_user()
    if not u:
        return redirect(f"http://portal.{LAB_DOMAIN}/login")
    return redirect(f"http://games.{LAB_DOMAIN}/")


@APP.route("/login", methods=["GET", "POST"])
def portal_login():
    if surface_from_host(request.host) != "portal":
        return redirect(f"http://portal.{LAB_DOMAIN}/login")

    if request.method == "GET":
        return render_template("portal_login.html", title="Login", surf="portal", domain=LAB_DOMAIN, user=None, logout_url="/logout", year=datetime.utcnow().year, error=None)

    email = (request.form.get("email") or "").strip().lower()
    password = (request.form.get("password") or "")

    row = db_get_user_by_email(email)
    if not row or row["password"] != password:
        return render_template("portal_login.html", title="Login", surf="portal", domain=LAB_DOMAIN, user=None, logout_url="/logout", year=datetime.utcnow().year, error="Invalid email or password.")

    token = auth_encode({"sub": int(row["id"]), "username": row["username"], "role": row["role"], "iat": int(time.time())})
    resp = redirect(f"http://games.{LAB_DOMAIN}/")
    return set_auth_cookie(resp, token)


@APP.route("/signup", methods=["GET", "POST"])
def portal_signup():
    if surface_from_host(request.host) != "portal":
        return redirect(f"http://portal.{LAB_DOMAIN}/signup")

    if request.method == "GET":
        return render_template("portal_signup.html", title="Sign up", surf="portal", domain=LAB_DOMAIN, user=None, logout_url="/logout", year=datetime.utcnow().year, error=None)

    username = (request.form.get("username") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    password = (request.form.get("password") or "")

    if not username or not email or not password:
        return render_template("portal_signup.html", title="Sign up", surf="portal", domain=LAB_DOMAIN, user=None, logout_url="/logout", year=datetime.utcnow().year, error="Missing fields.")

    ok, err = db_create_user(username, email, password)
    if not ok:
        return render_template("portal_signup.html", title="Sign up", surf="portal", domain=LAB_DOMAIN, user=None, logout_url="/logout", year=datetime.utcnow().year, error=err)

    # AUTO-LOGIN after signup + redirect to games
    row = db_get_user_by_email(email)
    if not row:
        return redirect(f"http://portal.{LAB_DOMAIN}/login")

    token = auth_encode({"sub": int(row["id"]), "username": row["username"], "role": row["role"], "iat": int(time.time())})
    resp = redirect(f"http://games.{LAB_DOMAIN}/")
    return set_auth_cookie(resp, token)


@APP.route("/reset", methods=["GET", "POST"])
def portal_reset():
    if surface_from_host(request.host) != "portal":
        return redirect(f"http://portal.{LAB_DOMAIN}/reset")

    if request.method == "GET":
        return render_template("portal_reset.html", title="Reset", surf="portal", domain=LAB_DOMAIN, user=None, logout_url="/logout", year=datetime.utcnow().year, msg=None, error=None)

    email = (request.form.get("email") or "").strip().lower()
    row = db_get_user_by_email(email)
    if row:
        code = f"QS-{int(row['id']):04d}-{secrets.randbelow(9000)+1000}"
        db_set_reset_code(email, code)

    return render_template("portal_reset.html", title="Reset", surf="portal", domain=LAB_DOMAIN, user=None, logout_url="/logout", year=datetime.utcnow().year, msg="If the account exists, a reset code was issued.", error=None)


@APP.route("/reset/confirm", methods=["GET", "POST"])
def portal_reset_confirm():
    if surface_from_host(request.host) != "portal":
        return redirect(f"http://portal.{LAB_DOMAIN}/reset/confirm")

    if request.method == "GET":
        return render_template("portal_reset_confirm.html", title="Reset code", surf="portal", domain=LAB_DOMAIN, user=None, logout_url="/logout", year=datetime.utcnow().year, error=None)

    email = (request.form.get("email") or "").strip().lower()
    code = (request.form.get("code") or "").strip()
    new_pw = (request.form.get("new_password") or "")
    if not db_reset_password(email, code, new_pw):
        return render_template("portal_reset_confirm.html", title="Reset code", surf="portal", domain=LAB_DOMAIN, user=None, logout_url="/logout", year=datetime.utcnow().year, error="Invalid reset code.")
    return redirect(f"http://portal.{LAB_DOMAIN}/login")


@APP.route("/standings")
def standings():
    if surface_from_host(request.host) != "games":
        return redirect(f"http://games.{LAB_DOMAIN}/standings")
    u = current_user()
    if not u:
        return redirect(f"http://portal.{LAB_DOMAIN}/login")
    return render_template("standings.html", title="Standings", surf="games", domain=LAB_DOMAIN, user=u, logout_url="/logout", year=datetime.utcnow().year)


@APP.route("/dashboard")
def dash_home():
    if surface_from_host(request.host) != "dashboard":
        return redirect(f"http://dashboard.{LAB_DOMAIN}/dashboard")
    u = current_user()
    if not u:
        return redirect(f"http://portal.{LAB_DOMAIN}/login")
    if u.get("role") != "moderator":
        return redirect(f"http://games.{LAB_DOMAIN}/")
    return render_template("dashboard.html", title="Moderator Console", surf="dashboard", domain=LAB_DOMAIN, user=u, logout_url="/logout", year=datetime.utcnow().year)


@APP.route("/v1/auth/login", methods=["POST"])
def api_login():
    if surface_from_host(request.host) != "auth":
        return auth_api_json({"error": "wrong-surface"}, 404)

    try:
        data = request.get_json(force=True)
    except Exception:
        data = {}
    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "")

    row = db_get_user_by_email(email)
    if not row or row["password"] != password:
        return auth_api_json({"ok": False, "error": "invalid_credentials"}, 401)

    token = auth_encode({"sub": int(row["id"]), "username": row["username"], "role": row["role"], "iat": int(time.time())})
    return auth_api_json({"ok": True, "token": token})


@APP.route("/v1/auth/reset/request", methods=["POST"])
def api_reset_request():
    if surface_from_host(request.host) != "auth":
        return auth_api_json({"error": "wrong-surface"}, 404)
    try:
        data = request.get_json(force=True)
    except Exception:
        data = {}
    email = (data.get("email") or "").strip().lower()

    row = db_get_user_by_email(email)
    if row:
        code = f"QS-{int(row['id']):04d}-{secrets.randbelow(9000)+1000}"
        db_set_reset_code(email, code)

    return auth_api_json({"ok": True})


@APP.route("/v1/auth/reset/confirm", methods=["POST"])
def api_reset_confirm():
    if surface_from_host(request.host) != "auth":
        return auth_api_json({"error": "wrong-surface"}, 404)
    try:
        data = request.get_json(force=True)
    except Exception:
        data = {}
    email = (data.get("email") or "").strip().lower()
    code = (data.get("code") or "").strip()
    new_pw = (data.get("new_password") or "")

    if not db_reset_password(email, code, new_pw):
        return auth_api_json({"ok": False, "error": "invalid_code"}, 400)
    return auth_api_json({"ok": True})


@APP.route("/graphql", methods=["GET", "POST", "OPTIONS"])
def graphql_endpoint():
    if surface_from_host(request.host) != "scores":
        return auth_api_json({"error": "wrong-surface"}, 404)

    cors_origin = "*"

    if request.method == "OPTIONS":
        r = make_response("", 204)
        r.headers["Access-Control-Allow-Origin"] = cors_origin
        r.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Client, Authorization"
        r.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return r

    # Cache only GET responses; BUG: cache key does not vary on X-Client.
    if request.method == "GET":
        k = cache_key()
        ent = cache_get(k)
        if ent:
            resp = make_response(ent.body, ent.status)
            for hk, hv in ent.headers.items():
                resp.headers[hk] = hv
            resp.headers["Age"] = str(int(time.time() - ent.created))
            resp.headers["Access-Control-Allow-Origin"] = cors_origin
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Client, Authorization"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            return resp

        gql_query = (request.args.get("query") or "").strip()
        variables = request.args.get("variables")
        try:
            vars_obj = json.loads(variables) if variables else None
        except Exception:
            vars_obj = None

        _, result = graphql_sync(schema, {"query": gql_query, "variables": vars_obj}, context_value={"request": request}, debug=True)
        body = json.dumps(result).encode()

        resp = make_response(body, 200)
        resp.headers["Content-Type"] = "application/json"
        resp.headers["Access-Control-Allow-Origin"] = cors_origin
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Client, Authorization"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        cache_set(k, CacheEntry(body=body, status=200, headers={"Content-Type": "application/json"}, created=time.time()))
        return resp

    try:
        data = request.get_json(force=True)
    except Exception:
        data = {}
    _, result = graphql_sync(schema, data, context_value={"request": request}, debug=True)
    resp = auth_api_json(result)
    resp.headers["Access-Control-Allow-Origin"] = cors_origin
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Client, Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


def is_loopback_host(hostname: str) -> bool:
    if not hostname:
        return False
    hostname = hostname.lower().strip()
    if hostname in {"127.0.0.1", "localhost"}:
        return True
    if hostname.endswith("." + LAB_DOMAIN):
        return True
    return False


@APP.route("/tools/fetch")
def moderator_fetch():
    if surface_from_host(request.host) != "dashboard":
        return redirect(f"http://dashboard.{LAB_DOMAIN}/tools/fetch")

    u = current_user()
    if not u or u.get("role") != "moderator":
        return redirect(f"http://portal.{LAB_DOMAIN}/login")

    source = (request.args.get("sourceUrl") or "").strip()
    if not source:
        return redirect(f"http://dashboard.{LAB_DOMAIN}/dashboard")

    parsed = urlparse(source)
    if parsed.scheme not in {"http", "https"}:
        return render_template("fetch.html", title="Fetch", surf="dashboard", domain=LAB_DOMAIN, user=u, logout_url="/logout", year=datetime.utcnow().year, source=source, body="Unsupported URL scheme."), 400

    # Only loopback / local surfaces allowed. Players will SSRF within .local by fuzzing.
    if not is_loopback_host(parsed.hostname or ""):
        return render_template("fetch.html", title="Fetch", surf="dashboard", domain=LAB_DOMAIN, user=u, logout_url="/logout", year=datetime.utcnow().year, source=source, body="Preview failed."), 502

    try:
        r = requests.get(source, timeout=3, cookies={"qs_token": (_get_token_from_request() or "")})
        body = r.text[:4000]
    except Exception:
        body = "Preview failed."
    return render_template("fetch.html", title="Fetch", surf="dashboard", domain=LAB_DOMAIN, user=u, logout_url="/logout", year=datetime.utcnow().year, source=source, body=body)


@APP.route("/exports")
def exports_home():
    if surface_from_host(request.host) != "dashboard":
        return redirect(f"http://dashboard.{LAB_DOMAIN}/exports")
    u = current_user()
    if not u or u.get("role") != "moderator":
        return redirect(f"http://portal.{LAB_DOMAIN}/login")
    return render_template("exports.html", title="Exports", surf="dashboard", domain=LAB_DOMAIN, user=u, logout_url="/logout", year=datetime.utcnow().year)


@APP.route("/exports/weekly")
def exports_weekly():
    if surface_from_host(request.host) != "dashboard":
        return redirect(f"http://dashboard.{LAB_DOMAIN}/exports/weekly")
    u = current_user()
    if not u or u.get("role") != "moderator":
        return redirect(f"http://portal.{LAB_DOMAIN}/login")

    source = (request.args.get("sourceUrl") or "").strip() or f"http://{LAB_DOMAIN}/about"
    parsed = urlparse(source)
    if parsed.scheme not in {"http", "https"}:
        return "Invalid sourceUrl", 400

    try:
        r = requests.get(source, timeout=3, cookies={"qs_token": (_get_token_from_request() or "")})
        content = r.text[:6000]
    except Exception:
        content = "Renderer error."

    resp = make_response(f"Quarter Shift Weekly Report\nGenerated: {now_iso()}\n\n---\n{content}\n")
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = "attachment; filename=weekly-report.pdf"
    return resp


@APP.route("/incidents")
def ops_incidents():
    if surface_from_host(request.host) == "ops":
        if not ops_internal_only() or not ops_require_admin():
            return marketing_home_override()
        return render_template("ops_incidents.html", title="Incidents", surf="ops", domain=LAB_DOMAIN, user=ops_current(), logout_url="/logout", year=datetime.utcnow().year)


@APP.route("/payouts")
def ops_payouts():
    if surface_from_host(request.host) == "ops":
        if not ops_internal_only() or not ops_require_admin():
            return marketing_home_override()
        return render_template("ops_payouts.html", title="Payouts", surf="ops", domain=LAB_DOMAIN, user=ops_current(), logout_url="/logout", year=datetime.utcnow().year)


@APP.route("/incidents/jackpot/download")
def ops_jackpot_download():
    if surface_from_host(request.host) == "ops":
        if not ops_internal_only() or not ops_require_admin():
            return marketing_home_override()

        report = f"""\
QUARTER SHIFT - JACKPOT INCIDENT REPORT
Case: J-2026-021
Generated: {now_iso()}

Summary:
A settlement reconciliation job detected repeated edge-cache hits on a kiosk-only tournament endpoint.
The issue presented as sporadic "phantom moderator sessions" during peak traffic.

Impact:
- Unintended disclosure of a limited credential artifact through shared cache keys.
- Elevated risk of unauthorized moderator actions.

Corrective Actions:
- Enforce cache Vary policies for access-tier headers.
- Remove reset-code fields from all API responses.
- Harden JWT verification, explicitly rejecting 'alg':'none'.

Closing Note:
Some doors aren't locked - they're just waiting for the right angle.

FLAG: {FLAG}
"""

        resp = make_response(report)
        resp.headers["Content-Type"] = "application/pdf"
        resp.headers["Content-Disposition"] = "attachment; filename=jackpot-incident-report.pdf"
        return resp


if __name__ == "__main__":
    init_db()
    APP.run(host="0.0.0.0", port=80, debug=False)
