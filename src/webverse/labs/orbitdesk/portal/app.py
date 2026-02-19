import os, json
from flask import Flask, render_template, redirect

app = Flask(__name__)
LAB_DOMAIN = os.getenv("LAB_DOMAIN", "orbitdesk.local")

lab_json = json.dumps({
    "LAB_DOMAIN": LAB_DOMAIN,
    "AUTH_BASE": os.getenv("AUTH_BASE", f"http://auth.{LAB_DOMAIN}"),
    "API_BASE": os.getenv("API_BASE", f"http://api.{LAB_DOMAIN}"),
    "FILES_BASE": os.getenv("FILES_BASE", f"http://files.{LAB_DOMAIN}"),
})

@app.get("/")
def home():
    return redirect("/login", code=302)

@app.get("/login")
def login():
    return render_template("login.html", lab_domain=LAB_DOMAIN, lab_json=lab_json, title="Sign in • OrbitDesk")

@app.get("/register")
def register():
    return render_template("register.html", lab_domain=LAB_DOMAIN, lab_json=lab_json, title="Create account • OrbitDesk")

@app.get("/app")
def app_page():
    return render_template("app.html", lab_domain=LAB_DOMAIN, lab_json=lab_json, title="Workspace • OrbitDesk")

@app.get("/app/documents")
def documents():
    return render_template("documents.html", lab_domain=LAB_DOMAIN, lab_json=lab_json, title="Documents • OrbitDesk")

@app.get("/app/integrations")
def integrations():
    return render_template("integrations.html", lab_domain=LAB_DOMAIN, lab_json=lab_json, title="Integrations • OrbitDesk")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
