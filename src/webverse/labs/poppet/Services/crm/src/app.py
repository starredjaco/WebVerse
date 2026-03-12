import os, re, jwt, pymysql, hashlib
from functools import wraps
from datetime import date
from flask import Flask, render_template, request, redirect, make_response, jsonify

app = Flask(__name__, static_folder='../Static', static_url_path='/Static', template_folder='../Templates')
JWT_SECRET_KEY = os.environ.get('JWT_SECRET', 'toystory2')

# ── Content validation for employee records ──
# Added after internal audit flagged template injection risk in free-text fields.
# Blocks dangerous patterns while allowing standard business text.
FIELD_BLOCKED_PATTERNS = [
    '__',               # dunder access
    '[', ']',           # bracket notation
    'config',           # Flask config
    'self',             # self reference
    'class',            # class traversal
    'mro',              # method resolution order
    'subclasses',       # subclass enumeration
    'globals',          # global namespace
    'builtins',         # builtin functions
    'import',           # module import
    'popen',            # process open
    'system',           # os.system
    'eval',             # eval execution
    'exec',             # exec execution
    'getattr',          # attribute access
    'subprocess',       # subprocess module
    'lipsum',           # Jinja2 global
    'cycler',           # Jinja2 global
    'joiner',           # Jinja2 global
    'namespace',        # Jinja2 global
    'range',            # Jinja2 global
    'request',          # Flask request
    'session',          # Flask session
]

def validate_employee_field(value):
    """Returns None if clean, or the matched pattern."""
    val_lower = value.lower()
    for p in FIELD_BLOCKED_PATTERNS:
        if p.lower() in val_lower:
            return p
    return None

def get_db():
    return pymysql.connect(host=os.environ.get('DB_HOST', 'db'), user=os.environ.get('DB_USER', 'crm_svc'),
        password=os.environ.get('DB_PASSWORD', 'CrmSvc#2024!'), database=os.environ.get('DB_NAME', 'crm_db'),
        cursorclass=pymysql.cursors.DictCursor)

def get_current_user():
    token = request.cookies.get('token')
    if not token: return None
    try: return jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
    except Exception: return None

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user: return redirect('/login')
        return f(user=user, *args, **kwargs)
    return decorated

def sidebar_context():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as c FROM deals WHERE stage NOT IN ('won','lost')"); oc = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) as c FROM tasks WHERE status='open'"); tc = cur.fetchone()['c']
    finally: conn.close()
    return {'deal_counts': {'open': oc}, 'task_count': tc}

# ═══ AUTH ═══
@app.route('/')
def index(): return redirect('/dashboard') if get_current_user() else redirect('/login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u, p = request.form.get('username', ''), request.form.get('password', '')
        p_hash = hashlib.sha256(p.encode()).hexdigest()
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT id, username, full_name, role, department FROM crm_users WHERE username=%s AND password=%s', (u, p_hash))
                user = cur.fetchone()
        finally: conn.close()
        if user:
            token = jwt.encode({'user_id': user['id'], 'username': user['username'], 'role': user['role'], 'department': user['department']}, JWT_SECRET_KEY, algorithm='HS256')
            resp = make_response(redirect('/dashboard'))
            resp.set_cookie('token', token, httponly=True)
            return resp
        return render_template('login.html', error='Invalid credentials.')
    return render_template('login.html')

@app.route('/logout')
def logout():
    resp = make_response(redirect('/login')); resp.delete_cookie('token'); return resp

# ═══ DASHBOARD ═══
@app.route('/dashboard')
@login_required
def dashboard(user):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) as c FROM contacts'); cc = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) as c FROM contacts WHERE status='active'"); ac = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) as c FROM deals WHERE stage NOT IN ('won','lost')"); od = cur.fetchone()['c']
            cur.execute("SELECT COALESCE(SUM(value),0) as v FROM deals WHERE stage NOT IN ('won','lost')"); pv = float(cur.fetchone()['v'] or 0)
            cur.execute("SELECT COUNT(*) as c FROM tasks WHERE status='open'"); ot = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) as c FROM tasks WHERE status='open' AND due_date < CURDATE()"); ovt = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) as c FROM cases WHERE status='open'"); occ = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) as c FROM cases WHERE status='open' AND priority='high'"); hc = cur.fetchone()['c']
            cur.execute('SELECT * FROM activity_log ORDER BY created_at DESC LIMIT 8'); activity = cur.fetchall()
            cur.execute('SELECT * FROM tasks WHERE status=%s ORDER BY due_date ASC LIMIT 6', ('open',)); tasks = cur.fetchall()
    finally: conn.close()
    stats = {'contacts': cc, 'active_contacts': ac, 'open_deals': od, 'pipeline_value': pv, 'open_tasks': ot, 'overdue_tasks': ovt, 'open_cases': occ, 'high_cases': hc}
    return render_template('dashboard.html', user=user, stats=stats, activity=activity, tasks=tasks, active='dash', **sidebar_context())

