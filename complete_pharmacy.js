// ============================================
// complete_pharmacy.js
// سیستم مدیریت داروخانه با تمام امکانات
// نسخه کامل - بدون Express - فروردین 1405
// ============================================

const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const querystring = require('querystring');
const url = require('url');
const sqlite3 = require('sqlite3').verbose();

// ===== تنظیمات =====
const PORT = 5000;
const DATABASE = 'pharmacy.db';
const UPLOAD_FOLDER = '/var/www/poldaroo/uploads';

// ایجاد پوشه آپلود
if (!fs.existsSync(UPLOAD_FOLDER)) {
    fs.mkdirSync(UPLOAD_FOLDER, { recursive: true });
}

// ============================================
// کلاس مدیریت دیتابیس
// ============================================
class DatabaseManager {
    constructor() {
        this.db = new sqlite3.Database(DATABASE);
        this.db.serialize(() => {
            this.initDB();
        });
    }

    run(sql, params = []) {
        return new Promise((resolve, reject) => {
            this.db.run(sql, params, function(err) {
                if (err) reject(err);
                else resolve({ lastID: this.lastID, changes: this.changes });
            });
        });
    }

    get(sql, params = []) {
        return new Promise((resolve, reject) => {
            this.db.get(sql, params, (err, row) => {
                if (err) reject(err);
                else resolve(row);
            });
        });
    }

    all(sql, params = []) {
        return new Promise((resolve, reject) => {
            this.db.all(sql, params, (err, rows) => {
                if (err) reject(err);
                else resolve(rows);
            });
        });
    }

    hashPassword(password) {
        return crypto.createHash('sha256').update(password).digest('hex');
    }

    getIranTimeISO() {
        const now = new Date();
        const offset = 3.5 * 60 * 60 * 1000;
        return new Date(now.getTime() + offset).toISOString();
    }

    async initDB() {
        console.log('🔄 Initializing database...');

        // ===== جدول users =====
        await this.run(`CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            is_full_user INTEGER DEFAULT 0,
            pharmacy_display_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            phone_number TEXT,
            address TEXT,
            is_approved INTEGER DEFAULT 1
        )`);

        // ===== جدول drugs (کسری) =====
        await this.run(`CREATE TABLE IF NOT EXISTS drugs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            type TEXT NOT NULL,
            priority INTEGER DEFAULT 4,
            created_at TEXT NOT NULL,
            ordered BOOLEAN DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )`);

        // ===== جدول orders =====
        await this.run(`CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            company TEXT NOT NULL,
            drug_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            ordered_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )`);

        // ===== جدول inventory =====
        await this.run(`CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            batch_number TEXT,
            expiry_date TEXT,
            manufacturer TEXT,
            location TEXT,
            created_at TEXT,
            invoice_number TEXT,
            supplier TEXT,
            purchase_price REAL,
            category TEXT DEFAULT 'other',
            FOREIGN KEY (user_id) REFERENCES users(id)
        )`);

        // ===== جدول sales =====
        await this.run(`CREATE TABLE IF NOT EXISTS sales (
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
        )`);

        // ===== جدول companies =====
        await this.run(`CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )`);

        // ===== جدول exchanges =====
        await this.run(`CREATE TABLE IF NOT EXISTS exchanges (
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
        )`);

        // ===== جدول user_categories =====
        await this.run(`CREATE TABLE IF NOT EXISTS user_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            categories TEXT DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES users(id)
        )`);

        // ===== جدول hidden_items =====
        await this.run(`CREATE TABLE IF NOT EXISTS hidden_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )`);

        // ===== جدول interviews =====
        await this.run(`CREATE TABLE IF NOT EXISTS interviews (
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
        )`);

        // ===== جدول announcements =====
        await this.run(`CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_active INTEGER DEFAULT 1
        )`);

        // ===== کاربران پیش‌فرض =====
        const users = [
            ['admin', 'admin123', 'مدیر سیستم', 1],
            ['nosratabadi', 'admin123', 'داروخانه نصرت‌آبادی', 1],
            ['soleymani', 'soleymani123', 'داروخانه سلیمانی', 1],
            ['A101', 'drsaboori', 'داروخانه A101', 1],
            ['A102', 'drjafari', 'داروخانه A102', 1]
        ];

        for (const [username, password, display, isFull] of users) {
            const existing = await this.get('SELECT COUNT(*) as count FROM users WHERE username = ?', [username]);
            if (existing.count === 0) {
                await this.run(
                    'INSERT INTO users (username, password_hash, is_full_user, pharmacy_display_name, created_at, is_approved) VALUES (?, ?, ?, ?, ?, ?)',
                    [username, this.hashPassword(password), isFull, display, new Date().toISOString(), 1]
                );
            }
        }

        // ===== شرکت‌ها =====
        const companies = ['داروپخش', 'البرز', 'اکسیر', 'رازی'];
        for (const c of companies) {
            await this.run('INSERT OR IGNORE INTO companies (name) VALUES (?)', [c]);
        }

        console.log('✅ Database initialized successfully');
    }
}

const db = new DatabaseManager();

// ============================================
// مدیریت Session
// ============================================
const sessions = {};

function generateSessionId() {
    return crypto.randomBytes(32).toString('hex');
}

function getSession(req) {
    const cookies = parseCookies(req.headers.cookie || '');
    const sessionId = cookies.sessionId;
    if (sessionId && sessions[sessionId]) {
        return sessions[sessionId];
    }
    return null;
}

function createSession(user) {
    const sessionId = generateSessionId();
    sessions[sessionId] = {
        loggedIn: true,
        userId: user.id,
        username: user.username,
        isFullUser: user.is_full_user,
        pharmacyDisplayName: user.pharmacy_display_name,
        isApproved: user.is_approved || 1,
        user: user,
        createdAt: Date.now()
    };
    return sessionId;
}

function destroySession(sessionId) {
    delete sessions[sessionId];
}

function parseCookies(cookieStr) {
    const cookies = {};
    if (!cookieStr) return cookies;
    cookieStr.split(';').forEach(cookie => {
        const parts = cookie.trim().split('=');
        if (parts.length === 2) {
            cookies[parts[0]] = decodeURIComponent(parts[1]);
        }
    });
    return cookies;
}

function setCookie(res, name, value, maxAge = 7 * 24 * 60 * 60 * 1000) {
    res.setHeader('Set-Cookie', `${name}=${value}; Path=/; Max-Age=${Math.floor(maxAge / 1000)}; HttpOnly`);
}

function deleteCookie(res, name) {
    res.setHeader('Set-Cookie', `${name}=; Path=/; Max-Age=0; HttpOnly`);
}

// ============================================
// توابع کمکی
// ============================================
function parseBody(req) {
    return new Promise((resolve, reject) => {
        let body = '';
        req.on('data', chunk => { body += chunk.toString(); });
        req.on('end', () => {
            try {
                if (req.headers['content-type'] === 'application/json') {
                    resolve(JSON.parse(body));
                } else {
                    resolve(querystring.parse(body));
                }
            } catch (e) {
                resolve({});
            }
        });
        req.on('error', reject);
    });
}

