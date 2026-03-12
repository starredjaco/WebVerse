import os, random, hashlib, pymysql, requests as http_client
from flask import Flask, render_template, request, redirect, session, jsonify

app = Flask(__name__, static_folder='../Static', static_url_path='/Static', template_folder='../Templates')
app.secret_key = os.environ.get('SECRET_KEY', 'shop-fallback')
CONNECT_URL = os.environ.get('CONNECT_URL', 'http://connect-api:5000')

def get_db():
    return pymysql.connect(host=os.environ.get('DB_HOST', 'db'), user=os.environ.get('DB_USER', 'shop_svc'), password=os.environ.get('DB_PASSWORD', 'ShopSvc#2024!'), database=os.environ.get('DB_NAME', 'shop_db'), cursorclass=pymysql.cursors.DictCursor)

def staff_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session or session.get('role') not in ('staff', 'manager', 'helpdesk'):
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated

# === PUBLIC ROUTES ===
@app.route('/')
def index(): return redirect('/products')

@app.route('/products')
def products():
    q = request.args.get('q', '')
    try:
        if q:
            r = http_client.get(f'{CONNECT_URL}/api/v1/products/search', params={'q': q}, timeout=5)
        else:
            r = http_client.get(f'{CONNECT_URL}/api/v1/products', timeout=5)
        prods = r.json().get('products', []) if r.status_code == 200 else []
    except Exception:
        prods = []
    return render_template('index.html', products=prods, query=q)

@app.route('/product/<int:pid>')
def product_detail(pid):
    try:
        r = http_client.get(f'{CONNECT_URL}/api/v1/products/{pid}', timeout=5)
        if r.status_code != 200: return 'Product not found', 404
        product = r.json()
    except Exception:
        return 'Product not found', 404
    return render_template('product_detail.html', product=product)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u, p = request.form.get('username', ''), request.form.get('password', '')
        p_hash = hashlib.sha256(p.encode()).hexdigest()
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT id, username, role FROM shop_users WHERE username=%s AND password=%s', (u, p_hash))
                user = cur.fetchone()
        finally: conn.close()
        if user:
            session['user'] = user['username']; session['user_id'] = user['id']; session['role'] = user['role']
            if user['role'] in ('staff', 'manager', 'helpdesk'): return redirect('/dashboard')
            return redirect('/products')
        return render_template('login.html', error='Invalid credentials.')
    return render_template('login.html')

@app.route('/logout')
def logout(): session.clear(); return redirect('/')

@app.route('/cart')
def cart(): return render_template('cart.html', cart=session.get('cart', []))

@app.route('/cart/add', methods=['POST'])
def cart_add():
    pid = request.form.get('product_id')
    try:
        r = http_client.get(f'{CONNECT_URL}/api/v1/products/{pid}', timeout=5)
        if r.status_code == 200:
            p = r.json()
            session['cart'] = session.get('cart', []) + [{'name': p['name'], 'price': float(p['price']), 'qty': 1}]
            session.modified = True
    except Exception:
        pass
    return redirect('/cart')

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user' not in session: return redirect('/login')
    msg, email = None, ''
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT email FROM shop_users WHERE id=%s', (session['user_id'],))
            row = cur.fetchone()
            if row: email = row['email']
            if request.method == 'POST':
                new_email = request.form.get('email', '')
                cur.execute('UPDATE shop_users SET email=%s WHERE id=%s', (new_email, session['user_id']))
                conn.commit(); msg = 'Profile updated.'; email = new_email
    finally: conn.close()
    return render_template('profile.html', message=msg, email=email)

# === STAFF ROUTES ===
@app.route('/dashboard')
@staff_required
def dashboard():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT SUM(total) as revenue, COUNT(*) as orders FROM orders')
            s = cur.fetchone()
            cur.execute("SELECT COUNT(*) as c FROM shop_users WHERE role='customer'")
            cust = cur.fetchone()['c']
            cur.execute('SELECT COUNT(*) as c FROM products')
            prods = cur.fetchone()['c']
            stats = {'revenue': float(s['revenue'] or 0), 'orders': s['orders'], 'customers': cust, 'products': prods}
            cur.execute('SELECT o.id, o.total, o.status, u.username FROM orders o JOIN shop_users u ON o.user_id=u.id ORDER BY o.created_at DESC LIMIT 5')
            recent = cur.fetchall()
            cur.execute('SELECT name, stock, sku FROM products WHERE stock < 50 ORDER BY stock ASC LIMIT 5')
            low = cur.fetchall()
    finally: conn.close()
    return render_template('dashboard.html', stats=stats, recent_orders=recent, low_stock=low, active_tab='dashboard')

