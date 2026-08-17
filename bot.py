# ============================================
# complete_pharmacy.py
# سیستم مدیریت داروخانه با تمام امکانات
# نسخه کامل - فروردین 1405
# ============================================
import sqlite3
import hashlib
import logging
import json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, session, redirect, url_for, g, send_from_directory, render_template_string
from functools import wraps
import os
import re
import sys

# ===== اصلاح 1: تابع get_iran_time_iso با فرمت صحیح =====
def get_iran_time_iso():
    iran_time = datetime.utcnow() + timedelta(hours=3, minutes=30)
    return iran_time.strftime('%Y-%m-%d %H:%M:%S')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'pharmacy-secret-key-2024')
app.config['JSON_AS_ASCII'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# ===== تغییر 1: افزودن after_request برای تمام API‌ها =====
@app.after_request
def add_no_cache_headers(response):
    """افزودن هدرهای ضد-کش به تمام پاسخ‌های API"""
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

UPLOAD_FOLDER = '/var/www/poldaroo/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DATABASE = 'pharmacy.db'

def to_persian_number(num):
    """تبدیل اعداد انگلیسی به فارسی"""
    persian_digits = {
        '0': '۰', '1': '۱', '2': '۲', '3': '۳', '4': '۴',
        '5': '۵', '6': '۶', '7': '۷', '8': '۸', '9': '۹'
    }
    return ''.join(persian_digits.get(c, c) for c in str(num))

def gregorian_to_jalali(gy, gm, gd):
    g_days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    j_days_in_month = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29]
    gy = gy - 1600
    gm = gm - 1
    gd = gd - 1
    g_day_no = 365 * gy + (gy + 3) // 4 - (gy + 99) // 100 + (gy + 399) // 400
    for i in range(gm):
        g_day_no += g_days_in_month[i]
    if gm > 1 and ((gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0)):
        g_day_no += 1
    g_day_no += gd
    j_day_no = g_day_no - 226899
    jy = (j_day_no * 100 + 322) // 36525
    j_rem = j_day_no - (jy * 36525 + 322) // 100
    jm = (j_rem * 1000 + 60000) // 1000000
    jd = j_rem - (jm * 1000000 + 60000) // 1000
    if jm == 0:
        jm = 12
        jy -= 1
        jd = 30
    elif jm == 12:
        if jd > 29:
            jd = 30
    else:
        if jd > 30:
            jd = 30
    # برگرداندن تاریخ با اعداد فارسی
    return f"{to_persian_number(jy)}/{to_persian_number(jm)}/{to_persian_number(jd)}"

def convert_date_to_jalali(date_str):
    if not date_str:
        return ''
    try:
        if 'T' in date_str:
            date_str = date_str.split('T')[0]
        parts = date_str.split('-')
        if len(parts) != 3:
            return date_str
        return gregorian_to_jalali(int(parts[0]), int(parts[1]), int(parts[2]))
    except:
        return date_str

def get_current_jalali_date():
    now = datetime.now()
    return gregorian_to_jalali(now.year, now.month, now.day)

def get_year_month_selectors(expiry_value=''):
    current_year = datetime.now().year
    current_month = datetime.now().month
    selected_year = current_year
    selected_month = current_month
    if expiry_value and '.' in expiry_value:
        try:
            parts = expiry_value.split('.')
            selected_year = int(parts[0])
            selected_month = int(parts[1])
        except:
            pass
    year_options = ''
    for y in range(current_year - 5, current_year + 6):
        selected = 'selected' if y == selected_year else ''
        year_options += f'<option value="{y}" {selected}>{y}</option>'
    month_options = ''
    for m in range(1, 13):
        selected = 'selected' if m == selected_month else ''
        month_label = f'{m:02d}'
        month_options += f'<option value="{m:02d}" {selected}>{month_label}</option>'
    return f'''
    <div class="expiry-selectors" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
        <div style="display:flex;align-items:center;gap:4px;">
            <label style="font-size:12px;color:#666;">سال:</label>
            <select class="expiry-year" style="padding:6px 8px;border:1px solid #ddd;border-radius:6px;font-size:13px;min-width:80px;">
                {year_options}
            </select>
        </div>
        <div style="display:flex;align-items:center;gap:4px;">
            <label style="font-size:12px;color:#666;">ماه:</label>
            <select class="expiry-month" style="padding:6px 8px;border:1px solid #ddd;border-radius:6px;font-size:13px;min-width:70px;">
                {month_options}
            </select>
        </div>
        <span class="expiry-preview" style="font-size:12px;color:#28a745;font-weight:bold;background:#e8f5e9;padding:4px 10px;border-radius:4px;">
            {selected_year}.{selected_month:02d}
        </span>
    </div>
    '''

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db:
        db.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_current_user_from_session():
    if not session.get('user_id'):
        return None
    if hasattr(g, 'current_user'):
        return g.current_user
    db = get_db()
    cursor = db.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],))
    g.current_user = cursor.fetchone()
    return g.current_user

def validate_expiry_date(date_str):
    if not date_str or date_str.strip() == '':
        return False
    pattern = r'^\d{4}\.(0[1-9]|1[0-2])$'
    return re.match(pattern, date_str) is not None

def parse_expiry_number(expiry_str):
    if not expiry_str or expiry_str is None or expiry_str == '':
        return 999999
    try:
        if '.' in expiry_str:
            parts = expiry_str.split('.')
            year = int(parts[0])
            month = int(parts[1])
            return year * 12 + month
    except:
        return 999999
    return 999999

def get_expiry_status(expiry_date):
    if not expiry_date or expiry_date == '':
        return {'text': 'نامشخص', 'class': ''}
    try:
        if '.' in expiry_date:
            parts = expiry_date.split('.')
            year = int(parts[0])
            month = int(parts[1])
        else:
            return {'text': 'نامعتبر', 'class': ''}
        now = datetime.now()
        exp = datetime(year, month, 1)
        months_left = (exp.year - now.year) * 12 + (exp.month - now.month)
        if months_left < 0:
            return {'text': 'منقضی', 'class': 'expired'}
        elif months_left <= 3:
            return {'text': f'{months_left} ماه مانده', 'class': 'expiring-soon'}
        else:
            return {'text': f'{months_left} ماه مانده', 'class': 'good-expiry'}
    except:
        return {'text': 'نامعتبر', 'class': ''}

def mask_pharmacy_name(name):
    if not name or len(name) <= 4:
        return name
    return name[:3] + '...' + name[-2:]

def cleanup_expired_items():
    db = get_db()
    try:
        db.execute("DELETE FROM inventory WHERE expiry_date IS NOT NULL AND expiry_date != '' AND substr(expiry_date, 1, 4) || substr(expiry_date, 6, 2) < strftime('%Y%m', 'now')")
        db.commit()
    except:
        pass