function validateExpiryDate(dateStr) {
    if (!dateStr || dateStr.trim() === '') return false;
    return /^\d{4}\.(0[1-9]|1[0-2])$/.test(dateStr);
}

function parseExpiryNumber(expiryStr) {
    if (!expiryStr) return 999999;
    try {
        if (expiryStr.includes('.')) {
            const parts = expiryStr.split('.');
            return parseInt(parts[0]) * 12 + parseInt(parts[1]);
        }
    } catch (e) {}
    return 999999;
}

function getExpiryStatus(expiryDate) {
    if (!expiryDate) return { text: 'نامشخص', class: '' };
    try {
        if (expiryDate.includes('.')) {
            const parts = expiryDate.split('.');
            const year = parseInt(parts[0]);
            const month = parseInt(parts[1]);
            const now = new Date();
            const exp = new Date(year, month - 1, 1);
            const monthsLeft = (exp.getFullYear() - now.getFullYear()) * 12 + (exp.getMonth() - now.getMonth());
            if (monthsLeft < 0) return { text: 'منقضی', class: 'expired' };
            if (monthsLeft <= 3) return { text: `${monthsLeft} ماه مانده`, class: 'expiring-soon' };
            return { text: `${monthsLeft} ماه مانده`, class: 'good-expiry' };
        }
    } catch (e) {}
    return { text: 'نامعتبر', class: '' };
}

function gregorianToJalali(gy, gm, gd) {
    const gDaysInMonth = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    let gy2 = gy - 1600;
    let gm2 = gm - 1;
    let gd2 = gd - 1;
    let gDayNo = 365 * gy2 + Math.floor((gy2 + 3) / 4) - Math.floor((gy2 + 99) / 100) + Math.floor((gy2 + 399) / 400);
    for (let i = 0; i < gm2; i++) {
        gDayNo += gDaysInMonth[i];
    }
    if (gm2 > 1 && ((gy2 % 4 === 0 && gy2 % 100 !== 0) || (gy2 % 400 === 0))) {
        gDayNo += 1;
    }
    gDayNo += gd2;
    let jDayNo = gDayNo - 226899;
    let jy = Math.floor((jDayNo * 100 + 322) / 36525);
    let jRem = jDayNo - Math.floor((jy * 36525 + 322) / 100);
    let jm = Math.floor((jRem * 1000 + 60000) / 1000000);
    let jd = jRem - Math.floor((jm * 1000000 + 60000) / 1000);
    if (jm === 0) {
        jm = 12;
        jy -= 1;
        jd = 30;
    } else if (jm === 12) {
        if (jd > 29) jd = 30;
    } else {
        if (jd > 30) jd = 30;
    }
    return `${String(jy).padStart(4, '0')}/${String(jm).padStart(2, '0')}/${String(jd).padStart(2, '0')}`;
}

function convertDateToJalali(dateStr) {
    if (!dateStr) return '';
    try {
        if (dateStr.includes('T')) dateStr = dateStr.split('T')[0];
        const parts = dateStr.split('-');
        if (parts.length !== 3) return dateStr;
        return gregorianToJalali(parseInt(parts[0]), parseInt(parts[1]), parseInt(parts[2]));
    } catch (e) {
        return dateStr;
    }
}

function maskPharmacyName(name) {
    if (!name || name.length <= 4) return name;
    return name.slice(0, 3) + '...' + name.slice(-2);
}

function loginRequired(req, res) {
    const session = getSession(req);
    if (!session || !session.loggedIn) {
        res.writeHead(302, { 'Location': '/login' });
        res.end();
        return false;
    }
    return session;
}

function adminRequired(req, res) {
    const session = getSession(req);
    if (!session || !session.loggedIn) {
        res.writeHead(302, { 'Location': '/login' });
        res.end();
        return false;
    }
    if (session.username !== 'admin') {
        res.writeHead(403);
        res.end('⛔ دسترسی غیرمجاز. فقط ادمین می‌تواند وارد این بخش شود.');
        return false;
    }
    return session;
}

// ============================================
// قالب HTML
// ============================================
const HTML_LAYOUT = `<!DOCTYPE html>
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
        .topbar .nav-links .btn-login { background: #4fc3f7; color: #1a1a1a; padding: 3px 12px; border-radius: 6px; font-weight: bold; }
        .topbar .nav-links .btn-register { background: #28a745; color: white; padding: 3px 12px; border-radius: 6px; font-weight: bold; }
        .topbar .nav-links .btn-logout { background: #dc3545; color: white; padding: 3px 10px; border-radius: 6px; }
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
        .exchange-dual-container { display: flex; gap: 15px; flex-wrap: wrap; }
        .exchange-list-box { flex: 1; min-width: 250px; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .exchange-list-header { background: #1a1a1a; color: white; padding: 10px; text-align: center; font-weight: bold; font-size: 13px; }
        .exchange-list-header.active { background: #28a745; }
        .exchange-list-items { max-height: 350px; overflow-y: auto; padding: 5px; }
        .exchange-drug-item { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-bottom: 1px solid #eee; cursor: pointer; border-radius: 4px; font-size: 13px; }
        .exchange-drug-item:hover { background: #f5f5f5; }
        .exchange-drug-item.selected { background: #d4edda; }
        .exchange-card { background: white; border-radius: 10px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow: hidden; border: 1px solid #e0e0e0; }
        .exchange-card-header { background: #1a1a1a; color: white; padding: 10px 14px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px; font-size: 13px; }
        .exchange-card-footer { padding: 8px 14px; background: #f8f9fa; display: flex; gap: 8px; justify-content: flex-end; border-top: 1px solid #e0e0e0; }
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
        .drug-item .drug-name { font-weight: bold; flex: 1; min-width: 80px; }
        .drug-item .drug-qty { color: #555; }
        .drug-item .drug-location { font-size: 10px; padding: 2px 6px; border-radius: 10px; }
        .location-warehouse { background: #cfe2ff; color: #084298; }
        .location-pharmacy { background: #d1e7dd; color: #0a3622; }
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
        @media (max-width: 768px) {
            .sidebar { width: 55px; }
            .sidebar .menu-text { display: none; }
            .main-content { margin-right: 55px; padding: 10px; }
            .topbar .brand { font-size: 13px; }
            .topbar .nav-links a { font-size: 10px; padding: 2px 6px; }
            .exchange-dual-container { flex-direction: column; }
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
            {{adminLink}}
            {{userBadge}}
            {{authLinks}}
        </div>
    </div>
    <div class="sidebar">
        <ul class="sidebar-menu">
            <li><a href="/"><span>🏠</span> <span class="menu-text">صفحه اصلی</span></a></li>
            <li><a href="/dashboard"><span>📊</span> <span class="menu-text">داشبورد</span></a></li>
            <li><a href="/inventory"><span>📦</span> <span class="menu-text">انبارداری</span></a></li>
            <li><a href="/exchange"><span>🔄</span> <span class="menu-text">تبادل دارو</span></a></li>
            <li><a href="/deficit"><span>📋</span> <span class="menu-text">دفتر کسری</span></a></li>
            {{adminSidebarLink}}
        </ul>
    </div>
    <div class="main-content">
        <div class="header">
            <div class="page-title">{{pageTitle}}</div>
            <div class="user-info">{{userInfo}}</div>
        </div>
        {{content}}
    </div>
    <script>
        function showToast(message, type) {
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.className = 'toast-message ' + (type || 'info');
            toast.style.display = 'block';
            setTimeout(() => { toast.style.display = 'none'; }, 3000);
        }
    </script>
</body>
</html>`;