@app.route('/orders')
@staff_required
def orders():
    status_filter = request.args.get('status', '')
    conn = get_db()
    try:
        with conn.cursor() as cur:
            if status_filter:
                cur.execute('SELECT o.id, o.quantity, o.total, o.status, o.created_at, u.username, p.name as product_name FROM orders o JOIN shop_users u ON o.user_id=u.id JOIN products p ON o.product_id=p.id WHERE o.status=%s ORDER BY o.created_at DESC', (status_filter,))
            else:
                cur.execute('SELECT o.id, o.quantity, o.total, o.status, o.created_at, u.username, p.name as product_name FROM orders o JOIN shop_users u ON o.user_id=u.id JOIN products p ON o.product_id=p.id ORDER BY o.created_at DESC')
            order_list = cur.fetchall()
    finally: conn.close()
    return render_template('orders.html', orders=order_list, status_filter=status_filter, active_tab='orders')

@app.route('/orders/<int:oid>')
@staff_required
def order_detail(oid):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT o.*, u.username, p.name as product_name FROM orders o JOIN shop_users u ON o.user_id=u.id JOIN products p ON o.product_id=p.id WHERE o.id=%s', (oid,))
            order = cur.fetchone()
            shipment = None
            if order:
                cur.execute('SELECT s.*, c.name as carrier_name FROM dispatch_db.shipments s JOIN dispatch_db.carriers c ON s.carrier_id=c.id WHERE s.order_id=%s', (oid,))
                shipment = cur.fetchone()
    finally: conn.close()
    if not order: return 'Order not found', 404
    return render_template('order_detail.html', order=order, shipment=shipment, active_tab='orders')

@app.route('/customers')
@staff_required
def customers():
    q = request.args.get('q', '')
    conn = get_db()
    try:
        with conn.cursor() as cur:
            base = "SELECT u.username, u.email, u.created_at, COUNT(o.id) as order_count, COALESCE(SUM(o.total),0) as total_spent FROM shop_users u LEFT JOIN orders o ON u.id=o.user_id WHERE u.role='customer'"
            if q: cur.execute(base + ' AND (u.username LIKE %s OR u.email LIKE %s) GROUP BY u.id ORDER BY total_spent DESC', (f'%{q}%', f'%{q}%'))
            else: cur.execute(base + ' GROUP BY u.id ORDER BY total_spent DESC')
            cust_list = cur.fetchall()
    finally: conn.close()
    return render_template('customers.html', customers=cust_list, active_tab='customers')

@app.route('/analytics')
@staff_required
def analytics():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT SUM(total) as revenue, COUNT(*) as orders, AVG(total) as avg_order FROM orders')
            s = cur.fetchone()
            cur.execute("SELECT COUNT(*) as c FROM shop_users WHERE role='customer'")
            cust = cur.fetchone()['c']
            stats = {'revenue': float(s['revenue'] or 0), 'orders': s['orders'], 'avg_order': float(s['avg_order'] or 0), 'customers': cust}
            cur.execute('SELECT p.name, SUM(o.quantity) as units, SUM(o.total) as revenue FROM orders o JOIN products p ON o.product_id=p.id GROUP BY p.id ORDER BY revenue DESC LIMIT 5')
            top = cur.fetchall()
            cur.execute('SELECT status, COUNT(*) as count, SUM(total) as total FROM orders GROUP BY status ORDER BY count DESC')
            breakdown = cur.fetchall()
    finally: conn.close()
    return render_template('analytics.html', stats=stats, top_products=top, status_breakdown=breakdown, active_tab='analytics')

@app.route('/inventory')
@staff_required
def inventory():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT id, name, category, price, stock, sku FROM products ORDER BY stock ASC')
            prods = cur.fetchall()
    finally: conn.close()
    return render_template('inventory.html', products=prods, active_tab='inventory')

# ═══════════════════════════════════════════════════════════
# ACCOUNT & AVATAR SYSTEM
# ═══════════════════════════════════════════════════════════
import base64
from datetime import datetime

AVATAR_PALETTES = [
    ('#c84b31', '#e8725a'), ('#4a7c6f', '#6a9e8f'), ('#8b6f47', '#a68b63'),
    ('#6366f1', '#818cf8'), ('#d97706', '#f59e0b'), ('#7c3aed', '#a78bfa'),
    ('#0891b2', '#22d3ee'), ('#be185d', '#ec4899'),
]

