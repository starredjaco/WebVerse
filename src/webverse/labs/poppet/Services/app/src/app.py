import os, pymysql
from flask import Flask, render_template, request, redirect, session, url_for, make_response
from lxml import etree

app = Flask(__name__, static_folder='../Static', static_url_path='/Static', template_folder='../Templates')
app.secret_key = os.environ.get('SECRET_KEY', 'fallback-secret')

def get_db():
    return pymysql.connect(host=os.environ.get('DB_HOST', 'db'), user=os.environ.get('DB_USER', 'app_svc'),
        password=os.environ.get('DB_PASSWORD', 'AppSvc#2024!'), database=os.environ.get('DB_NAME', 'app_db'),
        cursorclass=pymysql.cursors.DictCursor)

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session: return redirect('/login')
        return f(*args, **kwargs)
    return decorated

def sidebar_ctx():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as c FROM toy_designs WHERE status='review'")
            return {'review_count': cur.fetchone()['c']}
    finally: conn.close()

# ═══ PUBLIC ═══
@app.route('/')
def index():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT name, description, category, age_range, status, image_slug FROM toy_designs WHERE status='approved' ORDER BY created_at DESC LIMIT 6")
            featured = cur.fetchall()
    finally: conn.close()
    return render_template('index.html', featured=featured)

@app.route('/gallery')
def gallery():
    cat = request.args.get('cat', '')
    conn = get_db()
    try:
        with conn.cursor() as cur:
            if cat:
                cur.execute("SELECT name, description, category, age_range, image_slug FROM toy_designs WHERE status='approved' AND category=%s ORDER BY created_at DESC", (cat,))
            else:
                cur.execute("SELECT name, description, category, age_range, image_slug FROM toy_designs WHERE status='approved' ORDER BY created_at DESC")
            designs = cur.fetchall()
    finally: conn.close()
    return render_template('gallery.html', designs=designs, cat_filter=cat)

@app.route('/about')
def about():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT full_name, role FROM app_users WHERE full_name IS NOT NULL ORDER BY id")
            team = cur.fetchall()
    finally: conn.close()
    return render_template('about.html', team=team)

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    msg = None
    if request.method == 'POST':
        name = request.form.get('name', '')
        email = request.form.get('email', '')
        subject = request.form.get('subject', '')
        message = request.form.get('message', '')
        if name and email and message:
            conn = get_db()
            try:
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO contact_messages (name, email, subject, message) VALUES (%s,%s,%s,%s)", (name, email, subject, message))
                conn.commit()
            finally: conn.close()
            msg = 'Thank you! We will get back to you within 2 business days.'
    return render_template('contact.html', message=msg)

# ═══ AUTH ═══
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u, p = request.form.get('username', ''), request.form.get('password', '')
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT id, username, full_name, role FROM app_users WHERE username=%s AND password=%s', (u, p))
                user = cur.fetchone()
        finally: conn.close()
        if user:
            session['user'] = user['username']; session['user_id'] = user['id']
            session['role'] = user['role']; session['full_name'] = user['full_name'] or user['username']
            return redirect('/dashboard')
        return render_template('login.html', error='Invalid credentials.')
    return render_template('login.html')

@app.route('/logout')
def logout(): session.clear(); return redirect('/')

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as total, SUM(status='approved') as approved, SUM(status='review') as review, SUM(status='draft') as draft FROM toy_designs WHERE user_id=%s", (session['user_id'],))
            stats = cur.fetchone()
            cur.execute("SELECT id, name, category, status, created_at FROM toy_designs WHERE user_id=%s ORDER BY created_at DESC LIMIT 5", (session['user_id'],))
            recent = cur.fetchall()
            cur.execute("SELECT pq.*, td.name as design_name FROM production_queue pq JOIN toy_designs td ON pq.design_id=td.id WHERE pq.status IN ('queued','in_progress') ORDER BY pq.due_date LIMIT 4")
            prod = cur.fetchall()
    finally: conn.close()
    return render_template('dashboard.html', stats=stats, recent=recent, prod_queue=prod, active='dash', **sidebar_ctx())

@app.route('/designs')
@login_required
def designs():
    sf = request.args.get('status', '')
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as c FROM toy_designs"); all_c = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) as c FROM toy_designs WHERE status='approved'"); app_c = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) as c FROM toy_designs WHERE status='review'"); rev_c = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) as c FROM toy_designs WHERE status='draft'"); dra_c = cur.fetchone()['c']
            if sf:
                cur.execute("SELECT td.*, au.full_name as designer FROM toy_designs td LEFT JOIN app_users au ON td.user_id=au.id WHERE td.status=%s ORDER BY td.created_at DESC", (sf,))
            else:
                cur.execute("SELECT td.*, au.full_name as designer FROM toy_designs td LEFT JOIN app_users au ON td.user_id=au.id ORDER BY td.created_at DESC")
            dl = cur.fetchall()
    finally: conn.close()
    counts = {'all': all_c, 'approved': app_c, 'review': rev_c, 'draft': dra_c}
    return render_template('designs.html', designs=dl, counts=counts, status_filter=sf, active='designs', **sidebar_ctx())

@app.route('/designs/<int:did>')
@login_required
def design_detail(did):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT td.*, au.full_name as designer FROM toy_designs td LEFT JOIN app_users au ON td.user_id=au.id WHERE td.id=%s", (did,))
            design = cur.fetchone()
    finally: conn.close()
    if not design: return 'Design not found', 404
    return render_template('design_detail.html', design=design, active='designs', **sidebar_ctx())

