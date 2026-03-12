import os, pymysql
from flask import Flask, render_template, request, jsonify, session, redirect

app = Flask(__name__, static_folder='../Static', static_url_path='/Static', template_folder='../Templates')
CONNECT_API_KEY = os.environ.get('CONNECT_API_KEY', '')
app.secret_key = os.environ.get('SECRET_KEY', 'connect-docs-sk')

def get_db():
    return pymysql.connect(host=os.environ.get('DB_HOST', 'db'), user=os.environ.get('DB_USER', 'connect_svc'), password=os.environ.get('DB_PASSWORD', 'ConnSvc#2024!'), database=os.environ.get('DB_NAME', 'shop_db'), cursorclass=pymysql.cursors.DictCursor)

@app.route('/')
def index():
    if not session.get('docs_key'):
        return render_template('auth.html')
    return render_template('docs.html', api_key=session['docs_key'])

@app.route('/docs/auth', methods=['POST'])
def docs_auth():
    key = request.form.get('api_key', '').strip()
    if key == CONNECT_API_KEY:
        session['docs_key'] = key
        return redirect('/')
    return render_template('auth.html', error='Invalid API key. Check your integration settings and try again.')

@app.route('/docs/logout')
def docs_logout():
    session.clear()
    return redirect('/')
@app.route('/changelog')
def changelog():
    if not session.get('docs_key'): return redirect('/')
    return render_template('changelog.html')
@app.route('/status')
def status():
    if not session.get('docs_key'): return redirect('/')
    return render_template('status.html')

@app.route('/api/v1/products')
def api_products():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT id, name, description, price, category, stock FROM products')
            products = cur.fetchall()
    finally: conn.close()
    for p in products:
        if p.get('price'): p['price'] = float(p['price'])
    return jsonify({'products': products})

@app.route('/api/v1/products/search')
def api_search():
    q = request.args.get('q', '')
    if not q: return jsonify({'error': 'Missing query parameter q', 'products': []})
    conn = get_db()
    try:
        with conn.cursor() as cur:
            # Vulnerable: direct string concatenation
            query = "SELECT id, name, description, price, category, stock FROM products WHERE name LIKE '%" + q + "%'"
            cur.execute(query)
            products = cur.fetchall()
    finally: conn.close()
    for p in products:
        if p.get('price'): p['price'] = float(p['price'])
    return jsonify({'products': products})

@app.route('/api/v1/products/<int:pid>')
def api_product_detail(pid):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT id, name, description, price, category, stock FROM products WHERE id=%s', (pid,))
            product = cur.fetchone()
    finally: conn.close()
    if not product: return jsonify({'error': 'Product not found'}), 404
    product['price'] = float(product['price'])
    return jsonify(product)

if __name__ == '__main__': app.run(host='0.0.0.0', port=5000)