def make_avatar_svg(username, user_id):
    idx = abs(hash(username)) % len(AVATAR_PALETTES)
    c1, c2 = AVATAR_PALETTES[idx]
    initial = username[0].upper() if username else '?'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">'
        f'<defs><linearGradient id="av{user_id}" x1="0%" y1="0%" x2="100%" y2="100%">'
        f'<stop offset="0%" stop-color="{c1}"/><stop offset="100%" stop-color="{c2}"/>'
        f'</linearGradient></defs>'
        f'<rect width="120" height="120" rx="60" fill="url(#av{user_id})"/>'
        f'<text x="60" y="60" dy=".35em" text-anchor="middle" fill="#fff" '
        f'font-family="system-ui,-apple-system,sans-serif" font-size="48" font-weight="600">'
        f'{initial}</text></svg>')

def get_avatar_url(username, user_id):
    avatar_dir = os.path.join(app.static_folder, 'avatars')
    for ext in ('png', 'jpg', 'jpeg'):
        if os.path.exists(os.path.join(avatar_dir, f'{user_id}.{ext}')):
            return f'/Static/avatars/{user_id}.{ext}'
    svg = make_avatar_svg(username, user_id)
    b64 = base64.b64encode(svg.encode()).decode()
    return f'data:image/svg+xml;base64,{b64}'

FAKE_ACTIVITY = [
    {'time': '2024-12-05 14:23', 'action': 'Signed in', 'detail': 'Password authentication', 'ip': '10.0.2.14'},
    {'time': '2024-12-05 14:25', 'action': 'Viewed order #7', 'detail': 'Order detail page', 'ip': '10.0.2.14'},
    {'time': '2024-12-04 09:11', 'action': 'Signed in', 'detail': 'Password authentication', 'ip': '10.0.2.14'},
    {'time': '2024-12-04 09:15', 'action': 'Updated inventory', 'detail': 'Product PPT-EDU-005 stock adjustment', 'ip': '10.0.2.14'},
    {'time': '2024-12-03 16:42', 'action': 'Signed in', 'detail': 'Password authentication', 'ip': '192.168.1.105'},
    {'time': '2024-12-03 16:50', 'action': 'Generated reset code', 'detail': 'Account #5 (linda.wu)', 'ip': '192.168.1.105'},
    {'time': '2024-12-02 10:30', 'action': 'Signed in', 'detail': 'Password authentication', 'ip': '10.0.2.14'},
    {'time': '2024-12-01 08:55', 'action': 'Signed in', 'detail': 'Password authentication', 'ip': '10.0.2.14'},
]

DEPARTMENTS = {'helpdesk': 'Customer Support', 'staff': 'Operations', 'manager': 'Management', 'customer': 'N/A'}

# ═══ Profile overview (read-only) ═══
@app.route('/staff/account')
@staff_required
def staff_account():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT email, created_at FROM shop_users WHERE id=%s', (session['user_id'],))
            row = cur.fetchone()
    finally: conn.close()
    email = row['email'] if row else ''
    created = row['created_at'].strftime('%B %d, %Y') if row and row.get('created_at') else 'Unknown'
    return render_template('staff_account.html', active_tab='account',
        my_avatar=get_avatar_url(session['user'], session['user_id']),
        display_name=session['user'].replace('_', ' ').replace('.', ' ').title(),
        email=email, member_since=created,
        department=DEPARTMENTS.get(session.get('role', ''), 'General'),
        last_login=datetime.now().strftime('%b %d, %Y at %I:%M %p'),
        activity_log=FAKE_ACTIVITY, flash_msg=request.args.get('msg'))

# ═══ Edit profile ═══
@app.route('/staff/account/edit', methods=['GET', 'POST'])
@staff_required
def staff_account_edit():
    message, error = None, None
    if request.method == 'POST':
        new_email = request.form.get('email', '').strip()
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute('UPDATE shop_users SET email=%s WHERE id=%s', (new_email, session['user_id']))
                conn.commit()
                message = 'Profile updated successfully.'
        except Exception:
            error = 'Failed to update profile. Please try again.'
        finally: conn.close()
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT email FROM shop_users WHERE id=%s', (session['user_id'],))
            row = cur.fetchone()
    finally: conn.close()
    return render_template('staff_account_edit.html', active_tab='account',
        my_avatar=get_avatar_url(session['user'], session['user_id']),
        display_name=session['user'].replace('_', ' ').replace('.', ' ').title(),
        email=row['email'] if row else '', message=message, error=error)