function renderLayout(content, pageTitle, session) {
    let adminLink = '';
    let adminSidebarLink = '';
    let userBadge = '';
    let authLinks = '';
    let userInfo = '';

    if (session && session.loggedIn) {
        if (session.username === 'admin') {
            adminLink = '<a href="/admin" style="color:#ffc107;">👑 ادمین</a>';
            adminSidebarLink = '<li><a href="/admin" class="admin-link"><span>👑</span> <span class="menu-text">پنل ادمین</span></a></li>';
        }
        userBadge = `<span class="user-badge">👤 <strong>${session.pharmacyDisplayName || ''}</strong></span>`;
        authLinks = `<a href="/logout" class="btn-logout">🚪 خروج</a>`;
        userInfo = `<span>👤 ${session.pharmacyDisplayName || ''}</span>`;
    } else {
        authLinks = `<a href="/login" class="btn-login">🔐 ورود</a> <a href="/register" class="btn-register">📝 ثبت‌نام</a>`;
        userInfo = '<span>👤 مهمان</span>';
    }

    return HTML_LAYOUT
        .replace(/{{adminLink}}/g, adminLink)
        .replace(/{{adminSidebarLink}}/g, adminSidebarLink)
        .replace(/{{userBadge}}/g, userBadge)
        .replace(/{{authLinks}}/g, authLinks)
        .replace(/{{userInfo}}/g, userInfo)
        .replace(/{{pageTitle}}/g, pageTitle)
        .replace(/{{content}}/g, content);
}

// ============================================
// هندلرهای روت
// ============================================

// ===== صفحه اصلی =====
async function handleIndex(req, res) {
    try {
        const interviews = await db.all('SELECT * FROM interviews WHERE is_published = 1 ORDER BY created_at DESC');
        const announcements = await db.all('SELECT * FROM announcements WHERE is_active = 1 ORDER BY created_at DESC LIMIT 3');

        let content = '<div class="card"><div class="card-title">🎙️ مصاحبه با داروسازان</div>';
        if (interviews.length > 0) {
            for (const i of interviews) {
                content += `
                <div class="interview-card">
                    <h3>${i.title}</h3>
                    <div class="meta">👤 ${i.pharmacist_name} | 🏥 ${i.pharmacy_name} | 📅 ${i.created_at.slice(0, 10)}</div>
                    <div class="content">${i.content}</div>
                    <div class="media">
                        ${i.image_url ? `<img src="${i.image_url}" style="max-width:100%;border-radius:6px;max-height:300px;">` : ''}
                        ${i.audio_url ? `<audio controls style="width:100%;"><source src="${i.audio_url}"></audio>` : ''}
                    </div>
                </div>`;
            }
        } else {
            content += '<p style="text-align:center;padding:30px;color:#999;">هنوز مصاحبه‌ای ثبت نشده است</p>';
        }
        content += '</div>';

        if (announcements.length > 0) {
            content += `<div class="card" style="background:#e3f2fd;border:1px solid #90caf9;"><div class="card-title">📢 اطلاعیه‌ها</div>`;
            for (const a of announcements) {
                content += `
                <div style="padding:8px 0;border-bottom:1px solid #e0e0e0;">
                    <strong>${a.title}</strong>
                    <p style="font-size:13px;color:#555;margin-top:4px;">${a.content}</p>
                    <span style="font-size:11px;color:#999;">${a.created_at.slice(0, 10)}</span>
                </div>`;
            }
            content += '</div>';
        }

        const session = getSession(req);
        const html = renderLayout(content, 'صفحه اصلی', session);
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
        res.end(html);
    } catch (err) {
        console.error(err);
        res.writeHead(500);
        res.end('خطا در بارگذاری صفحه');
    }
}

// ===== لاگین =====
function handleLogin(req, res) {
    const session = getSession(req);
    if (session && session.loggedIn) {
        res.writeHead(302, { 'Location': '/' });
        res.end();
        return;
    }

    if (req.method === 'POST') {
        handleLoginPost(req, res);
        return;
    }

    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(`<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head><meta charset="UTF-8"><title>ورود</title>
<style>
body { font-family: Tahoma, sans-serif; background: #f5f5f5; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
.login-box { background: white; padding: 30px; border-radius: 16px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); width: 340px; text-align: center; }
.login-box h2 { margin-bottom: 20px; color: #1a1a1a; }
.login-box input { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; box-sizing: border-box; }
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
    <a href="/" class="back-link">← بازگشت</a>
</div>
</body>
</html>`);
}

async function handleLoginPost(req, res) {
    try {
        const body = await parseBody(req);
        const user = await db.get('SELECT * FROM users WHERE username = ?', [body.username]);

        if (user && user.password_hash === db.hashPassword(body.password)) {
            const isApproved = user.is_approved !== undefined ? user.is_approved : 1;
            if (isApproved === 0) {
                res.end('⏳ حساب کاربری در انتظار تأیید است. <a href="/">بازگشت</a>');
                return;
            }
            if (isApproved === 2) {
                res.end('❌ حساب کاربری رد شده است. <a href="/">بازگشت</a>');
                return;
            }

            const sessionId = createSession(user);
            setCookie(res, 'sessionId', sessionId);
            res.writeHead(302, { 'Location': '/' });
            res.end();
            return;
        }

        res.end('❌ نام کاربری یا رمز عبور اشتباه است. <a href="/login">بازگشت</a>');
    } catch (err) {
        console.error(err);
        res.writeHead(500);
        res.end('خطا در ورود');
    }
}