# ═══ CONTACTS ═══
@app.route('/contacts')
@login_required
def contacts(user):
    q = request.args.get('q', '')
    sf = request.args.get('status', '')
    conn = get_db()
    try:
        with conn.cursor() as cur:
            base = 'SELECT c.*, u.full_name as assigned_name FROM contacts c LEFT JOIN crm_users u ON c.assigned_to=u.id'
            conds, params = [], []
            if q: conds.append('(c.name LIKE %s OR c.company LIKE %s)'); params += [f'%{q}%', f'%{q}%']
            if sf: conds.append('c.status=%s'); params.append(sf)
            where = ' WHERE ' + ' AND '.join(conds) if conds else ''
            cur.execute(base + where + ' ORDER BY c.created_at DESC', params)
            cl = cur.fetchall()
    finally: conn.close()
    return render_template('contacts.html', user=user, contacts=cl, query=q, status_filter=sf, active='contacts', **sidebar_context())

@app.route('/contacts/<int:cid>')
@login_required
def contact_detail(user, cid):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT c.*, u.full_name as assigned_name FROM contacts c LEFT JOIN crm_users u ON c.assigned_to=u.id WHERE c.id=%s', (cid,))
            contact = cur.fetchone()
            if not contact: return 'Contact not found', 404
            cur.execute('SELECT d.*, u.full_name as assigned_name FROM deals d LEFT JOIN crm_users u ON d.assigned_to=u.id WHERE d.contact_id=%s ORDER BY d.created_at DESC', (cid,))
            deals = cur.fetchall()
            cur.execute("SELECT * FROM activity_log WHERE entity_type='contact' AND entity_id=%s ORDER BY created_at DESC LIMIT 10", (cid,))
            activity = cur.fetchall()
            cur.execute("SELECT ca.*, u.full_name as assigned_name FROM cases ca LEFT JOIN crm_users u ON ca.assigned_to=u.id WHERE ca.contact_id=%s AND ca.status='open' ORDER BY ca.created_at DESC", (cid,))
            cases = cur.fetchall()
    finally: conn.close()
    return render_template('contact_detail.html', user=user, contact=contact, deals=deals, activity=activity, cases=cases, active='contacts', **sidebar_context())

# ═══ PIPELINE ═══
@app.route('/pipeline')
@login_required
def pipeline(user):
    stage_defs = [('inquiry', 'Inquiry'), ('proposal', 'Proposal'), ('negotiation', 'Negotiation'), ('won', 'Won'), ('lost', 'Lost')]
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT d.*, c.name as contact_name, u.full_name as assigned_name FROM deals d JOIN contacts c ON d.contact_id=c.id LEFT JOIN crm_users u ON d.assigned_to=u.id ORDER BY d.created_at DESC')
            all_deals = cur.fetchall()
    finally: conn.close()
    stages = []
    total_value = 0
    for key, label in stage_defs:
        stage_deals = [d for d in all_deals if d['stage'] == key]
        stages.append({'key': key, 'label': label, 'deals': stage_deals})
        for d in stage_deals: total_value += float(d['value'] or 0)
    return render_template('pipeline.html', user=user, stages=stages, total_deals=len(all_deals), total_value=total_value, active='pipeline', **sidebar_context())

