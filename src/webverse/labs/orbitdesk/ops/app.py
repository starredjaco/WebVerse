import os, time, subprocess
from flask import Flask, request, render_template, Response
import jwt

app = Flask(__name__)

LAB_DOMAIN = os.getenv("LAB_DOMAIN", "orbitdesk.local")
AUTH_SECRET = os.getenv("AUTH_SECRET", "dev-secret")
FLAG = os.getenv("FLAG", "WEBVERSE{dev_flag}")
TRUST_NET_PREFIX = os.getenv("TRUST_NET_PREFIX", "10.77.0.")

def ensure_flag():
    path = "/root/flag.txt"
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(FLAG + "\n")
        os.chmod(path, 0o600)

def _trusted():
    # Trust policy:
    # - request appears to originate from bridge subnet (server-to-server)
    # - and is marked internal by a proxy header (set by internal systems)
    ip = request.headers.get("X-Real-IP") or request.remote_addr or ""
    internal = request.headers.get("X-Internal-Request") == "1"
    forwarded_host = request.headers.get("X-Forwarded-Host") or ""
    # Host-binding is common for internal gateways
    host_ok = forwarded_host.endswith(f".{LAB_DOMAIN}") or forwarded_host == LAB_DOMAIN
    return ip.startswith(TRUST_NET_PREFIX) and internal and host_ok

def _claims():
    auth = request.headers.get("Authorization","")
    if not auth.startswith("Bearer "):
        return None
    token = auth.split(" ",1)[1].strip()
    try:
        return jwt.decode(token, AUTH_SECRET, algorithms=["HS256"])
    except Exception:
        return None

def _admin(claims):
    return claims and (claims.get("role") == "admin" or "ops:admin" in (claims.get("scopes") or ""))

@app.before_request
def boot():
    ensure_flag()

@app.get("/")
def root():
    if not _trusted():
        return render_template("denied.html", lab_domain=LAB_DOMAIN), 403
    return render_template("internal.html", lab_domain=LAB_DOMAIN)

@app.get("/internal")
def internal():
    if not _trusted():
        return render_template("denied.html", lab_domain=LAB_DOMAIN), 403
    return render_template("internal.html", lab_domain=LAB_DOMAIN)

@app.get("/internal/diagnostics")
def diagnostics():
    if not _trusted():
        return render_template("denied.html", lab_domain=LAB_DOMAIN), 403
    return render_template("diagnostics.html", lab_domain=LAB_DOMAIN)

@app.post("/internal/probe")
def probe():
    if not _trusted():
        return Response("forbidden\n", status=403, mimetype="text/plain")
    claims = _claims()
    if not _admin(claims):
        return Response("forbidden\n", status=403, mimetype="text/plain")

    data = request.get_json(force=True, silent=True) or {}
    host = (data.get("host") or "").strip()
    if not host:
        return Response("missing host\n", status=400, mimetype="text/plain")

    # Vulnerable diagnostic call: host is interpolated into a shell command.
    # (This is common when ops tooling gets built quickly for internal use.)
    cmd = f"getent hosts {host}"
    try:
        out = subprocess.check_output(["sh","-c", cmd], stderr=subprocess.STDOUT, timeout=2)
        return Response(out, mimetype="text/plain")
    except subprocess.CalledProcessError as e:
        return Response(e.output or b"error\n", status=500, mimetype="text/plain")
    except Exception:
        return Response(b"error\n", status=500, mimetype="text/plain")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