// ===== ثبت‌نام =====
function handleRegister(req, res) {
    if (req.method === 'POST') {
        handleRegisterPost(req, res);
        return;
    }

    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(`<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head><meta charset="UTF-8"><title>ثبت‌نام</title>
<style>
body { font-family: Tahoma, sans-serif; background: #f5f5f5; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 20px; }
.register-box { background: white; padding: 30px; border-radius: 16px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); width: 380px; text-align: center; }
.register-box h2 { margin-bottom: 20px; color: #1a1a1a; }
.register-box input { width: 100%; padding: 10px; margin: 8px 0; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; box-sizing: border-box; }
.register-box button { width: 100%; padding: 10px; background: #28a745; color: white; border: none; border-radius: 8px; font-size: 14px; cursor: pointer; }
.register-box .field-label { text-align: right; font-size: 13px; color: #555; margin-top: 5px; }
.back-link { display: block; margin-top: 15px; color: #007bff; text-decoration: none; }
.login-link { display: block; margin-top: 5px; color: #28a745; text-decoration: none; }
</style>
</head>
<body>
<div class="register-box">
    <h2>📝 ثبت‌نام</h2>
    <form method="post">
        <div class="field-label">نام کاربری *</div>
        <input type="text" name="username" placeholder="حداقل 3 کاراکتر" required>
        <div class="field-label">رمز عبور *</div>
        <input type="password" name="password" placeholder="حداقل 4 کاراکتر" required>
        <div class="field-label">تکرار رمز عبور *</div>
        <input type="password" name="confirm_password" placeholder="تکرار رمز عبور" required>
        <div class="field-label">نام داروخانه *</div>
        <input type="text" name="pharmacy_name" placeholder="نام کامل داروخانه" required>
        <div class="field-label">شماره همراه</div>
        <input type="tel" name="phone_number" placeholder="مثال: 09121234567">
        <div class="field-label">آدرس</div>
        <input type="text" name="address" placeholder="آدرس کامل داروخانه">
        <button type="submit">ثبت‌نام</button>
    </form>
    <a href="/login" class="login-link">← قبلاً ثبت‌نام کرده‌اید؟ ورود</a>
    <a href="/" class="back-link">← بازگشت</a>
</div>
</body>
</html>`);
}

async function handleRegisterPost(req, res) {
    try {
        const body = await parseBody(req);
        const { username, password, confirm_password, pharmacy_name, phone_number, address } = body;

        if (!username || !password || !pharmacy_name) {
            res.end('❌ همه فیلدهای اجباری را پر کنید');
            return;
        }
        if (username.length < 3) {
            res.end('❌ نام کاربری باید حداقل 3 کاراکتر باشد');
            return;
        }
        if (password.length < 4) {
            res.end('❌ رمز عبور باید حداقل 4 کاراکتر باشد');
            return;
        }
        if (password !== confirm_password) {
            res.end('❌ رمز عبور و تکرار آن مطابقت ندارند');
            return;
        }

        const existing = await db.get('SELECT COUNT(*) as count FROM users WHERE username = ?', [username]);
        if (existing.count > 0) {
            res.end('❌ این نام کاربری قبلاً ثبت شده است');
            return;
        }

        await db.run(
            'INSERT INTO users (username, password_hash, is_full_user, pharmacy_display_name, created_at, phone_number, address, is_approved) VALUES (?, ?, ?, ?, ?, ?, ?, 0)',
            [username, db.hashPassword(password), 0, pharmacy_name, new Date().toISOString(), phone_number || null, address || null]
        );

        res.end(`<!DOCTYPE html>
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
    <p>حساب کاربری شما با موفقیت ایجاد شد.<br>پس از تأیید توسط ادمین، می‌توانید وارد شوید.</p>
    <a href="/" class="back-link">← بازگشت</a>
</div>
</body>
</html>`);
    } catch (err) {
        console.error(err);
        res.writeHead(500);
        res.end('خطا در ثبت‌نام');
    }
}

// ===== خروج =====
function handleLogout(req, res) {
    const cookies = parseCookies(req.headers.cookie || '');
    if (cookies.sessionId) {
        destroySession(cookies.sessionId);
        deleteCookie(res, 'sessionId');
    }
    res.writeHead(302, { 'Location': '/' });
    res.end();
}

// ===== داشبورد =====
async function handleDashboard(req, res) {
    const session = loginRequired(req, res);
    if (!session) return;

    try {
        const userId = session.userId;
        const drugs = await db.get('SELECT COUNT(*) as count FROM drugs WHERE user_id = ? AND ordered = 0', [userId]);
        const orders = await db.get('SELECT COUNT(*) as count FROM orders WHERE user_id = ?', [userId]);
        const inventory = await db.get('SELECT SUM(quantity) as total FROM inventory WHERE user_id = ?', [userId]);

        const content = `
        <div class="card">
            <div class="card-title">📊 داشبورد</div>
            <div class="stats-grid">
                <div class="stat-card"><div class="number">${drugs.count || 0}</div><div class="label">💊 داروهای کسری</div></div>
                <div class="stat-card"><div class="number">${orders.count || 0}</div><div class="label">📜 سفارشات</div></div>
                <div class="stat-card"><div class="number">${inventory.total || 0}</div><div class="label">📦 موجودی</div></div>
            </div>
            <p style="text-align:center;padding:20px;color:#666;">✅ سیستم با موفقیت اجرا شد!</p>
        </div>`;

        const html = renderLayout(content, '📊 داشبورد', session);
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
        res.end(html);
    } catch (err) {
        console.error(err);
        res.writeHead(500);
        res.end('خطا در بارگذاری داشبورد');
    }
}

// ===== انبارداری =====
async function handleInventory(req, res) {
    const session = loginRequired(req, res);
    if (!session) return;

    const content = `
    <div class="card">
        <div class="card-title">📦 ثبت فاکتور جدید</div>
        <div class="form-row">
            <input type="text" id="invName" placeholder="نام دارو" style="flex:2;">
            <input type="number" id="invQty" placeholder="تعداد" value="1">
            <input type="text" id="invExpiry" placeholder="تاریخ انقضا (2026.12)">
            <select id="invLocation"><option value="warehouse">انبار</option><option value="pharmacy">داروخانه</option></select>
            <input type="text" id="invSupplier" placeholder="تامین کننده">
            <button onclick="addInventory()">ثبت</button>
        </div>
    </div>
    <div class="card">
        <div class="card-title">📊 لیست انبار</div>
        <div id="inventoryContainer"><p style="text-align:center;padding:20px;color:#999;">بارگذاری...</p></div>
    </div>
    <script>
    function showToast(msg, type) {
        const t = document.getElementById('toast');
        t.textContent = msg;
        t.className = 'toast-message ' + (type || 'info');
        t.style.display = 'block';
        setTimeout(() => t.style.display = 'none', 3000);
    }
    function addInventory() {
        const name = document.getElementById('invName').value;
        const qty = document.getElementById('invQty').value;
        const expiry = document.getElementById('invExpiry').value;
        const location = document.getElementById('invLocation').value;
        const supplier = document.getElementById('invSupplier').value;
        if (!name || !qty || !expiry) { showToast('نام، تعداد و تاریخ انقضا اجباری است', 'error'); return; }
        const fd = new FormData();
        fd.append('name', name); fd.append('quantity', qty); fd.append('expiry_date', expiry);
        fd.append('location', location); fd.append('supplier', supplier);
        fetch('/api/add_inventory', { method: 'POST', body: fd })
            .then(r => r.json())
            .then(data => {
                if (data.success) { showToast('✅ ثبت شد', 'success'); loadInventory();
                    document.getElementById('invName').value = ''; document.getElementById('invQty').value = '1';
                    document.getElementById('invExpiry').value = ''; document.getElementById('invSupplier').value = '';
                } else { showToast('خطا: ' + data.error, 'error'); }
            })
            .catch(() => showToast('❌ خطا', 'error'));
    }
    function loadInventory() {
        fetch('/api/get_inventory')
            .then(r => r.json())
            .then(data => {
                const container = document.getElementById('inventoryContainer');
                if (!data.items || data.items.length === 0) {
                    container.innerHTML = '<p style="text-align:center;padding:20px;color:#999;">انبار خالی است</p>';
                    return;
                }
                let html = '<div style="overflow-x:auto;"><table><thead><tr><th>نام</th><th>تعداد</th><th>انقضا</th><th>مکان</th><th>عملیات</th></tr></thead><tbody>';
                data.items.forEach(item => {
                    html += \`<tr><td><strong>\${item.name}</strong></td><td>\${item.quantity}</td><td>\${item.expiry_date || '-'}</td><td>\${item.location === 'warehouse' ? 'انبار' : 'داروخانه'}</td>
                    <td><button onclick="deleteItem(\${item.id})" class="btn-danger btn-sm">🗑️</button></td></tr>\`;
                });
                html += '</tbody></table></div>';
                container.innerHTML = html;
            })
            .catch(() => { document.getElementById('inventoryContainer').innerHTML = '<p style="text-align:center;padding:20px;color:#dc3545;">❌ خطا</p>'; });
    }
    function deleteItem(id) {
        if (!confirm('حذف شود؟')) return;
        fetch('/api/delete_inventory_item/' + id, { method: 'POST' })
            .then(r => r.json())
            .then(data => { if (data.success) { showToast('✅ حذف شد', 'success'); loadInventory(); } })
            .catch(() => showToast('❌ خطا', 'error'));
    }
    loadInventory();
    </script>`;

    const html = renderLayout(content, '📦 انبارداری', session);
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(html);
}