# ═══ Avatar upload (SAFE — content-type check, no traversal, no execution) ═══
@app.route('/staff/account/avatar', methods=['POST'])
@staff_required
def staff_avatar_upload():
    f = request.files.get('avatar')
    if not f or not f.filename:
        return redirect('/staff/account/edit')
    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
    if ext not in ('png', 'jpg', 'jpeg'):
        return redirect('/staff/account/edit')
    data = f.read()
    if len(data) > 2 * 1024 * 1024:
        return redirect('/staff/account/edit')
    avatar_dir = os.path.join(app.static_folder, 'avatars')
    os.makedirs(avatar_dir, exist_ok=True)
    # Remove any previous avatar
    for old_ext in ('png', 'jpg', 'jpeg'):
        old_path = os.path.join(avatar_dir, f'{session["user_id"]}.{old_ext}')
        if os.path.exists(old_path): os.remove(old_path)
    safe_name = f'{session["user_id"]}.{ext}'
    with open(os.path.join(avatar_dir, safe_name), 'wb') as out:
        out.write(data)
    return redirect('/staff/account?msg=Profile+photo+updated.')

# ═══ Password recovery tool — BOLA: any staff can reset any user_id ═══
@app.route('/staff/account/recovery', methods=['GET', 'POST'])
@staff_required
def staff_recovery():
    message, error = None, None
    search_query = request.args.get('q', '').strip() if request.method == 'GET' else None
    search_results = None
    if request.method == 'POST':
        user_id = request.form.get('user_id', '')
        code = str(random.randint(1000, 9999))
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT id, username, email FROM shop_users WHERE id=%s', (user_id,))
                target = cur.fetchone()
                if target:
                    cur.execute('UPDATE shop_users SET reset_code=%s, reset_code_expiry=DATE_ADD(NOW(), INTERVAL 15 MINUTE) WHERE id=%s', (code, user_id))
                    conn.commit()
                    masked_email = target['email'][:3] + '***' if target.get('email') else 'registered channel'
                    message = f'A reset code has been generated for {target["username"]} (#{user_id}). The code was delivered to {masked_email}.'
                else:
                    error = f'No account found with ID #{user_id}.'
        finally: conn.close()
    if search_query is not None and search_query:
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT id, username, email, role, reset_code FROM shop_users WHERE username LIKE %s OR email LIKE %s ORDER BY id', (f'%{search_query}%', f'%{search_query}%'))
                search_results = cur.fetchall()
                for u in search_results:
                    u['avatar'] = get_avatar_url(u['username'], u['id'])
        finally: conn.close()
    elif search_query is not None:
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT id, username, email, role, reset_code FROM shop_users ORDER BY id')
                search_results = cur.fetchall()
                for u in search_results:
                    u['avatar'] = get_avatar_url(u['username'], u['id'])
        finally: conn.close()
    return render_template('staff_recovery.html', active_tab='recovery',
        message=message, error=error, search_query=search_query, search_results=search_results)

# ═══ Verify reset code — No rate limit (brute-forceable) ═══
@app.route('/staff/account/recovery/verify', methods=['GET', 'POST'])
@staff_required
def staff_recovery_verify():
    message, error = None, None
    prefill_uid = request.args.get('uid', '')
    if request.method == 'POST':
        user_id = request.form.get('user_id', '')
        code = request.form.get('code', '')
        new_pw = request.form.get('new_password', '')
        prefill_uid = user_id
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT id, reset_code FROM shop_users WHERE id=%s AND reset_code=%s AND reset_code_expiry > NOW()', (user_id, code))
                if cur.fetchone():
                    new_pw_hash = hashlib.sha256(new_pw.encode()).hexdigest()
                    cur.execute('UPDATE shop_users SET password=%s, reset_code=NULL, reset_code_expiry=NULL WHERE id=%s', (new_pw_hash, user_id))
                    conn.commit()
                    message = f'Password has been reset for account #{user_id}. The user can now sign in with the new password.'
                else:
                    error = 'Invalid or expired reset code. Codes are valid for 15 minutes after generation.'
        finally: conn.close()
    return render_template('staff_recovery_verify.html', active_tab='recovery',
        message=message, error=error, prefill_uid=prefill_uid)


# === STAFF ROUTES: Settings ===
@app.route('/settings')
@staff_required
def settings():
    return render_template('settings.html', active_tab='settings')

@app.route('/settings/integrations')
@staff_required
def settings_integrations():
    if session.get('role') not in ('staff', 'manager'):
        return redirect('/dashboard')
    return render_template('settings_integrations.html', active_tab='integrations',
        connect_api_key=os.environ.get('CONNECT_API_KEY', ''),
        dispatch_api_key=os.environ.get('DISPATCH_API_KEY', ''))

@app.route('/settings/notifications', methods=['GET', 'POST'])
@staff_required
def settings_notifications():
    msg = 'Notification preferences saved.' if request.method == 'POST' else None
    return render_template('settings_notifications.html', active_tab='notifications', message=msg)

if __name__ == '__main__': app.run(host='0.0.0.0', port=5000)