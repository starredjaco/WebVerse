/* global __LAB */
const Portal = (() => {
  const state = {
    token: localStorage.getItem("od_token") || "",
    projectId: localStorage.getItem("od_last_project") || "",
  };

  function showNotice(msg, kind="") {
    const el = document.getElementById("notice");
    if (!el) return;
    el.style.display = "block";
    el.className = "notice" + (kind ? " " + kind : "");
    el.textContent = msg;
  }

  function getJwtPayload() {
    try {
      const parts = state.token.split(".");
      if (parts.length < 2) return null;
      const json = atob(parts[1].replace(/-/g, "+").replace(/_/g, "/"));
      return JSON.parse(json);
    } catch {
      return null;
    }
  }

  async function apiFetch(url, opts={}) {
    const headers = Object.assign({}, opts.headers || {});
    if (state.token) headers["Authorization"] = "Bearer " + state.token;
    if (opts.json) {
      headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(opts.json);
    }
    const res = await fetch(url, Object.assign({}, opts, { headers }));
    const text = await res.text();
    let data = null;
    try { data = JSON.parse(text); } catch { data = text; }
    if (!res.ok) {
      const msg = (data && data.error) ? data.error : (typeof data === "string" ? data : "Request failed");
      throw new Error(msg);
    }
    return data;
  }

  function updateNav() {
    const signIn = document.getElementById("navSignIn");
    const create = document.getElementById("navCreate");
    const ws = document.getElementById("navWorkspace");
    const out = document.getElementById("navSignOut");
    const hasToken = !!state.token;

    if (signIn) signIn.style.display = hasToken ? "none" : "";
    if (create) create.style.display = hasToken ? "none" : "";
    if (ws) ws.style.display = hasToken ? "" : "none";
    if (out) out.style.display = hasToken ? "" : "none";

    // Brand goes to /app when signed in, /login when signed out
    const brand = document.getElementById("brandLink");
    if (brand) brand.setAttribute("href", hasToken ? "/app" : "/login");

    // Bind signout once
    if (out && !out.__bound) {
      out.__bound = true;
      out.addEventListener("click", (e) => {
        e.preventDefault();
        logout();
      });
    }
  }

  async function login() {
    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;
    try {
      const data = await apiFetch(__LAB.AUTH_BASE + "/api/v1/auth/login", { method:"POST", json:{ email, password }});
      const token = data.token;
      state.token = token;
      localStorage.setItem("od_token", token);
      setSharedAuthCookie(token);
      window.location.href = "/app";
    } catch (e) {
      showNotice(e.message, "bad");
    }
  }

  function setSharedAuthCookie(token) {
    // Cross-subdomain session: cookie visible to *.orbitdesk.local AND orbitdesk.local
    // Host-only cookies won't work here, so we explicitly set Domain=.<LAB_DOMAIN>.
    const domain = __LAB.LAB_DOMAIN || "orbitdesk.local";
    // 7 days
    const maxAge = 60 * 60 * 24 * 7;
    // Lax so navigation works; no Secure since you're using http in the lab
    document.cookie =
      `od_token=${encodeURIComponent(token)}; ` +
      `Domain=.${domain}; Path=/; Max-Age=${maxAge}; SameSite=Lax`;
  }

  function clearSharedAuthCookie() {
    const domain = __LAB.LAB_DOMAIN || "orbitdesk.local";
    document.cookie =
      `od_token=; Domain=.${domain}; Path=/; Max-Age=0; SameSite=Lax`;
  }

  async function register() {
    const name = document.getElementById("name").value.trim();
    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;
    try {
      await apiFetch(__LAB.AUTH_BASE + "/api/v1/auth/register", { method:"POST", json:{ name, email, password }});
      showNotice("Account created. Signing you in…", "ok");
      setTimeout(login, 350);
    } catch (e) {
      showNotice(e.message, "bad");
    }
  }

  function logout() {
    localStorage.removeItem("od_token");
    state.token = "";
    clearSharedAuthCookie();
    window.location.href = "/login";
  }

  async function loadApp() {
    if (!state.token) { window.location.href="/login"; return; }
  try {
    const me = await apiFetch(__LAB.API_BASE + "/api/v1/me");
    const meEl = document.getElementById("me");
    if (meEl) meEl.className="notice ok", meEl.textContent = `Signed in as ${me.email} (${me.role})`;

    const list = await apiFetch(__LAB.API_BASE + "/api/v1/projects");
    const rows = (list.items || []);
    const tbody = document.querySelector("#projects tbody");
    if (tbody) {
      tbody.innerHTML = "";
      rows.forEach(p => {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td><a href="#" class="plink" data-pid="${p.id}">${escapeHtml(p.name)}</a></td><td class="code">${escapeHtml(p.id)}</td><td>${escapeHtml(p.owner.email)}</td><td><button class="btn sm" data-open="${p.id}">Open</button></td>`;
        tbody.appendChild(tr);
      });

      tbody.querySelectorAll("[data-open]").forEach(btn => {
        btn.addEventListener("click", (e) => {
          e.preventDefault();
          const pid = btn.getAttribute("data-open");
          openProject(pid);
        });
      });
      tbody.querySelectorAll("[data-pid]").forEach(a => {
        a.addEventListener("click", (e) => {
          e.preventDefault();
          openProject(a.getAttribute("data-pid"));
        });
      });
    }

    // auto-open last project if remembered
    const last = localStorage.getItem("od_last_project");
    if (last) {
      const exists = rows.find(r => r.id === last);
      if (exists) openProject(last);
    }
  } catch (e) {
    const meEl = document.getElementById("me");
    if (meEl) meEl.className="notice bad", meEl.textContent = e.message;
  }
}

function escapeHtml(s) {
  return String(s || "").replace(/[&<>"']/g, (c) => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
}

async function openProject(projectId) {
  state.projectId = projectId;
  localStorage.setItem("od_last_project", projectId);
  const panel = document.getElementById("projectPanel");
  if (panel) panel.style.display = "block";
  await refreshProject();
}

async function refreshProject() {
  if (!state.projectId) return;
  const pid = state.projectId;

  const p = await apiFetch(__LAB.API_BASE + `/api/v1/projects/${encodeURIComponent(pid)}`);
  document.getElementById("pName").textContent = p.project.name;
  document.getElementById("pId").textContent = p.project.id;

  const members = await apiFetch(__LAB.API_BASE + `/api/v1/projects/${encodeURIComponent(pid)}/members`);
  const mEl = document.getElementById("membersList");
  if (mEl) {
    mEl.innerHTML = members.items.map(x => `<div class="row" style="justify-content:space-between;gap:10px"><span>${escapeHtml(x.email)}</span><span class="badge">${escapeHtml(x.memberRole)}</span></div>`).join("");
    if (!members.items.length) mEl.textContent = "No members found.";
  }

  const tasks = await apiFetch(__LAB.API_BASE + `/api/v1/projects/${encodeURIComponent(pid)}/tasks`);
  const tEl = document.getElementById("tasksList");
  if (tEl) {
    tEl.innerHTML = (tasks.items || []).map(t => `
      <div class="task">
        <div class="row" style="justify-content:space-between;gap:10px;align-items:flex-start">
          <div>
            <div class="task-title">${escapeHtml(t.title)}</div>
            <div class="task-meta">${escapeHtml(t.status)} • ${escapeHtml(t.priority)}${t.dueDate ? " • due " + escapeHtml(t.dueDate) : ""}</div>
          </div>
          <select class="input sm" data-task="${t.id}">
            <option value="open"${t.status==="open"?" selected":""}>Open</option>
            <option value="in_progress"${t.status==="in_progress"?" selected":""}>In progress</option>
            <option value="blocked"${t.status==="blocked"?" selected":""}>Blocked</option>
            <option value="done"${t.status==="done"?" selected":""}>Done</option>
          </select>
        </div>
      </div>
    `).join("") || `<div class="p">No tasks yet.</div>`;

    tEl.querySelectorAll("[data-task]").forEach(sel => {
      sel.addEventListener("change", async () => {
        const tid = sel.getAttribute("data-task");
        await apiFetch(__LAB.API_BASE + `/api/v1/projects/${encodeURIComponent(pid)}/tasks/${encodeURIComponent(tid)}`, { method:"PATCH", json:{ status: sel.value }});
      });
    });
  }

  const updates = await apiFetch(__LAB.API_BASE + `/api/v1/projects/${encodeURIComponent(pid)}/updates`);
  const uEl = document.getElementById("updatesList");
  if (uEl) {
    uEl.innerHTML = (updates.items || []).map(u => `
      <div class="update">
        <div class="update-title">${escapeHtml(u.title)}</div>
        <div class="update-meta">${escapeHtml(u.createdBy.email)} • ${escapeHtml(new Date(u.createdAt).toLocaleString())}</div>
        <div class="update-body">${escapeHtml(u.body).replace(/\n/g,"<br>")}</div>
      </div>
    `).join("") || `<div class="p">No updates yet.</div>`;
  }

  const activity = await apiFetch(__LAB.API_BASE + `/api/v1/projects/${encodeURIComponent(pid)}/activity?limit=25`);
  const aEl = document.getElementById("activityList");
  if (aEl) {
    aEl.innerHTML = (activity.items || []).map(a => `
      <div class="act">
        <div class="act-line"><span class="badge">${escapeHtml(a.action)}</span> ${a.actor ? escapeHtml(a.actor.email) : "system"}</div>
        <div class="act-meta">${escapeHtml(new Date(a.createdAt).toLocaleString())}</div>
      </div>
    `).join("") || `<div class="p">No recent activity.</div>`;
  }
}

async function createProject(ev) {
  ev.preventDefault();
  const form = ev.target;
  const name = form.name.value.trim();
  if (!name) return false;
  await apiFetch(__LAB.API_BASE + "/api/v1/projects", { method:"POST", json:{ name }});
  form.reset();
  await loadApp();
  return false;
}

async function inviteMember(ev) {
  ev.preventDefault();
  const form = ev.target;
  if (!state.projectId) return false;
  await apiFetch(__LAB.API_BASE + `/api/v1/projects/${encodeURIComponent(state.projectId)}/members`, { method:"POST", json:{ email: form.email.value.trim(), memberRole: form.memberRole.value }});
  form.reset();
  await refreshProject();
  return false;
}

async function createTask(ev) {
  ev.preventDefault();
  const form = ev.target;
  if (!state.projectId) return false;
  await apiFetch(__LAB.API_BASE + `/api/v1/projects/${encodeURIComponent(state.projectId)}/tasks`, { method:"POST", json:{ title: form.title.value.trim(), priority: form.priority.value, dueDate: form.dueDate.value.trim() }});
  form.reset();
  await refreshProject();
  return false;
}

async function createUpdate(ev) {
  ev.preventDefault();
  const form = ev.target;
  if (!state.projectId) return false;
  await apiFetch(__LAB.API_BASE + `/api/v1/projects/${encodeURIComponent(state.projectId)}/updates`, { method:"POST", json:{ title: form.title.value.trim(), body: form.body.value }});
  form.reset();
  await refreshProject();
  return false;
}

function closeProject() {
  state.projectId = "";
  localStorage.removeItem("od_last_project");
  const panel = document.getElementById("projectPanel");
  if (panel) panel.style.display = "none";
}

  async function loadDocs() {
    if (!state.token) { window.location.href="/login"; return; }
    const table = document.getElementById("docs");
    const tbody = table ? table.querySelector("tbody") : null;
    const notice = document.getElementById("notice");

    function setNotice(msg, kind="") {
      if (!notice) return;
      notice.style.display = msg ? "block" : "none";
      notice.className = "notice" + (kind ? " " + kind : "");
      notice.textContent = msg || "";
    }

    function clearRows() {
      if (tbody) tbody.innerHTML = "";
    }
    try {
      // Client-side gate: customers ("user" role) should not even attempt GraphQL.
      const payload = getJwtPayload() || {};
      const role = (payload.role || "").toLowerCase();
      const isEmployeeOrAdmin = role === "employee" || role === "admin";

      if (!isEmployeeOrAdmin) {
        clearRows();
        setNotice(
          "This customer workspace can’t access OrbitDesk’s internal documents directory. " +
          "Documents are available to staff accounts only.",
          "bad"
        );
        return;
      }

      setNotice("", "");

      // 1) fetch projects visible to this account
      const qProjects = `query{ myProjects { id name } }`;
      const projResp = await apiFetch(__LAB.API_BASE + "/graphql", { method:"POST", json:{ query:qProjects }});
      const projects = (projResp && projResp.data && projResp.data.myProjects) ? projResp.data.myProjects : [];
      if (!projects.length) {
        clearRows();
        setNotice("No projects are available for this account.", "bad");
        return;
      }

      // 2) for each project, fetch docs + the project-scoped documentsApiKey
      const rows = [];
      for (const p of projects) {
        const q = `query($id:ID!){
          project(id:$id){ id name documentsApiKey }
          documents(projectId:$id){ id filename fileId createdAt }
        }`;
        const data = await apiFetch(__LAB.API_BASE + "/graphql", { method:"POST", json:{ query:q, variables:{ id: p.id } }});
        const proj = data && data.data ? data.data.project : null;
        const docs = data && data.data ? (data.data.documents || []) : [];
        if (!proj) continue;

        for (const d of docs) {
          rows.push({
            projectId: proj.id,
            projectName: proj.name,
            documentsApiKey: proj.documentsApiKey,
            docId: d.id,
            filename: d.filename,
            fileId: d.fileId,
            createdAt: d.createdAt
          });
        }
      }

      if (!rows.length) {
        clearRows();
        setNotice("No documents are available yet for your staff workspace.", "");
        return;
      }

      // helper: request a signed share URL from the files service
      async function getShareUrl(documentsApiKey, fileId) {
        const headers = { "X-Documents-Key": documentsApiKey };
        const res = await fetch(__LAB.FILES_BASE + "/api/v1/share", {
          method: "POST",
          headers: Object.assign({ "Content-Type": "application/json" }, headers),
          body: JSON.stringify({ fileId })
        });
        const text = await res.text();
        let data = null;
        try { data = JSON.parse(text); } catch { data = { error: text }; }
        if (!res.ok) {
          const msg = data && data.error ? data.error : "Failed to create share link";
          throw new Error(msg);
        }
        return data.url;
      }

      // 3) render table + mint download links
      clearRows();

      // keep UI responsive while we mint URLs
      for (const r of rows) {
        const tr = document.createElement("tr");

        const created = r.createdAt ? new Date(r.createdAt).toLocaleString() : "—";

        tr.innerHTML = `
          <td>
            <div style="font-weight:700">${escapeHtml(r.filename)}</div>
          </td>
          <td class="code">${escapeHtml(r.fileId)}</td>
          <td class="small">${escapeHtml(created)}</td>
          <td><span class="small">Generating…</span></td>
        `;
        tbody.appendChild(tr);

        // Mint share URL (per row), then patch the action cell
        try {
          const url = await getShareUrl(r.documentsApiKey, r.fileId);
          const a = document.createElement("a");
          a.className = "btn sm";
          a.href = url;
          a.target = "_blank";
          a.rel = "noopener";
          a.textContent = "Download";
          tr.children[3].innerHTML = "";
          tr.children[3].appendChild(a);
        } catch (e) {
          tr.children[3].innerHTML = `<span class="small" style="color:#b00">${escapeHtml(e.message)}</span>`;
        }
      }
    } catch (e) {
      clearRows();
      // Friendlier messaging if GraphQL rejects access for some reason.
      const msg = (e && e.message) ? e.message : "Request failed";
      if (msg.toLowerCase().includes("forbidden")) {
        setNotice("This workspace doesn’t have access to the internal documents directory.", "bad");
      } else {
        setNotice(msg, "bad");
      }
    }
  }

  async function loadIntegrations() {
    if (!state.token) { window.location.href="/login"; return; }
    const gate = document.getElementById("gate");
    const panel = document.getElementById("panel");
    const payload = getJwtPayload() || {};
    const isAdmin = payload.role === "admin" || (payload.scopes || "").includes("ops:");
    if (!isAdmin) {
      gate.className="notice";
      gate.textContent="This section is available for Enterprise workspaces (admin access required).";
      return;
    }
    gate.style.display="none";
    panel.style.display="block";
  }

  async function testWebhook() {
    const result = document.getElementById("result");
    try {
      const url = document.getElementById("hookUrl").value.trim();
      const method = document.getElementById("hookMethod").value;
      const headersRaw = document.getElementById("hookHeaders").value.trim() || "{}";
      const body = document.getElementById("hookBody").value;
      let headers = {};
      try { headers = JSON.parse(headersRaw); } catch { headers = {}; }
      const data = await apiFetch(__LAB.API_BASE + "/api/v2/integrations/test", { method:"POST", json:{ url, method, headers, body }});
      result.className="notice ok";
      result.textContent = JSON.stringify(data, null, 2);
    } catch (e) {
      result.className="notice bad";
      result.textContent = e.message;
    }
  }

  return { login, register, logout, createProject,
    inviteMember,
    createTask,
    createUpdate,
    refreshProject,
    closeProject,
    loadApp, loadDocs, loadIntegrations, testWebhook, updateNav };
})();

document.addEventListener("DOMContentLoaded", () => {
  try { Portal.updateNav(); } catch {}
  
  const path = window.location.pathname;
  if (path === "/app") Portal.loadApp();
  if (path === "/app/documents") Portal.loadDocs();
  if (path === "/app/integrations") Portal.loadIntegrations();
});