def init_db():
    db = get_db()
    db.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        is_full_user INTEGER DEFAULT 0,
        pharmacy_display_name TEXT NOT NULL,
        created_at TEXT NOT NULL,
        phone_number TEXT,
        address TEXT,
        is_approved INTEGER DEFAULT 1
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS drugs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        type TEXT NOT NULL,
        priority INTEGER DEFAULT 4,
        created_at TEXT NOT NULL,
        ordered BOOLEAN DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        company TEXT NOT NULL,
        drug_name TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        ordered_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        batch_number TEXT,
        expiry_date TEXT,
        manufacturer TEXT,
        registered_by TEXT,
        created_at TEXT,
        invoice_number TEXT,
        supplier TEXT,
        purchase_price REAL,
        category TEXT DEFAULT 'other',
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        drug_name TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        sale_date TEXT,
        expiry_date TEXT,
        invoice_number TEXT,
        customer_name TEXT,
        price REAL,
        location TEXT,
        created_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS companies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS exchanges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        buyer_name TEXT NOT NULL,
        drug_name TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        expiry_date TEXT,
        location TEXT,
        exchange_date TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        batch_number TEXT,
        invoice_number TEXT,
        target_pharmacy_id INTEGER DEFAULT NULL,
        category TEXT DEFAULT 'other',
        sender_categories TEXT DEFAULT '',
        my_items_json TEXT DEFAULT '',
        target_items_json TEXT DEFAULT '',
        source_pharmacy_id INTEGER DEFAULT NULL,
        source_pharmacy_name TEXT DEFAULT '',
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS user_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL UNIQUE,
        categories TEXT DEFAULT '',
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS hidden_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS interviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pharmacist_name TEXT NOT NULL,
        pharmacy_name TEXT NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        image_url TEXT DEFAULT '',
        audio_url TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        is_published INTEGER DEFAULT 1,
        views INTEGER DEFAULT 0
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS announcements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL,
        is_active INTEGER DEFAULT 1
    )''')
    
    try:
        db.execute("ALTER TABLE users ADD COLUMN phone_number TEXT")
    except:
        pass
    try:
        db.execute("ALTER TABLE users ADD COLUMN address TEXT")
    except:
        pass
    try:
        db.execute("ALTER TABLE users ADD COLUMN is_approved INTEGER DEFAULT 1")
    except:
        pass
    try:
        db.execute("ALTER TABLE interviews ADD COLUMN audio_url TEXT DEFAULT ''")
    except:
        pass
    try:
        db.execute("ALTER TABLE inventory ADD COLUMN category TEXT DEFAULT 'other'")
    except:
        pass
    try:
        db.execute("ALTER TABLE inventory ADD COLUMN registered_by TEXT DEFAULT ''")
    except:
        pass
    try:
        db.execute("ALTER TABLE exchanges ADD COLUMN sender_categories TEXT DEFAULT ''")
    except:
        pass
    try:
        db.execute("ALTER TABLE exchanges ADD COLUMN my_items_json TEXT DEFAULT ''")
    except:
        pass
    try:
        db.execute("ALTER TABLE exchanges ADD COLUMN target_items_json TEXT DEFAULT ''")
    except:
        pass
    try:
        db.execute("ALTER TABLE exchanges ADD COLUMN source_pharmacy_id INTEGER DEFAULT NULL")
    except:
        pass
    try:
        db.execute("ALTER TABLE exchanges ADD COLUMN source_pharmacy_name TEXT DEFAULT ''")
    except:
        pass
    
    users = [
        ('admin', 'admin123', 'مدیر سیستم', 1),
        ('nosratabadi', 'admin123', 'داروخانه نصرت‌آبادی', 1),
        ('soleymani', 'soleymani123', 'داروخانه سلیمانی', 1),
        ('A101', 'drsaboori', 'داروخانه A101', 1),
        ('A102', 'drjafari', 'داروخانه A102', 1)
    ]
    for username, password, display, is_full in users:
        cursor = db.execute("SELECT COUNT(*) as count FROM users WHERE username = ?", (username,))
        if cursor.fetchone()['count'] == 0:
            db.execute("INSERT INTO users (username, password_hash, is_full_user, pharmacy_display_name, created_at, is_approved) VALUES (?, ?, ?, ?, ?, ?)",
                       (username, hash_password(password), is_full, display, datetime.now().isoformat(), 1))
    
    cursor = db.execute("SELECT id FROM users")
    all_users = cursor.fetchall()
    for u in all_users:
        cursor2 = db.execute("SELECT COUNT(*) as count FROM user_categories WHERE user_id = ?", (u['id'],))
        if cursor2.fetchone()['count'] == 0:
            db.execute("INSERT INTO user_categories (user_id, categories) VALUES (?, ?)", (u['id'], ''))
    
    companies = ['داروپخش', 'البرز', 'اکسیر', 'رازی']
    for c in companies:
        db.execute("INSERT OR IGNORE INTO companies (name) VALUES (?)", (c,))
    
    for username, password, display, is_full in users:
        cursor = db.execute("SELECT id FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        if user:
            user_id = user['id']
            cursor = db.execute("SELECT COUNT(*) as count FROM inventory WHERE user_id = ?", (user_id,))
            if cursor.fetchone()['count'] == 0:
                sample_data = [
                    ('آسپرین', 100, '2026.03', 'admin'),
                    ('آسپرین', 50, '2025.12', 'admin'),
                    ('ایبوپروفن', 75, '2025.09', 'admin'),
                    ('ایبوپروفن', 30, '2026.01', 'admin'),
                    ('آمپی سیلین', 40, '2025.06', 'admin'),
                    ('آمپی سیلین', 20, '2025.08', 'admin'),
                    ('دیازپام', 60, '2026.02', 'admin'),
                    ('دیازپام', 25, '2026.04', 'admin'),
                    ('لوزارتان', 45, '2026.05', 'admin'),
                    ('مترونیدازول', 80, '2025.11', 'admin'),
                    ('سفالکسین', 35, '2025.10', 'admin'),
                    ('آموکسی سیلین', 120, '2026.08', 'admin'),
                ]
                for name, qty, expiry, registered_by in sample_data:
                    db.execute('''INSERT INTO inventory (user_id, name, quantity, expiry_date, registered_by, created_at)
                                  VALUES (?, ?, ?, ?, ?, ?)''',
                               (user_id, name, qty, expiry, registered_by, datetime.now().isoformat()))
    
    cleanup_expired_items()
    db.commit()

with app.app_context():
    init_db()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        if session.get('username') != 'admin':
            return "⛔ دسترسی غیرمجاز. فقط ادمین می‌تواند وارد این بخش شود.", 403
        return f(*args, **kwargs)
    return decorated

# ===== قالب HTML یکپارچه =====
HTML = '''<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
    <title>داروخانه</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Tahoma', 'Segoe UI', sans-serif; background: #f5f5f5; color: #1a1a1a; }
        .topbar {
            background: #1a1a1a;
            color: white;
            padding: 6px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            z-index: 9999;
            flex-wrap: wrap;
            gap: 5px;
        }
        .topbar .brand { font-size: 16px; font-weight: bold; color: white; text-decoration: none; }
        .topbar .brand span { color: #4fc3f7; }
        .topbar .nav-links { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
        .topbar .nav-links a {
            color: #e0e0e0;
            text-decoration: none;
            font-size: 12px;
            padding: 3px 8px;
            border-radius: 6px;
            transition: all 0.3s;
        }
        .topbar .nav-links a:hover { background: #333; color: white; }
        .topbar .nav-links a.active { background: #333; color: white; }
        .topbar .nav-links .btn-login { background: #4fc3f7; color: #1a1a1a; padding: 3px 12px; border-radius: 6px; font-weight: bold; font-size: 12px; }
        .topbar .nav-links .btn-login:hover { background: #81d4fa; }
        .topbar .nav-links .btn-register { background: #28a745; color: white; padding: 3px 12px; border-radius: 6px; font-weight: bold; font-size: 12px; }
        .topbar .nav-links .btn-register:hover { background: #34ce57; }
        .topbar .nav-links .btn-logout { background: #dc3545; color: white; padding: 3px 10px; border-radius: 6px; font-size: 12px; }
        .topbar .nav-links .btn-logout:hover { background: #c82333; }
        .topbar .user-badge { background: #333; padding: 3px 10px; border-radius: 20px; font-size: 11px; color: #aaa; }
        .topbar .user-badge strong { color: white; }
        .sidebar {
            position: fixed;
            right: 0;
            top: 46px;
            width: 200px;
            height: calc(100% - 46px);
            background: #1a1a1a;
            color: white;
            z-index: 1000;
            overflow-y: auto;
        }
        .sidebar-menu { list-style: none; padding: 8px 0; }
        .sidebar-menu li { margin-bottom: 2px; }
        .sidebar-menu a {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 8px 16px;
            color: #e0e0e0;
            text-decoration: none;
            transition: all 0.3s;
            font-size: 13px;
        }
        .sidebar-menu a:hover { background: #333; color: white; }
        .sidebar-menu a.active { background: #2c2c2c; border-right: 3px solid #4fc3f7; }
        .sidebar-menu .admin-link { border-right: 3px solid #ffc107; }
        .main-content {
            margin-right: 200px;
            margin-top: 46px;
            padding: 15px;
            min-height: calc(100vh - 46px);
        }
        .header {
            background: white;
            border-radius: 10px;
            padding: 10px 18px;
            margin-bottom: 15px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .page-title { font-size: 17px; font-weight: 600; }
        .user-info { display: flex; gap: 12px; align-items: center; font-size: 12px; }
        .card {
            background: white;
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 15px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .card-title {
            font-size: 15px;
            font-weight: 600;
            margin-bottom: 10px;
            padding-bottom: 6px;
            border-bottom: 2px solid #e0e0e0;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 12px;
            margin-bottom: 15px;
        }
        .stat-card {
            background: white;
            padding: 10px;
            border-radius: 10px;
            text-align: center;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .stat-card .number { font-size: 22px; font-weight: bold; }
        .stat-card .label { color: #666; font-size: 11px; margin-top: 4px; }
        .form-row {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            margin-bottom: 10px;
            align-items: center;
        }
        .form-row input, .form-row select, .form-row textarea {
            flex: 1;
            min-width: 120px;
            padding: 7px 10px;
            border: 1px solid #ddd;
            border-radius: 6px;
            font-size: 13px;
        }
        .form-row textarea { min-height: 70px; resize: vertical; }
        button {
            background: #1a1a1a;
            color: white;
            border: none;
            padding: 7px 14px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            transition: all 0.3s;
        }
        button:hover { opacity: 0.85; }
        .btn-danger { background: #dc3545; }
        .btn-success { background: #28a745; }
        .btn-warning { background: #ffc107; color: #1a1a1a; }
        .btn-primary { background: #007bff; }
        .btn-sm { padding: 3px 8px; font-size: 11px; }
        .table-responsive { overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        table th, table td { padding: 8px 10px; text-align: center; border-bottom: 1px solid #eee; }
        table th { background: #f0f0f0; font-weight: bold; }
        table tr:hover { background: #f9f9f9; }
        .badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 20px;
            font-size: 11px;
        }
        .badge-success { background: #d4edda; color: #155724; }
        .badge-danger { background: #f8d7da; color: #721c24; }
        .badge-warning { background: #fff3cd; color: #856404; }
        .badge-info { background: #d1ecf1; color: #0c5460; }
        .interview-card {
            background: white;
            border-radius: 10px;
            padding: 14px;
            margin-bottom: 12px;
            border: 1px solid #e0e0e0;
        }
        .interview-card h3 { margin-bottom: 6px; color: #1a1a1a; font-size: 16px; }
        .interview-card .meta { font-size: 11px; color: #666; margin-bottom: 8px; }
        .interview-card .content { font-size: 13px; line-height: 1.8; }
        .interview-card .media { margin-top: 8px; }
        .interview-card .media img { max-width: 100%; border-radius: 6px; max-height: 300px; }
        .interview-card .media audio { width: 100%; }
        .exchange-tab { display: flex; gap: 8px; margin-bottom: 15px; border-bottom: 2px solid #e0e0e0; }
        .exchange-tab button { background: none; color: #1a1a1a; border: none; padding: 8px 16px; font-size: 13px; cursor: pointer; border-radius: 0; }
        .exchange-tab button.active { border-bottom: 3px solid #1a1a1a; font-weight: bold; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .deficit-table { width: 100%; border-collapse: collapse; }
        .deficit-table th, .deficit-table td { padding: 8px; text-align: center; border-bottom: 1px solid #eee; }
        .deficit-table th { background: #f0f0f0; font-weight: bold; }
        .search-container { position: relative; flex: 1; }
        .suggestions-list {
            position: absolute;
            top: 100%;
            left: 0;
            right: 0;
            background: white;
            border: 1px solid #ddd;
            border-radius: 6px;
            max-height: 200px;
            overflow-y: auto;
            z-index: 1000;
            display: none;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
        }
        .suggestions-list div { padding: 8px; cursor: pointer; border-bottom: 1px solid #eee; font-size: 13px; }
        .suggestions-list div:hover { background: #f0f0f0; }
        .suggestions-list .stock-info { font-size: 11px; color: #666; margin-top: 3px; }
        .exchange-dual-container { display: flex; gap: 15px; flex-wrap: wrap; }
        .exchange-list-box { flex: 1; min-width: 250px; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .exchange-list-header { background: #1a1a1a; color: white; padding: 10px; text-align: center; font-weight: bold; font-size: 13px; }
        .exchange-list-header.active { background: #28a745; }
        .exchange-list-items { max-height: 350px; overflow-y: auto; padding: 5px; }
        .exchange-drug-item { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-bottom: 1px solid #eee; cursor: pointer; border-radius: 4px; font-size: 13px; }
        .exchange-drug-item:hover { background: #f5f5f5; }
        .exchange-drug-item.selected { background: #d4edda; }
        .exchange-card {
            background: white;
            border-radius: 10px;
            margin-bottom: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            overflow: hidden;
            border: 1px solid #e0e0e0;
        }
        .exchange-card-header {
            background: #1a1a1a;
            color: white;
            padding: 10px 14px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 6px;
            font-size: 13px;
        }
        .exchange-card-body {
            padding: 12px 14px;
        }
        .exchange-card-footer {
            padding: 8px 14px;
            background: #f8f9fa;
            display: flex;
            gap: 8px;
            justify-content: flex-end;
            border-top: 1px solid #e0e0e0;
        }
        .exchange-section {
            margin-bottom: 10px;
        }
        .exchange-section-title {
            font-weight: bold;
            font-size: 13px;
            margin-bottom: 6px;
        }
        .exchange-drug-list {
            list-style: none;
            padding: 0;
        }
        .exchange-drug-list li {
            padding: 4px 0;
            border-bottom: 1px solid #f0f0f0;
            font-size: 13px;
            display: flex;
            justify-content: space-between;
        }
        .exchange-drug-list li:last-child {
            border-bottom: none;
        }
        .status-pending { background: #ffc107; color: #1a1a1a; padding: 2px 8px; border-radius: 20px; font-size: 11px; }
        .status-confirmed { background: #28a745; color: white; padding: 2px 8px; border-radius: 20px; font-size: 11px; }
        .drugs-columns { display: flex; gap: 15px; flex-wrap: wrap; }
        .drugs-column { flex: 1; min-width: 220px; background: #fafafa; border-radius: 10px; padding: 10px; }
        .drugs-column h4 { margin-bottom: 10px; padding-bottom: 6px; border-bottom: 2px solid #ddd; font-size: 14px; }
        .dashboard-tab { display: flex; gap: 8px; margin-bottom: 15px; border-bottom: 2px solid #e0e0e0; }
        .dashboard-tab button { background: none; color: #1a1a1a; border: none; padding: 8px 16px; font-size: 13px; cursor: pointer; border-radius: 0; }
        .dashboard-tab button.active { border-bottom: 3px solid #1a1a1a; font-weight: bold; }
        .toolbar { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; align-items: center; }
        .toolbar button { font-size: 11px; padding: 5px 12px; }
        .export-btn { background: #17a2b8; }
        .expiry-tab { border: 1px solid #e0e0e0; border-radius: 10px; margin-bottom: 10px; overflow: hidden; }
        .expiry-tab-header { padding: 10px 14px; font-weight: bold; cursor: pointer; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px; font-size: 13px; }
        .expiry-tab-body { display: none; padding: 8px 12px; background: #fafafa; }
        .expiry-tab-body.show { display: block; }
        .pharmacy-group { border: 1px solid #ddd; border-radius: 6px; margin-bottom: 6px; overflow: hidden; }
        .pharmacy-group-header { background: #f0f0f0; padding: 8px 12px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 4px; font-weight: bold; font-size: 13px; }
        .pharmacy-group-body { display: none; padding: 6px 10px; background: white; }
        .pharmacy-group-body.show { display: block; }
        .drug-item { display: flex; align-items: center; gap: 10px; padding: 5px 8px; border-bottom: 1px solid #f0f0f0; flex-wrap: wrap; font-size: 13px; }
        .drug-item:last-child { border-bottom: none; }
        .drug-item .drug-name { font-weight: bold; flex: 1; min-width: 80px; cursor: pointer; color: #007bff; }
        .drug-item .drug-name:hover { text-decoration: underline; }
        .drug-item .drug-qty { color: #555; }
        .drug-item .drug-registered { font-size: 10px; padding: 2px 6px; border-radius: 10px; background: #e3f2fd; color: #084298; }
        .toast-message {
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: #1a1a1a;
            color: white;
            padding: 12px 24px;
            border-radius: 10px;
            z-index: 99999;
            font-size: 14px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            max-width: 90%;
            display: none;
        }
        .toast-message.success { background: #28a745; }
        .toast-message.error { background: #dc3545; }
        .toast-message.info { background: #17a2b8; }
        .drug-item .drug-actions { display: flex; gap: 4px; align-items: center; }
        .drug-item .drug-actions button { padding: 2px 6px; font-size: 10px; border-radius: 4px; }
        .drug-date { font-size: 11px; color: #999; }
        .name-display {
            background: #e8f5e9;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            color: #2e7d32;
            font-weight: bold;
        }
        @media (max-width: 768px) {
            .sidebar { width: 55px; }
            .sidebar .menu-text { display: none; }
            .main-content { margin-right: 55px; padding: 10px; }
            .topbar .brand { font-size: 13px; }
            .topbar .nav-links a { font-size: 10px; padding: 2px 6px; }
            .exchange-dual-container { flex-direction: column; }
            .month-grid { grid-template-columns: repeat(3, 1fr); }
        }
    </style>
</head>
<body>
    <div id="toast" class="toast-message"></div>
    <div class="topbar">
        <a href="/" class="brand">💊 <span>دارو</span>خانه</a>
        <div class="nav-links">
            <a href="/">🏠 صفحه اصلی</a>
            <a href="/dashboard">📊 داشبورد</a>
            <a href="/inventory">📦 انبارداری</a>
            <a href="/exchange">🔄 تبادل</a>
            <a href="/deficit">📋 کسری</a>
            {% if session.username == 'admin' %}
                <a href="/admin" style="color:#ffc107;">👑 ادمین</a>
            {% endif %}
            {% if session.logged_in %}
                <span class="user-badge">👤 <strong>{{ session.pharmacy_display_name }}</strong></span>
                <a href="/logout" class="btn-logout">🚪 خروج</a>
            {% else %}
                <a href="/login" class="btn-login">🔐 ورود</a>
                <a href="/register" class="btn-register">📝 ثبت‌نام</a>
            {% endif %}
        </div>
    </div>
    <div class="sidebar">
        <ul class="sidebar-menu">
            <li><a href="/"><span>🏠</span> <span class="menu-text">صفحه اصلی</span></a></li>
            <li><a href="/dashboard"><span>📊</span> <span class="menu-text">داشبورد</span></a></li>
            <li><a href="/inventory"><span>📦</span> <span class="menu-text">انبارداری</span></a></li>
            <li><a href="/exchange"><span>🔄</span> <span class="menu-text">تبادل دارو</span></a></li>
            <li><a href="/deficit"><span>📋</span> <span class="menu-text">دفتر کسری</span></a></li>
            {% if session.username == 'admin' %}
                <li><a href="/admin" class="admin-link"><span>👑</span> <span class="menu-text">پنل ادمین</span></a></li>
            {% endif %}
        </ul>
    </div>
    <div class="main-content">
        <div class="header">
            <div class="page-title">{{ page_title }}</div>
            <div class="user-info">
                {% if session.logged_in %}
                    <span>👤 {{ session.pharmacy_display_name }}</span>
                {% else %}
                    <span>👤 مهمان</span>
                {% endif %}
            </div>
        </div>
        {{ content|safe }}
    </div>
    <script>
        function showToast(message, type) {
            var toast = document.getElementById('toast');
            toast.textContent = message;
            toast.className = 'toast-message ' + (type || 'info');
            toast.style.display = 'block';
            setTimeout(function() {
                toast.style.display = 'none';
            }, 3000);
        }
        function confirmAction(message, callback) {
            if (confirm(message)) {
                callback();
            }
        }
    </script>
</body>
</html>'''

# ===== روت‌های اصلی =====

@app.route('/')
def index():
    db = get_db()
    cursor = db.execute("SELECT * FROM interviews WHERE is_published = 1 ORDER BY created_at DESC")
    interviews = cursor.fetchall()
    cursor = db.execute("SELECT * FROM announcements WHERE is_active = 1 ORDER BY created_at DESC LIMIT 3")
    announcements = cursor.fetchall()
    content = '<div class="card"><div class="card-title">🎙️ مصاحبه با داروسازان</div>'
    if interviews:
        for i in interviews:
            content += f'''
            <div class="interview-card">
                <h3>{i['title']}</h3>
                <div class="meta">👤 {i['pharmacist_name']} | 🏥 {i['pharmacy_name']} | 📅 {i['created_at'][:10]}</div>
                <div class="content">{i['content']}</div>
                <div class="media">
                    {f'<img src="{i["image_url"]}" alt="{i["title"]}" style="max-width:100%;border-radius:6px;max-height:300px;">' if i['image_url'] else ''}
                    {f'<audio controls style="width:100%;"><source src="{i["audio_url"]}"></audio>' if i['audio_url'] else ''}
                </div>
            </div>
            '''
    else:
        content += '<p style="text-align:center;padding:30px;color:#999;">هنوز مصاحبه‌ای ثبت نشده است</p>'
    content += '</div>'
    if announcements:
        content += '''
        <div class="card" style="background:#e3f2fd;border:1px solid #90caf9;">
            <div class="card-title">📢 اطلاعیه‌ها</div>
        '''
        for a in announcements:
            content += f'''
            <div style="padding:8px 0;border-bottom:1px solid #e0e0e0;">
                <strong>{a['title']}</strong>
                <p style="font-size:13px;color:#555;margin-top:4px;">{a['content']}</p>
                <span style="font-size:11px;color:#999;">{a['created_at'][:10]}</span>
            </div>
            '''
        content += '</div>'
    return render_template_string(HTML, content=content, page_title='صفحه اصلی', session=session)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        db = get_db()
        cursor = db.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        if user and user['password_hash'] == hash_password(password):
            try:
                is_approved = user['is_approved']
            except:
                is_approved = 1
            if is_approved == 0:
                return '''
                <!DOCTYPE html>
                <html dir="rtl" lang="fa">
                <head><meta charset="UTF-8"><title>ورود</title>
                <style>
                    body { font-family: Tahoma, sans-serif; background: #f5f5f5; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
                    .login-box { background: white; padding: 30px; border-radius: 16px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); width: 340px; text-align: center; }
                    .login-box h2 { margin-bottom: 20px; color: #1a1a1a; }
                    .warning { color: #856404; margin-top: 10px; font-size: 13px; background: #fff3cd; padding: 10px; border-radius: 8px; }
                    .back-link { display: block; margin-top: 15px; color: #007bff; text-decoration: none; }
                </style>
                </head>
                <body>
                <div class="login-box">
                    <h2>🏥 ورود</h2>
                    <div class="warning">⏳ حساب کاربری شما در انتظار تأیید ادمین است.</div>
                    <a href="/" class="back-link">← بازگشت به صفحه اصلی</a>
                </div>
                </body>
                </html>
                '''
            if is_approved == 2:
                return '''
                <!DOCTYPE html>
                <html dir="rtl" lang="fa">
                <head><meta charset="UTF-8"><title>ورود</title>
                <style>
                    body { font-family: Tahoma, sans-serif; background: #f5f5f5; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
                    .login-box { background: white; padding: 30px; border-radius: 16px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); width: 340px; text-align: center; }
                    .login-box h2 { margin-bottom: 20px; color: #1a1a1a; }
                    .warning { color: #721c24; margin-top: 10px; font-size: 13px; background: #f8d7da; padding: 10px; border-radius: 8px; }
                    .back-link { display: block; margin-top: 15px; color: #007bff; text-decoration: none; }
                </style>
                </head>
                <body>
                <div class="login-box">
                    <h2>🏥 ورود</h2>
                    <div class="warning">❌ حساب کاربری شما رد شده است. با ادمین تماس بگیرید.</div>
                    <a href="/" class="back-link">← بازگشت به صفحه اصلی</a>
                </div>
                </body>
                </html>
                '''
            session.clear()
            session['logged_in'] = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_full_user'] = user['is_full_user']
            session['pharmacy_display_name'] = user['pharmacy_display_name']
            session['is_approved'] = is_approved
            session['registered_name'] = user['pharmacy_display_name']  # تنظیم نام پیش‌فرض
            return redirect(url_for('index'))
        
        return '''
        <!DOCTYPE html>
        <html dir="rtl" lang="fa">
        <head><meta charset="UTF-8"><title>ورود</title>
        <style>
            body { font-family: Tahoma, sans-serif; background: #f5f5f5; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
            .login-box { background: white; padding: 30px; border-radius: 16px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); width: 340px; text-align: center; }
            .login-box h2 { margin-bottom: 20px; color: #1a1a1a; }
            .login-box input { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; }
            .login-box button { width: 100%; padding: 10px; background: #1a1a1a; color: white; border: none; border-radius: 8px; font-size: 14px; cursor: pointer; }
            .error { color: #dc3545; margin-top: 10px; font-size: 13px; }
            .back-link { display: block; margin-top: 15px; color: #007bff; text-decoration: none; }
        </style>
        </head>
        <body>
        <div class="login-box">
            <h2>🏥 ورود</h2>
            <form method="post">
                <input type="text" name="username" placeholder="نام کاربری" required>
                <input type="password" name="password" placeholder="رمز عبور" required>
                <button type="submit">ورود</button>
            </form>
            <div class="error">❌ نام کاربری یا رمز عبور اشتباه است</div>
            <a href="/" class="back-link">← بازگشت به صفحه اصلی</a>
        </div>
        </body>
        </html>
        '''
    
    return '''
    <!DOCTYPE html>
    <html dir="rtl" lang="fa">
    <head><meta charset="UTF-8"><title>ورود</title>
    <style>
        body { font-family: Tahoma, sans-serif; background: #f5f5f5; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-box { background: white; padding: 30px; border-radius: 16px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); width: 340px; text-align: center; }
        .login-box h2 { margin-bottom: 20px; color: #1a1a1a; }
        .login-box input { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; }
        .login-box button { width: 100%; padding: 10px; background: #1a1a1a; color: white; border: none; border-radius: 8px; font-size: 14px; cursor: pointer; }
        .register-link { display: block; margin-top: 15px; color: #28a745; text-decoration: none; }
        .back-link { display: block; margin-top: 5px; color: #007bff; text-decoration: none; }
    </style>
    </head>
    <body>
    <div class="login-box">
        <h2>🏥 ورود</h2>
        <form method="post">
            <input type="text" name="username" placeholder="نام کاربری" required>
            <input type="password" name="password" placeholder="رمز عبور" required>
            <button type="submit">ورود</button>
        </form>
        <a href="/register" class="register-link">📝 ثبت‌نام</a>
        <a href="/" class="back-link">← بازگشت به صفحه اصلی</a>
    </div>
    </body>
    </html>
    '''

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        pharmacy_name = request.form.get('pharmacy_name')
        phone_number = request.form.get('phone_number')
        address = request.form.get('address')
        
        if not username or not password or not pharmacy_name:
            return '❌ همه فیلدهای اجباری را پر کنید'
        if len(username) < 3:
            return '❌ نام کاربری باید حداقل 3 کاراکتر باشد'
        if len(password) < 4:
            return '❌ رمز عبور باید حداقل 4 کاراکتر باشد'
        if password != confirm_password:
            return '❌ رمز عبور و تکرار آن مطابقت ندارند'
        if ' ' in username:
            return '❌ نام کاربری نباید شامل فاصله باشد'
        if phone_number and not re.match(r'^09[0-9]{9}$', phone_number):
            return '❌ شماره همراه نامعتبر است. فرمت صحیح: 09121234567'
        
        db = get_db()
        cursor = db.execute("SELECT COUNT(*) as count FROM users WHERE username = ?", (username,))
        if cursor.fetchone()['count'] > 0:
            return '❌ این نام کاربری قبلاً ثبت شده است'
        
        db.execute('''INSERT INTO users (username, password_hash, is_full_user, pharmacy_display_name, created_at, phone_number, address, is_approved)
                      VALUES (?, ?, ?, ?, ?, ?, ?, 0)''',
                   (username, hash_password(password), 0, pharmacy_name, datetime.now().isoformat(), phone_number, address))
        db.commit()
        
        cursor = db.execute("SELECT id FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        if user:
            db.execute("INSERT INTO user_categories (user_id, categories) VALUES (?, ?)", (user['id'], ''))
            db.commit()
        
        return '''
        <!DOCTYPE html>
        <html dir="rtl" lang="fa">
        <head><meta charset="UTF-8"><title>ثبت‌نام</title>
        <style>
            body { font-family: Tahoma, sans-serif; background: #f5f5f5; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
            .box { background: white; padding: 30px; border-radius: 16px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); width: 380px; text-align: center; }
            .box h2 { margin-bottom: 20px; color: #28a745; }
            .box p { color: #555; line-height: 1.8; }
            .back-link { display: block; margin-top: 15px; color: #007bff; text-decoration: none; }
        </style>
        </head>
        <body>
        <div class="box">
            <h2>✅ ثبت‌نام موفق</h2>
            <p>حساب کاربری شما با موفقیت ایجاد شد.<br>
            پس از تأیید توسط ادمین، می‌توانید وارد شوید.</p>
            <a href="/" class="back-link">← بازگشت به صفحه اصلی</a>
        </div>
        </body>
        </html>
        '''
    
    return '''
    <!DOCTYPE html>
    <html dir="rtl" lang="fa">
    <head><meta charset="UTF-8"><title>ثبت‌نام</title>
    <style>
        body { font-family: Tahoma, sans-serif; background: #f5f5f5; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 20px; }
        .register-box { background: white; padding: 30px; border-radius: 16px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); width: 380px; text-align: center; }
        .register-box h2 { margin-bottom: 20px; color: #1a1a1a; }
        .register-box input { width: 100%; padding: 10px; margin: 8px 0; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; box-sizing: border-box; }
        .register-box button { width: 100%; padding: 10px; background: #28a745; color: white; border: none; border-radius: 8px; font-size: 14px; cursor: pointer; }
        .register-box .field-label { text-align: right; font-size: 13px; color: #555; margin-top: 5px; }
        .register-box .help-text { font-size: 11px; color: #999; text-align: right; }
        .back-link { display: block; margin-top: 15px; color: #007bff; text-decoration: none; }
        .login-link { display: block; margin-top: 5px; color: #28a745; text-decoration: none; }
    </style>
    </head>
    <body>
    <div class="register-box">
        <h2>📝 ثبت‌نام</h2>
        <form method="post">
            <div class="field-label">نام کاربری *</div>
            <input type="text" name="username" placeholder="حداقل 3 کاراکتر (هر زبانی)" required>
            <div class="field-label">رمز عبور *</div>
            <input type="password" name="password" placeholder="حداقل 4 کاراکتر" required>
            <div class="field-label">تکرار رمز عبور *</div>
            <input type="password" name="confirm_password" placeholder="تکرار رمز عبور" required>
            <div class="field-label">نام داروخانه *</div>
            <input type="text" name="pharmacy_name" placeholder="نام کامل داروخانه" required>
            <div class="field-label">شماره همراه</div>
            <input type="tel" name="phone_number" placeholder="مثال: 09121234567">
            <div class="help-text">فرمت: 09XXXXXXXXX</div>
            <div class="field-label">آدرس</div>
            <input type="text" name="address" placeholder="آدرس کامل داروخانه">
            <button type="submit">ثبت‌نام</button>
        </form>
        <a href="/login" class="login-link">← قبلاً ثبت‌نام کرده‌اید؟ ورود</a>
        <a href="/" class="back-link">← بازگشت به صفحه اصلی</a>
    </div>
    </body>
    </html>
    '''

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# ===== ادامه کد =====

# ===== داشبورد =====
@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    user_id = session['user_id']
    
    cursor = db.execute("SELECT COUNT(*) as count FROM drugs WHERE user_id = ? AND ordered = 0", (user_id,))
    total_drugs = cursor.fetchone()['count']
    
    cursor = db.execute("SELECT COUNT(*) as count FROM orders WHERE user_id = ?", (user_id,))
    total_orders = cursor.fetchone()['count']
    
    cursor = db.execute("SELECT SUM(quantity) as total FROM inventory WHERE user_id = ?", (user_id,))
    total_inventory = cursor.fetchone()['total'] or 0
    
    cursor = db.execute("SELECT COUNT(*) as count FROM exchanges WHERE user_id = ?", (user_id,))
    total_exchanges = cursor.fetchone()['count']
    
    cursor = db.execute("SELECT * FROM drugs WHERE user_id = ? AND ordered = 0 ORDER BY priority ASC, created_at DESC", (user_id,))
    drugs = cursor.fetchall()
    
    drugs_html = ''
    quota_html = ''
    normal_html = ''
    for d in drugs:
        drug_html = f'''
        <div style="padding:8px;margin:5px 0;background:#f8f8f8;border-radius:8px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            <input type="checkbox" class="chk" data-id="{d['id']}">
            <span style="flex:1"><strong>{d['name']}</strong> - {d['quantity']} عدد</span>
            <input type="number" class="qty-{d['id']}" value="{d['quantity']}" style="width:70px;padding:4px">
        </div>
        '''
        if d['type'] == 'quota':
            quota_html += drug_html
        else:
            normal_html += drug_html
    
    cursor = db.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY ordered_at DESC", (user_id,))
    orders = cursor.fetchall()
    
    orders_html = ''
    if orders:
        for o in orders:
            orders_html += f'''
            <tr>
                <td>{o['company']}</td>
                <td><strong>{o['drug_name']}</strong></td>
                <td>{o['quantity']}</td>
                <td>{o['ordered_at'][:10]}</td>
            </tr>
            '''
    else:
        orders_html = '<tr><td colspan="4" style="text-align:center;padding:20px;color:#999;">هیچ سفارشی ثبت نشده است</td></tr>'
    
    content = f'''
    <div class="dashboard-tab">
        <button class="active" onclick="showDashboardTab('assistant')">📋 دستیار خرید</button>
        <button onclick="showDashboardTab('orders')">📜 سفارشات ثبت شده</button>
    </div>
    
    <div id="assistantTab" class="tab-content active">
        <div class="stats-grid">
            <div class="stat-card"><div class="number">{total_drugs}</div><div class="label">💊 کل داروهای کسری</div></div>
            <div class="stat-card"><div class="number">{len([d for d in drugs if d['type'] == 'quota'])}</div><div class="label">📦 سهمیه ای</div></div>
            <div class="stat-card"><div class="number">{len([d for d in drugs if d['type'] != 'quota'])}</div><div class="label">📦 عادی</div></div>
        </div>
        <div class="card">
            <div class="card-title">📋 دستیار خرید</div>
            <div class="form-row">
                <select id="company">
                    <option value="داروپخش">داروپخش</option>
                    <option value="البرز">البرز</option>
                    <option value="اکسیر">اکسیر</option>
                    <option value="رازی">رازی</option>
                </select>
                <button onclick="submitOrder()">📦 ثبت سفارش</button>
            </div>
            <div class="drugs-columns">
                <div class="drugs-column">
                    <h4>📦 سهمیه ای</h4>
                    <div id="quotaDrugsList">{quota_html or '<p style="text-align:center;padding:20px;color:#999">هیچ داروی سهمیه‌ای وجود ندارد</p>'}</div>
                </div>
                <div class="drugs-column">
                    <h4>📦 عادی</h4>
                    <div id="normalDrugsList">{normal_html or '<p style="text-align:center;padding:20px;color:#999">هیچ داروی عادی وجود ندارد</p>'}</div>
                </div>
            </div>
        </div>
    </div>
    
    <div id="ordersTab" class="tab-content">
        <div class="card">
            <div class="card-title">🔍 فیلتر سفارشات</div>
            <div class="form-row">
                <select id="companyFilter">
                    <option value="all">همه شرکت ها</option>
                    <option value="داروپخش">داروپخش</option>
                    <option value="البرز">البرز</option>
                    <option value="اکسیر">اکسیر</option>
                    <option value="رازی">رازی</option>
                </select>
                <input type="text" id="searchFilter" placeholder="جستجوی نام دارو...">
                <button onclick="resetFilters()">حذف فیلتر</button>
            </div>
        </div>
        <div class="card">
            <div class="card-title">📋 لیست سفارشات</div>
            <div style="max-height:400px;overflow-y:auto;">
                <table style="width:100%;border-collapse:collapse;font-size:13px">
                    <thead><tr><th>شرکت</th><th>نام دارو</th><th>تعداد</th><th>تاریخ سفارش</th></tr></thead>
                    <tbody id="ordersList">{orders_html}</tbody>
                </table>
            </div>
        </div>
    </div>
    
    <script>
    function showToast(message, type) {{
        var toast = document.getElementById('toast');
        toast.textContent = message;
        toast.className = 'toast-message ' + (type || 'info');
        toast.style.display = 'block';
        setTimeout(function() {{
            toast.style.display = 'none';
        }}, 3000);
    }}
    
    function showDashboardTab(tab) {{
        document.querySelectorAll('#assistantTab, #ordersTab').forEach(el => el.classList.remove('active'));
        document.querySelectorAll('.dashboard-tab button').forEach(btn => btn.classList.remove('active'));
        if(tab === 'assistant') {{
            document.getElementById('assistantTab').classList.add('active');
            document.querySelector('.dashboard-tab button:first-child').classList.add('active');
        }} else {{
            document.getElementById('ordersTab').classList.add('active');
            document.querySelector('.dashboard-tab button:last-child').classList.add('active');
        }}
    }}
    
    function submitOrder() {{
        let ids = [], qty = {{}};
        document.querySelectorAll('.chk:checked').forEach(c => {{
            let id = parseInt(c.dataset.id);
            ids.push(id);
            qty[id] = document.querySelector('.qty-'+id).value;
        }});
        let company = document.getElementById('company').value;
        if(!company){{ showToast('شرکت را انتخاب کنید', 'error'); return; }}
        if(ids.length==0){{ showToast('حداقل یک دارو انتخاب کنید', 'error'); return; }}
        fetch('/api/place_order', {{ method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify({{selected_ids:ids, company:company, quantities:qty}}) }})
            .then(r=>r.json())
            .then(data=>{{
                if(data.success) {{
                    showToast('✅ سفارش با موفقیت ثبت شد', 'success');
                    location.reload();
                }} else {{
                    showToast('❌ خطا: ' + data.error, 'error');
                }}
            }})
            .catch(err => {{
                showToast('❌ خطا در ارتباط با سرور', 'error');
            }});
    }}
    
    document.getElementById('companyFilter').addEventListener('change', function() {{
        let company = this.value;
        let search = document.getElementById('searchFilter').value.toLowerCase();
        let rows = document.querySelectorAll('#ordersList tr');
        rows.forEach(row => {{
            let show = true;
            if(company !== 'all') {{
                let td = row.querySelector('td:first-child');
                if(td && td.textContent !== company) show = false;
            }}
            if(search) {{
                let td = row.querySelector('td:nth-child(2)');
                if(td && !td.textContent.toLowerCase().includes(search)) show = false;
            }}
            row.style.display = show ? '' : 'none';
        }});
    }});
    
    document.getElementById('searchFilter').addEventListener('input', function() {{
        document.getElementById('companyFilter').dispatchEvent(new Event('change'));
    }});
    
    function resetFilters() {{
        document.getElementById('companyFilter').value = 'all';
        document.getElementById('searchFilter').value = '';
        document.getElementById('companyFilter').dispatchEvent(new Event('change'));
    }}
    </script>
    '''
    return render_template_string(HTML, content=content, page_title='📊 داشبورد', session=session)

# ===== انبارداری (اصلاح شده با دکمه ثبت نام) =====
@app.route('/inventory')
@login_required
def inventory():
    # دریافت نام ثبت‌کننده از session یا تنظیم پیش‌فرض
    registered_name = session.get('registered_name', session.get('pharmacy_display_name', 'کاربر'))
    
    content = f'''
    <div class="card">
        <div class="card-title">📦 ثبت فاکتور جدید</div>
        <div class="form-row">
            <div class="search-container" style="flex:2">
                <input type="text" id="invName" placeholder="نام دارو" onkeyup="searchDrugsInv(this.value)" autocomplete="off">
                <div id="suggestionsInv" class="suggestions-list"></div>
            </div>
            <input type="number" id="invQty" placeholder="تعداد" value="1">
            <div style="flex:1;min-width:200px;">
                {get_year_month_selectors()}
            </div>
            <button onclick="addInventory()">ثبت فاکتور</button>
            <button onclick="changeRegisteredName()" class="btn-primary" style="display:flex;align-items:center;gap:6px;">
                👤 <span id="registeredNameDisplay">{registered_name}</span>
            </button>
        </div>
    </div>
    
    <div class="card">
        <div class="card-title">📊 لیست انبار</div>
        <div class="toolbar">
            <input type="text" id="liveSearch" placeholder="🔍 جستجوی زنده..." onkeyup="filterInventory()" style="flex:2;padding:8px 10px;border:1px solid #ddd;border-radius:6px;font-size:13px;">
            <button onclick="copySelectedItems()" class="export-btn">📋 کپی انتخاب‌ها</button>
            <button onclick="hideSelectedItems()" class="btn-warning">🙈 هاید انتخاب‌ها</button>
            <button onclick="unhideSelectedItems()" class="btn-success">🔓 آن هاید</button>
            <button onclick="deleteSelectedItems()" class="btn-danger">🗑️ حذف انتخاب‌ها</button>
            <button onclick="selectAllItems()" class="btn-sm">✅ انتخاب همه</button>
            <button onclick="deselectAllItems()" class="btn-sm">❌ لغو</button>
            <button onclick="toggleHiddenItems()" class="btn-sm">👁️ نمایش هاید</button>
        </div>
        <div id="stats" class="stats-grid"></div>
        <div id="inventoryContainer"></div>
    </div>
    
    <script>
    const USER_ID = {session['user_id']};
    let inventoryData = [];
    let currentFilter = '';
    let showHidden = false;
    let hiddenIds = new Set();
    let editingDrugId = null;
    
    try {{
        var saved = localStorage.getItem('hiddenIds_' + USER_ID);
        if(saved) {{
            hiddenIds = new Set(JSON.parse(saved));
        }}
    }} catch(e) {{
        hiddenIds = new Set();
    }}
    
    function showToast(message, type) {{
        var toast = document.getElementById('toast');
        toast.textContent = message;
        toast.className = 'toast-message ' + (type || 'info');
        toast.style.display = 'block';
        setTimeout(function() {{
            toast.style.display = 'none';
        }}, 3000);
    }}
    
    function loadHiddenItems() {{
        fetch('/api/get_hidden_items')
            .then(r => r.json())
            .then(data => {{
                hiddenIds = new Set(data.hidden_ids || []);
                localStorage.setItem('hiddenIds_' + USER_ID, JSON.stringify([...hiddenIds]));
                renderInventory();
            }})
            .catch(() => {{ 
                hiddenIds = new Set(); 
                localStorage.setItem('hiddenIds_' + USER_ID, JSON.stringify([]));
                renderInventory(); 
            }});
    }}
    
    function validateExpiryFormat(expiry) {{
        return /^\\d{{4}}\\.(0[1-9]|1[0-2])$/.test(expiry);
    }}
    
    function getExpiryStatusText(expiryDate) {{
        if(!expiryDate) return {{ text: 'نامشخص', class: '' }};
        try {{
            var parts = expiryDate.split('.');
            if(parts.length !== 2) return {{ text: 'نامشخص', class: '' }};
            var now = new Date();
            var expYear = parseInt(parts[0]), expMonth = parseInt(parts[1]) - 1;
            var exp = new Date(expYear, expMonth, 1);
            var monthsLeft = (exp.getFullYear() - now.getFullYear()) * 12 + (exp.getMonth() - now.getMonth());
            if(monthsLeft < 0) return {{ text: '🔴 منقضی', class: 'expired' }};
            if(monthsLeft <= 3) return {{ text: '🟡 ' + monthsLeft + ' ماه مانده', class: 'expiring-soon' }};
            return {{ text: '🟢 ' + monthsLeft + ' ماه مانده', class: 'good-expiry' }};
        }} catch(e) {{ return {{ text: 'نامشخص', class: '' }}; }}
    }}
    
    function filterInventory() {{
        currentFilter = document.getElementById('liveSearch')?.value.toLowerCase() || '';
        renderInventory();
    }}
    
    function toggleHiddenItems() {{
        showHidden = !showHidden;
        renderInventory();
    }}
    
    function selectAllItems() {{
        document.querySelectorAll('.drug-item .item-checkbox').forEach(cb => cb.checked = true);
    }}
    
    function deselectAllItems() {{
        document.querySelectorAll('.drug-item .item-checkbox').forEach(cb => cb.checked = false);
    }}
    
    function getSelectedItemIds() {{
        var ids = [];
        document.querySelectorAll('.drug-item .item-checkbox:checked').forEach(cb => {{
            ids.push(parseInt(cb.dataset.id));
        }});
        return ids;
    }}
    
    function copySelectedItems() {{
        var ids = getSelectedItemIds();
        if(ids.length === 0) {{ showToast('هیچ آیتمی انتخاب نشده است', 'error'); return; }}
        var text = "📋 لیست داروهای انتخاب شده\\n";
        text += "📅 " + new Date().toLocaleDateString('fa-IR') + "\\n─────────────────────\\n";
        inventoryData.forEach(tab => {{
            if(!tab || !tab.pharmacies) return;
            tab.pharmacies.forEach(ph => {{
                if(!ph || !ph.drugs) return;
                ph.drugs.forEach(d => {{
                    if(ids.includes(d.id) && (!d.hidden || showHidden)) {{
                        text += "• " + d.name + ": " + d.quantity + " عدد (ثبت‌کننده: " + (d.registered_by || 'نامشخص') + ") - انقضا: " + (d.expiry_date || 'نامشخص') + "\\n";
                    }}
                }});
            }});
        }});
        if(text.length > 5000) {{ showToast('گزارش بیش از حد بزرگ است', 'error'); return; }}
        var textarea = document.createElement('textarea');
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        showToast('✅ متن در کلیپبورد کپی شد', 'success');
    }}
    
    function hideSelectedItems() {{
        var ids = getSelectedItemIds();
        if(ids.length === 0) {{ showToast('هیچ آیتمی انتخاب نشده است', 'error'); return; }}
        if(!confirm(ids.length + ' آیتم هاید شود؟')) return;
        fetch('/api/toggle_hidden_items', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{item_ids: ids, hidden: true}})
        }}).then(r=>r.json()).then(data=>{{
            if(data.success) {{ 
                showToast('✅ ' + ids.length + ' آیتم هاید شد', 'success'); 
                ids.forEach(id => hiddenIds.add(id));
                localStorage.setItem('hiddenIds_' + USER_ID, JSON.stringify([...hiddenIds]));
                loadInventory(); 
            }} else {{ 
                showToast('خطا: ' + data.error, 'error'); 
            }}
        }}).catch(() => showToast('❌ خطا در ارتباط با سرور', 'error'));
    }}
    
    function unhideSelectedItems() {{
        var ids = getSelectedItemIds();
        if(ids.length === 0) {{ showToast('هیچ آیتمی انتخاب نشده است', 'error'); return; }}
        if(!confirm(ids.length + ' آیتم unhide شود؟')) return;
        fetch('/api/toggle_hidden_items', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{item_ids: ids, hidden: false}})
        }}).then(r=>r.json()).then(data=>{{
            if(data.success) {{ 
                showToast('✅ ' + ids.length + ' آیتم unhide شد', 'success');
                ids.forEach(id => hiddenIds.delete(id));
                localStorage.setItem('hiddenIds_' + USER_ID, JSON.stringify([...hiddenIds]));
                loadInventory(); 
            }} else {{ 
                showToast('خطا: ' + data.error, 'error'); 
            }}
        }}).catch(() => showToast('❌ خطا در ارتباط با سرور', 'error'));
    }}
    
    function deleteSelectedItems() {{
        var ids = getSelectedItemIds();
        if(ids.length === 0) {{ showToast('هیچ آیتمی انتخاب نشده است', 'error'); return; }}
        if(!confirm('آیا از حذف ' + ids.length + ' آیتم انتخاب شده اطمینان دارید؟')) return;
        fetch('/api/delete_inventory_items', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{item_ids: ids}})
        }}).then(r=>r.json()).then(data=>{{
            if(data.success) {{ 
                showToast('✅ ' + ids.length + ' آیتم حذف شد', 'success');
                loadInventory(); 
            }} else {{ 
                showToast('خطا: ' + data.error, 'error'); 
            }}
        }}).catch(() => showToast('❌ خطا در ارتباط با سرور', 'error'));
    }}
    
    function deleteSingleItem(id) {{
        if(!confirm('آیا از حذف این آیتم اطمینان دارید؟')) return;
        fetch('/api/delete_inventory_item/' + id, {{ method: 'POST' }})
            .then(r=>r.json())
            .then(data=>{{
                if(data.success) {{ 
                    showToast('✅ آیتم حذف شد', 'success');
                    loadInventory(); 
                }} else {{ 
                    showToast('خطا: ' + data.error, 'error'); 
                }}
            }})
            .catch(() => showToast('❌ خطا در ارتباط با سرور', 'error'));
    }}
    
    // ===== تغییر نام ثبت‌کننده =====
    function changeRegisteredName() {{
        var currentName = document.getElementById('registeredNameDisplay').textContent;
        var newName = prompt('نام خود را وارد کنید:', currentName);
        if(newName && newName.trim() !== '') {{
            fetch('/api/set_registered_name', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{name: newName.trim()}})
            }})
            .then(r=>r.json())
            .then(data=>{{
                if(data.success) {{
                    document.getElementById('registeredNameDisplay').textContent = newName.trim();
                    showToast('✅ نام ثبت‌کننده تغییر یافت', 'success');
                }} else {{
                    showToast('❌ خطا: ' + data.error, 'error');
                }}
            }})
            .catch(() => showToast('❌ خطا در ارتباط با سرور', 'error'));
        }}
    }}
    
    // ===== ویرایش سریع دارو با کلیک روی نام =====
    function editDrug(drugId, drugName, expiryDate, quantity, registeredBy) {{
        // پر کردن فرم با اطلاعات دارو
        document.getElementById('invName').value = drugName;
        document.getElementById('invQty').value = quantity;
        
        // تنظیم تاریخ انقضا در سلکتورها
        if(expiryDate && expiryDate.includes('.')) {{
            var parts = expiryDate.split('.');
            var year = parseInt(parts[0]);
            var month = parseInt(parts[1]);
            
            var yearSelect = document.querySelector('.expiry-year');
            var monthSelect = document.querySelector('.expiry-month');
            var preview = document.querySelector('.expiry-preview');
            
            if(yearSelect) {{
                for(var i=0; i<yearSelect.options.length; i++) {{
                    if(parseInt(yearSelect.options[i].value) === year) {{
                        yearSelect.selectedIndex = i;
                        break;
                    }}
                }}
            }}
            if(monthSelect) {{
                var monthStr = month.toString().padStart(2, '0');
                for(var i=0; i<monthSelect.options.length; i++) {{
                    if(monthSelect.options[i].value === monthStr) {{
                        monthSelect.selectedIndex = i;
                        break;
                    }}
                }}
            }}
            if(preview) {{
                preview.textContent = year + '.' + month.toString().padStart(2, '0');
            }}
        }}
        
        // تنظیم نام ثبت‌کننده
        if(registeredBy) {{
            document.getElementById('registeredNameDisplay').textContent = registeredBy;
        }}
        
        editingDrugId = drugId;
        document.querySelector('.card').scrollIntoView({{ behavior: 'smooth' }});
        showToast('✏️ دارو برای ویرایش آماده شد. تعداد و تاریخ را تغییر دهید و ثبت کنید.', 'info');
    }}
    
    function renderInventory() {{
        var container = document.getElementById('inventoryContainer');
        if (!container) return;
        var filtered = inventoryData.filter(tab => {{
            if(!currentFilter) return true;
            return tab.pharmacies.some(ph => 
                ph.drugs.some(d => d.name.toLowerCase().includes(currentFilter))
            );
        }});
        var totalVisible = 0;
        filtered.forEach(tab => {{
            tab.pharmacies.forEach(ph => {{
                ph.drugs.forEach(d => {{
                    if((!d.hidden || showHidden) && d.name.toLowerCase().includes(currentFilter)) totalVisible += d.quantity;
                }});
            }});
        }});
        document.getElementById('stats').innerHTML = '<div class="stat-card"><div class="number">' + filtered.length + '</div><div class="label">تاریخ انقضا</div></div>' +
            '<div class="stat-card"><div class="number">' + totalVisible + '</div><div class="label">مجموع اقلام</div></div>';
        if(filtered.length === 0) {{
            container.innerHTML = '<p style="text-align:center;padding:40px;color:#999">انبار خالی است</p>';
            return;
        }}
        var html = '';
        filtered.forEach((tab, idx) => {{
            var status = getExpiryStatusText(tab.expiry_date);
            var isOpen = idx === 0 ? 'show' : '';
            html += '<div class="expiry-tab">';
            html += '<div class="expiry-tab-header" style="background:' + (status.class === 'expired' ? '#f8d7da' : status.class === 'expiring-soon' ? '#fff3cd' : '#d4edda') + '" onclick="toggleTab(this)">';
            html += '<span class="expiry-date">📅 ' + tab.expiry_date + '</span>';
            html += '<span><span class="expiry-status ' + status.class + '">' + status.text + '</span>';
            var totalQty = 0;
            tab.pharmacies.forEach(ph => ph.drugs.forEach(d => {{ if((!d.hidden || showHidden) && d.name.toLowerCase().includes(currentFilter)) totalQty += d.quantity; }}));
            html += ' | 🏥 ' + tab.pharmacies.length + ' داروخانه | 📦 ' + totalQty + ' عدد</span>';
            html += '</div>';
            html += '<div class="expiry-tab-body ' + isOpen + '">';
            tab.pharmacies.forEach((ph, phIdx) => {{
                var visibleDrugs = ph.drugs.filter(d => (!d.hidden || showHidden) && d.name.toLowerCase().includes(currentFilter));
                if(visibleDrugs.length === 0) return;
                var isPhOpen = phIdx === 0 ? 'show' : '';
                html += '<div class="pharmacy-group">';
                html += '<div class="pharmacy-group-header" onclick="togglePharmacyGroup(this)">';
                html += '<span>🏥 ' + ph.pharmacy_name + '</span>';
                html += '<span>📦 ' + visibleDrugs.reduce((a,b) => a + b.quantity, 0) + ' عدد</span>';
                html += '</div>';
                html += '<div class="pharmacy-group-body ' + isPhOpen + '">';
                visibleDrugs.forEach(d => {{
                    var jalaliDate = d.created_at_jalali || '-';
                    html += '<div class="drug-item">';
                    html += '<input type="checkbox" class="item-checkbox" data-id="' + d.id + '">';
                    html += '<span class="drug-name" onclick="editDrug(' + d.id + ', \\'' + d.name.replace(/'/g, "\\\\'") + '\\', \\'' + (d.expiry_date || '') + '\\', ' + d.quantity + ', \\'' + (d.registered_by || '') + '\\')">' + d.name + '</span>';
                    html += '<span class="drug-qty">' + d.quantity + ' عدد</span>';
                    html += '<span class="drug-registered">👤 ' + (d.registered_by || 'نامشخص') + '</span>';
                    html += '<span class="drug-date">📅 ' + jalaliDate + '</span>';
                    if(d.hidden) html += '<span style="font-size:11px;color:#dc3545;">🙈 هاید</span>';
                    html += '<div class="drug-actions">';
                    html += '<button onclick="deleteSingleItem(' + d.id + ')" class="btn-danger btn-sm">🗑️</button>';
                    html += '</div>';
                    html += '</div>';
                }});
                html += '</div></div>';
            }});
            html += '</div></div>';
        }});
        container.innerHTML = html;
    }}
    
    function toggleTab(header) {{ var body = header.nextElementSibling; body.classList.toggle('show'); }}
    function togglePharmacyGroup(header) {{ var body = header.nextElementSibling; body.classList.toggle('show'); }}
    
    function loadInventory() {{
        fetch('/api/get_inventory_grouped_by_expiry', {{
            headers: {{
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }}
        }})
        .then(r => r.json())
        .then(data => {{
            inventoryData = data.data || [];
            loadHiddenItems();
        }})
        .catch(err => {{
            console.error('Error loading inventory:', err);
            document.getElementById('inventoryContainer').innerHTML = '<p style="text-align:center;padding:40px;color:#dc3545">❌ خطا در بارگذاری</p>';
            showToast('❌ خطا در بارگذاری انبار', 'error');
        }});
    }}
    
    function searchDrugsInv(query) {{
        var suggestions = document.getElementById('suggestionsInv');
        if(query.length < 2) {{ suggestions.style.display = 'none'; return; }}
        fetch('/api/search_with_stock?q=' + encodeURIComponent(query))
            .then(r => r.json())
            .then(data => {{
                if(data.length > 0) {{
                    var html = '';
                    data.forEach(drug => {{
                        html += '<div onclick="selectDrugInv(\\'' + drug.name + '\\')"><strong>' + drug.name + '</strong><div class="stock-info">🏭 انبار: ' + drug.warehouse_qty + ' | 🏪 داروخانه: ' + drug.pharmacy_qty + ' | 📅 نزدیک‌ترین انقضا: ' + (drug.nearest_expiry || '-') + '</div></div>';
                    }});
                    suggestions.innerHTML = html;
                    suggestions.style.display = 'block';
                }} else {{ suggestions.style.display = 'none'; }}
            }})
            .catch(() => {{ suggestions.style.display = 'none'; }});
    }}
    
    function selectDrugInv(name) {{ document.getElementById('invName').value = name; document.getElementById('suggestionsInv').style.display = 'none'; }}
    
    function getExpiryFromSelectors(formRow) {{
        var yearEl = formRow ? formRow.querySelector('.expiry-year') : null;
        var monthEl = formRow ? formRow.querySelector('.expiry-month') : null;
        var year = yearEl ? yearEl.value : new Date().getFullYear();
        var month = monthEl ? monthEl.value : '01';
        return year + '.' + month;
    }}
    
    function addInventory() {{
        var name = document.getElementById('invName').value;
        var qty = document.getElementById('invQty').value;
        var formRow = document.getElementById('invName').closest('.form-row');
        var expiry = getExpiryFromSelectors(formRow);
        var registeredBy = document.getElementById('registeredNameDisplay').textContent;
        
        if(!name || !qty || !expiry) {{
            showToast('نام دارو، تعداد و تاریخ انقضا اجباری است', 'error');
            return;
        }}
        
        var fd = new FormData();
        fd.append('name', name);
        fd.append('quantity', qty);
        fd.append('expiry_date', expiry);
        fd.append('registered_by', registeredBy);
        if(editingDrugId) {{
            fd.append('edit_id', editingDrugId);
        }}
        
        fetch('/api/add_inventory', {{
            method: 'POST',
            body: fd
        }})
        .then(r => r.json())
        .then(data => {{
            if(data.success) {{ 
                showToast('✅ دارو ثبت شد', 'success');
                editingDrugId = null;
                loadInventory();
                document.getElementById('invName').value = '';
                document.getElementById('invQty').value = '1';
            }} else {{ 
                showToast('خطا: ' + data.error, 'error'); 
            }} 
        }})
        .catch(err => {{
            showToast('❌ خطا در ارتباط با سرور', 'error');
        }});
    }}
    
    document.addEventListener('change', function(e) {{
        if(e.target.classList.contains('expiry-year') || e.target.classList.contains('expiry-month')) {{
            var row = e.target.closest('.form-row');
            if(row) {{
                var year = row.querySelector('.expiry-year');
                var month = row.querySelector('.expiry-month');
                var preview = row.querySelector('.expiry-preview');
                if(year && month && preview) {{
                    preview.textContent = year.value + '.' + month.value;
                }}
            }}
        }}
    }});
    
    document.addEventListener('click', function(e) {{
        if(!e.target.closest('.search-container')) {{
            ['suggestionsInv'].forEach(id => {{ var s = document.getElementById(id); if(s) s.style.display = 'none'; }});
        }}
    }});
    
    loadInventory();
    </script>
    '''
    return render_template_string(HTML, content=content, page_title='📦 انبارداری', session=session)

# ===== تبادل دارو =====
@app.route('/exchange')
@login_required
def exchange():
    db = get_db()
    user_id = session['user_id']
    
    cursor = db.execute("SELECT id, pharmacy_display_name FROM users WHERE id != ? AND is_approved = 1", (user_id,))
    pharmacies = cursor.fetchall()
    
    pharmacy_options = ''
    for p in pharmacies:
        pharmacy_options += f'<option value="{p["id"]}">{p["pharmacy_display_name"]}</option>'
    
    cursor = db.execute("SELECT categories FROM user_categories WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    user_categories = row['categories'].split(',') if row and row['categories'] else []
    
    cat_checks = ''
    cat_map = {
        'heart': '❤️ قلب', 'respiratory': '🌬️ تنفس', 'women': '👩 زنان', 
        'orthopedic': '🦵 ارتوپد', 'urology': '🚽 ارولوژی', 'endocrine': '🧬 غدد',
        'neurology': '🧠 مغز و اعصاب', 'dermatology': '🧴 پوست', 'pediatric': '👶 کودکان',
        'eye': '👁️ چشم', 'other': '📦 سایر'
    }
    for key, label in cat_map.items():
        checked = 'checked' if key in user_categories else ''
        cat_checks += f'<label><input type="checkbox" value="{key}" {checked}> {label}</label>'
    
    content = f'''
    <style>
    .exchange-tab {{
        display: flex;
        gap: 8px;
        margin-bottom: 15px;
        border-bottom: 2px solid #e0e0e0;
        padding-bottom: 10px;
    }}
    .exchange-tab button {{
        background: none;
        color: #1a1a1a;
        border: none;
        padding: 8px 16px;
        font-size: 13px;
        cursor: pointer;
        border-radius: 0;
        transition: all 0.3s;
    }}
    .exchange-tab button:hover {{
        background: #f0f0f0;
    }}
    .exchange-tab button.active {{
        border-bottom: 3px solid #1a1a1a;
        font-weight: bold;
        color: #1a1a1a;
    }}
    .tab-content {{
        display: none;
    }}
    .tab-content.active {{
        display: block;
    }}
    .category-checkboxes {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        padding: 10px;
        background: #f8f9fa;
        border-radius: 10px;
    }}
    .category-checkboxes label {{
        display: flex;
        align-items: center;
        gap: 5px;
        cursor: pointer;
        padding: 5px 10px;
        background: white;
        border-radius: 6px;
        border: 1px solid #ddd;
        font-size: 13px;
    }}
    .category-checkboxes label:hover {{
        background: #e9ecef;
    }}
    .exchange-drug-item {{
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 8px 10px;
        border-bottom: 1px solid #eee;
        cursor: pointer;
        border-radius: 4px;
        font-size: 13px;
        transition: background 0.2s;
    }}
    .exchange-drug-item:hover {{
        background: #f5f5f5;
    }}
    .exchange-drug-item.selected {{
        background: #d4edda !important;
    }}
    .exchange-drug-item input[type="checkbox"] {{
        cursor: pointer;
    }}
    .exchange-drug-info {{
        flex: 1;
    }}
    .exchange-drug-name {{
        font-weight: bold;
        font-size: 14px;
    }}
    .exchange-drug-detail {{
        font-size: 12px;
        color: #666;
        margin-top: 2px;
    }}
    .exchange-qty-input {{
        width: 60px;
        padding: 4px 6px;
        border: 1px solid #ddd;
        border-radius: 4px;
        font-size: 13px;
        text-align: center;
    }}
    .exchange-list-box {{
        flex: 1;
        min-width: 250px;
        background: white;
        border-radius: 10px;
        overflow: hidden;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        border: 1px solid #e0e0e0;
    }}
    .exchange-list-header {{
        background: #1a1a1a;
        color: white;
        padding: 10px;
        text-align: center;
        font-weight: bold;
        font-size: 13px;
        cursor: pointer;
        transition: background 0.3s;
    }}
    .exchange-list-header.active {{
        background: #28a745;
    }}
    .exchange-list-header:hover {{
        opacity: 0.9;
    }}
    .exchange-list-items {{
        max-height: 350px;
        overflow-y: auto;
        padding: 5px;
    }}
    .exchange-dual-container {{
        display: flex;
        gap: 15px;
        flex-wrap: wrap;
    }}
    @media (max-width: 768px) {{
        .exchange-dual-container {{
            flex-direction: column;
        }}
        .exchange-list-box {{
            min-width: unset;
        }}
    }}
    </style>

    <div class="exchange-tab">
        <button class="active" onclick="showExchangeTab('register')">🔄 ثبت تبادل</button>
        <button onclick="showExchangeTab('list')">📋 تبادلات من</button>
        <button onclick="showExchangeTab('pending')">⏳ درخواست‌های دریافتی</button>
    </div>
    
    <div id="registerTab" class="tab-content active">
        <div class="card">
            <div class="card-title">📋 دسته‌بندی مصرفی</div>
            <div class="category-checkboxes" id="categoryCheckboxes">
                {cat_checks}
            </div>
            <button onclick="saveUserCategories()" class="btn-success" style="margin-top:10px;">💾 ذخیره دسته‌بندی</button>
        </div>
        
        <div class="card">
            <div class="card-title">🔍 جستجوی دارو در تمام داروخانه‌ها</div>
            <div class="form-row">
                <input type="text" id="drugFilter" placeholder="🔍 نام دارو..." onkeyup="filterExchangeDrugs()" style="flex:2;padding:8px 10px;border:1px solid #ddd;border-radius:6px;font-size:13px;">
                <select id="targetPharmacySelect" style="flex:1;" onchange="filterExchangeDrugs()">
                    <option value="all">همه داروخانه‌ها</option>
                    {pharmacy_options}
                </select>
            </div>
            <div id="exchangeAllDrugsContainer"></div>
        </div>
        
        <div id="exchangeDualView" style="display:none;">
            <div class="exchange-dual-container">
                <div class="exchange-list-box">
                    <div class="exchange-list-header active" id="myListHeader" onclick="switchToMyList()">📦 داروهای من</div>
                    <div class="exchange-list-items" id="myDrugsList"></div>
                </div>
                <div class="exchange-list-box">
                    <div class="exchange-list-header" id="targetListHeader" onclick="switchToTargetList()">🏥 داروهای داروخانه هدف</div>
                    <div class="exchange-list-items" id="targetDrugsList"></div>
                </div>
            </div>
            <div class="exchange-summary" style="background:#f8f9fa;padding:15px;border-radius:10px;margin-top:15px;">
                <strong>📋 خلاصه انتخاب‌ها:</strong>
                <div id="summaryText" style="margin-top:10px;padding:10px;background:white;border-radius:8px;">هیچ دارویی انتخاب نشده است</div>
                <div style="display:flex;gap:10px;margin-top:15px;flex-wrap:wrap;">
                    <button onclick="resetExchangeSelection()" class="btn-danger">🔄 ریست انتخاب‌ها</button>
                    <button onclick="confirmExchangeFinal()" class="btn-success">✅ ثبت درخواست تبادل</button>
                </div>
            </div>
        </div>
    </div>
    
    <div id="listTab" class="tab-content">
        <div class="card">
            <div class="card-title">📋 تبادلات ثبت شده (من)</div>
            <div class="exchange-filter">
                <input type="text" id="exchangePharmacyFilter" placeholder="🔍 فیلتر نام داروخانه..." onkeyup="filterMyExchanges()" style="width:100%;padding:8px;border-radius:6px;border:1px solid #ddd;">
            </div>
            <div class="exchanges-wrapper" id="myExchangesList"></div>
        </div>
    </div>
    
    <div id="pendingTab" class="tab-content">
        <div class="card">
            <div class="card-title">⏳ تبادلات دریافتی</div>
            <div id="pendingExchangesList"></div>
        </div>
    </div>
    
    <script>
    const USER_ID = {user_id};
    var selectedTargetPharmacy = null;
    var selectedTargetPharmacyName = '';
    var myDrugs = [];
    var targetDrugs = [];
    var selectedItems = [];
    var userCategories = [];
    var allMyExchanges = [];
    var exchangeAllDrugsData = [];
    var hiddenIds = new Set();
    
    function showToast(message, type) {{
        var toast = document.getElementById('toast');
        toast.textContent = message;
        toast.className = 'toast-message ' + (type || 'info');
        toast.style.display = 'block';
        setTimeout(function() {{
            toast.style.display = 'none';
        }}, 3000);
    }}
    
    function loadHiddenItems() {{
        fetch('/api/get_hidden_items').then(r=>r.json()).then(data=>{{
            hiddenIds = new Set(data.hidden_ids || []);
            renderExchangeAllDrugs();
        }}).catch(()=>{{ hiddenIds = new Set(); renderExchangeAllDrugs(); }});
    }}
    
    function loadUserCategories() {{
        fetch('/api/get_user_categories').then(r=>r.json()).then(data=>{{
            userCategories = data.categories || [];
            document.querySelectorAll('#categoryCheckboxes input').forEach(cb => {{
                cb.checked = userCategories.includes(cb.value);
            }});
        }}).catch(()=>{{}});
    }}
    
    function saveUserCategories() {{
        var categories = [];
        document.querySelectorAll('#categoryCheckboxes input:checked').forEach(cb => {{
            categories.push(cb.value);
        }});
        fetch('/api/save_user_categories', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{categories: categories}})
        }}).then(r=>r.json()).then(data=>{{
            if(data.success) {{
                showToast('✅ دسته‌بندی مصرفی ذخیره شد', 'success');
                userCategories = categories;
            }} else {{
                showToast('خطا: ' + data.error, 'error');
            }}
        }}).catch(()=> showToast('❌ خطا در ارتباط با سرور', 'error'));
    }}
    
    function getExpiryStatusText(expiryDate) {{
        if(!expiryDate) return {{ text: 'نامشخص', class: '' }};
        try {{
            var parts = expiryDate.split('.');
            if(parts.length !== 2) return {{ text: 'نامشخص', class: '' }};
            var now = new Date();
            var expYear = parseInt(parts[0]), expMonth = parseInt(parts[1]) - 1;
            var exp = new Date(expYear, expMonth, 1);
            var monthsLeft = (exp.getFullYear() - now.getFullYear()) * 12 + (exp.getMonth() - now.getMonth());
            if(monthsLeft < 0) return {{ text: '🔴 منقضی', class: 'expired' }};
            if(monthsLeft <= 3) return {{ text: '🟡 ' + monthsLeft + ' ماه مانده', class: 'expiring-soon' }};
            return {{ text: '🟢 ' + monthsLeft + ' ماه مانده', class: 'good-expiry' }};
        }} catch(e) {{ return {{ text: 'نامشخص', class: '' }}; }}
    }}
    
    function sortByExpiryDate(drugs) {{
        return [...drugs].sort((a, b) => {{
            if(!a.expiry_date && !b.expiry_date) return 0;
            if(!a.expiry_date) return 1;
            if(!b.expiry_date) return -1;
            var aParts = a.expiry_date.split('.');
            var bParts = b.expiry_date.split('.');
            if(aParts.length !== 2 && bParts.length !== 2) return 0;
            if(aParts.length !== 2) return 1;
            if(bParts.length !== 2) return -1;
            return (parseInt(aParts[0]) * 12 + parseInt(aParts[1])) - (parseInt(bParts[0]) * 12 + parseInt(bParts[1]));
        }});
    }}
    
    function loadExchangeAllDrugs() {{
        var container = document.getElementById('exchangeAllDrugsContainer');
        container.innerHTML = '<div style="text-align:center;padding:20px;color:#666">🔄 در حال بارگذاری...</div>';
        fetch('/api/get_all_pharmacies_drugs_grouped_by_expiry')
            .then(r => r.json())
            .then(data => {{
                exchangeAllDrugsData = data.data || [];
                loadHiddenItems();
            }})
            .catch(err => {{
                console.error('Error:', err);
                container.innerHTML = '<div style="text-align:center;padding:20px;color:#dc3545">❌ خطا در بارگذاری</div>';
                showToast('❌ خطا در بارگذاری', 'error');
            }});
    }}
    
    function renderExchangeAllDrugs() {{
        var container = document.getElementById('exchangeAllDrugsContainer');
        var filter = document.getElementById('drugFilter').value.toLowerCase();
        var targetPharmacy = document.getElementById('targetPharmacySelect').value;
        var filtered = exchangeAllDrugsData.filter(tab => {{
            if(!filter) return true;
            return tab.pharmacies.some(ph => 
                ph.drugs.some(d => d.name.toLowerCase().includes(filter) && !hiddenIds.has(d.id))
            );
        }});
        if(targetPharmacy !== 'all') {{
            filtered = filtered.map(tab => {{
                var newPh = tab.pharmacies.filter(ph => ph.pharmacy_id == targetPharmacy);
                return {{...tab, pharmacies: newPh}};
            }}).filter(tab => tab.pharmacies.length > 0);
        }}
        if(filtered.length === 0) {{
            container.innerHTML = '<div style="text-align:center;padding:30px;color:#999">هیچ دارویی یافت نشد</div>';
            return;
        }}
        var html = '';
        filtered.forEach((tab, idx) => {{
            var status = getExpiryStatusText(tab.expiry_date);
            var isOpen = idx === 0 ? 'show' : '';
            html += '<div class="expiry-tab">';
            html += '<div class="expiry-tab-header" style="background:' + (status.class === 'expired' ? '#f8d7da' : status.class === 'expiring-soon' ? '#fff3cd' : '#d4edda') + '" onclick="toggleExchangeTab(this)">';
            html += '<span class="expiry-date">📅 ' + tab.expiry_date + '</span>';
            html += '<span><span class="expiry-status ' + status.class + '">' + status.text + '</span>';
            var totalQty = 0;
            tab.pharmacies.forEach(ph => ph.drugs.forEach(d => {{ if(!hiddenIds.has(d.id) && d.name.toLowerCase().includes(filter)) totalQty += d.quantity; }}));
            html += ' | 🏥 ' + tab.pharmacies.length + ' داروخانه | 📦 ' + totalQty + ' عدد</span>';
            html += '</div>';
            html += '<div class="expiry-tab-body ' + isOpen + '">';
            tab.pharmacies.forEach((ph, phIdx) => {{
                var visibleDrugs = ph.drugs.filter(d => !hiddenIds.has(d.id) && d.name.toLowerCase().includes(filter));
                if(visibleDrugs.length === 0) return;
                var isPhOpen = phIdx === 0 ? 'show' : '';
                var isMyPharmacy = ph.pharmacy_id == USER_ID;
                html += '<div class="pharmacy-group">';
                html += '<div class="pharmacy-group-header" onclick="toggleExchangePharmacyGroup(this)">';
                html += '<span>🏥 ' + ph.pharmacy_name + (isMyPharmacy ? ' (من)' : '') + '</span>';
                html += '<span>📦 ' + visibleDrugs.reduce((a,b) => a + b.quantity, 0) + ' عدد</span>';
                html += '</div>';
                html += '<div class="pharmacy-group-body ' + isPhOpen + '">';
                visibleDrugs.forEach(d => {{
                    var locText = d.location === 'warehouse' ? 'انبار' : 'داروخانه';
                    var locClass = d.location === 'warehouse' ? 'location-warehouse' : 'location-pharmacy';
                    var isSelected = selectedItems.some(item => item.pharmacy_id === ph.pharmacy_id && item.id === d.id);
                    html += '<div class="drug-item" style="' + (isSelected ? 'background:#d4edda;' : '') + '">';
                    html += '<span class="drug-name">' + d.name + '</span>';
                    html += '<span class="drug-qty">' + d.quantity + ' عدد</span>';
                    html += '<span class="drug-location ' + locClass + '">' + locText + '</span>';
                    html += '<button class="btn-exchange-select ' + (isSelected ? 'selected' : '') + '" onclick="event.stopPropagation(); selectDrugFromExchange(' + ph.pharmacy_id + ', \\'' + ph.pharmacy_name.replace(/'/g, "\\\\'") + '\\', \\'' + d.name.replace(/'/g, "\\\\'") + '\\', ' + d.quantity + ', \\'' + (d.expiry_date || '') + '\\', ' + d.id + ')">' + (isSelected ? '✅ انتخاب شده' : '🔹 انتخاب') + '</button>';
                    html += '</div>';
                }});
                html += '</div></div>';
            }});
            html += '</div></div>';
        }});
        container.innerHTML = html;
    }}
    
    function filterExchangeDrugs() {{
        renderExchangeAllDrugs();
    }}
    
    function toggleExchangeTab(header) {{ var body = header.nextElementSibling; body.classList.toggle('show'); }}
    function toggleExchangePharmacyGroup(header) {{ var body = header.nextElementSibling; body.classList.toggle('show'); }}
    
    function selectDrugFromExchange(pharmacyId, pharmacyName, drugName, quantity, expiryDate, drugId) {{
        if(selectedTargetPharmacy !== null && selectedTargetPharmacy !== pharmacyId && pharmacyId != USER_ID) {{
            showToast('❌ شما نمی‌توانید از دو داروخانه مختلف به طور همزمان انتخاب کنید.', 'error');
            return;
        }}
        if(pharmacyId == USER_ID) {{
            if(selectedTargetPharmacy !== null && selectedTargetPharmacy != USER_ID) {{
                showToast('❌ شما در حال انتخاب از داروهای خود هستید، اما قبلاً داروخانه هدف دیگری انتخاب کرده‌اید.', 'error');
                return;
            }}
            selectedTargetPharmacy = null;
            selectedTargetPharmacyName = '';
            var drug = myDrugs.find(d => d.id === drugId);
            if(drug) {{
                toggleDrugSelection('my', drugId, drugName, drug.quantity, expiryDate, USER_ID);
                document.getElementById('exchangeDualView').style.display = 'block';
                loadDrugsForExchange();
            }} else {{
                fetch('/api/get_my_drugs_for_exchange')
                    .then(r=>r.json())
                    .then(data=>{{
                        myDrugs = sortByExpiryDate(data.drugs || []);
                        renderMyDrugsList();
                        var newDrug = myDrugs.find(d => d.id === drugId);
                        if(newDrug) {{
                            toggleDrugSelection('my', drugId, drugName, newDrug.quantity, expiryDate, USER_ID);
                            document.getElementById('exchangeDualView').style.display = 'block';
                            loadDrugsForExchange();
                        }} else {{
                            showToast('این دارو در لیست داروهای من موجود نیست', 'error');
                        }}
                    }})
                    .catch(()=> showToast('❌ خطا در دریافت داروهای من', 'error'));
                return;
            }}
        }} else {{
            if(selectedTargetPharmacy === null) {{
                selectedTargetPharmacy = pharmacyId;
                selectedTargetPharmacyName = pharmacyName;
            }} else if(selectedTargetPharmacy !== pharmacyId) {{
                showToast('❌ شما نمی‌توانید از دو داروخانه مختلف انتخاب کنید.', 'error');
                return;
            }}
            var drug = targetDrugs.find(d => d.id === drugId);
            if(drug) {{
                toggleDrugSelection('target', drugId, drugName, drug.quantity, expiryDate, pharmacyId);
                document.getElementById('exchangeDualView').style.display = 'block';
                loadDrugsForExchange();
            }} else {{
                fetch('/api/get_pharmacy_drugs?pharmacy_id=' + pharmacyId)
                    .then(r=>r.json())
                    .then(data=>{{
                        targetDrugs = sortByExpiryDate(data.drugs || []);
                        renderTargetDrugsList();
                        var newDrug = targetDrugs.find(d => d.id === drugId);
                        if(newDrug) {{
                            toggleDrugSelection('target', drugId, drugName, newDrug.quantity, expiryDate, pharmacyId);
                            document.getElementById('exchangeDualView').style.display = 'block';
                            loadDrugsForExchange();
                        }} else {{
                            showToast('این دارو در داروخانه هدف موجود نیست', 'error');
                        }}
                    }})
                    .catch(()=> showToast('❌ خطا در دریافت اطلاعات', 'error'));
                return;
            }}
        }}
        renderExchangeAllDrugs();
    }}
    
    function loadDrugsForExchange() {{
        fetch('/api/get_my_drugs_for_exchange')
            .then(r=>r.json()).then(data=>{{ myDrugs = sortByExpiryDate(data.drugs || []); renderMyDrugsList(); }})
            .catch(()=> showToast('❌ خطا در دریافت داروهای من', 'error'));
        if(selectedTargetPharmacy) {{
            fetch('/api/get_pharmacy_drugs_for_exchange?pharmacy_id=' + selectedTargetPharmacy)
                .then(r=>r.json()).then(data=>{{ targetDrugs = sortByExpiryDate(data.drugs || []); renderTargetDrugsList(); }})
                .catch(()=> showToast('❌ خطا در دریافت داروهای هدف', 'error'));
        }} else {{ targetDrugs = []; renderTargetDrugsList(); }}
        document.getElementById('exchangeDualView').style.display = 'block';
        renderSummary();
    }}
    
    function renderMyDrugsList() {{
        var container = document.getElementById('myDrugsList');
        if(myDrugs.length === 0) {{ container.innerHTML = '<div style="padding:20px;text-align:center;color:#999">هیچ دارویی موجود نیست</div>'; return; }}
        var html = '';
        myDrugs.forEach(drug => {{
            var isSelected = selectedItems.some(item => item.source === 'my' && item.id === drug.id);
            var status = getExpiryStatusText(drug.expiry_date);
            var safeName = drug.name.replace(/'/g, "\\\\'").replace(/"/g, '&quot;');
            html += '<div class="exchange-drug-item ' + (isSelected ? 'selected' : '') + '" onclick="toggleDrugSelection(\\'my\\', ' + drug.id + ', \\'' + safeName + '\\', ' + drug.quantity + ', \\'' + (drug.expiry_date || '') + '\\', ' + USER_ID + ')">';
            html += '<input type="checkbox" class="exchange-drug-check" ' + (isSelected ? 'checked' : '') + ' onchange="event.stopPropagation(); toggleDrugSelection(\\'my\\', ' + drug.id + ', \\'' + safeName + '\\', ' + drug.quantity + ', \\'' + (drug.expiry_date || '') + '\\', ' + USER_ID + ')">';
            html += '<div class="exchange-drug-info"><div class="exchange-drug-name">' + drug.name + '</div>';
            html += '<div class="exchange-drug-detail">📦 ' + drug.quantity + ' عدد | 📅 ' + (drug.expiry_date || 'نامشخص') + ' ' + status.text + '</div></div>';
            if(isSelected) {{
                var selectedItem = selectedItems.find(item => item.source === 'my' && item.id === drug.id);
                var qty = selectedItem ? selectedItem.quantity : drug.quantity;
                html += '<input type="number" class="exchange-qty-input" value="' + qty + '" min="1" max="' + drug.quantity + '" onchange="updateSelectedQuantity(\\'my\\', ' + drug.id + ', this.value)" onclick="event.stopPropagation()">';
            }}
            html += '</div>';
        }});
        container.innerHTML = html;
    }}
    
    function renderTargetDrugsList() {{
        var container = document.getElementById('targetDrugsList');
        if(!selectedTargetPharmacy) {{ container.innerHTML = '<div style="padding:20px;text-align:center;color:#999">ابتدا دارویی از داروخانه هدف انتخاب کنید</div>'; return; }}
        if(targetDrugs.length === 0) {{ container.innerHTML = '<div style="padding:20px;text-align:center;color:#999">هیچ دارویی در داروخانه هدف موجود نیست</div>'; return; }}
        var html = '';
        targetDrugs.forEach(drug => {{
            var isSelected = selectedItems.some(item => item.source === 'target' && item.id === drug.id);
            var status = getExpiryStatusText(drug.expiry_date);
            var safeName = drug.name.replace(/'/g, "\\\\'").replace(/"/g, '&quot;');
            html += '<div class="exchange-drug-item ' + (isSelected ? 'selected' : '') + '" onclick="toggleDrugSelection(\\'target\\', ' + drug.id + ', \\'' + safeName + '\\', ' + drug.quantity + ', \\'' + (drug.expiry_date || '') + '\\', ' + selectedTargetPharmacy + ')">';
            html += '<input type="checkbox" class="exchange-drug-check" ' + (isSelected ? 'checked' : '') + ' onchange="event.stopPropagation(); toggleDrugSelection(\\'target\\', ' + drug.id + ', \\'' + safeName + '\\', ' + drug.quantity + ', \\'' + (drug.expiry_date || '') + '\\', ' + selectedTargetPharmacy + ')">';
            html += '<div class="exchange-drug-info"><div class="exchange-drug-name">' + drug.name + '</div>';
            html += '<div class="exchange-drug-detail">📦 ' + drug.quantity + ' عدد | 📅 ' + (drug.expiry_date || 'نامشخص') + ' ' + status.text + '</div></div>';
            if(isSelected) {{
                var selectedItem = selectedItems.find(item => item.source === 'target' && item.id === drug.id);
                var qty = selectedItem ? selectedItem.quantity : drug.quantity;
                html += '<input type="number" class="exchange-qty-input" value="' + qty + '" min="1" max="' + drug.quantity + '" onchange="updateSelectedQuantity(\\'target\\', ' + drug.id + ', this.value)" onclick="event.stopPropagation()">';
            }}
            html += '</div>';
        }});
        container.innerHTML = html;
    }}
    
    function toggleDrugSelection(source, id, name, maxQty, expiryDate, pharmacyId) {{
        var existingIndex = selectedItems.findIndex(item => item.source === source && item.id === id);
        if(existingIndex !== -1) {{
            selectedItems.splice(existingIndex, 1);
        }} else {{
            selectedItems.push({{ source: source, id: id, name: name, quantity: maxQty, max_quantity: maxQty, expiry_date: expiryDate, pharmacy_id: pharmacyId }});
        }}
        if(source === 'my') renderMyDrugsList();
        else renderTargetDrugsList();
        renderSummary();
        renderExchangeAllDrugs();
    }}
    
    function updateSelectedQuantity(source, id, newQuantity) {{
        var item = selectedItems.find(item => item.source === source && item.id === id);
        if(item) {{
            var qty = parseInt(newQuantity);
            if(isNaN(qty)) qty = item.max_quantity;
            if(qty < 1) qty = 1;
            if(qty > item.max_quantity) qty = item.max_quantity;
            item.quantity = qty;
        }}
        renderSummary();
        if(source === 'my') renderMyDrugsList();
        else renderTargetDrugsList();
        renderExchangeAllDrugs();
    }}
    
    function switchToMyList() {{ document.getElementById('myListHeader').classList.add('active'); document.getElementById('targetListHeader').classList.remove('active'); }}
    function switchToTargetList() {{ document.getElementById('targetListHeader').classList.add('active'); document.getElementById('myListHeader').classList.remove('active'); }}
    
    function renderSummary() {{
        var myItems = selectedItems.filter(item => item.source === 'my');
        var targetItems = selectedItems.filter(item => item.source === 'target');
        if(selectedItems.length === 0) {{ document.getElementById('summaryText').innerHTML = 'هیچ دارویی انتخاب نشده است'; return; }}
        var html = '';
        if(myItems.length > 0) {{ html += '<strong>📦 داروهایی که می‌دهم:</strong><br>'; myItems.forEach(item => {{ html += '• ' + item.name + ' - ' + item.quantity + ' عدد (📅 ' + (item.expiry_date || 'نامشخص') + ')<br>'; }}); }}
        if(targetItems.length > 0) {{ html += '<br><strong>🏥 داروهایی که می‌گیرم (از ' + selectedTargetPharmacyName + '):</strong><br>'; targetItems.forEach(item => {{ html += '• ' + item.name + ' - ' + item.quantity + ' عدد (📅 ' + (item.expiry_date || 'نامشخص') + ')<br>'; }}); }}
        document.getElementById('summaryText').innerHTML = html;
    }}
    
    function resetExchangeSelection() {{ 
        selectedItems = []; 
        selectedTargetPharmacy = null;
        selectedTargetPharmacyName = '';
        renderMyDrugsList(); 
        renderTargetDrugsList(); 
        renderSummary(); 
        renderExchangeAllDrugs();
        document.getElementById('exchangeDualView').style.display = 'none';
    }}
    
    function confirmExchangeFinal() {{
        var myItems = selectedItems.filter(item => item.source === 'my');
        var targetItems = selectedItems.filter(item => item.source === 'target');
        if(myItems.length === 0 && targetItems.length === 0) {{ showToast('هیچ دارویی برای تبادل انتخاب نشده است', 'error'); return; }}
        if(!selectedTargetPharmacy) {{ showToast('لطفا داروخانه هدف را انتخاب کنید', 'error'); return; }}
        var summary = '';
        if(myItems.length > 0) {{ summary += '📦 داروهایی که می‌دهم:\\n'; myItems.forEach(i => summary += '- ' + i.name + ': ' + i.quantity + ' عدد\\n'); }}
        if(targetItems.length > 0) {{ summary += '\\n🏥 داروهایی که می‌گیرم:\\n'; targetItems.forEach(i => summary += '- ' + i.name + ': ' + i.quantity + ' عدد (از ' + selectedTargetPharmacyName + ')\\n'); }}
        if(!confirm('آیا از ارسال درخواست تبادل اطمینان دارید؟\\n\\n' + summary)) return;
        var data = {{ target_pharmacy_id: selectedTargetPharmacy, my_items: myItems, target_items: targetItems }};
        fetch('/api/register_exchange', {{ 
            method: 'POST', 
            headers: {{ 
                'Content-Type': 'application/json',
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
        }}, 
            body: JSON.stringify(data) 
        }})
        .then(r=>r.json())
        .then(res => {{
            if(res.success) {{ 
                showToast('✅ درخواست تبادل با موفقیت ارسال شد', 'success'); 
                resetExchangeSelection(); 
                loadDrugsForExchange(); 
                loadExchanges(); 
                loadPendingExchanges();
                loadExchangeAllDrugs();
            }} else {{ 
                showToast('❌ خطا: ' + res.error, 'error'); 
            }}
        }})
        .catch(()=> showToast('❌ خطا در ارتباط با سرور', 'error'));
    }}
    
    function loadExchanges() {{
        fetch('/api/get_exchanges', {{
            headers: {{
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }}
        }})
        .then(r => r.json())
        .then(data => {{
            allMyExchanges = data.exchanges || [];
            renderMyExchangesList(allMyExchanges);
        }})
        .catch(err => {{
            showToast('❌ خطا در دریافت تبادلات', 'error');
        }});
    }}
    
    function loadPendingExchanges() {{
        fetch('/api/get_pending_exchanges', {{
            headers: {{
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }} 
        }})
        .then(r=>r.json())
        .then(d=>{{
            var exchanges = d.exchanges || [];
            if(exchanges.length===0){{
                document.getElementById('pendingExchangesList').innerHTML = '<p style="text-align:center;padding:30px;color:#999">هیچ تبادل دریافتی در انتظار تایید نیست</p>';
                return;
            }}
            var html = '';
            exchanges.forEach(ex => {{
                var d = new Date(ex.exchange_date + 'Z');
                var myItems = ex.my_items_json ? JSON.parse(ex.my_items_json) : [];
                var targetItems = ex.target_items_json ? JSON.parse(ex.target_items_json) : [];
                var sourceName = ex.source_pharmacy_name || 'داروخانه';
                html += '<div class="exchange-card">';
                html += '<div class="exchange-card-header">';
                html += '<h4>🏥 ' + sourceName + ' به شما پیشنهاد تبادل داده است</h4>';
                html += '<div class="date">' + d.toLocaleDateString('fa-IR') + ' ' + d.toLocaleTimeString('fa-IR') + '</div>';
                html += '</div>';
                html += '<div class="exchange-card-body">';
                if(targetItems.length > 0) {{
                    html += '<div class="exchange-section"><div class="exchange-section-title" style="color:#dc3545;">📦 داروهایی که از شما درخواست کرده:</div><ul class="exchange-drug-list">';
                    targetItems.forEach(i => {{
                        html += '<li><strong>' + i.name + '</strong> <span>' + i.quantity + ' عدد (انقضا: ' + (i.expiry_date || '-') + ')</span></li>';
                    }});
                    html += '</ul></div>';
                }}
                if(myItems.length > 0) {{
                    html += '<div class="exchange-section"><div class="exchange-section-title" style="color:#28a745;">📦 داروهایی که به شما می‌دهد:</div><ul class="exchange-drug-list">';
                    myItems.forEach(i => {{
                        html += '<li><strong>' + i.name + '</strong> <span>' + i.quantity + ' عدد (انقضا: ' + (i.expiry_date || '-') + ')</span></li>';
                    }});
                    html += '</ul></div>';
                }}
                html += '</div>';
                html += '<div class="exchange-card-footer">';
                html += '<button class="btn-success" onclick="confirmPendingExchange(' + ex.id + ')">✅ تایید تبادل</button>';
                html += '<button class="btn-danger" onclick="rejectPendingExchange(' + ex.id + ')">❌ رد درخواست</button>';
                html += '</div></div>';
            }});
            document.getElementById('pendingExchangesList').innerHTML = html;
        }})
        .catch(()=> showToast('❌ خطا در دریافت تبادلات', 'error'));
    }}
    
    function filterMyExchanges() {{
        var filter = document.getElementById('exchangePharmacyFilter').value.toLowerCase();
        var filtered = allMyExchanges.filter(ex => ex.buyer_name.toLowerCase().includes(filter));
        renderMyExchangesList(filtered);
    }}
    
    function renderMyExchangesList(exchanges) {{
        const container = document.getElementById('myExchangesList');
        if (!container) return;
        if (!exchanges || exchanges.length === 0) {{
            container.innerHTML = '<p style="text-align:center;padding:30px;color:#999;">هیچ تبادلی ثبت نشده است</p>';
            return;
        }}
        let html = '';
        exchanges.forEach(function(ex) {{
            const statusText = ex.status === 'confirmed' ? '✅ تایید شده' : '⏳ در انتظار';
            const statusColor = ex.status === 'confirmed' ? '#28a745' : '#ffc107';
            const date = new Date(ex.exchange_date + 'Z');
            let pharmacyName = ex.buyer_name || 'نامشخص';
            if (ex.source_pharmacy_id && ex.source_pharmacy_id != 1) {{
                pharmacyName = ex.source_pharmacy_name || pharmacyName;
            }}
            var myItems = ex.my_items_json ? JSON.parse(ex.my_items_json) : [];
            var targetItems = ex.target_items_json ? JSON.parse(ex.target_items_json) : [];
            
            html += '<div class="exchange-card">';
            html += '<div class="exchange-card-header">';
            html += '<h4>💊 ' + ex.drug_name + '</h4>';
            html += '<div><span style="background:' + statusColor + ';color:white;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:bold;">' + statusText + '</span></div>';
            html += '</div>';
            html += '<div class="exchange-card-body">';
            html += '<div style="font-size:12px;color:#999;margin-bottom:10px;">';
            html += '🏥 ' + pharmacyName + ' | 📅 ' + date.toLocaleDateString('fa-IR') + ' ' + date.toLocaleTimeString('fa-IR');
            if (ex.expiry_date) {{
                html += ' | 📅 انقضا: ' + ex.expiry_date;
            }}
            html += '</div>';
            
            if(myItems.length > 0) {{
                html += '<div class="exchange-section"><div class="exchange-section-title" style="color:#28a745;">📦 داروهایی که می‌دهم:</div><ul class="exchange-drug-list">';
                myItems.forEach(i => {{
                    html += '<li><strong>' + i.name + '</strong> <span>' + i.quantity + ' عدد (انقضا: ' + (i.expiry_date || '-') + ')</span></li>';
                }});
                html += '</ul></div>';
            }}
            if(targetItems.length > 0) {{
                html += '<div class="exchange-section"><div class="exchange-section-title" style="color:#dc3545;">📦 داروهایی که می‌گیرم:</div><ul class="exchange-drug-list">';
                targetItems.forEach(i => {{
                    html += '<li><strong>' + i.name + '</strong> <span>' + i.quantity + ' عدد (انقضا: ' + (i.expiry_date || '-') + ')</span></li>';
                }});
                html += '</ul></div>';
            }}
            html += '</div>';
            if (ex.status === 'pending') {{
                html += '<div class="exchange-card-footer">';
                html += '<button onclick="cancelExchange(' + ex.id + ')" class="btn-danger">❌ لغو درخواست</button>';
                html += '</div>';
            }}
            html += '</div>';
        }});
        container.innerHTML = html;
    }}
    
    function cancelExchange(exchangeId) {{
        if (!confirm('آیا از لغو این درخواست تبادل اطمینان دارید؟')) return;
        fetch('/api/reject_exchange/' + exchangeId, {{ method: 'POST' }})
            .then(r => r.json())
            .then(data => {{
                if (data.success) {{
                    showToast('✅ درخواست تبادل لغو شد', 'success');
                    loadExchanges();
                    loadPendingExchanges();
                }} else {{
                    showToast('❌ خطا: ' + data.error, 'error');
                }}
            }})
            .catch(() => showToast('❌ خطا در ارتباط با سرور', 'error'));
    }}
    
    function confirmPendingExchange(exchangeId) {{
        if(confirm('آیا از تایید این تبادل اطمینان دارید؟')) {{
            fetch('/api/confirm_exchange/' + exchangeId, {{ method: 'POST' }}).then(r=>r.json()).then(data=>{{ 
                if(data.success) {{ 
                    showToast('✅ تبادل با موفقیت تایید شد', 'success'); 
                    loadPendingExchanges(); 
                    loadExchanges(); 
                }} else {{ 
                    showToast('❌ خطا: ' + data.error, 'error'); 
                }} 
            }}).catch(()=> showToast('❌ خطا در ارتباط با سرور', 'error'));
        }}
    }}
    
    function rejectPendingExchange(exchangeId) {{
        if(confirm('آیا از رد این تبادل اطمینان دارید؟')) {{
            fetch('/api/reject_exchange/' + exchangeId, {{ method: 'POST' }}).then(r=>r.json()).then(data=>{{ 
                if(data.success) {{ 
                    showToast('✅ درخواست تبادل رد شد', 'success'); 
                    loadPendingExchanges(); 
                }} else {{ 
                    showToast('❌ خطا: ' + data.error, 'error'); 
                }} 
            }}).catch(()=> showToast('❌ خطا در ارتباط با سرور', 'error'));
        }}
    }}
    
    function showExchangeTab(tab) {{
        document.querySelectorAll('#registerTab, #listTab, #pendingTab').forEach(el => el.classList.remove('active'));
        document.querySelectorAll('.exchange-tab button').forEach(btn => btn.classList.remove('active'));
        if(tab === 'register') {{ 
            document.getElementById('registerTab').classList.add('active'); 
            document.querySelector('.exchange-tab button:first-child').classList.add('active'); 
            loadExchangeAllDrugs(); 
        }} else if(tab === 'list') {{ 
            document.getElementById('listTab').classList.add('active'); 
            document.querySelector('.exchange-tab button:nth-child(2)').classList.add('active'); 
            loadExchanges(); 
        }} else {{ 
            document.getElementById('pendingTab').classList.add('active'); 
            document.querySelector('.exchange-tab button:nth-child(3)').classList.add('active'); 
            loadPendingExchanges(); 
        }}
    }}
    
    loadUserCategories();
    loadExchanges();
    loadPendingExchanges();
    loadExchangeAllDrugs();
    </script>
    '''
    return render_template_string(HTML, content=content, page_title='🔄 تبادل دارو', session=session)

# ===== دفتر کسری =====
@app.route('/deficit')
@login_required
def deficit():
    content = '''
    <div class="card">
        <div class="card-title">➕ افزودن دارو به کسری</div>
        <div class="form-row">
            <div class="search-container" style="flex:2">
                <input type="text" id="drugName" placeholder="نام دارو" onkeyup="searchDrugs(this.value)" autocomplete="off">
                <div id="suggestions" class="suggestions-list"></div>
            </div>
            <input type="number" id="qty" placeholder="تعداد">
            <select id="type">
                <option value="normal">عادی</option>
                <option value="quota">سهمیه ای</option>
            </select>
            <select id="priority">
                <option value="1">اولویت 1</option>
                <option value="2">اولویت 2</option>
                <option value="3">اولویت 3</option>
                <option value="4">اولویت 4</option>
            </select>
            <button onclick="addDrug()">➕ افزودن</button>
        </div>
    </div>
    
    <div class="card">
        <div class="card-title">📋 لیست داروهای کسری</div>
        <div class="form-row">
            <button onclick="deleteSelectedDrugs()" class="btn-danger">🗑️ حذف انتخاب شده‌ها</button>
            <button onclick="selectAllDeficit()" class="btn-sm">✅ انتخاب همه</button>
            <button onclick="deselectAllDeficit()" class="btn-sm">❌ لغو همه</button>
        </div>
        <div id="list"></div>
    </div>
    
    <script>
    let allDrugs = [];
    const USER_ID = ''' + str(session['user_id']) + ''';
    
    function showToast(message, type) {
        var toast = document.getElementById('toast');
        toast.textContent = message;
        toast.className = 'toast-message ' + (type || 'info');
        toast.style.display = 'block';
        setTimeout(function() {
            toast.style.display = 'none';
        }, 3000);
    }
    
    function searchDrugs(query) {
        let suggestions = document.getElementById('suggestions');
        if(query.length < 1) { suggestions.style.display = 'none'; return; }
        fetch('/api/search_with_stock?q=' + encodeURIComponent(query))
            .then(r => r.json())
            .then(data => {
                let html = '';
                if(data.length > 0) {
                    data.forEach(drug => {
                        let totalStock = drug.warehouse_qty + drug.pharmacy_qty;
                        let stockStatus = '';
                        if(totalStock > 0) {
                            stockStatus = '🟢 <span style="color:#28a745;">موجود (' + totalStock + ' عدد)</span>';
                        } else {
                            stockStatus = '🔴 <span style="color:#dc3545;">ناموجود</span>';
                        }
                        html += '<div onclick="selectDrug(\\'' + drug.name + '\\')" style="padding:10px;border-bottom:1px solid #eee;cursor:pointer;">';
                        html += '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;">';
                        html += '<strong style="font-size:14px;">' + drug.name + '</strong>';
                        html += '<span style="font-size:12px;">' + stockStatus + '</span>';
                        html += '</div>';
                        html += '<div class="stock-info" style="font-size:11px;color:#666;margin-top:4px;">';
                        html += '🏭 انبار: ' + drug.warehouse_qty + ' عدد | 🏪 داروخانه: ' + drug.pharmacy_qty + ' عدد';
                        if(drug.nearest_expiry && drug.nearest_expiry !== '-') {
                            html += ' | 📅 نزدیک‌ترین انقضا: ' + drug.nearest_expiry;
                        }
                        html += '</div>';
                        html += '</div>';
                    });
                    suggestions.innerHTML = html;
                    suggestions.style.display = 'block';
                } else {
                    suggestions.innerHTML = '<div style="padding:10px;color:#999;">هیچ دارویی یافت نشد</div>';
                    suggestions.style.display = 'block';
                }
            })
            .catch(() => { suggestions.style.display = 'none'; });
    }
    
    function selectDrug(name) {
        document.getElementById('drugName').value = name;
        document.getElementById('suggestions').style.display = 'none';
    }
    
    function addDrug() {
        var name = document.getElementById('drugName').value.trim();
        var qty = document.getElementById('qty').value;
        var type = document.getElementById('type').value;
        var priority = document.getElementById('priority').value;
        if(!name) { showToast('❌ لطفاً نام دارو را وارد کنید', 'error'); return; }
        if(!qty || parseInt(qty) <= 0) { showToast('❌ تعداد معتبر وارد کنید', 'error'); return; }
        fetch('/api/add_drug', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, quantity: parseInt(qty), type: type, priority: parseInt(priority) })
        })
        .then(r => r.json())
        .then(data => {
            if(data.success) {
                showToast('✅ دارو به کسری اضافه شد', 'success');
                document.getElementById('drugName').value = '';
                document.getElementById('qty').value = '';
                loadDrugs();
            } else {
                showToast('❌ خطا: ' + data.error, 'error');
            }
        })
        .catch(err => { showToast('❌ خطا در ارتباط با سرور', 'error'); });
    }
    
    function loadDrugs() {
        fetch('/api/get_drugs').then(r=>r.json()).then(d=>{
            allDrugs = d.drugs || [];
            renderDrugsList();
        }).catch(() => showToast('❌ خطا در دریافت لیست', 'error'));
    }
    
    function renderDrugsList() {
        if(allDrugs.length==0){
            document.getElementById('list').innerHTML = '<p style="text-align:center;padding:30px;color:#999">لیست کسری خالی است</p>';
            return;
        }
        let html = '<table class="deficit-table"><thead><tr><th><input type="checkbox" id="selectAll" onchange="toggleSelectAll(this)"></th><th>نام دارو</th><th>تعداد</th><th>نوع</th><th>اولویت</th><th>عملیات</th></tr></thead><tbody>';
        allDrugs.forEach(d=>{
            let typeText = d.type=='quota' ? '<span style="color:#28a745">سهمیه ای</span>' : '<span style="color:#17a2b8">عادی</span>';
            html += '<tr data-id="'+d.id+'">';
            html += '<td><input type="checkbox" class="drug-checkbox" data-id="'+d.id+'"></td>';
            html += '<td><strong>' + d.name + '</strong></td>';
            html += '<td>' + d.quantity + ' عدد</td>';
            html += '<td>' + typeText + '</td>';
            html += '<td>' + d.priority + '</td>';
            html += '<td><button class="btn-danger btn-sm" onclick="del(' + d.id + ')">🗑️ حذف</button></td>';
            html += '</tr>';
        });
        html += '</tbody></table>';
        document.getElementById('list').innerHTML = html;
    }
    
    function toggleSelectAll(checkbox) {
        document.querySelectorAll('.drug-checkbox').forEach(cb => cb.checked = checkbox.checked);
    }
    
    function selectAllDeficit() {
        document.querySelectorAll('.drug-checkbox').forEach(cb => cb.checked = true);
    }
    
    function deselectAllDeficit() {
        document.querySelectorAll('.drug-checkbox').forEach(cb => cb.checked = false);
    }
    
    function getSelectedDrugIds() {
        let ids = [];
        document.querySelectorAll('.drug-checkbox:checked').forEach(cb => {
            ids.push(parseInt(cb.dataset.id));
        });
        return ids;
    }
    
    function deleteSelectedDrugs() {
        let ids = getSelectedDrugIds();
        if(ids.length === 0) { showToast('حداقل یک دارو را انتخاب کنید', 'error'); return; }
        if(confirm(ids.length + ' دارو حذف شود؟')) {
            fetch('/api/delete_drugs', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({drug_ids: ids})
            }).then(r=>r.json()).then(data=>{
                if(data.success) { showToast('✅ داروها حذف شدند', 'success'); loadDrugs(); }
                else { showToast('خطا: ' + data.error, 'error'); }
            }).catch(() => showToast('❌ خطا در ارتباط با سرور', 'error'));
        }
    }
    
    function del(id) {
        if(confirm('حذف شود؟')) fetch('/api/delete_drug/'+id, {method:'POST'}).then(()=>loadDrugs()).catch(()=>showToast('❌ خطا', 'error'));
    }
    
    document.addEventListener('click', function(e) {
        if(!e.target.closest('.search-container')) {
            document.getElementById('suggestions').style.display = 'none';
        }
    });
    
    loadDrugs();
    </script>
    '''
    return render_template_string(HTML, content=content, page_title='📋 دفتر کسری', session=session)

# ===== پنل ادمین =====
@app.route('/admin')
@admin_required
def admin_panel():
    db = get_db()
    
    cursor = db.execute("SELECT COUNT(*) as count FROM users")
    total_users = cursor.fetchone()['count']
    cursor = db.execute("SELECT COUNT(*) as count FROM users WHERE is_approved = 0")
    pending_users = cursor.fetchone()['count']
    cursor = db.execute("SELECT COUNT(*) as count FROM drugs")
    total_drugs = cursor.fetchone()['count']
    cursor = db.execute("SELECT SUM(quantity) as total FROM inventory")
    total_inventory = cursor.fetchone()['total'] or 0
    
    cursor = db.execute("SELECT * FROM users ORDER BY created_at DESC")
    users = cursor.fetchall()
    cursor = db.execute("SELECT * FROM interviews ORDER BY created_at DESC")
    interviews = cursor.fetchall()
    cursor = db.execute("SELECT * FROM announcements ORDER BY created_at DESC")
    announcements = cursor.fetchall()
    
    users_html = ''
    for u in users:
        status_badge = ''
        if u['username'] == 'admin':
            status_badge = '<span class="badge badge-danger">ادمین</span>'
        else:
            try:
                is_approved = u['is_approved']
            except:
                is_approved = 1
            if is_approved == 0:
                status_badge = '<span class="badge badge-warning">⏳ در انتظار تأیید</span>'
            elif is_approved == 2:
                status_badge = '<span class="badge badge-danger">❌ رد شده</span>'
            elif u['is_full_user']:
                status_badge = '<span class="badge badge-success">کاربر کامل</span>'
            else:
                status_badge = '<span class="badge badge-info">کاربر عادی</span>'
        
        actions = ''
        if u['username'] != 'admin':
            try:
                is_approved = u['is_approved']
            except:
                is_approved = 1
            if is_approved == 0:
                actions += f'<button onclick="approveUser({u["id"]})" class="btn-success btn-sm">✅ تأیید</button> '
                actions += f'<button onclick="rejectUser({u["id"]})" class="btn-danger btn-sm">❌ رد</button> '
            actions += f'<button onclick="deleteUser({u["id"]})" class="btn-danger btn-sm">🗑️</button>'
        else:
            actions = '<span style="color:#999;font-size:11px;">غیرقابل حذف</span>'
        
        try:
            phone = u['phone_number'] or '-'
        except:
            phone = '-'
        try:
            addr = u['address'] or '-'
        except:
            addr = '-'
        
        users_html += f'''
        <tr>
            <td>{u['id']}</td>
            <td><strong>{u['username']}</strong></td>
            <td>{u['pharmacy_display_name']}</td>
            <td>{phone}</td>
            <td>{addr}</td>
            <td>{status_badge}</td>
            <td>{u['created_at'][:10]}</td>
            <td>{actions}</td>
        </tr>
        '''
    
    interviews_html = ''
    for i in interviews:
        status = '✅ منتشر شده' if i['is_published'] else '⏳ پیش‌نویس'
        status_class = 'badge-success' if i['is_published'] else 'badge-warning'
        interviews_html += f'''
        <tr>
            <td>{i['id']}</td>
            <td><strong>{i['title']}</strong></td>
            <td>{i['pharmacist_name']}</td>
            <td>{i['pharmacy_name']}</td>
            <td><span class="badge {status_class}">{status}</span></td>
            <td>{i['created_at'][:10]}</td>
            <td>
                <button onclick="toggleInterview({i['id']})" class="btn-warning btn-sm">{'🔒 غیرفعال' if i['is_published'] else '✅ فعال'}</button>
                <button onclick="deleteInterview({i['id']})" class="btn-danger btn-sm">🗑️</button>
            </td>
        </tr>
        '''
    
    announcements_html = ''
    for a in announcements:
        status = '✅ فعال' if a['is_active'] else '⏳ غیرفعال'
        status_class = 'badge-success' if a['is_active'] else 'badge-warning'
        announcements_html += f'''
        <tr>
            <td>{a['id']}</td>
            <td><strong>{a['title']}</strong></td>
            <td>{a['content'][:50]}{'...' if len(a['content']) > 50 else ''}</td>
            <td><span class="badge {status_class}">{status}</span></td>
            <td>{a['created_at'][:10]}</td>
            <td>
                <button onclick="toggleAnnouncement({a['id']})" class="btn-warning btn-sm">{'🔒 غیرفعال' if a['is_active'] else '✅ فعال'}</button>
                <button onclick="deleteAnnouncement({a['id']})" class="btn-danger btn-sm">🗑️</button>
            </td>
        </tr>
        '''
    
    content = f'''
    <div class="stats-grid">
        <div class="stat-card"><div class="number">{total_users}</div><div class="label">👤 کل کاربران</div></div>
        <div class="stat-card"><div class="number">{pending_users}</div><div class="label" style="color:#856404;">⏳ در انتظار تأیید</div></div>
        <div class="stat-card"><div class="number">{total_drugs}</div><div class="label">💊 داروهای کسری</div></div>
        <div class="stat-card"><div class="number">{total_inventory}</div><div class="label">📦 موجودی انبار</div></div>
    </div>
    
    <div class="card">
        <div class="card-title">👤 مدیریت کاربران</div>
        <div class="table-responsive">
            <table>
                <thead><tr><th>#</th><th>نام کاربری</th><th>نام داروخانه</th><th>شماره همراه</th><th>آدرس</th><th>وضعیت</th><th>تاریخ ثبت</th><th>عملیات</th></tr></thead>
                <tbody>{users_html}</tbody>
            </table>
        </div>
    </div>
    
    <div class="card">
        <div class="card-title">🎙️ مدیریت مصاحبه‌ها</div>
        <form method="post" action="/admin/add_interview" style="margin-bottom:15px;padding:12px;background:#f8f9fa;border-radius:10px;">
            <div class="form-row">
                <input type="text" name="pharmacist_name" placeholder="نام داروساز" required>
                <input type="text" name="pharmacy_name" placeholder="نام داروخانه" required>
                <input type="text" name="title" placeholder="عنوان مصاحبه" required>
            </div>
            <div class="form-row">
                <textarea name="content" placeholder="متن مصاحبه (HTML مجاز)" required style="flex:3;"></textarea>
            </div>
            <div class="form-row">
                <input type="text" name="image_url" placeholder="آدرس تصویر">
                <input type="text" name="audio_url" placeholder="آدرس فایل صوتی">
                <button type="submit" class="btn-success">➕ افزودن مصاحبه</button>
            </div>
        </form>
        <div class="table-responsive">
            <table>
                <thead><tr><th>#</th><th>عنوان</th><th>داروساز</th><th>داروخانه</th><th>وضعیت</th><th>تاریخ</th><th>عملیات</th></tr></thead>
                <tbody>{interviews_html}</tbody>
            </table>
        </div>
    </div>
    
    <div class="card">
        <div class="card-title">📢 مدیریت اطلاعیه‌ها</div>
        <form method="post" action="/admin/add_announcement" style="margin-bottom:15px;padding:12px;background:#f8f9fa;border-radius:10px;">
            <div class="form-row">
                <input type="text" name="title" placeholder="عنوان اطلاعیه" required style="flex:1;">
                <input type="text" name="content" placeholder="متن اطلاعیه" required style="flex:2;">
                <button type="submit" class="btn-primary">➕ افزودن اطلاعیه</button>
            </div>
        </form>
        <div class="table-responsive">
            <table>
                <thead><tr><th>#</th><th>عنوان</th><th>متن</th><th>وضعیت</th><th>تاریخ</th><th>عملیات</th></tr></thead>
                <tbody>{announcements_html}</tbody>
            </table>
        </div>
    </div>
    
    <script>
    function showToast(message, type) {{
        var toast = document.getElementById('toast');
        toast.textContent = message;
        toast.className = 'toast-message ' + (type || 'info');
        toast.style.display = 'block';
        setTimeout(function() {{
            toast.style.display = 'none';
        }}, 3000);
    }}
    
    function approveUser(id) {{
        if(confirm('آیا از تأیید این کاربر اطمینان دارید؟')) {{
            fetch('/admin/approve_user/'+id, {{method:'POST'}}).then(r=>r.json()).then(data=>{{
                if(data.success) {{ showToast('✅ کاربر تأیید شد', 'success'); location.reload(); }}
                else {{ showToast('❌ خطا: ' + data.error, 'error'); }}
            }}).catch(()=> showToast('❌ خطا در ارتباط با سرور', 'error'));
        }}
    }}
    
    function rejectUser(id) {{
        if(confirm('آیا از رد این کاربر اطمینان دارید؟')) {{
            fetch('/admin/reject_user/'+id, {{method:'POST'}}).then(r=>r.json()).then(data=>{{
                if(data.success) {{ showToast('✅ کاربر رد شد', 'success'); location.reload(); }}
                else {{ showToast('❌ خطا: ' + data.error, 'error'); }}
            }}).catch(()=> showToast('❌ خطا در ارتباط با سرور', 'error'));
        }}
    }}
    
    function deleteUser(id) {{
        if(confirm('آیا از حذف این کاربر اطمینان دارید؟')) {{
            fetch('/admin/delete_user/'+id, {{method:'POST'}}).then(r=>r.json()).then(data=>{{
                if(data.success) {{ showToast('✅ کاربر حذف شد', 'success'); location.reload(); }}
                else {{ showToast('❌ خطا: ' + data.error, 'error'); }}
            }}).catch(()=> showToast('❌ خطا در ارتباط با سرور', 'error'));
        }}
    }}
    
    function toggleInterview(id) {{
        fetch('/admin/toggle_interview/'+id, {{method:'POST'}}).then(r=>r.json()).then(data=>{{
            if(data.success) location.reload();
            else showToast('❌ خطا: ' + data.error, 'error');
        }}).catch(()=> showToast('❌ خطا در ارتباط با سرور', 'error'));
    }}
    
    function deleteInterview(id) {{
        if(confirm('آیا از حذف این مصاحبه اطمینان دارید؟')) {{
            fetch('/admin/delete_interview/'+id, {{method:'POST'}}).then(r=>r.json()).then(data=>{{
                if(data.success) {{ showToast('✅ مصاحبه حذف شد', 'success'); location.reload(); }}
                else {{ showToast('❌ خطا: ' + data.error, 'error'); }}
            }}).catch(()=> showToast('❌ خطا در ارتباط با سرور', 'error'));
        }}
    }}
    
    function toggleAnnouncement(id) {{
        fetch('/admin/toggle_announcement/'+id, {{method:'POST'}}).then(r=>r.json()).then(data=>{{
            if(data.success) location.reload();
            else showToast('❌ خطا: ' + data.error, 'error');
        }}).catch(()=> showToast('❌ خطا در ارتباط با سرور', 'error'));
    }}
    
    function deleteAnnouncement(id) {{
        if(confirm('آیا از حذف این اطلاعیه اطمینان دارید؟')) {{
            fetch('/admin/delete_announcement/'+id, {{method:'POST'}}).then(r=>r.json()).then(data=>{{
                if(data.success) {{ showToast('✅ اطلاعیه حذف شد', 'success'); location.reload(); }}
                else {{ showToast('❌ خطا: ' + data.error, 'error'); }}
            }}).catch(()=> showToast('❌ خطا در ارتباط با سرور', 'error'));
        }}
    }}
    </script>
    '''
    return render_template_string(HTML, content=content, page_title='👑 پنل ادمین', session=session)

# ===== روت‌های ادمین API =====

@app.route('/admin/approve_user/<int:user_id>', methods=['POST'])
@admin_required
def approve_user(user_id):
    db = get_db()
    db.execute("UPDATE users SET is_approved = 1 WHERE id = ? AND username != 'admin'", (user_id,))
    db.commit()
    return jsonify({'success': True})

@app.route('/admin/reject_user/<int:user_id>', methods=['POST'])
@admin_required
def reject_user(user_id):
    db = get_db()
    db.execute("UPDATE users SET is_approved = 2 WHERE id = ? AND username != 'admin'", (user_id,))
    db.commit()
    return jsonify({'success': True})

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    db = get_db()
    cursor = db.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        return jsonify({'success': False, 'error': 'کاربر یافت نشد'})
    if user['username'] == 'admin':
        return jsonify({'success': False, 'error': 'نمی‌توان ادمین را حذف کرد'})
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.execute("DELETE FROM drugs WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM inventory WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM orders WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM sales WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM exchanges WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM user_categories WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM hidden_items WHERE user_id = ?", (user_id,))
    db.commit()
    return jsonify({'success': True})

@app.route('/admin/add_interview', methods=['POST'])
@admin_required
def add_interview():
    pharmacist_name = request.form.get('pharmacist_name')
    pharmacy_name = request.form.get('pharmacy_name')
    title = request.form.get('title')
    content = request.form.get('content')
    image_url = request.form.get('image_url', '')
    audio_url = request.form.get('audio_url', '')
    if not pharmacist_name or not pharmacy_name or not title or not content:
        return '❌ همه فیلدها اجباری هستند', 400
    db = get_db()
    db.execute('''INSERT INTO interviews (pharmacist_name, pharmacy_name, title, content, image_url, audio_url, created_at, is_published)
                  VALUES (?, ?, ?, ?, ?, ?, ?, 1)''',
               (pharmacist_name, pharmacy_name, title, content, image_url, audio_url, datetime.now().isoformat()))
    db.commit()
    return redirect(url_for('admin_panel'))

@app.route('/admin/toggle_interview/<int:interview_id>', methods=['POST'])
@admin_required
def toggle_interview(interview_id):
    db = get_db()
    cursor = db.execute("SELECT is_published FROM interviews WHERE id = ?", (interview_id,))
    interview = cursor.fetchone()
    if not interview:
        return jsonify({'success': False, 'error': 'مصاحبه یافت نشد'})
    new_status = 0 if interview['is_published'] else 1
    db.execute("UPDATE interviews SET is_published = ? WHERE id = ?", (new_status, interview_id))
    db.commit()
    return jsonify({'success': True})

@app.route('/admin/delete_interview/<int:interview_id>', methods=['POST'])
@admin_required
def delete_interview(interview_id):
    db = get_db()
    db.execute("DELETE FROM interviews WHERE id = ?", (interview_id,))
    db.commit()
    return jsonify({'success': True})

@app.route('/admin/add_announcement', methods=['POST'])
@admin_required
def add_announcement():
    title = request.form.get('title')
    content = request.form.get('content')
    if not title or not content:
        return '❌ همه فیلدها اجباری هستند', 400
    db = get_db()
    db.execute('''INSERT INTO announcements (title, content, created_at, is_active)
                  VALUES (?, ?, ?, 1)''',
               (title, content, datetime.now().isoformat()))
    db.commit()
    return redirect(url_for('admin_panel'))

@app.route('/admin/toggle_announcement/<int:announcement_id>', methods=['POST'])
@admin_required
def toggle_announcement(announcement_id):
    db = get_db()
    cursor = db.execute("SELECT is_active FROM announcements WHERE id = ?", (announcement_id,))
    announcement = cursor.fetchone()
    if not announcement:
        return jsonify({'success': False, 'error': 'اطلاعیه یافت نشد'})
    new_status = 0 if announcement['is_active'] else 1
    db.execute("UPDATE announcements SET is_active = ? WHERE id = ?", (new_status, announcement_id))
    db.commit()
    return jsonify({'success': True})

@app.route('/admin/delete_announcement/<int:announcement_id>', methods=['POST'])
@admin_required
def delete_announcement(announcement_id):
    db = get_db()
    db.execute("DELETE FROM announcements WHERE id = ?", (announcement_id,))
    db.commit()
    return jsonify({'success': True})

# ===== API اصلی =====

@app.route('/api/set_registered_name', methods=['POST'])
@login_required
def api_set_registered_name():
    data = request.get_json()
    name = data.get('name')
    if not name or name.strip() == '':
        return jsonify({'success': False, 'error': 'نام معتبر وارد کنید'})
    session['registered_name'] = name.strip()
    return jsonify({'success': True})

@app.route('/api/get_current_user')
@login_required
def api_get_current_user():
    user = get_current_user_from_session()
    if not user:
        return jsonify({'error': 'user not found'}), 404
    try:
        is_approved = user['is_approved']
    except:
        is_approved = 1
    return jsonify({
        'id': user['id'],
        'username': user['username'],
        'is_full_user': user['is_full_user'],
        'pharmacy_display_name': user['pharmacy_display_name'],
        'is_approved': is_approved,
        'registered_name': session.get('registered_name', user['pharmacy_display_name'])
    })

@app.route('/api/get_drugs')
@login_required
def api_get_drugs():
    db = get_db()
    user_id = session['user_id']
    cursor = db.execute("SELECT * FROM drugs WHERE user_id = ? AND ordered = 0 ORDER BY priority ASC, created_at DESC", (user_id,))
    return jsonify({'drugs': [dict(row) for row in cursor.fetchall()]})

@app.route('/api/get_all_drugs')
@login_required
def api_get_all_drugs():
    db = get_db()
    user_id = session['user_id']
    cursor = db.execute("SELECT * FROM drugs WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    return jsonify({'drugs': [dict(row) for row in cursor.fetchall()]})

@app.route('/api/get_orders')
@login_required
def api_get_orders():
    db = get_db()
    user_id = session['user_id']
    cursor = db.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY ordered_at DESC", (user_id,))
    return jsonify({'orders': [dict(row) for row in cursor.fetchall()]})

@app.route('/api/get_inventory')
@login_required
def api_get_inventory():
    db = get_db()
    user_id = session['user_id']
    cursor = db.execute("SELECT * FROM inventory WHERE user_id = ? AND quantity > 0 ORDER BY created_at DESC", (user_id,))
    return jsonify({'items': [dict(row) for row in cursor.fetchall()]})

@app.route('/api/get_pharmacy_drugs')
@login_required
def api_get_pharmacy_drugs():
    pharmacy_id = request.args.get('pharmacy_id', type=int)
    if not pharmacy_id:
        return jsonify({'drugs': []})
    db = get_db()
    cursor = db.execute("SELECT id, name, quantity, expiry_date FROM inventory WHERE user_id = ? AND quantity > 0", (pharmacy_id,))
    return jsonify({'drugs': [dict(row) for row in cursor.fetchall()]})

@app.route('/api/get_all_pharmacies')
@login_required
def api_get_all_pharmacies():
    db = get_db()
    cursor = db.execute("SELECT id, pharmacy_display_name FROM users WHERE id != ? AND is_approved = 1", (session['user_id'],))
    pharmacies = cursor.fetchall()
    try:
        is_pending = session.get('is_approved', 1) == 0
    except:
        is_pending = False
    result = []
    for p in pharmacies:
        name = p['pharmacy_display_name']
        if is_pending:
            name = mask_pharmacy_name(name)
        result.append({'id': p['id'], 'name': name})
    return jsonify({'pharmacies': result})

@app.route('/api/delete_drug/<int:drug_id>', methods=['POST'])
@login_required
def api_delete_drug(drug_id):
    db = get_db()
    user_id = session['user_id']
    db.execute("DELETE FROM drugs WHERE id = ? AND user_id = ?", (drug_id, user_id))
    db.commit()
    return jsonify({'success': True})

@app.route('/api/delete_drugs', methods=['POST'])
@login_required
def api_delete_drugs():
    db = get_db()
    user_id = session['user_id']
    data = request.get_json()
    drug_ids = data.get('drug_ids', [])
    if not drug_ids:
        return jsonify({'success': False, 'error': 'هیچ دارویی انتخاب نشده است'})
    placeholders = ','.join('?' for _ in drug_ids)
    db.execute(f"DELETE FROM drugs WHERE id IN ({placeholders}) AND user_id = ?", (*drug_ids, user_id))
    db.commit()
    return jsonify({'success': True})

@app.route('/api/delete_inventory_item/<int:item_id>', methods=['POST'])
@login_required
def api_delete_inventory_item(item_id):
    db = get_db()
    user_id = session['user_id']
    db.execute("DELETE FROM inventory WHERE id = ? AND user_id = ?", (item_id, user_id))
    db.commit()
    return jsonify({'success': True})

@app.route('/api/delete_inventory_items', methods=['POST'])
@login_required
def api_delete_inventory_items():
    db = get_db()
    user_id = session['user_id']
    data = request.get_json()
    item_ids = data.get('item_ids', [])
    if not item_ids:
        return jsonify({'success': False, 'error': 'هیچ آیتمی انتخاب نشده است'})
    placeholders = ','.join('?' for _ in item_ids)
    db.execute(f"DELETE FROM inventory WHERE id IN ({placeholders}) AND user_id = ?", (*item_ids, user_id))
    db.commit()
    return jsonify({'success': True})

@app.route('/api/add_drug', methods=['POST'])
@login_required
def add_drug():
    db = get_db()
    user_id = session['user_id']
    if request.is_json:
        data = request.get_json()
        name = data.get('name')
        quantity = data.get('quantity', 0)
        drug_type = data.get('type', 'normal')
        priority = data.get('priority', 4)
    else:
        name = request.form.get('name')
        quantity = int(request.form.get('quantity', 0))
        drug_type = request.form.get('type', 'normal')
        priority = int(request.form.get('priority', 4))
    if not name or not name.strip():
        return jsonify({'success': False, 'error': 'نام دارو را وارد کنید'})
    if not quantity or quantity <= 0:
        return jsonify({'success': False, 'error': 'تعداد معتبر وارد کنید'})
    db.execute('INSERT INTO drugs (user_id, name, quantity, type, priority, created_at, ordered) VALUES (?, ?, ?, ?, ?, ?, ?)',
               (user_id, name.strip(), quantity, drug_type, priority, datetime.now().isoformat(), 0))
    db.commit()
    return jsonify({'success': True})

@app.route('/api/place_order', methods=['POST'])
@login_required
def place_order():
    db = get_db()
    user_id = session['user_id']
    req = request.get_json()
    selected_ids = req.get('selected_ids', [])
    company = req.get('company')
    quantities = req.get('quantities', {})
    if not selected_ids:
        return jsonify({'success': False, 'error': 'هیچ دارویی انتخاب نشده است'})
    for drug_id in selected_ids:
        cursor = db.execute("SELECT * FROM drugs WHERE id = ? AND user_id = ?", (drug_id, user_id))
        drug = cursor.fetchone()
        if drug:
            qty = int(quantities.get(str(drug_id), drug['quantity']))
            db.execute('INSERT INTO orders (user_id, company, drug_name, quantity, ordered_at) VALUES (?, ?, ?, ?, ?)',
                      (user_id, company, drug['name'], qty, datetime.now().isoformat()))
            if drug['type'] != 'quota':
                db.execute("UPDATE drugs SET ordered = 1 WHERE id = ?", (drug_id,))
    db.execute("DELETE FROM drugs WHERE ordered = 1 AND user_id = ? AND type != 'quota'", (user_id,))
    db.commit()
    return jsonify({'success': True})

@app.route('/api/search_with_stock')
@login_required
def search_with_stock():
    q = request.args.get('q', '')
    user_id = session['user_id']
    db = get_db()
    cursor = db.execute("SELECT DISTINCT name FROM inventory WHERE user_id = ? AND name LIKE ? LIMIT 10", (user_id, f'%{q}%'))
    names = [row['name'] for row in cursor.fetchall()]
    result = []
    for name in names:
        cursor = db.execute("SELECT SUM(quantity) as total FROM inventory WHERE user_id = ? AND name = ? AND location = 'warehouse'", (user_id, name))
        warehouse_qty = cursor.fetchone()['total'] or 0
        cursor = db.execute("SELECT SUM(quantity) as total FROM inventory WHERE user_id = ? AND name = ? AND location = 'pharmacy'", (user_id, name))
        pharmacy_qty = cursor.fetchone()['total'] or 0
        cursor = db.execute("SELECT expiry_date FROM inventory WHERE user_id = ? AND name = ? AND expiry_date IS NOT NULL AND expiry_date != '' ORDER BY expiry_date ASC LIMIT 1", (user_id, name))
        nearest = cursor.fetchone()
        result.append({'name': name, 'warehouse_qty': warehouse_qty, 'pharmacy_qty': pharmacy_qty, 'nearest_expiry': nearest['expiry_date'] if nearest else '-'})
    return jsonify(result)

# تنظیم لاگ
LOG_FILE = '/var/www/poldaroo/pharmacy.log'
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

@app.route('/api/get_inventory_grouped_by_expiry')
@login_required
def get_inventory_grouped_by_expiry():
    db = get_db()
    user_id = session['user_id']
    cursor = db.execute("SELECT item_id FROM hidden_items WHERE user_id = ?", (user_id,))
    hidden_ids = [row['item_id'] for row in cursor.fetchall()]
    cursor = db.execute("""
        SELECT id, name, quantity, expiry_date, registered_by, created_at 
        FROM inventory 
        WHERE user_id = ? AND quantity > 0
        ORDER BY 
            CASE WHEN expiry_date IS NULL OR expiry_date = '' THEN 1 ELSE 0 END,
            substr(expiry_date, 1, 4) ASC,
            substr(expiry_date, 6, 2) ASC
    """, (user_id,))
    items = [dict(row) for row in cursor.fetchall()]
    cursor = db.execute("SELECT pharmacy_display_name FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    pharmacy_name = user['pharmacy_display_name'] if user else 'داروخانه من'
    expiry_groups = {}
    for item in items:
        expiry = item['expiry_date'] or 'نامشخص'
        if expiry not in expiry_groups:
            expiry_groups[expiry] = []
        expiry_groups[expiry].append(item)
    result = []
    for expiry_date, drugs in expiry_groups.items():
        drugs.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        pharmacies = [{
            'pharmacy_id': user_id,
            'pharmacy_name': pharmacy_name,
            'last_update': convert_date_to_jalali(drugs[0]['created_at']) if drugs and drugs[0]['created_at'] else '',
            'drugs': [{
                'id': d['id'],
                'name': d['name'],
                'quantity': d['quantity'],
                'expiry_date': d['expiry_date'],
                'registered_by': d.get('registered_by', 'نامشخص'),
                'created_at': d.get('created_at'),
                'created_at_jalali': convert_date_to_jalali(d.get('created_at', '')),
                'hidden': d['id'] in hidden_ids
            } for d in drugs]
        }]
        result.append({
            'expiry_date': expiry_date,
            'status_text': get_expiry_status(expiry_date)['text'],
            'pharmacies': pharmacies
        })
    result.sort(key=lambda x: parse_expiry_number(x['expiry_date']))
    return jsonify({'data': result})

@app.route('/api/get_all_pharmacies_drugs_grouped_by_expiry')
@login_required
def get_all_pharmacies_drugs_grouped_by_expiry():
    user_id = session['user_id']
    db = get_db()
    result = []
    cursor = db.execute("SELECT item_id FROM hidden_items WHERE user_id = ?", (user_id,))
    hidden_ids = [row['item_id'] for row in cursor.fetchall()]
    cursor = db.execute("""
        SELECT id, pharmacy_display_name 
        FROM users 
        WHERE id != ? AND is_approved = 1
    """, (user_id,))
    other_pharmacies = [dict(row) for row in cursor.fetchall()]
    cursor = db.execute("SELECT pharmacy_display_name FROM users WHERE id = ?", (user_id,))
    my_user = cursor.fetchone()
    my_pharmacy_name = my_user['pharmacy_display_name'] if my_user else 'داروخانه من'
    all_pharmacies = [{'id': user_id, 'pharmacy_display_name': my_pharmacy_name}] + other_pharmacies
    expiry_groups = {}
    for ph in all_pharmacies:
        cursor = db.execute("""
            SELECT id, name, quantity, expiry_date, location, created_at 
            FROM inventory 
            WHERE user_id = ? AND quantity > 0
        """, (ph['id'],))
        drugs = [dict(row) for row in cursor.fetchall()]
        if not drugs:
            continue
        for drug in drugs:
            if ph['id'] == user_id and drug['id'] in hidden_ids:
                continue
            expiry = drug['expiry_date'] or 'نامشخص'
            if expiry not in expiry_groups:
                expiry_groups[expiry] = {}
            if ph['id'] not in expiry_groups[expiry]:
                expiry_groups[expiry][ph['id']] = {
                    'pharmacy_id': ph['id'],
                    'pharmacy_name': ph['pharmacy_display_name'],
                    'drugs': [],
                    'last_update': ''
                }
            expiry_groups[expiry][ph['id']]['drugs'].append({
                'id': drug['id'],
                'name': drug['name'],
                'quantity': drug['quantity'],
                'expiry_date': drug['expiry_date'],
                'location': drug['location'],
                'hidden': drug['id'] in hidden_ids
            })
            if drug.get('created_at') and drug['created_at'] > expiry_groups[expiry][ph['id']]['last_update']:
                expiry_groups[expiry][ph['id']]['last_update'] = convert_date_to_jalali(drug['created_at'])
    for expiry_date, pharmacies_dict in expiry_groups.items():
        pharmacies = list(pharmacies_dict.values())
        pharmacies.sort(key=lambda x: x['last_update'], reverse=True)
        result.append({
            'expiry_date': expiry_date,
            'status_text': get_expiry_status(expiry_date)['text'],
            'pharmacies': pharmacies
        })
    result.sort(key=lambda x: parse_expiry_number(x['expiry_date']))
    return jsonify({'data': result})

@app.route('/api/get_my_drugs_for_exchange')
@login_required
def get_my_drugs_for_exchange():
    user_id = session['user_id']
    db = get_db()
    cursor = db.execute("SELECT id, name, quantity, expiry_date FROM inventory WHERE user_id = ? AND quantity > 0", (user_id,))
    return jsonify({'drugs': [dict(row) for row in cursor.fetchall()]})

@app.route('/api/get_pharmacy_drugs_for_exchange')
@login_required
def get_pharmacy_drugs_for_exchange():
    pharmacy_id = request.args.get('pharmacy_id', type=int)
    if not pharmacy_id:
        return jsonify({'drugs': []})
    db = get_db()
    cursor = db.execute("SELECT id, name, quantity, expiry_date FROM inventory WHERE user_id = ? AND quantity > 0 ORDER BY name", (pharmacy_id,))
    return jsonify({'drugs': [dict(row) for row in cursor.fetchall()]})

@app.route('/api/add_inventory', methods=['POST'])
@login_required
def add_inventory():
    logging.info(f"🚀 add_inventory called by user_id={session['user_id']}")
    try:
        db = get_db()
        user_id = session['user_id']
        name = request.form.get('name')
        quantity = int(request.form.get('quantity', 0))
        expiry_date = request.form.get('expiry_date')
        registered_by = request.form.get('registered_by', session.get('registered_name', session.get('pharmacy_display_name', 'کاربر')))
        edit_id = request.form.get('edit_id')
        
        logging.info(f"📦 Data: name={name}, qty={quantity}, expiry={expiry_date}, registered_by={registered_by}, edit_id={edit_id}")
        
        if not name or quantity <= 0 or not expiry_date:
            logging.error("❌ Missing required fields")
            return jsonify({'success': False, 'error': 'نام، تعداد و تاریخ انقضا اجباری است'})
        if not validate_expiry_date(expiry_date):
            logging.error(f"❌ Invalid expiry date: {expiry_date}")
            return jsonify({'success': False, 'error': 'تاریخ انقضا نامعتبر است'})
        
        if edit_id:
            db.execute("DELETE FROM inventory WHERE id = ? AND user_id = ?", (edit_id, user_id))
            logging.info(f"🔄 Deleting old item id={edit_id} for edit")
        
        cursor = db.execute("SELECT id, quantity FROM inventory WHERE user_id = ? AND name = ? AND expiry_date = ?", 
                           (user_id, name, expiry_date))
        existing = cursor.fetchone()
        if existing:
            logging.info(f"🔄 Updating existing drug id={existing['id']}, old_qty={existing['quantity']}, add={quantity}")
            db.execute("UPDATE inventory SET quantity = quantity + ?, registered_by = ? WHERE id = ?", 
                      (quantity, registered_by, existing['id']))
        else:
            logging.info(f"➕ Inserting new drug")
            db.execute('''INSERT INTO inventory (user_id, name, quantity, expiry_date, registered_by, created_at)
                          VALUES (?, ?, ?, ?, ?, ?)''',
                       (user_id, name, quantity, expiry_date, registered_by, datetime.now().isoformat()))
        db.commit()
        logging.info(f"✅ Successfully added/updated inventory for {name}")
        return jsonify({'success': True})
    except Exception as e:
        logging.error(f"❌ Exception in add_inventory: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)})

# ===== API تبادل =====

@app.route('/api/register_exchange', methods=['POST'])
@login_required
def register_exchange():
    db = get_db()
    user_id = session['user_id']
    data = request.get_json()
    target_pharmacy_id = data.get('target_pharmacy_id')
    my_items = data.get('my_items', [])
    target_items = data.get('target_items', [])
    if not target_pharmacy_id:
        return jsonify({'success': False, 'error': 'Target pharmacy not selected'})
    cursor = db.execute("SELECT categories FROM user_categories WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    sender_categories = row['categories'] if row else ''
    cursor = db.execute("SELECT pharmacy_display_name FROM users WHERE id = ?", (user_id,))
    sender = cursor.fetchone()
    sender_name = sender['pharmacy_display_name'] if sender else 'My Pharmacy'
    cursor = db.execute("SELECT pharmacy_display_name FROM users WHERE id = ?", (target_pharmacy_id,))
    target = cursor.fetchone()
    target_name = target['pharmacy_display_name'] if target else 'Target Pharmacy'
    now_iran = get_iran_time_iso()
    if target_items:
        for item in target_items:
            db.execute('''INSERT INTO exchanges (
                user_id, buyer_name, drug_name, quantity, expiry_date, location, 
                exchange_date, status, target_pharmacy_id, sender_categories, 
                my_items_json, target_items_json, source_pharmacy_id, source_pharmacy_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?)''',
                (target_pharmacy_id, sender_name, item['name'], item['quantity'], 
                 item.get('expiry_date', ''), 'pharmacy', now_iran, user_id, 
                 sender_categories, json.dumps(my_items), json.dumps(target_items), 
                 user_id, sender_name))
    if my_items:
        for item in my_items:
            db.execute('''INSERT INTO exchanges (
                user_id, buyer_name, drug_name, quantity, expiry_date, location, 
                exchange_date, status, target_pharmacy_id, sender_categories, 
                my_items_json, target_items_json, source_pharmacy_id, source_pharmacy_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?)''',
                (user_id, target_name, item['name'], item['quantity'], 
                 item.get('expiry_date', ''), 'pharmacy', now_iran, target_pharmacy_id, 
                 sender_categories, json.dumps(my_items), json.dumps(target_items), 
                 user_id, sender_name))
    db.commit()
    return jsonify({'success': True})

@app.route('/api/get_exchanges')
@login_required
def get_exchanges():
    db = get_db()
    user_id = session['user_id']
    cursor = db.execute("""
        SELECT * FROM exchanges 
        WHERE user_id = ? 
        OR target_pharmacy_id = ?
        OR source_pharmacy_id = ?
        ORDER BY exchange_date DESC
    """, (user_id, user_id, user_id))
    exchanges = []
    for row in cursor.fetchall():
        ex = dict(row)
        if ex.get('exchange_date'):
            try:
                dt = datetime.fromisoformat(ex['exchange_date'])
                iran_time = dt + timedelta(hours=3, minutes=30)
                ex['exchange_date'] = iran_time.isoformat()
            except:
                pass
        exchanges.append(ex)
    return jsonify({'exchanges': exchanges})

@app.route('/api/get_pending_exchanges')
@login_required
def get_pending_exchanges():
    db = get_db()
    user_id = session['user_id']
    cursor = db.execute("""
        SELECT * FROM exchanges 
        WHERE (user_id = ? OR target_pharmacy_id = ?)
        AND status = 'pending'
        AND source_pharmacy_id IS NOT NULL
        AND source_pharmacy_id != ?
        ORDER BY exchange_date DESC
    """, (user_id, user_id, user_id))
    exchanges = []
    for row in cursor.fetchall():
        ex = dict(row)
        if ex.get('exchange_date'):
            try:
                dt = datetime.fromisoformat(ex['exchange_date'])
                iran_time = dt + timedelta(hours=3, minutes=30)
                ex['exchange_date'] = iran_time.isoformat()
            except:
                pass
        exchanges.append(ex)
    return jsonify({'exchanges': exchanges})

@app.route('/api/confirm_exchange/<int:exchange_id>', methods=['POST'])
@login_required
def confirm_exchange(exchange_id):
    db = get_db()
    user_id = session['user_id']
    cursor = db.execute("SELECT * FROM exchanges WHERE id = ? AND user_id = ? AND status = 'pending'", (exchange_id, user_id))
    exchange = cursor.fetchone()
    if not exchange:
        return jsonify({'success': False, 'error': 'تبادل یافت نشد یا قبلا پردازش شده است'})
    exchange_dict = dict(exchange)
    if exchange_dict.get('source_pharmacy_id') and exchange_dict['source_pharmacy_id'] != user_id:
        target_items = json.loads(exchange_dict['target_items_json']) if exchange_dict['target_items_json'] else []
        my_items = json.loads(exchange_dict['my_items_json']) if exchange_dict['my_items_json'] else []
        for item in target_items:
            drug_name = item.get('name')
            expiry_date = item.get('expiry_date', '')
            quantity = item.get('quantity')
            cursor = db.execute("SELECT * FROM inventory WHERE user_id = ? AND name = ? AND expiry_date = ? AND quantity > 0", (user_id, drug_name, expiry_date))
            inv_items = cursor.fetchall()
            total_available = sum(i['quantity'] for i in inv_items)
            if total_available < quantity:
                return jsonify({'success': False, 'error': f'موجودی {drug_name} با تاریخ {expiry_date} کافی نیست'})
            remaining = quantity
            for inv_item in inv_items:
                if remaining <= 0:
                    break
                take = min(inv_item['quantity'], remaining)
                new_qty = inv_item['quantity'] - take
                if new_qty == 0:
                    db.execute("DELETE FROM inventory WHERE id = ?", (inv_item['id'],))
                else:
                    db.execute("UPDATE inventory SET quantity = ? WHERE id = ?", (new_qty, inv_item['id']))
                remaining -= take
        for item in my_items:
            drug_name = item.get('name')
            expiry_date = item.get('expiry_date', '')
            quantity = item.get('quantity')
            cursor = db.execute("SELECT * FROM inventory WHERE user_id = ? AND name = ? AND expiry_date = ?", (user_id, drug_name, expiry_date))
            inv_item = cursor.fetchone()
            if inv_item:
                db.execute("UPDATE inventory SET quantity = quantity + ? WHERE id = ?", (quantity, inv_item['id']))
            else:
                db.execute('''INSERT INTO inventory (user_id, name, quantity, expiry_date, created_at)
                              VALUES (?, ?, ?, ?, ?)''',
                           (user_id, drug_name, quantity, expiry_date, get_iran_time_iso()))
    db.execute("UPDATE exchanges SET status = 'confirmed' WHERE id = ?", (exchange_id,))
    if exchange_dict.get('source_pharmacy_id'):
        db.execute("UPDATE exchanges SET status = 'confirmed' WHERE source_pharmacy_id = ? AND target_pharmacy_id = ? AND status = 'pending'",
                   (exchange_dict['source_pharmacy_id'], user_id))
    db.commit()
    return jsonify({'success': True})

@app.route('/api/reject_exchange/<int:exchange_id>', methods=['POST'])
@login_required
def reject_exchange(exchange_id):
    db = get_db()
    user_id = session['user_id']
    cursor = db.execute("SELECT * FROM exchanges WHERE id = ? AND user_id = ? AND status = 'pending'", (exchange_id, user_id))
    exchange = cursor.fetchone()
    if not exchange:
        return jsonify({'success': False, 'error': 'تبادل یافت نشد یا قبلا پردازش شده است'})
    exchange_dict = dict(exchange)
    db.execute("DELETE FROM exchanges WHERE id = ?", (exchange_id,))
    if exchange_dict.get('source_pharmacy_id'):
        db.execute("DELETE FROM exchanges WHERE source_pharmacy_id = ? AND target_pharmacy_id = ? AND status = 'pending'",
                   (exchange_dict['source_pharmacy_id'], user_id))
    db.commit()
    return jsonify({'success': True})

@app.route('/api/get_user_categories')
@login_required
def get_user_categories():
    db = get_db()
    user_id = session['user_id']
    cursor = db.execute("SELECT categories FROM user_categories WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    categories = row['categories'].split(',') if row and row['categories'] else []
    return jsonify({'categories': categories})

@app.route('/api/save_user_categories', methods=['POST'])
@login_required
def save_user_categories():
    db = get_db()
    user_id = session['user_id']
    data = request.get_json()
    categories = data.get('categories', [])
    categories_str = ','.join(categories)
    db.execute("INSERT OR REPLACE INTO user_categories (user_id, categories) VALUES (?, ?)", (user_id, categories_str))
    db.commit()
    return jsonify({'success': True})

@app.route('/api/get_hidden_items')
@login_required
def get_hidden_items():
    db = get_db()
    user_id = session['user_id']
    cursor = db.execute("SELECT item_id FROM hidden_items WHERE user_id = ?", (user_id,))
    return jsonify({'hidden_ids': [row['item_id'] for row in cursor.fetchall()]})

@app.route('/api/toggle_hidden_items', methods=['POST'])
@login_required
def toggle_hidden_items():
    db = get_db()
    user_id = session['user_id']
    data = request.get_json()
    item_ids = data.get('item_ids', [])
    hidden = data.get('hidden', False)
    if not item_ids:
        return jsonify({'success': False, 'error': 'هیچ آیتمی انتخاب نشده است'})
    if hidden:
        for item_id in item_ids:
            db.execute("INSERT OR IGNORE INTO hidden_items (user_id, item_id) VALUES (?, ?)", (user_id, item_id))
    else:
        placeholders = ','.join('?' for _ in item_ids)
        db.execute(f"DELETE FROM hidden_items WHERE user_id = ? AND item_id IN ({placeholders})", (user_id, *item_ids))
    db.commit()
    return jsonify({'success': True})

# ===== اجرای برنامه =====
if __name__ == '__main__':
    print("=" * 50)
    print("✅ داروخانه با موفقیت راه اندازی شد")
    print("=" * 50)
    print("🌐 آدرس: http://0.0.0.0:5000")
    print("👑 ادمین: admin / admin123")
    print("📝 کاربران نمونه:")
    print("   nosratabadi / admin123")
    print("   soleymani / soleymani123")
    print("   A101 / drsaboori")
    print("   A102 / drjafari")
    print("=" * 50)
    print("⚠️ کاربران جدید پس از ثبت‌نام نیاز به تأیید ادمین دارند")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=False)