// ===== تبادل =====
async function handleExchange(req, res) {
    const session = loginRequired(req, res);
    if (!session) return;

    const content = `
    <div class="card">
        <div class="card-title">🔄 تبادل دارو</div>
        <p style="text-align:center;padding:30px;color:#666;">سیستم تبادل دارو بین داروخانه‌ها</p>
        <p style="text-align:center;color:#999;">برای استفاده از تبادل از API استفاده کنید.</p>
    </div>`;

    const html = renderLayout(content, '🔄 تبادل', session);
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(html);
}

// ===== دفتر کسری =====
async function handleDeficit(req, res) {
    const session = loginRequired(req, res);
    if (!session) return;

    const content = `
    <div class="card">
        <div class="card-title">📋 دفتر کسری</div>
        <div class="form-row">
            <input type="text" id="drugName" placeholder="نام دارو" style="flex:2;">
            <input type="number" id="drugQty" placeholder="تعداد">
            <select id="drugType"><option value="normal">عادی</option><option value="quota">سهمیه ای</option></select>
            <select id="drugPriority"><option value="1">اولویت 1</option><option value="2">اولویت 2</option><option value="3">اولویت 3</option><option value="4">اولویت 4</option></select>
            <button onclick="addDrug()">➕ افزودن</button>
        </div>
        <div id="drugsList"><p style="text-align:center;padding:20px;color:#999;">بارگذاری...</p></div>
    </div>
    <script>
    function showToast(msg, type) {
        const t = document.getElementById('toast');
        t.textContent = msg;
        t.className = 'toast-message ' + (type || 'info');
        t.style.display = 'block';
        setTimeout(() => t.style.display = 'none', 3000);
    }
    function addDrug() {
        const name = document.getElementById('drugName').value;
        const qty = document.getElementById('drugQty').value;
        const type = document.getElementById('drugType').value;
        const priority = document.getElementById('drugPriority').value;
        if (!name || !qty) { showToast('نام و تعداد را وارد کنید', 'error'); return; }
        fetch('/api/add_drug', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, quantity: parseInt(qty), type, priority: parseInt(priority) })
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) { showToast('✅ اضافه شد', 'success');
                document.getElementById('drugName').value = ''; document.getElementById('drugQty').value = ''; loadDrugs();
            } else { showToast('خطا: ' + data.error, 'error'); }
        })
        .catch(() => showToast('❌ خطا', 'error'));
    }
    function loadDrugs() {
        fetch('/api/get_drugs')
            .then(r => r.json())
            .then(data => {
                const container = document.getElementById('drugsList');
                if (!data.drugs || data.drugs.length === 0) {
                    container.innerHTML = '<p style="text-align:center;padding:20px;color:#999;">لیست کسری خالی است</p>';
                    return;
                }
                let html = '<table class="deficit-table"><thead><tr><th>نام</th><th>تعداد</th><th>نوع</th><th>اولویت</th><th>عملیات</th></tr></thead><tbody>';
                data.drugs.forEach(d => {
                    html += \`<tr><td><strong>\${d.name}</strong></td><td>\${d.quantity}</td><td>\${d.type === 'quota' ? 'سهمیه ای' : 'عادی'}</td>
                    <td>\${d.priority}</td><td><button onclick="deleteDrug(\${d.id})" class="btn-danger btn-sm">🗑️</button></td></tr>\`;
                });
                html += '</tbody></table>';
                container.innerHTML = html;
            })
            .catch(() => { document.getElementById('drugsList').innerHTML = '<p style="text-align:center;padding:20px;color:#dc3545;">❌ خطا</p>'; });
    }
    function deleteDrug(id) {
        if (!confirm('حذف شود؟')) return;
        fetch('/api/delete_drug/' + id, { method: 'POST' })
            .then(r => r.json())
            .then(data => { if (data.success) { showToast('✅ حذف شد', 'success'); loadDrugs(); } })
            .catch(() => showToast('❌ خطا', 'error'));
    }
    loadDrugs();
    </script>`;

    const html = renderLayout(content, '📋 دفتر کسری', session);
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(html);
}