@app.route('/pipeline/<int:did>')
@login_required
def deal_detail(user, did):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT d.*, c.name as contact_name, u.full_name as assigned_name FROM deals d JOIN contacts c ON d.contact_id=c.id LEFT JOIN crm_users u ON d.assigned_to=u.id WHERE d.id=%s', (did,))
            deal = cur.fetchone()
            if not deal: return 'Deal not found', 404
            cur.execute('SELECT t.*, u.full_name as assigned_name FROM tasks t LEFT JOIN crm_users u ON t.assigned_to=u.id WHERE t.deal_id=%s ORDER BY t.due_date', (did,))
            tasks = cur.fetchall()
    finally: conn.close()
    return render_template('deal_detail.html', user=user, deal=deal, tasks=tasks, active='pipeline', **sidebar_context())

# ═══ EMPLOYEES (CHAIN CRITICAL) ═══
@app.route('/employees')
@login_required
def employees(user):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT id, full_name, department, email, hire_date FROM employees ORDER BY full_name')
            el = cur.fetchall()
    finally: conn.close()
    return render_template('employees.html', user=user, employees=el, active='emp', **sidebar_context())

@app.route('/employees/<int:eid>')
@login_required
def employee_detail(user, eid):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT id, full_name, email, department, job_description, salary, hire_date, notes FROM employees WHERE id=%s', (eid,))
            emp = cur.fetchone()
    finally: conn.close()
    if not emp: return 'Employee not found', 404
    return render_template('employee_detail.html', user=user, employee=emp, active='emp', **sidebar_context())

@app.route('/employees/<int:eid>/edit', methods=['GET', 'POST'])
@login_required
def employee_edit(user, eid):
    if user['role'] not in ('manager', 'admin'): return redirect('/employees')
    msg, error = None, None
    conn = get_db()
    try:
        with conn.cursor() as cur:
            if request.method == 'POST':
                fn = request.form.get('full_name', '')
                dep = request.form.get('department', '')
                em = request.form.get('email', '')
                jd = request.form.get('job_description', '')
                # Validate all text fields
                for field_name, field_val in [('full_name', fn), ('email', em), ('job_description', jd)]:
                    violation = validate_employee_field(field_val)
                    if violation:
                        app.logger.warning('Content policy violation in %s: pattern=%s user=%s', field_name, violation, user['username'])
                        error = 'Content validation failed. The text contains characters or patterns that are not permitted in employee records. Please use standard business language only.'
                        break
                if not error:
                    cur.execute('UPDATE employees SET full_name=%s, department=%s, email=%s, job_description=%s WHERE id=%s', (fn, dep, em, jd, eid))
                    conn.commit()
                    msg = 'Employee record updated.'
            cur.execute('SELECT id, full_name, email, department, job_description, salary, hire_date, notes FROM employees WHERE id=%s', (eid,))
            emp = cur.fetchone()
    finally: conn.close()
    if not emp: return 'Employee not found', 404
    return render_template('employee_edit.html', user=user, employee=emp, message=msg, error=error, active='emp', **sidebar_context())

# ═══ TASKS ═══
@app.route('/tasks')
@login_required
def tasks(user):
    sf = request.args.get('status', '')
    conn = get_db()
    try:
        with conn.cursor() as cur:
            base = 'SELECT t.*, u.full_name as assigned_name, c.name as contact_name FROM tasks t LEFT JOIN crm_users u ON t.assigned_to=u.id LEFT JOIN contacts c ON t.contact_id=c.id'
            if sf: cur.execute(base + ' WHERE t.status=%s ORDER BY t.due_date ASC', (sf,))
            else: cur.execute(base + ' ORDER BY t.status ASC, t.due_date ASC')
            tl = cur.fetchall()
    finally: conn.close()
    today = date.today()
    for t in tl: t['overdue'] = t['status'] == 'open' and t.get('due_date') and t['due_date'] < today
    return render_template('tasks.html', user=user, tasks=tl, status_filter=sf, active='tasks', **sidebar_context())

