import os
import time
import requests
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
LAB_DOMAIN = os.getenv("LAB_DOMAIN", "orbitdesk.local")
API_BASE = os.getenv("API_BASE", f"http://api.{LAB_DOMAIN}")
AUTH_BASE = os.getenv("AUTH_BASE", f"http://auth.{LAB_DOMAIN}")

def _nav_state():
    tok = request.cookies.get("od_token")
    if not tok:
        return {"is_authed": False, "cta_href": f"http://portal.{LAB_DOMAIN}/login", "cta_label": "Sign in"}
    return {"is_authed": True, "cta_href": "http://portal.%s/app" % LAB_DOMAIN, "cta_label": "Dashboard"}

def _fetch_team_list():
    try:
        r = requests.get(f"{AUTH_BASE}/api/v1/public/team", timeout=3)
        if r.status_code == 200:
            return (r.json() or {}).get("items") or []
    except Exception:
        pass
    return []

def _fetch_team_member(user_id: int):
    try:
        r = requests.get(f"{AUTH_BASE}/api/v1/public/team/{user_id}", timeout=3)
        if r.status_code == 200:
            return r.json() or None
    except Exception:
        pass
    return None

@app.get("/")
def index():
    sent = request.args.get("sent") == "1"
    return render_template("index.html", lab_domain=LAB_DOMAIN, sent=sent, title="OrbitDesk", nav=_nav_state())

@app.get("/pricing")
def pricing():
    return render_template("pricing.html", lab_domain=LAB_DOMAIN, title="Pricing • OrbitDesk", nav=_nav_state())

@app.get("/security")
def security():
    return render_template("security.html", lab_domain=LAB_DOMAIN, title="Trust Center • OrbitDesk", nav=_nav_state())

@app.get("/team")
def team_index():
    members = _fetch_team_list()
    return render_template("team_index.html", lab_domain=LAB_DOMAIN, title="Meet the team • OrbitDesk", members=members, nav=_nav_state())

@app.get("/team/<int:user_id>")
def team_member(user_id: int):
    member = _fetch_team_member(user_id)
    if not member:
        return render_template("team_member.html", lab_domain=LAB_DOMAIN, title="Team • OrbitDesk", member=None, nav=_nav_state()), 404
    return render_template("team_member.html", lab_domain=LAB_DOMAIN, title=f"{member.get('name','Team')} • OrbitDesk", member=member, nav=_nav_state())

@app.get("/contact")
def contact_get():
    sent = request.args.get("sent") == "1"
    return render_template("contact.html", lab_domain=LAB_DOMAIN, sent=sent, title="Contact • OrbitDesk", nav=_nav_state())

@app.post("/contact")
def contact_post():
    # Support both form submits and JSON submits so testers can
    # easily see output changes beyond a 302.
    payload = {}
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        name = (payload.get("name") or "").strip()
        email = (payload.get("email") or "").strip()
        message = (payload.get("message") or "").strip()
    else:
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip()
        message = (request.form.get("message") or "").strip()
    try:
        requests.post(f"{API_BASE}/api/v1/contact", json={"name": name, "email": email, "message": message}, timeout=3)
    except Exception:
        # In a local lab, failing silently keeps the UX believable.
        pass
    ticket_id = f"OD-{int(time.time())}"
    return jsonify({
        "ok": True,
        "ticket_id": ticket_id,
        "received": {
            "name": name,
            "email": email,
            "message_len": len(message)
        },
        "message": "Thanks - we received your request."
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
