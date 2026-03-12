import os, pymysql
from flask import Flask, render_template, render_template_string, request, redirect, session

app = Flask(__name__, static_folder='../Static', static_url_path='/Static', template_folder='../Templates')
app.secret_key = os.environ.get('SECRET_KEY', 'payroll-fallback')

def get_db():
    return pymysql.connect(host=os.environ.get('DB_HOST', 'db'), user=os.environ.get('DB_USER', 'payroll_svc'),
        password=os.environ.get('DB_PASSWORD', 'PaySvc#2024!'), database=os.environ.get('DB_NAME', 'payroll_db'),
        cursorclass=pymysql.cursors.DictCursor)

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'payroll_user' not in session: return redirect('/login')
        return f(*args, **kwargs)
    return decorated

def sidebar_ctx():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as c FROM time_off WHERE status='pending'")
            return {'pending_pto': cur.fetchone()['c']}
    finally: conn.close()

# === AUTH ===
@app.route('/')
def index(): return redirect('/dashboard') if 'payroll_user' in session else redirect('/login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u, p = request.form.get('username', ''), request.form.get('password', '')
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT id, username, employee_id, role FROM payroll_users WHERE username=%s AND password=%s', (u, p))
                user = cur.fetchone()
        finally: conn.close()
        if user:
            session['payroll_user'] = user['username']; session['payroll_user_id'] = user['id']
            session['payroll_role'] = user['role']; session['employee_id'] = user['employee_id']
            return redirect('/dashboard')
        return render_template('login.html', error='Invalid credentials.')
    return render_template('login.html')

@app.route('/logout')
def logout(): session.clear(); return redirect('/login')

# === DASHBOARD ===
@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) as c FROM crm_db.employees'); te = cur.fetchone()['c']
            cur.execute('SELECT SUM(salary) as s FROM crm_db.employees'); ts = float(cur.fetchone()['s'] or 0)
            cur.execute('SELECT COUNT(DISTINCT department) as d FROM crm_db.employees'); dep = cur.fetchone()['d']
            cur.execute("SELECT COUNT(*) as c FROM time_off WHERE status='pending'"); pp = cur.fetchone()['c']
            cur.execute('SELECT * FROM pay_runs ORDER BY period_start DESC LIMIT 3'); runs = cur.fetchall()
            cur.execute("SELECT * FROM time_off WHERE status IN ('approved','pending') AND end_date >= CURDATE() ORDER BY start_date LIMIT 5"); pto = cur.fetchall()
    finally: conn.close()
    stats = {'employees': te, 'monthly_gross': ts/12, 'annual_payroll': ts, 'monthly_net': ts/12*0.71, 'departments': dep, 'pending_pto': pp}
    return render_template('dashboard.html', stats=stats, recent_runs=runs, upcoming_pto=pto, active='dash', **sidebar_ctx())

# === EMPLOYEES ===
@app.route('/employees')
@login_required
def employees():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT id, full_name, email, department, salary, hire_date FROM crm_db.employees ORDER BY full_name')
            el = cur.fetchall()
    finally: conn.close()
    return render_template('employees.html', employees=el, active='emp', **sidebar_ctx())

@app.route('/employees/<int:eid>')
@login_required
def employee_detail(eid):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT id, full_name, email, department, job_description, salary, hire_date FROM crm_db.employees WHERE id=%s', (eid,))
            emp = cur.fetchone()
            stub = None
            if emp:
                cur.execute('SELECT ps.*, pr.period_start, pr.period_end FROM pay_stubs ps JOIN pay_runs pr ON ps.pay_run_id=pr.id WHERE ps.employee_id=%s ORDER BY pr.period_start DESC LIMIT 1', (eid,))
                stub = cur.fetchone()
    finally: conn.close()
    if not emp: return 'Record not found', 404
    rendered = emp['job_description'] or ''
    try: rendered = render_template_string(rendered)
    except Exception: pass
    latest = None
    if stub:
        latest = stub
        latest['period'] = stub['period_start'].strftime('%B %Y') if stub.get('period_start') else ''
    return render_template('employee_detail.html', employee=emp, rendered_job_description=rendered, latest_stub=latest, active='emp', **sidebar_ctx())

# === PAY RUNS ===
@app.route('/payruns')
@login_required
def payruns():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM pay_runs ORDER BY period_start DESC')
            runs = cur.fetchall()
    finally: conn.close()
    return render_template('payruns.html', runs=runs, active='payruns', **sidebar_ctx())

@app.route('/payruns/<int:rid>')
@login_required
def payrun_detail(rid):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM pay_runs WHERE id=%s', (rid,))
            run = cur.fetchone()
            stubs = []
            if run:
                cur.execute('SELECT * FROM pay_stubs WHERE pay_run_id=%s ORDER BY employee_name', (rid,))
                stubs = cur.fetchall()
    finally: conn.close()
    if not run: return 'Pay run not found', 404
    return render_template('payrun_detail.html', run=run, stubs=stubs, active='payruns', **sidebar_ctx())

# === DEDUCTIONS ===
@app.route('/deductions')
@login_required
def deductions():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM deductions ORDER BY category, name')
            dl = cur.fetchall()
    finally: conn.close()
    return render_template('deductions.html', deductions=dl, active='deductions', **sidebar_ctx())

# === TIME OFF ===
@app.route('/timeoff')
@login_required
def timeoff():
    sf = request.args.get('status', '')
    conn = get_db()
    try:
        with conn.cursor() as cur:
            if sf: cur.execute('SELECT * FROM time_off WHERE status=%s ORDER BY start_date DESC', (sf,))
            else: cur.execute('SELECT * FROM time_off ORDER BY start_date DESC')
            reqs = cur.fetchall()
    finally: conn.close()
    return render_template('timeoff.html', requests=reqs, status_filter=sf, active='timeoff', **sidebar_ctx())

# === REPORTS ===
@app.route('/reports')
@login_required
def reports():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT SUM(salary) as s FROM crm_db.employees'); ta = float(cur.fetchone()['s'] or 0)
            cur.execute('SELECT AVG(salary) as a FROM crm_db.employees'); av = float(cur.fetchone()['a'] or 0)
            cur.execute('SELECT COUNT(DISTINCT department) as d FROM crm_db.employees'); dc = cur.fetchone()['d']
            cur.execute('SELECT department, COUNT(*) as count, SUM(salary) as total FROM crm_db.employees GROUP BY department ORDER BY total DESC')
            dr = cur.fetchall()
            for r in dr: r['total'] = float(r['total'] or 0)
    finally: conn.close()
    return render_template('reports.html', total_annual=ta, avg_salary=av, dept_count=dc, dept_report=dr, active='reports', **sidebar_ctx())

# === INTEGRATIONS ===
@app.route('/integrations')
@login_required
def integrations():
    return render_template('integrations.html', active='integrations', **sidebar_ctx())

# === SETTINGS ===
@app.route('/settings')
@login_required
def settings():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT id, username, employee_id, role FROM payroll_users ORDER BY id')
            users = cur.fetchall()
    finally: conn.close()
    return render_template('settings.html', users=users, active='settings', **sidebar_ctx())

if __name__ == '__main__': app.run(host='0.0.0.0', port=5000)