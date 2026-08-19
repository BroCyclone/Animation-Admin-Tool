from flask import Flask, render_template, request, jsonify, session, redirect
import os
import hashlib
import uuid
from datetime import datetime
from config import get_db_connection, init_db
from psycopg2.extras import RealDictCursor

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.getenv("SESSION_SECRET", "super-encrypted-fallback-cyclone-key")

# Auto-initialize database matrices if executed dynamically
try:
    if os.getenv("DATABASE_URL"):
        init_db()
except Exception as e:
    print(f"Database setup notice: {e}")

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

@app.route('/')
def index():
    if 'user' in session:
        return redirect('/admin') if session.get('role') == 'admin' else redirect('/user')
    return redirect('/login')

@app.route('/login')
def login_page(): return render_template('login.html')

@app.route('/admin')
def admin_page():
    if session.get('role') != 'admin': return redirect('/login')
    return render_template('admin.html')

@app.route('/user')
def user_page():
    if 'user' not in session: return redirect('/login')
    return render_template('user.html')

# === API CHANNELS ===

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    
    if user and user['password'] == hash_password(password):
        if user['approval_status'] != 'approved':
            return jsonify({'error': 'Account pending administrative approval matrix'}), 403
        session['user'] = username
        session['role'] = user['role']
        return jsonify({'success': True, 'role': session['role']})
    return jsonify({'error': 'Invalid credentials supplied'}), 401

@app.route('/api/auth/register', methods=['POST'])
def api_register():
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT username FROM users WHERE username = %s", (username,))
    if cur.fetchone():
        cur.close()
        conn.close()
        return jsonify({'error': 'Account identity already registered'}), 400
        
    cur.execute(
        "INSERT INTO users (username, password, role, approval_status, internet_access) VALUES (%s, %s, 'user', 'pending', TRUE)",
        (username, hash_password(password))
    )
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True, 'message': 'Registration queued'})

@app.route('/api/admin/change-password', methods=['POST'])
def change_password():
    if session.get('role') != 'admin': return jsonify({'error': 'Forbidden'}), 403
    data = request.get_json() or {}
    old_pass = data.get('old_password')
    new_pass = data.get('new_password')
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT password FROM users WHERE username = 'admin'")
    admin = cur.fetchone()
    
    if admin and admin['password'] == hash_password(old_pass):
        cur.execute("UPDATE users SET password = %s WHERE username = 'admin'", (hash_password(new_pass),))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True})
    
    cur.close()
    conn.close()
    return jsonify({'error': 'Verification of existing credential matrix failed'}), 400

@app.route('/api/device/ping', methods=['POST'])
def api_device_ping():
    if 'user' not in session: return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json() or {}
    device_id = data.get('deviceId', 'unknown_fingerprint')
    username = session['user']
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("SELECT internet_access FROM users WHERE username = %s", (username,))
    user = cur.fetchone()
    if not user or not user['internet_access']:
        cur.close()
        conn.close()
        return jsonify({'kick': True, 'reason': 'Terminal control routing link severed by admin'}), 403
        
    cur.execute("SELECT value FROM settings WHERE key = 'maintenance_mode'")
    m_mode = cur.fetchone()
    cur.execute("SELECT value FROM settings WHERE key = 'maintenance_notice'")
    m_notice = cur.fetchone()
    
    if m_mode and m_mode['value'] == 'true' and session.get('role') != 'admin':
        cur.close()
        conn.close()
        return jsonify({'maintenance': True, 'notice': m_notice['value'] if m_notice else 'Maintenance active'})

    cur.execute(
        "INSERT INTO devices (username, device_id, login_count, last_seen) VALUES (%s, %s, 1, NOW()) "
        "ON CONFLICT (username, device_id) DO UPDATE SET login_count = devices.login_count + 1, last_seen = NOW()",
        (username, device_id)
    )
    
    cur.execute("SELECT message, timestamp FROM notifications WHERE target_users = 'all' OR target_users = %s ORDER BY timestamp DESC LIMIT 1", (username,))
    latest_notification = cur.fetchone()
    
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({
        'success': True, 
        'status': 'alive',
        'notification': latest_notification['message'] if latest_notification else None
    })

@app.route('/api/admin/users', methods=['GET'])
def api_get_users():
    if session.get('role') != 'admin': return jsonify({'error': 'Forbidden'}), 403
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT username, role, approval_status, internet_access, created_at FROM users")
    users_list = cur.fetchall()
    cur.close()
    conn.close()
    
    users_dict = {u['username']: dict(u) for u in users_list}
    return jsonify(users_dict)

@app.route('/api/admin/action-user', methods=['POST'])
def api_action_user():
    if session.get('role') != 'admin': return jsonify({'error': 'Forbidden'}), 403
    data = request.get_json() or {}
    username = data.get('username')
    action = data.get('action')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    if action == 'approve':
        cur.execute("UPDATE users SET approval_status = 'approved' WHERE username = %s", (username,))
    elif action == 'reject':
        cur.execute("DELETE FROM users WHERE username = %s", (username,))
    elif action == 'toggle_internet':
        cur.execute("UPDATE users SET internet_access = NOT internet_access WHERE username = %s", (username,))
        
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/admin/settings', methods=['GET', 'POST'])
def api_admin_settings():
    if session.get('role') != 'admin': return jsonify({'error': 'Forbidden'}), 403
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    if request.method == 'POST':
        data = request.get_json() or {}
        for k, v in data.items():
            val_str = 'true' if v is True else ('false' if v is False else str(v))
            cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = %s", (k, val_str, val_str))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True})
        
    cur.execute("SELECT key, value FROM settings")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    settings_dict = {}
    for r in rows:
        val = r['value']
        if val == 'true': val = True
        elif val == 'false': val = False
        settings_dict[r['key']] = val
    return jsonify(settings_dict)

@app.route('/api/public/settings', methods=['GET'])
def get_public_settings():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT key, value FROM settings")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    settings_dict = {}
    for r in rows:
        val = r['value']
        if val == 'true': val = True
        elif val == 'false': val = False
        settings_dict[r['key']] = val
    return jsonify(settings_dict)

@app.route('/api/admin/send-notification', methods=['POST'])
def send_notification():
    if session.get('role') != 'admin': return jsonify({'error': 'Forbidden'}), 403
    data = request.get_json() or {}
    message = data.get('message')
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO notifications (id, message, target_users) VALUES (%s, %s, 'all')", (str(uuid.uuid4()), message))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'success': True})