# ═══ CASES ═══
@app.route('/cases')
@login_required
def cases(user):
    sf = request.args.get('status', '')
    conn = get_db()
    try:
        with conn.cursor() as cur:
            base = 'SELECT ca.*, c.name as contact_name, u.full_name as assigned_name FROM cases ca JOIN contacts c ON ca.contact_id=c.id LEFT JOIN crm_users u ON ca.assigned_to=u.id'
            if sf: cur.execute(base + ' WHERE ca.status=%s ORDER BY ca.created_at DESC', (sf,))
            else: cur.execute(base + ' ORDER BY ca.created_at DESC')
            cl = cur.fetchall()
    finally: conn.close()
    return render_template('cases.html', user=user, cases=cl, status_filter=sf, active='cases', **sidebar_context())

@app.route('/cases/<int:cid>')
@login_required
def case_detail(user, cid):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT ca.*, c.name as contact_name, u.full_name as assigned_name FROM cases ca JOIN contacts c ON ca.contact_id=c.id LEFT JOIN crm_users u ON ca.assigned_to=u.id WHERE ca.id=%s', (cid,))
            case = cur.fetchone()
    finally: conn.close()
    if not case: return 'Case not found', 404
    return render_template('case_detail.html', user=user, case=case, active='cases', **sidebar_context())

# ═══ ACTIVITY ═══
@app.route('/activity')
@login_required
def activity(user):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM activity_log ORDER BY created_at DESC LIMIT 50')
            al = cur.fetchall()
    finally: conn.close()
    return render_template('activity.html', user=user, activity=al, active='activity', **sidebar_context())

# ═══ REPORTS ═══
@app.route('/reports')
@login_required
def reports(user):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT COALESCE(SUM(value),0) as v FROM deals'); pt = float(cur.fetchone()['v'] or 0)
            cur.execute("SELECT COALESCE(SUM(value),0) as v FROM deals WHERE stage='won'"); wt = float(cur.fetchone()['v'] or 0)
            cur.execute("SELECT COUNT(*) as c FROM deals WHERE stage='won'"); wc = cur.fetchone()['c']
            cur.execute('SELECT COUNT(*) as c FROM deals'); tc = cur.fetchone()['c']
            wr = (wc / tc * 100) if tc > 0 else 0
            cur.execute("SELECT stage, COUNT(*) as count, COALESCE(SUM(value),0) as value FROM deals GROUP BY stage ORDER BY FIELD(stage,'inquiry','proposal','negotiation','won','lost')")
            sb = cur.fetchall()
            for s in sb: s['value'] = float(s['value'] or 0)
            cur.execute('SELECT c.name, COUNT(d.id) as deals, COALESCE(SUM(d.value),0) as value FROM deals d JOIN contacts c ON d.contact_id=c.id GROUP BY c.id ORDER BY value DESC LIMIT 5')
            ta = cur.fetchall()
            for a in ta: a['value'] = float(a['value'] or 0)
    finally: conn.close()
    return render_template('reports.html', user=user, pipeline_total=pt, won_total=wt, won_count=wc, win_rate=wr, stage_breakdown=sb, top_accounts=ta, active='reports', **sidebar_context())

# ═══ SETTINGS ═══
@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings(user):
    import json as _json
    prefs_default = {'email_new_deal': True, 'email_case': True, 'email_task': True, 'weekly_digest': False}
    msg = None
    try: prefs = _json.loads(request.cookies.get('crm_prefs', '{}'))
    except Exception: prefs = {}
    prefs = {**prefs_default, **prefs}
    if request.method == 'POST':
        prefs = {k: (k in request.form) for k in prefs_default}
        msg = 'Notification preferences saved.'
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT username, full_name, role, department FROM crm_users ORDER BY id')
            users = cur.fetchall()
    finally: conn.close()
    resp = make_response(render_template('settings.html', user=user, users=users, prefs=prefs, message=msg, active='settings', **sidebar_context()))
    if request.method == 'POST':
        resp.set_cookie('crm_prefs', _json.dumps(prefs), httponly=True, max_age=60*60*24*365)
    return resp

if __name__ == '__main__': app.run(host='0.0.0.0', port=5000)