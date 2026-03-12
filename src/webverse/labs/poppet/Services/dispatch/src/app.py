import os, re, pymysql, json, datetime
from flask import Flask, render_template, request, jsonify, session, redirect

app = Flask(__name__, static_folder='../Static', static_url_path='/Static', template_folder='../Templates')
DISPATCH_API_KEY = os.environ.get('DISPATCH_API_KEY', '')
app.secret_key = os.environ.get('SECRET_KEY', 'dispatch-docs-sk')

# ── Input validation for search parameters ──
# Added after Q3 security review flagged unparameterized tracking search.
# Uses word-boundary matching to avoid false positives on partial matches.
SEARCH_BLOCKED_KEYWORDS = [
    'union', 'select', 'insert', 'update', 'delete', 'drop',
    'from', 'where', 'having', 'order by', 'group by',
    'concat', 'group_concat', 'substr', 'substring', 'mid',
    'information_schema', 'load_file', 'into outfile', 'into dumpfile',
    'benchmark', 'sleep', 'extractvalue', 'updatexml',
]

def validate_search_param(value):
    """Returns None if clean, or the matched pattern for logging."""
    if '--' in value:
        return 'comment'
    if '#' in value:
        return 'comment'
    if re.search(r'/\*(?!!)', value):
        return 'comment'
    for kw in SEARCH_BLOCKED_KEYWORDS:
        if re.search(r'\b' + re.escape(kw) + r'\b', value, re.IGNORECASE):
            return kw
    return None

def get_db():
    return pymysql.connect(host=os.environ.get('DB_HOST', 'db'), user=os.environ.get('DB_USER', 'dispatch_svc'), password=os.environ.get('DB_PASSWORD', 'DspSvc#2024!'), database=os.environ.get('DB_NAME', 'dispatch_db'), cursorclass=pymysql.cursors.DictCursor)

class JSONEnc(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, (datetime.date, datetime.datetime)): return o.isoformat()
        if isinstance(o, __import__('decimal').Decimal): return float(o)
        return super().default(o)

app.json_encoder = JSONEnc

@app.route('/')
def index():
    if not session.get('docs_key'):
        return render_template('auth.html')
    return render_template('docs.html', api_key=session['docs_key'])

@app.route('/docs/auth', methods=['POST'])
def docs_auth():
    key = request.form.get('api_key', '').strip()
    if key == DISPATCH_API_KEY:
        session['docs_key'] = key
        return redirect('/')
    return render_template('auth.html', error='Invalid API key. Check your integration settings and try again.')

@app.route('/docs/logout')
def docs_logout():
    session.clear()
    return redirect('/')

@app.before_request
def check_auth():
    if request.path.startswith('/api/'):
        key = request.headers.get('X-Api-Key', '')
        if key != DISPATCH_API_KEY:
            return jsonify({'error': 'Unauthorized. Valid API key required.'}), 401

@app.route('/api/v1/health')
def health(): return jsonify({'status': 'ok', 'service': 'dispatch'})

@app.route('/api/v1/orders')
def api_orders():
    status = request.args.get('status', '')
    conn = get_db()
    try:
        with conn.cursor() as cur:
            if status: cur.execute('SELECT o.id, o.user_id, o.product_id, o.quantity, o.total, o.status, o.shipping_address, o.created_at, p.name as product_name FROM shop_db.orders o JOIN shop_db.products p ON o.product_id=p.id WHERE o.status=%s ORDER BY o.created_at DESC', (status,))
            else: cur.execute('SELECT o.id, o.user_id, o.product_id, o.quantity, o.total, o.status, o.shipping_address, o.created_at, p.name as product_name FROM shop_db.orders o JOIN shop_db.products p ON o.product_id=p.id ORDER BY o.created_at DESC')
            orders = cur.fetchall()
    finally: conn.close()
    for o in orders:
        if o.get('total'): o['total'] = float(o['total'])
    return jsonify({'orders': orders, 'count': len(orders)})

@app.route('/api/v1/orders/<int:oid>')
def api_order_detail(oid):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT o.*, p.name as product_name, u.username FROM shop_db.orders o JOIN shop_db.products p ON o.product_id=p.id JOIN shop_db.shop_users u ON o.user_id=u.id WHERE o.id=%s', (oid,))
            order = cur.fetchone()
    finally: conn.close()
    if not order: return jsonify({'error': 'Order not found'}), 404
    if order.get('total'): order['total'] = float(order['total'])
    return jsonify(order)

@app.route('/api/v1/orders/<int:oid>/pack', methods=['POST'])
def api_pack_order(oid):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT id, status FROM shop_db.orders WHERE id=%s', (oid,))
            order = cur.fetchone()
            if not order: return jsonify({'error': 'Order not found'}), 404
            if order['status'] != 'pending': return jsonify({'error': f'Cannot pack order in {order["status"]} status'}), 400
            cur.execute("UPDATE shop_db.orders SET status='processing' WHERE id=%s", (oid,))
            conn.commit()
    finally: conn.close()
    return jsonify({'status': 'ok', 'order_id': oid, 'new_status': 'processing'})