# ═══ STUDIO (XXE vulnerability preserved) ═══
@app.route('/studio')
@login_required
def studio():
    return render_template('studio.html', active='studio', **sidebar_ctx())

@app.route('/studio/upload', methods=['POST'])
@login_required
def studio_upload():
    design_name = request.form.get('design_name', '')
    description = request.form.get('description', '')
    category = request.form.get('category', 'figurines')
    age_range = request.form.get('age_range', '3+')
    materials_used = request.form.get('materials_used', '')
    uploaded = request.files.get('image')
    if not uploaded or not design_name:
        return render_template('studio.html', error='Please provide a name and image file.', active='studio', **sidebar_ctx())
    filename = uploaded.filename.lower()
    if not filename.endswith('.svg'):
        return render_template('studio.html', error='Only SVG format is accepted. Please convert your design to SVG.', active='studio', **sidebar_ctx())
    file_data = uploaded.read()
    # SVG content security validation — block XML injection patterns
    raw_check = file_data.upper()
    SVG_BLOCKED = [b'ENTITY', b'SYSTEM', b'PUBLIC', b'DOCTYPE', b'NOTATION']
    for pattern in SVG_BLOCKED:
        if pattern in raw_check:
            app.logger.warning('SVG upload rejected: blocked pattern %s from user %s', pattern.decode(), session.get('user', ''))
            return render_template('studio.html', error='SVG validation failed. The file contains unsupported XML declarations. Please upload a clean SVG file exported from your design tool.', active='studio', **sidebar_ctx())
    preview = ''
    try:
        parser = etree.XMLParser(resolve_entities=True, no_network=False)
        tree = etree.fromstring(file_data, parser=parser)
        preview = etree.tostring(tree, pretty_print=True, encoding='unicode')
    except Exception as e: preview = 'SVG parse error: ' + str(e)
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO toy_designs (user_id, name, description, category, materials_used, age_range, image_data, status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                (session['user_id'], design_name, description, category, materials_used, age_range, preview[:5000], 'draft'))
        conn.commit()
    finally: conn.close()
    return render_template('studio.html', message='Design uploaded successfully.', preview=preview, active='studio', **sidebar_ctx())

# ═══ MATERIALS ═══
@app.route('/materials')
@login_required
def materials():
    cat = request.args.get('cat', '')
    conn = get_db()
    try:
        with conn.cursor() as cur:
            if cat:
                cur.execute("SELECT * FROM materials WHERE category=%s ORDER BY name", (cat,))
            else:
                cur.execute("SELECT * FROM materials ORDER BY category, name")
            ml = cur.fetchall()
    finally: conn.close()
    return render_template('materials.html', materials=ml, cat_filter=cat, active='materials', **sidebar_ctx())

# ═══ PRODUCTION ═══
@app.route('/production')
@login_required
def production():
    sf = request.args.get('status', '')
    conn = get_db()
    try:
        with conn.cursor() as cur:
            if sf:
                cur.execute("SELECT pq.*, td.name as design_name, au.full_name as assigned_name FROM production_queue pq JOIN toy_designs td ON pq.design_id=td.id LEFT JOIN app_users au ON pq.assigned_to=au.id WHERE pq.status=%s ORDER BY pq.due_date", (sf,))
            else:
                cur.execute("SELECT pq.*, td.name as design_name, au.full_name as assigned_name FROM production_queue pq JOIN toy_designs td ON pq.design_id=td.id LEFT JOIN app_users au ON pq.assigned_to=au.id ORDER BY FIELD(pq.status,'in_progress','queued','completed'), pq.due_date")
            queue = cur.fetchall()
    finally: conn.close()
    return render_template('production.html', queue=queue, status_filter=sf, active='production', **sidebar_ctx())

# ═══ PROFILE ═══
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    import json as _json
    msg = None
    prefs_default = {'notify_review': True, 'show_gallery': True, 'weekly_digest': False}
    try: prefs = _json.loads(request.cookies.get('studio_prefs', '{}'))
    except Exception: prefs = {}
    prefs = {**prefs_default, **prefs}
    conn = get_db()
    try:
        with conn.cursor() as cur:
            if request.method == 'POST':
                action = request.form.get('action', 'profile')
                if action == 'prefs':
                    prefs = {k: (k in request.form) for k in prefs_default}
                    msg = 'Preferences saved.'
                else:
                    fn = request.form.get('full_name', '')
                    bio = request.form.get('bio', '')
                    cur.execute("UPDATE app_users SET full_name=%s, bio=%s WHERE id=%s", (fn, bio, session['user_id']))
                    conn.commit()
                    session['full_name'] = fn
                    msg = 'Profile updated.'
            cur.execute("SELECT * FROM app_users WHERE id=%s", (session['user_id'],))
            user = cur.fetchone()
            cur.execute("SELECT COUNT(*) as c FROM toy_designs WHERE user_id=%s", (session['user_id'],))
            dc = cur.fetchone()['c']
    finally: conn.close()
    resp = make_response(render_template('profile.html', user=user, design_count=dc, prefs=prefs, message=msg, active='profile', **sidebar_ctx()))
    if request.method == 'POST' and request.form.get('action') == 'prefs':
        resp.set_cookie('studio_prefs', _json.dumps(prefs), httponly=True, max_age=60*60*24*365)
    return resp

if __name__ == '__main__': app.run(host='0.0.0.0', port=5000)