// ===== پنل ادمین =====
async function handleAdmin(req, res) {
    const session = adminRequired(req, res);
    if (!session) return;

    try {
        const users = await db.all('SELECT * FROM users ORDER BY created_at DESC');
        const interviews = await db.all('SELECT * FROM interviews ORDER BY created_at DESC');
        const announcements = await db.all('SELECT * FROM announcements ORDER BY created_at DESC');
        const totalUsers = await db.get('SELECT COUNT(*) as count FROM users');
        const pendingUsers = await db.get('SELECT COUNT(*) as count FROM users WHERE is_approved = 0');

        let usersHtml = '';
        for (const u of users) {
            let statusBadge = '';
            if (u.username === 'admin') {
                statusBadge = '<span class="badge badge-danger">ادمین</span>';
            } else {
                const isApproved = u.is_approved !== undefined ? u.is_approved : 1;
                if (isApproved === 0) statusBadge = '<span class="badge badge-warning">⏳ در انتظار</span>';
                else if (isApproved === 2) statusBadge = '<span class="badge badge-danger">رد شده</span>';
                else if (u.is_full_user) statusBadge = '<span class="badge badge-success">کامل</span>';
                else statusBadge = '<span class="badge badge-info">عادی</span>';
            }
            let actions = '';
            if (u.username !== 'admin') {
                const isApproved = u.is_approved !== undefined ? u.is_approved : 1;
                if (isApproved === 0) {
                    actions += `<button onclick="approveUser(${u.id})" class="btn-success btn-sm">✅</button> `;
                    actions += `<button onclick="rejectUser(${u.id})" class="btn-danger btn-sm">❌</button> `;
                }
                actions += `<button onclick="deleteUser(${u.id})" class="btn-danger btn-sm">🗑️</button>`;
            } else {
                actions = '<span style="color:#999;">غیرقابل حذف</span>';
            }
            usersHtml += `<tr><td>${u.id}</td><td><strong>${u.username}</strong></td><td>${u.pharmacy_display_name}</td>
                <td>${u.phone_number || '-'}</td><td>${statusBadge}</td><td>${u.created_at.slice(0, 10)}</td><td>${actions}</td></tr>`;
        }

        let interviewsHtml = '';
        for (const i of interviews) {
            const status = i.is_published ? '✅ منتشر شده' : '⏳ پیش‌نویس';
            const statusClass = i.is_published ? 'badge-success' : 'badge-warning';
            interviewsHtml += `<tr><td>${i.id}</td><td><strong>${i.title}</strong></td><td>${i.pharmacist_name}</td>
                <td>${i.pharmacy_name}</td><td><span class="badge ${statusClass}">${status}</span></td>
                <td><button onclick="toggleInterview(${i.id})" class="btn-warning btn-sm">${i.is_published ? '🔒' : '✅'}</button>
                <button onclick="deleteInterview(${i.id})" class="btn-danger btn-sm">🗑️</button></td></tr>`;
        }

        let announcementsHtml = '';
        for (const a of announcements) {
            const status = a.is_active ? '✅ فعال' : '⏳ غیرفعال';
            const statusClass = a.is_active ? 'badge-success' : 'badge-warning';
            announcementsHtml += `<tr><td>${a.id}</td><td><strong>${a.title}</strong></td><td>${a.content.slice(0, 30)}${a.content.length > 30 ? '...' : ''}</td>
                <td><span class="badge ${statusClass}">${status}</span></td>
                <td><button onclick="toggleAnnouncement(${a.id})" class="btn-warning btn-sm">${a.is_active ? '🔒' : '✅'}</button>
                <button onclick="deleteAnnouncement(${a.id})" class="btn-danger btn-sm">🗑️</button></td></tr>`;
        }

        const content = `
        <div class="stats-grid">
            <div class="stat-card"><div class="number">${totalUsers.count}</div><div class="label">👤 کل کاربران</div></div>
            <div class="stat-card"><div class="number">${pendingUsers.count}</div><div class="label" style="color:#856404;">⏳ در انتظار</div></div>
        </div>
        <div class="card">
            <div class="card-title">👤 مدیریت کاربران</div>
            <div class="table-responsive"><table><thead><tr><th>#</th><th>نام کاربری</th><th>داروخانه</th><th>شماره</th><th>وضعیت</th><th>تاریخ</th><th>عملیات</th></tr></thead><tbody>${usersHtml}</tbody></table></div>
        </div>
        <div class="card">
            <div class="card-title">🎙️ مدیریت مصاحبه‌ها</div>
            <form method="post" action="/admin/add_interview" style="margin-bottom:15px;padding:12px;background:#f8f9fa;border-radius:10px;">
                <div class="form-row">
                    <input type="text" name="pharmacist_name" placeholder="نام داروساز" required>
                    <input type="text" name="pharmacy_name" placeholder="نام داروخانه" required>
                    <input type="text" name="title" placeholder="عنوان" required>
                </div>
                <div class="form-row">
                    <textarea name="content" placeholder="متن مصاحبه" required style="flex:3;"></textarea>
                </div>
                <div class="form-row">
                    <input type="text" name="image_url" placeholder="آدرس تصویر">
                    <input type="text" name="audio_url" placeholder="آدرس صوت">
                    <button type="submit" class="btn-success">➕ افزودن</button>
                </div>
            </form>
            <div class="table-responsive"><table><thead><tr><th>#</th><th>عنوان</th><th>داروساز</th><th>داروخانه</th><th>وضعیت</th><th>عملیات</th></tr></thead><tbody>${interviewsHtml}</tbody></table></div>
        </div>
        <div class="card">
            <div class="card-title">📢 مدیریت اطلاعیه‌ها</div>
            <form method="post" action="/admin/add_announcement" style="margin-bottom:15px;padding:12px;background:#f8f9fa;border-radius:10px;">
                <div class="form-row">
                    <input type="text" name="title" placeholder="عنوان" required style="flex:1;">
                    <input type="text" name="content" placeholder="متن" required style="flex:2;">
                    <button type="submit" class="btn-primary">➕ افزودن</button>
                </div>
            </form>
            <div class="table-responsive"><table><thead><tr><th>#</th><th>عنوان</th><th>متن</th><th>وضعیت</th><th>عملیات</th></tr></thead><tbody>${announcementsHtml}</tbody></table></div>
        </div>
        <script>
        function approveUser(id) { if(confirm('تأیید شود؟')) { fetch('/admin/approve_user/'+id,{method:'POST'}).then(()=>location.reload()); } }
        function rejectUser(id) { if(confirm('رد شود؟')) { fetch('/admin/reject_user/'+id,{method:'POST'}).then(()=>location.reload()); } }
        function deleteUser(id) { if(confirm('حذف شود؟')) { fetch('/admin/delete_user/'+id,{method:'POST'}).then(()=>location.reload()); } }
        function toggleInterview(id) { fetch('/admin/toggle_interview/'+id,{method:'POST'}).then(()=>location.reload()); }
        function deleteInterview(id) { if(confirm('حذف شود؟')) { fetch('/admin/delete_interview/'+id,{method:'POST'}).then(()=>location.reload()); } }
        function toggleAnnouncement(id) { fetch('/admin/toggle_announcement/'+id,{method:'POST'}).then(()=>location.reload()); }
        function deleteAnnouncement(id) { if(confirm('حذف شود؟')) { fetch('/admin/delete_announcement/'+id,{method:'POST'}).then(()=>location.reload()); } }
        </script>`;

        const html = renderLayout(content, '👑 پنل ادمین', session);
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
        res.end(html);
    } catch (err) {
        console.error(err);
        res.writeHead(500);
        res.end('خطا در بارگذاری پنل ادمین');
    }
}

// ============================================
// API Routes
// ============================================

async function apiGetDrugs(req, res) {
    const session = loginRequired(req, res);
    if (!session) return;
    try {
        const drugs = await db.all('SELECT * FROM drugs WHERE user_id = ? AND ordered = 0 ORDER BY priority ASC', [session.userId]);
        res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ drugs }));
    } catch (err) {
        res.writeHead(500);
        res.end(JSON.stringify({ error: err.message }));
    }
}