@app.route('/api/v1/orders/<int:oid>/ship', methods=['POST'])
def api_ship_order(oid):
    data = request.get_json(silent=True) or {}
    carrier_id = data.get('carrier_id')
    tracking = data.get('tracking_number', '')
    weight = data.get('weight_grams', 0)
    if not carrier_id or not tracking: return jsonify({'error': 'carrier_id and tracking_number required'}), 400
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT id, status FROM shop_db.orders WHERE id=%s', (oid,))
            order = cur.fetchone()
            if not order: return jsonify({'error': 'Order not found'}), 404
            cur.execute("UPDATE shop_db.orders SET status='shipped' WHERE id=%s", (oid,))
            cur.execute('INSERT INTO shipments (order_id, carrier_id, tracking_number, status, weight_grams, ship_date) VALUES (%s,%s,%s,%s,%s,NOW())', (oid, carrier_id, tracking, 'in_transit', weight))
            conn.commit()
            shipment_id = cur.lastrowid
    finally: conn.close()
    return jsonify({'status': 'ok', 'order_id': oid, 'shipment_id': shipment_id, 'tracking_number': tracking})

@app.route('/api/v1/shipments')
def api_shipments():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT s.*, c.name as carrier_name FROM shipments s JOIN carriers c ON s.carrier_id=c.id ORDER BY s.created_at DESC')
            shipments = cur.fetchall()
    finally: conn.close()
    return jsonify({'shipments': shipments, 'count': len(shipments)})

@app.route('/api/v1/shipments/search')
def api_shipment_search():
    tracking = request.args.get('tracking', '')
    if not tracking: return jsonify({'error': 'Request has been blocked.', 'shipments': []})
    violation = validate_search_param(tracking)
    if violation:
        app.logger.warning('Search input rejected: matched=%s remote=%s', violation, request.remote_addr)
        return jsonify({'error': 'Invalid tracking number format. Tracking numbers contain only alphanumeric characters and hyphens.', 'shipments': []}), 400
    conn = get_db()
    try:
        with conn.cursor() as cur:
            query = "SELECT s.id, s.order_id, s.tracking_number, s.status, s.ship_date, c.name as carrier_name FROM shipments s JOIN carriers c ON s.carrier_id=c.id WHERE s.tracking_number LIKE '%" + tracking + "%'"
            cur.execute(query)
            results = cur.fetchall()
    finally: conn.close()
    return jsonify({'shipments': results, 'count': len(results)})

@app.route('/api/v1/shipments/<int:sid>')
def api_shipment_detail(sid):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT s.*, c.name as carrier_name, c.tracking_url_template FROM shipments s JOIN carriers c ON s.carrier_id=c.id WHERE s.id=%s', (sid,))
            s = cur.fetchone()
    finally: conn.close()
    if not s: return jsonify({'error': 'Shipment not found'}), 404
    return jsonify(s)

@app.route('/api/v1/shipments/<int:sid>/track')
def api_track(sid):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT s.tracking_number, s.status, s.ship_date, s.delivered_date, c.name as carrier, c.tracking_url_template FROM shipments s JOIN carriers c ON s.carrier_id=c.id WHERE s.id=%s', (sid,))
            s = cur.fetchone()
    finally: conn.close()
    if not s: return jsonify({'error': 'Shipment not found'}), 404
    url = s['tracking_url_template'].replace('{tracking}', s['tracking_number']) if s.get('tracking_url_template') else None
    return jsonify({'tracking_number': s['tracking_number'], 'carrier': s['carrier'], 'status': s['status'], 'ship_date': s['ship_date'], 'delivered_date': s['delivered_date'], 'tracking_url': url})

@app.route('/api/v1/carriers')
def api_carriers():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT id, name, code, active FROM carriers ORDER BY name')
            carriers = cur.fetchall()
    finally: conn.close()
    return jsonify({'carriers': carriers})

@app.route('/api/v1/stats')
def api_stats():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) as total FROM shop_db.orders'); total = cur.fetchone()['total']
            cur.execute("SELECT COUNT(*) as c FROM shop_db.orders WHERE status='pending'"); pending = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) as c FROM shop_db.orders WHERE status='shipped'"); shipped = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) as c FROM shop_db.orders WHERE status='delivered'"); delivered = cur.fetchone()['c']
            cur.execute('SELECT COUNT(*) as c FROM shipments'); total_shipments = cur.fetchone()['c']
            cur.execute('SELECT AVG(weight_grams) as avg_weight FROM shipments WHERE weight_grams > 0'); avg_w = cur.fetchone()['avg_weight']
    finally: conn.close()
    return jsonify({'total_orders': total, 'pending': pending, 'shipped': shipped, 'delivered': delivered, 'total_shipments': total_shipments, 'avg_weight_grams': float(avg_w or 0)})

@app.route('/api/v1/labels/<int:oid>', methods=['POST'])
def api_generate_label(oid):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT o.id, o.shipping_address, p.name as product_name, p.sku FROM shop_db.orders o JOIN shop_db.products p ON o.product_id=p.id WHERE o.id=%s', (oid,))
            order = cur.fetchone()
    finally: conn.close()
    if not order: return jsonify({'error': 'Order not found'}), 404
    return jsonify({'label_generated': True, 'order_id': oid, 'from': 'Poppet Studio, 45 Craft Lane, Asheville, NC 28801', 'to': order['shipping_address'], 'item': order['product_name'], 'sku': order['sku'], 'format': 'PDF', 'note': 'Label data generated. In production this would return a PDF binary.'})

@app.route('/api/v1/returns')
def api_returns():
    return jsonify({'returns': [], 'count': 0, 'note': 'No return requests pending.'})

@app.route('/api/v1/returns', methods=['POST'])
def api_create_return():
    data = request.get_json(silent=True) or {}
    order_id = data.get('order_id')
    reason = data.get('reason', '')
    if not order_id: return jsonify({'error': 'order_id is required'}), 400
    return jsonify({'status': 'ok', 'return_id': 'RET-' + str(order_id), 'order_id': order_id, 'reason': reason, 'note': 'Return request created. Awaiting approval.'})

if __name__ == '__main__': app.run(host='0.0.0.0', port=5000)