async function apiAddDrug(req, res) {
    const session = loginRequired(req, res);
    if (!session) return;
    try {
        const body = await parseBody(req);
        const { name, quantity, type, priority } = body;
        if (!name || !name.trim() || !quantity || quantity <= 0) {
            res.end(JSON.stringify({ success: false, error: 'نام و تعداد معتبر وارد کنید' }));
            return;
        }
        await db.run('INSERT INTO drugs (user_id, name, quantity, type, priority, created_at, ordered) VALUES (?, ?, ?, ?, ?, ?, ?)',
            [session.userId, name.trim(), quantity, type || 'normal', priority || 4, new Date().toISOString(), 0]);
        res.end(JSON.stringify({ success: true }));
    } catch (err) {
        res.end(JSON.stringify({ error: err.message }));
    }
}

async function apiDeleteDrug(req, res, params) {
    const session = loginRequired(req, res);
    if (!session) return;
    try {
        await db.run('DELETE FROM drugs WHERE id = ? AND user_id = ?', [parseInt(params.id), session.userId]);
        res.end(JSON.stringify({ success: true }));
    } catch (err) {
        res.end(JSON.stringify({ error: err.message }));
    }
}

async function apiGetInventory(req, res) {
    const session = loginRequired(req, res);
    if (!session) return;
    try {
        const items = await db.all('SELECT * FROM inventory WHERE user_id = ? AND quantity > 0 ORDER BY created_at DESC', [session.userId]);
        res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ items }));
    } catch (err) {
        res.writeHead(500);
        res.end(JSON.stringify({ error: err.message }));
    }
}

async function apiAddInventory(req, res) {
    const session = loginRequired(req, res);
    if (!session) return;
    try {
        const body = await parseBody(req);
        const { name, quantity, expiry_date, location, supplier, purchase_price } = body;

        if (!name || !quantity || quantity <= 0 || !expiry_date) {
            res.end(JSON.stringify({ success: false, error: 'نام، تعداد و تاریخ انقضا اجباری است' }));
            return;
        }
        if (!validateExpiryDate(expiry_date)) {
            res.end(JSON.stringify({ success: false, error: 'تاریخ انقضا نامعتبر است' }));
            return;
        }

        const existing = await db.get('SELECT id FROM inventory WHERE user_id = ? AND name = ? AND expiry_date = ? AND location = ?',
            [session.userId, name, expiry_date, location || 'warehouse']);

        if (existing) {
            await db.run('UPDATE inventory SET quantity = quantity + ? WHERE id = ?', [parseInt(quantity), existing.id]);
        } else {
            await db.run('INSERT INTO inventory (user_id, name, quantity, expiry_date, location, created_at, supplier, purchase_price) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                [session.userId, name, parseInt(quantity), expiry_date, location || 'warehouse', new Date().toISOString(), supplier || '', parseFloat(purchase_price) || 0]);
        }

        res.end(JSON.stringify({ success: true }));
    } catch (err) {
        console.error(err);
        res.end(JSON.stringify({ error: err.message }));
    }
}

async function apiDeleteInventoryItem(req, res, params) {
    const session = loginRequired(req, res);
    if (!session) return;
    try {
        await db.run('DELETE FROM inventory WHERE id = ? AND user_id = ?', [parseInt(params.id), session.userId]);
        res.end(JSON.stringify({ success: true }));
    } catch (err) {
        res.end(JSON.stringify({ error: err.message }));
    }
}

// ============================================
// Admin API
// ============================================

async function adminApproveUser(req, res, params) {
    const session = adminRequired(req, res);
    if (!session) return;
    try {
        await db.run('UPDATE users SET is_approved = 1 WHERE id = ? AND username != "admin"', [params.id]);
        res.end(JSON.stringify({ success: true }));
    } catch (err) {
        res.end(JSON.stringify({ error: err.message }));
    }
}

async function adminRejectUser(req, res, params) {
    const session = adminRequired(req, res);
    if (!session) return;
    try {
        await db.run('UPDATE users SET is_approved = 2 WHERE id = ? AND username != "admin"', [params.id]);
        res.end(JSON.stringify({ success: true }));
    } catch (err) {
        res.end(JSON.stringify({ error: err.message }));
    }
}

async function adminDeleteUser(req, res, params) {
    const session = adminRequired(req, res);
    if (!session) return;
    try {
        const user = await db.get('SELECT username FROM users WHERE id = ?', [params.id]);
        if (!user || user.username === 'admin') {
            res.end(JSON.stringify({ success: false, error: 'نمی‌توان ادمین را حذف کرد' }));
            return;
        }
        await db.run('DELETE FROM users WHERE id = ?', [params.id]);
        await db.run('DELETE FROM drugs WHERE user_id = ?', [params.id]);
        await db.run('DELETE FROM inventory WHERE user_id = ?', [params.id]);
        await db.run('DELETE FROM orders WHERE user_id = ?', [params.id]);
        await db.run('DELETE FROM sales WHERE user_id = ?', [params.id]);
        await db.run('DELETE FROM exchanges WHERE user_id = ?', [params.id]);
        res.end(JSON.stringify({ success: true }));
    } catch (err) {
        res.end(JSON.stringify({ error: err.message }));
    }
}

async function adminToggleInterview(req, res, params) {
    const session = adminRequired(req, res);
    if (!session) return;
    try {
        const interview = await db.get('SELECT is_published FROM interviews WHERE id = ?', [params.id]);
        if (!interview) { res.end(JSON.stringify({ success: false, error: 'یافت نشد' })); return; }
        await db.run('UPDATE interviews SET is_published = ? WHERE id = ?', [interview.is_published ? 0 : 1, params.id]);
        res.end(JSON.stringify({ success: true }));
    } catch (err) {
        res.end(JSON.stringify({ error: err.message }));
    }
}

async function adminDeleteInterview(req, res, params) {
    const session = adminRequired(req, res);
    if (!session) return;
    try {
        await db.run('DELETE FROM interviews WHERE id = ?', [params.id]);
        res.end(JSON.stringify({ success: true }));
    } catch (err) {
        res.end(JSON.stringify({ error: err.message }));
    }
}

async function adminToggleAnnouncement(req, res, params) {
    const session = adminRequired(req, res);
    if (!session) return;
    try {
        const ann = await db.get('SELECT is_active FROM announcements WHERE id = ?', [params.id]);
        if (!ann) { res.end(JSON.stringify({ success: false, error: 'یافت نشد' })); return; }
        await db.run('UPDATE announcements SET is_active = ? WHERE id = ?', [ann.is_active ? 0 : 1, params.id]);
        res.end(JSON.stringify({ success: true }));
    } catch (err) {
        res.end(JSON.stringify({ error: err.message }));
    }
}

async function adminDeleteAnnouncement(req, res, params) {
    const session = adminRequired(req, res);
    if (!session) return;
    try {
        await db.run('DELETE FROM announcements WHERE id = ?', [params.id]);
        res.end(JSON.stringify({ success: true }));
    } catch (err) {
        res.end(JSON.stringify({ error: err.message }));
    }
}

async function adminAddInterview(req, res) {
    const session = adminRequired(req, res);
    if (!session) return;
    try {
        const body = await parseBody(req);
        const { pharmacist_name, pharmacy_name, title, content, image_url, audio_url } = body;
        if (!pharmacist_name || !pharmacy_name || !title || !content) {
            res.writeHead(400);
            res.end('❌ همه فیلدها اجباری هستند');
            return;
        }
        await db.run('INSERT INTO interviews (pharmacist_name, pharmacy_name, title, content, image_url, audio_url, created_at, is_published) VALUES (?, ?, ?, ?, ?, ?, ?, 1)',
            [pharmacist_name, pharmacy_name, title, content, image_url || '', audio_url || '', new Date().toISOString()]);
        res.writeHead(302, { 'Location': '/admin' });
        res.end();
    } catch (err) {
        res.writeHead(500);
        res.end('خطا در افزودن مصاحبه');
    }
}

async function adminAddAnnouncement(req, res) {
    const session = adminRequired(req, res);
    if (!session) return;
    try {
        const body = await parseBody(req);
        const { title, content } = body;
        if (!title || !content) {
            res.writeHead(400);
            res.end('❌ همه فیلدها اجباری هستند');
            return;
        }
        await db.run('INSERT INTO announcements (title, content, created_at, is_active) VALUES (?, ?, ?, 1)',
            [title, content, new Date().toISOString()]);
        res.writeHead(302, { 'Location': '/admin' });
        res.end();
    } catch (err) {
        res.writeHead(500);
        res.end('خطا در افزودن اطلاعیه');
    }
}

// ============================================
// Main Request Handler
// ============================================
async function handleRequest(req, res) {
    const parsedUrl = url.parse(req.url, true);
    const pathname = parsedUrl.pathname;
    const method = req.method;

    console.log(`${method} ${pathname}`);

    // ===== API Routes =====
    if (pathname.startsWith('/api/')) {
        if (pathname === '/api/get_drugs' && method === 'GET') { await apiGetDrugs(req, res); return; }
        if (pathname === '/api/add_drug' && method === 'POST') { await apiAddDrug(req, res); return; }
        const deleteDrugMatch = pathname.match(/^\/api\/delete_drug\/(\d+)$/);
        if (deleteDrugMatch && method === 'POST') { await apiDeleteDrug(req, res, { id: deleteDrugMatch[1] }); return; }
        if (pathname === '/api/get_inventory' && method === 'GET') { await apiGetInventory(req, res); return; }
        if (pathname === '/api/add_inventory' && method === 'POST') { await apiAddInventory(req, res); return; }
        const deleteInvMatch = pathname.match(/^\/api\/delete_inventory_item\/(\d+)$/);
        if (deleteInvMatch && method === 'POST') { await apiDeleteInventoryItem(req, res, { id: deleteInvMatch[1] }); return; }
        res.writeHead(404);
        res.end(JSON.stringify({ error: 'API not found' }));
        return;
    }

    // ===== Admin API =====
    if (pathname.startsWith('/admin/')) {
        const approveMatch = pathname.match(/^\/admin\/approve_user\/(\d+)$/);
        if (approveMatch && method === 'POST') { await adminApproveUser(req, res, { id: approveMatch[1] }); return; }
        const rejectMatch = pathname.match(/^\/admin\/reject_user\/(\d+)$/);
        if (rejectMatch && method === 'POST') { await adminRejectUser(req, res, { id: rejectMatch[1] }); return; }
        const deleteUserMatch = pathname.match(/^\/admin\/delete_user\/(\d+)$/);
        if (deleteUserMatch && method === 'POST') { await adminDeleteUser(req, res, { id: deleteUserMatch[1] }); return; }
        const toggleIntMatch = pathname.match(/^\/admin\/toggle_interview\/(\d+)$/);
        if (toggleIntMatch && method === 'POST') { await adminToggleInterview(req, res, { id: toggleIntMatch[1] }); return; }
        const deleteIntMatch = pathname.match(/^\/admin\/delete_interview\/(\d+)$/);
        if (deleteIntMatch && method === 'POST') { await adminDeleteInterview(req, res, { id: deleteIntMatch[1] }); return; }
        const toggleAnnMatch = pathname.match(/^\/admin\/toggle_announcement\/(\d+)$/);
        if (toggleAnnMatch && method === 'POST') { await adminToggleAnnouncement(req, res, { id: toggleAnnMatch[1] }); return; }
        const deleteAnnMatch = pathname.match(/^\/admin\/delete_announcement\/(\d+)$/);
        if (deleteAnnMatch && method === 'POST') { await adminDeleteAnnouncement(req, res, { id: deleteAnnMatch[1] }); return; }
        if (pathname === '/admin/add_interview' && method === 'POST') { await adminAddInterview(req, res); return; }
        if (pathname === '/admin/add_announcement' && method === 'POST') { await adminAddAnnouncement(req, res); return; }
    }

    // ===== Web Routes =====
    switch (pathname) {
        case '/': await handleIndex(req, res); break;
        case '/login': handleLogin(req, res); break;
        case '/register': handleRegister(req, res); break;
        case '/logout': handleLogout(req, res); break;
        case '/dashboard': await handleDashboard(req, res); break;
        case '/inventory': await handleInventory(req, res); break;
        case '/exchange': await handleExchange(req, res); break;
        case '/deficit': await handleDeficit(req, res); break;
        case '/admin': await handleAdmin(req, res); break;
        default:
            res.writeHead(404, { 'Content-Type': 'text/html; charset=utf-8' });
            res.end('<h1 style="text-align:center;padding:50px;">404 - صفحه یافت نشد</h1>');
    }
}

// ============================================
// Create Server
// ============================================
const server = http.createServer((req, res) => {
    handleRequest(req, res).catch(err => {
        console.error('Server error:', err);
        if (!res.headersSent) {
            res.writeHead(500, { 'Content-Type': 'text/html; charset=utf-8' });
            res.end('<h1 style="text-align:center;padding:50px;">خطای داخلی سرور</h1>');
        }
    });
});

// ============================================
// Start Server
// ============================================
server.listen(PORT, '0.0.0.0', () => {
    console.log('='.repeat(50));
    console.log('✅ داروخانه با موفقیت راه اندازی شد');
    console.log('='.repeat(50));
    console.log(`🌐 آدرس: http://0.0.0.0:${PORT}`);
    console.log('👑 ادمین: admin / admin123');
    console.log('📝 کاربران نمونه:');
    console.log('   nosratabadi / admin123');
    console.log('   soleymani / soleymani123');
    console.log('   A101 / drsaboori');
    console.log('   A102 / drjafari');
    console.log('='.repeat(50));
    console.log('⚠️ کاربران جدید پس از ثبت‌نام نیاز به تأیید ادمین دارند');
    console.log('='.repeat(50));
});

// ============================================
// Graceful Shutdown
// ============================================
process.on('SIGINT', () => {
    console.log('\n🛑 Shutting down gracefully...');
    server.close(() => {
        console.log('✅ Server closed');
        process.exit(0);
    });
});

process.on('SIGTERM', () => {
    console.log('\n🛑 Shutting down gracefully...');
    server.close(() => {
        console.log('✅ Server closed');
        process.exit(0);
    });
});

console.log('✅ Server starting...');
EOF
