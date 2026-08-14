// ============================================
// complete_pharmacy.js
// سیستم مدیریت داروخانه با تمام امکانات
// نسخه کامل - فروردین 1405
// ============================================

const express = require('express');
const session = require('express-session');
const SQLite3 = require('sqlite3').verbose();
const crypto = require('crypto');
const multer = require('multer');
const path = require('path');
const fs = require('fs');

const app = express();
const PORT = 5000;

// ===== تنظیمات اولیه =====
const UPLOAD_FOLDER = '/var/www/poldaroo/uploads';
if (!fs.existsSync(UPLOAD_FOLDER)) {
    fs.mkdirSync(UPLOAD_FOLDER, { recursive: true });
}

const DATABASE = 'pharmacy.db';

app.set('view engine', 'ejs');
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(express.static('public'));

// ===== Session =====
app.use(session({
    secret: 'pharmacy-secret-key-2024',
    resave: false,
    saveUninitialized: false,
    cookie: { maxAge: 7 * 24 * 60 * 60 * 1000 }
}));

// ===== Multer برای آپلود فایل =====
const storage = multer.diskStorage({
    destination: UPLOAD_FOLDER,
    filename: (req, file, cb) => {
        cb(null, Date.now() + '-' + file.originalname);
    }
});
const upload = multer({ storage, limits: { fileSize: 16 * 1024 * 1024 } });

// ===== کلاس مدیریت دیتابیس =====
class DatabaseManager {
    constructor() {
        this.db = new SQLite3.Database(DATABASE);
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

    exec(sql) {
        return new Promise((resolve, reject) => {
            this.db.exec(sql, (err) => {
                if (err) reject(err);
                else resolve();
            });
        });
    }

    // ===== توابع کمکی =====
    async initDB() {
        // Users
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

        // Drugs
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

        // Orders
        await this.run(`CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            company TEXT NOT NULL,
            drug_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            ordered_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )`);

        // Inventory
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

        // Sales
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

        // Companies
        await this.run(`CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )`);

        // Exchanges
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

        // User Categories
        await this.run(`CREATE TABLE IF NOT EXISTS user_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            categories TEXT DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES users(id)
        )`);

        // Hidden Items
        await this.run(`CREATE TABLE IF NOT EXISTS hidden_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )`);

        // Interviews
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

        // Announcements
        await this.run(`CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_active INTEGER DEFAULT 1
        )`);

        // کاربران پیش‌فرض
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

        // شرکت‌ها
        const companies = ['داروپخش', 'البرز', 'اکسیر', 'رازی'];
        for (const c of companies) {
            await this.run('INSERT OR IGNORE INTO companies (name) VALUES (?)', [c]);
        }

        // نمونه داده‌های انبار
        const allUsers = await this.all('SELECT id FROM users');
        for (const u of allUsers) {
            const count = await this.get('SELECT COUNT(*) as count FROM inventory WHERE user_id = ?', [u.id]);
            if (count.count === 0) {
                const sampleData = [
                    ['آسپرین', 100, '2026.03', 'warehouse'],
                    ['آسپرین', 50, '2025.12', 'pharmacy'],
                    ['ایبوپروفن', 75, '2025.09', 'pharmacy'],
                    ['ایبوپروفن', 30, '2026.01', 'warehouse'],
                    ['آمپی سیلین', 40, '2025.06', 'warehouse'],
                    ['آمپی سیلین', 20, '2025.08', 'pharmacy'],
                    ['دیازپام', 60, '2026.02', 'pharmacy'],
                    ['دیازپام', 25, '2026.04', 'warehouse'],
                    ['لوزارتان', 45, '2026.05', 'pharmacy'],
                    ['مترونیدازول', 80, '2025.11', 'warehouse'],
                    ['سفالکسین', 35, '2025.10', 'pharmacy'],
                    ['آموکسی سیلین', 120, '2026.08', 'warehouse'],
                ];
                for (const [name, qty, expiry, loc] of sampleData) {
                    await this.run(
                        'INSERT INTO inventory (user_id, name, quantity, expiry_date, location, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                        [u.id, name, qty, expiry, loc, new Date().toISOString()]
                    );
                }
            }

            // User Categories
            const catExists = await this.get('SELECT COUNT(*) as count FROM user_categories WHERE user_id = ?', [u.id]);
            if (catExists.count === 0) {
                await this.run('INSERT INTO user_categories (user_id, categories) VALUES (?, ?)', [u.id, '']);
            }
        }

        await this.cleanupExpiredItems();
        console.log('✅ Database initialized successfully');
    }

    hashPassword(password) {
        return crypto.createHash('sha256').update(password).digest('hex');
    }

    async cleanupExpiredItems() {
        await this.run("DELETE FROM inventory WHERE expiry_date IS NOT NULL AND expiry_date != '' AND substr(expiry_date, 1, 4) || substr(expiry_date, 6, 2) < strftime('%Y%m', 'now')");
    }

    getIranTimeISO() {
        const now = new Date();
        const offset = 3.5 * 60 * 60 * 1000;
        const iranTime = new Date(now.getTime() + offset);
        return iranTime.toISOString();
    }
}

const dbManager = new DatabaseManager();

// ===== توابع کمکی =====
function getCurrentUser(req) {
    if (!req.session.userId) return null;
    return req.session.user;
}

function hashPassword(password) {
    return crypto.createHash('sha256').update(password).digest('hex');
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

function maskPharmacyName(name) {
    if (!name || name.length <= 4) return name;
    return name.slice(0, 3) + '...' + name.slice(-2);
}

function getYearMonthSelectors(expiryValue = '') {
    const now = new Date();
    let selectedYear = now.getFullYear();
    let selectedMonth = now.getMonth() + 1;

    if (expiryValue && expiryValue.includes('.')) {
        const parts = expiryValue.split('.');
        if (parts.length === 2) {
            selectedYear = parseInt(parts[0]);
            selectedMonth = parseInt(parts[1]);
        }
    }

    let yearOptions = '';
    for (let y = now.getFullYear() - 5; y <= now.getFullYear() + 5; y++) {
        const selected = y === selectedYear ? 'selected' : '';
        yearOptions += `<option value="${y}" ${selected}>${y}</option>`;
    }

    let monthOptions = '';
    for (let m = 1; m <= 12; m++) {
        const selected = m === selectedMonth ? 'selected' : '';
        const label = String(m).padStart(2, '0');
        monthOptions += `<option value="${String(m).padStart(2, '0')}" ${selected}>${label}</option>`;
    }

    return `
    <div class="expiry-selectors" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
        <div style="display:flex;align-items:center;gap:4px;">
            <label style="font-size:12px;color:#666;">سال:</label>
            <select class="expiry-year" style="padding:6px 8px;border:1px solid #ddd;border-radius:6px;font-size:13px;min-width:80px;">
                ${yearOptions}
            </select>
        </div>
        <div style="display:flex;align-items:center;gap:4px;">
            <label style="font-size:12px;color:#666;">ماه:</label>
            <select class="expiry-month" style="padding:6px 8px;border:1px solid #ddd;border-radius:6px;font-size:13px;min-width:70px;">
                ${monthOptions}
            </select>
        </div>
        <span class="expiry-preview" style="font-size:12px;color:#28a745;font-weight:bold;background:#e8f5e9;padding:4px 10px;border-radius:4px;">
            ${selectedYear}.${String(selectedMonth).padStart(2, '0')}
        </span>
    </div>
    `;
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

// ===== Middleware =====
function loginRequired(req, res, next) {
    if (!req.session.loggedIn) {
        return res.redirect('/login');
    }
    next();
}

function adminRequired(req, res, next) {
    if (!req.session.loggedIn) {
        return res.redirect('/login');
    }
    if (req.session.username !== 'admin') {
        return res.status(403).send('⛔ دسترسی غیرمجاز. فقط ادمین می‌تواند وارد این بخش شود.');
    }
    next();
}

// ===== Headers ضد کش =====
app.use((req, res, next) => {
    if (req.path.startsWith('/api/')) {
        res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
        res.setHeader('Pragma', 'no-cache');
        res.setHeader('Expires', '0');
    }
    next();
});

// ===== قالب HTML =====
// از EJS استفاده می‌کنیم. فایل views/layout.ejs ایجاد می‌شود

// ===== روت‌ها =====

// صفحه اصلی
app.get('/', async (req, res) => {
    try {
        const interviews = await dbManager.all('SELECT * FROM interviews WHERE is_published = 1 ORDER BY created_at DESC');
        const announcements = await dbManager.all('SELECT * FROM announcements WHERE is_active = 1 ORDER BY created_at DESC LIMIT 3');

        const content = `
        <div class="card"><div class="card-title">🎙️ مصاحبه با داروسازان</div>
        ${interviews.length > 0 ? interviews.map(i => `
            <div class="interview-card">
                <h3>${i.title}</h3>
                <div class="meta">👤 ${i.pharmacist_name} | 🏥 ${i.pharmacy_name} | 📅 ${i.created_at.slice(0, 10)}</div>
                <div class="content">${i.content}</div>
                <div class="media">
                    ${i.image_url ? `<img src="${i.image_url}" alt="${i.title}" style="max-width:100%;border-radius:6px;max-height:300px;">` : ''}
                    ${i.audio_url ? `<audio controls style="width:100%;"><source src="${i.audio_url}"></audio>` : ''}
                </div>
            </div>
        `).join('') : '<p style="text-align:center;padding:30px;color:#999;">هنوز مصاحبه‌ای ثبت نشده است</p>'}
        </div>
        ${announcements.length > 0 ? `
        <div class="card" style="background:#e3f2fd;border:1px solid #90caf9;">
            <div class="card-title">📢 اطلاعیه‌ها</div>
            ${announcements.map(a => `
                <div style="padding:8px 0;border-bottom:1px solid #e0e0e0;">
                    <strong>${a.title}</strong>
                    <p style="font-size:13px;color:#555;margin-top:4px;">${a.content}</p>
                    <span style="font-size:11px;color:#999;">${a.created_at.slice(0, 10)}</span>
                </div>
            `).join('')}
        </div>
        ` : ''}`;

        res.render('layout', {
            content,
            pageTitle: 'صفحه اصلی',
            session: req.session
        });
    } catch (err) {
        console.error(err);
        res.status(500).send('خطا در بارگذاری صفحه');
    }
});

// Login
app.get('/login', (req, res) => {
    res.send(`
    <!DOCTYPE html>
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
        .error { color: #dc3545; margin-top: 10px; font-size: 13px; }
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
    `);
});

app.post('/login', async (req, res) => {
    try {
        const { username, password } = req.body;
        const user = await dbManager.get('SELECT * FROM users WHERE username = ?', [username]);

        if (user && user.password_hash === hashPassword(password)) {
            const isApproved = user.is_approved !== undefined ? user.is_approved : 1;

            if (isApproved === 0) {
                return res.send(`
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
                `);
            }

            if (isApproved === 2) {
                return res.send(`
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
                `);
            }

            req.session.loggedIn = true;
            req.session.userId = user.id;
            req.session.username = user.username;
            req.session.isFullUser = user.is_full_user;
            req.session.pharmacyDisplayName = user.pharmacy_display_name;
            req.session.isApproved = isApproved;
            req.session.user = user;

            return res.redirect('/');
        }

        res.send(`
        <!DOCTYPE html>
        <html dir="rtl" lang="fa">
        <head><meta charset="UTF-8"><title>ورود</title>
        <style>
            body { font-family: Tahoma, sans-serif; background: #f5f5f5; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
            .login-box { background: white; padding: 30px; border-radius: 16px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); width: 340px; text-align: center; }
            .login-box h2 { margin-bottom: 20px; color: #1a1a1a; }
            .login-box input { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; box-sizing: border-box; }
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
        `);
    } catch (err) {
        console.error(err);
        res.status(500).send('خطا در ورود');
    }
});

// Register
app.get('/register', (req, res) => {
    res.send(`
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
    `);
});

app.post('/register', async (req, res) => {
    try {
        const { username, password, confirm_password, pharmacy_name, phone_number, address } = req.body;

        if (!username || !password || !pharmacy_name) {
            return res.send('❌ همه فیلدهای اجباری را پر کنید');
        }
        if (username.length < 3) {
            return res.send('❌ نام کاربری باید حداقل 3 کاراکتر باشد');
        }
        if (password.length < 4) {
            return res.send('❌ رمز عبور باید حداقل 4 کاراکتر باشد');
        }
        if (password !== confirm_password) {
            return res.send('❌ رمز عبور و تکرار آن مطابقت ندارند');
        }
        if (username.includes(' ')) {
            return res.send('❌ نام کاربری نباید شامل فاصله باشد');
        }
        if (phone_number && !/^09[0-9]{9}$/.test(phone_number)) {
            return res.send('❌ شماره همراه نامعتبر است. فرمت صحیح: 09121234567');
        }

        const existing = await dbManager.get('SELECT COUNT(*) as count FROM users WHERE username = ?', [username]);
        if (existing.count > 0) {
            return res.send('❌ این نام کاربری قبلاً ثبت شده است');
        }

        await dbManager.run(
            'INSERT INTO users (username, password_hash, is_full_user, pharmacy_display_name, created_at, phone_number, address, is_approved) VALUES (?, ?, ?, ?, ?, ?, ?, 0)',
            [username, hashPassword(password), 0, pharmacy_name, new Date().toISOString(), phone_number || null, address || null]
        );

        const user = await dbManager.get('SELECT id FROM users WHERE username = ?', [username]);
        if (user) {
            await dbManager.run('INSERT INTO user_categories (user_id, categories) VALUES (?, ?)', [user.id, '']);
        }

        res.send(`
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
        `);
    } catch (err) {
        console.error(err);
        res.status(500).send('خطا در ثبت‌نام');
    }
});

// Logout
app.get('/logout', (req, res) => {
    req.session.destroy();
    res.redirect('/');
});

// ===== Dashboard =====
app.get('/dashboard', loginRequired, async (req, res) => {
    try {
        const userId = req.session.userId;

        const totalDrugsResult = await dbManager.get('SELECT COUNT(*) as count FROM drugs WHERE user_id = ? AND ordered = 0', [userId]);
        const totalDrugs = totalDrugsResult.count;

        const totalOrdersResult = await dbManager.get('SELECT COUNT(*) as count FROM orders WHERE user_id = ?', [userId]);
        const totalOrders = totalOrdersResult.count;

        const totalInventoryResult = await dbManager.get('SELECT SUM(quantity) as total FROM inventory WHERE user_id = ?', [userId]);
        const totalInventory = totalInventoryResult.total || 0;

        const totalExchangesResult = await dbManager.get('SELECT COUNT(*) as count FROM exchanges WHERE user_id = ?', [userId]);
        const totalExchanges = totalExchangesResult.count;

        const drugs = await dbManager.all('SELECT * FROM drugs WHERE user_id = ? AND ordered = 0 ORDER BY priority ASC, created_at DESC', [userId]);

        let quotaHtml = '';
        let normalHtml = '';
        for (const d of drugs) {
            const drugHtml = `
            <div style="padding:8px;margin:5px 0;background:#f8f8f8;border-radius:8px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
                <input type="checkbox" class="chk" data-id="${d.id}">
                <span style="flex:1"><strong>${d.name}</strong> - ${d.quantity} عدد</span>
                <input type="number" class="qty-${d.id}" value="${d.quantity}" style="width:70px;padding:4px">
            </div>`;
            if (d.type === 'quota') {
                quotaHtml += drugHtml;
            } else {
                normalHtml += drugHtml;
            }
        }

        const orders = await dbManager.all('SELECT * FROM orders WHERE user_id = ? ORDER BY ordered_at DESC', [userId]);

        let ordersHtml = '';
        if (orders.length > 0) {
            ordersHtml = orders.map(o => `
            <tr>
                <td>${o.company}</td>
                <td><strong>${o.drug_name}</strong></td>
                <td>${o.quantity}</td>
                <td>${o.ordered_at.slice(0, 10)}</td>
            </tr>
            `).join('');
        } else {
            ordersHtml = '<tr><td colspan="4" style="text-align:center;padding:20px;color:#999;">هیچ سفارشی ثبت نشده است</td></tr>';
        }

        const quotaCount = drugs.filter(d => d.type === 'quota').length;
        const normalCount = drugs.filter(d => d.type !== 'quota').length;

        const content = `
        <div class="dashboard-tab">
            <button class="active" onclick="showDashboardTab('assistant')">📋 دستیار خرید</button>
            <button onclick="showDashboardTab('orders')">📜 سفارشات ثبت شده</button>
        </div>

        <div id="assistantTab" class="tab-content active">
            <div class="stats-grid">
                <div class="stat-card"><div class="number">${totalDrugs}</div><div class="label">💊 کل داروهای کسری</div></div>
                <div class="stat-card"><div class="number">${quotaCount}</div><div class="label">📦 سهمیه ای</div></div>
                <div class="stat-card"><div class="number">${normalCount}</div><div class="label">📦 عادی</div></div>
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
                        <div id="quotaDrugsList">${quotaHtml || '<p style="text-align:center;padding:20px;color:#999">هیچ داروی سهمیه‌ای وجود ندارد</p>'}</div>
                    </div>
                    <div class="drugs-column">
                        <h4>📦 عادی</h4>
                        <div id="normalDrugsList">${normalHtml || '<p style="text-align:center;padding:20px;color:#999">هیچ داروی عادی وجود ندارد</p>'}</div>
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
                        <tbody id="ordersList">${ordersHtml}</tbody>
                    </table>
                </div>
            </div>
        </div>

        <script>
        function showToast(message, type) {
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.className = 'toast-message ' + (type || 'info');
            toast.style.display = 'block';
            setTimeout(() => { toast.style.display = 'none'; }, 3000);
        }

        function showDashboardTab(tab) {
            document.querySelectorAll('#assistantTab, #ordersTab').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.dashboard-tab button').forEach(btn => btn.classList.remove('active'));
            if (tab === 'assistant') {
                document.getElementById('assistantTab').classList.add('active');
                document.querySelector('.dashboard-tab button:first-child').classList.add('active');
            } else {
                document.getElementById('ordersTab').classList.add('active');
                document.querySelector('.dashboard-tab button:last-child').classList.add('active');
            }
        }

        function submitOrder() {
            const ids = [];
            const qty = {};
            document.querySelectorAll('.chk:checked').forEach(c => {
                const id = parseInt(c.dataset.id);
                ids.push(id);
                qty[id] = document.querySelector('.qty-'+id).value;
            });
            const company = document.getElementById('company').value;
            if (!company) { showToast('شرکت را انتخاب کنید', 'error'); return; }
            if (ids.length === 0) { showToast('حداقل یک دارو انتخاب کنید', 'error'); return; }
            fetch('/api/place_order', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ selected_ids: ids, company: company, quantities: qty })
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    showToast('✅ سفارش با موفقیت ثبت شد', 'success');
                    location.reload();
                } else {
                    showToast('❌ خطا: ' + data.error, 'error');
                }
            })
            .catch(err => {
                showToast('❌ خطا در ارتباط با سرور', 'error');
            });
        }

        document.getElementById('companyFilter').addEventListener('change', function() {
            const company = this.value;
            const search = document.getElementById('searchFilter').value.toLowerCase();
            document.querySelectorAll('#ordersList tr').forEach(row => {
                let show = true;
                if (company !== 'all') {
                    const td = row.querySelector('td:first-child');
                    if (td && td.textContent !== company) show = false;
                }
                if (search) {
                    const td = row.querySelector('td:nth-child(2)');
                    if (td && !td.textContent.toLowerCase().includes(search)) show = false;
                }
                row.style.display = show ? '' : 'none';
            });
        });

        document.getElementById('searchFilter').addEventListener('input', function() {
            document.getElementById('companyFilter').dispatchEvent(new Event('change'));
        });

        function resetFilters() {
            document.getElementById('companyFilter').value = 'all';
            document.getElementById('searchFilter').value = '';
            document.getElementById('companyFilter').dispatchEvent(new Event('change'));
        }
        </script>
        `;

        res.render('layout', {
            content,
            pageTitle: '📊 داشبورد',
            session: req.session
        });
    } catch (err) {
        console.error(err);
        res.status(500).send('خطا در بارگذاری داشبورد');
    }
});

// ===== Inventory =====
app.get('/inventory', loginRequired, async (req, res) => {
    const expiryHtml = getYearMonthSelectors();
    const content = `
    <div class="card">
        <div class="card-title">📦 ثبت فاکتور جدید</div>
        <div class="form-row">
            <div class="search-container" style="flex:2">
                <input type="text" id="invName" placeholder="نام دارو" onkeyup="searchDrugsInv(this.value)" autocomplete="off">
                <div id="suggestionsInv" class="suggestions-list"></div>
            </div>
            <input type="number" id="invQty" placeholder="تعداد" value="1">
            <div style="flex:1;min-width:200px;">
                ${expiryHtml}
            </div>
            <select id="location">
                <option value="warehouse">انبار</option>
                <option value="pharmacy">داروخانه</option>
            </select>
            <input type="text" id="supplier" placeholder="تامین کننده">
            <input type="text" id="price" placeholder="قیمت خرید">
            <button onclick="addInventory()">ثبت فاکتور</button>
        </div>
    </div>

    <div class="card">
        <div class="card-title">💸 ثبت فروش</div>
        <div class="form-row">
            <div class="search-container" style="flex:2">
                <input type="text" id="saleDrugName" placeholder="نام دارو" onkeyup="searchDrugsForSale(this.value)" autocomplete="off">
                <div id="suggestionsSale" class="suggestions-list"></div>
            </div>
            <input type="number" id="saleQty" placeholder="تعداد" value="1">
            <div style="flex:1;min-width:200px;">
                ${expiryHtml}
            </div>
            <input type="text" id="customerName" placeholder="نام مشتری">
            <input type="text" id="salePrice" placeholder="قیمت فروش">
            <select id="saleLocation">
                <option value="warehouse">انبار</option>
                <option value="pharmacy">داروخانه</option>
            </select>
            <button onclick="registerSale()" class="btn-success">ثبت فروش</button>
        </div>
    </div>

    <div class="card">
        <div class="card-title">🔄 جابجایی دارو</div>
        <div class="form-row">
            <div class="search-container" style="flex:2">
                <input type="text" id="moveDrug" placeholder="نام دارو" onkeyup="searchDrugsMove(this.value)" autocomplete="off">
                <div id="suggestionsMove" class="suggestions-list"></div>
            </div>
            <input type="number" id="moveQty" placeholder="تعداد" value="1">
            <div style="flex:1;min-width:200px;">
                ${expiryHtml}
            </div>
            <select id="moveFromLocation">
                <option value="warehouse">انبار</option>
                <option value="pharmacy">داروخانه</option>
            </select>
            <span style="font-size:18px">➡</span>
            <select id="moveToLocation">
                <option value="warehouse">انبار</option>
                <option value="pharmacy">داروخانه</option>
            </select>
            <button onclick="moveDrug()">انتقال</button>
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
    const USER_ID = ${req.session.userId};
    let inventoryData = [];
    let currentFilter = '';
    let showHidden = false;
    let hiddenIds = new Set();

    try {
        const saved = localStorage.getItem('hiddenIds_' + USER_ID);
        if (saved) {
            hiddenIds = new Set(JSON.parse(saved));
        }
    } catch(e) {
        hiddenIds = new Set();
    }

    function showToast(message, type) {
        const toast = document.getElementById('toast');
        toast.textContent = message;
        toast.className = 'toast-message ' + (type || 'info');
        toast.style.display = 'block';
        setTimeout(() => { toast.style.display = 'none'; }, 3000);
    }

    function loadHiddenItems() {
        fetch('/api/get_hidden_items')
            .then(r => r.json())
            .then(data => {
                hiddenIds = new Set(data.hidden_ids || []);
                localStorage.setItem('hiddenIds_' + USER_ID, JSON.stringify([...hiddenIds]));
                renderInventory();
            })
            .catch(() => {
                hiddenIds = new Set();
                localStorage.setItem('hiddenIds_' + USER_ID, JSON.stringify([]));
                renderInventory();
            });
    }

    function validateExpiryFormat(expiry) {
        return /^\\d{4}\\.(0[1-9]|1[0-2])$/.test(expiry);
    }

    function getExpiryStatusText(expiryDate) {
        if (!expiryDate) return { text: 'نامشخص', class: '' };
        try {
            const parts = expiryDate.split('.');
            if (parts.length !== 2) return { text: 'نامشخص', class: '' };
            const now = new Date();
            const expYear = parseInt(parts[0]);
            const expMonth = parseInt(parts[1]) - 1;
            const exp = new Date(expYear, expMonth, 1);
            const monthsLeft = (exp.getFullYear() - now.getFullYear()) * 12 + (exp.getMonth() - now.getMonth());
            if (monthsLeft < 0) return { text: '🔴 منقضی', class: 'expired' };
            if (monthsLeft <= 3) return { text: '🟡 ' + monthsLeft + ' ماه مانده', class: 'expiring-soon' };
            return { text: '🟢 ' + monthsLeft + ' ماه مانده', class: 'good-expiry' };
        } catch(e) { return { text: 'نامشخص', class: '' }; }
    }

    function filterInventory() {
        currentFilter = document.getElementById('liveSearch')?.value.toLowerCase() || '';
        renderInventory();
    }

    function toggleHiddenItems() {
        showHidden = !showHidden;
        renderInventory();
    }

    function selectAllItems() {
        document.querySelectorAll('.drug-item .item-checkbox').forEach(cb => cb.checked = true);
    }

    function deselectAllItems() {
        document.querySelectorAll('.drug-item .item-checkbox').forEach(cb => cb.checked = false);
    }

    function getSelectedItemIds() {
        const ids = [];
        document.querySelectorAll('.drug-item .item-checkbox:checked').forEach(cb => {
            ids.push(parseInt(cb.dataset.id));
        });
        return ids;
    }

    function copySelectedItems() {
        const ids = getSelectedItemIds();
        if (ids.length === 0) { showToast('هیچ آیتمی انتخاب نشده است', 'error'); return; }
        let text = "📋 لیست داروهای انتخاب شده\\n";
        text += "📅 " + new Date().toLocaleDateString('fa-IR') + "\\n─────────────────────\\n";
        inventoryData.forEach(tab => {
            if (!tab || !tab.pharmacies) return;
            tab.pharmacies.forEach(ph => {
                if (!ph || !ph.drugs) return;
                ph.drugs.forEach(d => {
                    if (ids.includes(d.id) && (!d.hidden || showHidden)) {
                        text += "• " + d.name + ": " + d.quantity + " عدد (" + (d.location === 'warehouse' ? 'انبار' : 'داروخانه') + ") - انقضا: " + (d.expiry_date || 'نامشخص') + "\\n";
                    }
                });
            });
        });
        if (text.length > 5000) { showToast('گزارش بیش از حد بزرگ است', 'error'); return; }
        const textarea = document.createElement('textarea');
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        showToast('✅ متن در کلیپبورد کپی شد', 'success');
    }

    function hideSelectedItems() {
        const ids = getSelectedItemIds();
        if (ids.length === 0) { showToast('هیچ آیتمی انتخاب نشده است', 'error'); return; }
        if (!confirm(ids.length + ' آیتم هاید شود؟')) return;
        fetch('/api/toggle_hidden_items', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ item_ids: ids, hidden: true })
        }).then(r => r.json()).then(data => {
            if (data.success) {
                showToast('✅ ' + ids.length + ' آیتم هاید شد', 'success');
                ids.forEach(id => hiddenIds.add(id));
                localStorage.setItem('hiddenIds_' + USER_ID, JSON.stringify([...hiddenIds]));
                loadInventory();
            } else {
                showToast('خطا: ' + data.error, 'error');
            }
        }).catch(() => showToast('❌ خطا در ارتباط با سرور', 'error'));
    }

    function unhideSelectedItems() {
        const ids = getSelectedItemIds();
        if (ids.length === 0) { showToast('هیچ آیتمی انتخاب نشده است', 'error'); return; }
        if (!confirm(ids.length + ' آیتم unhide شود؟')) return;
        fetch('/api/toggle_hidden_items', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ item_ids: ids, hidden: false })
        }).then(r => r.json()).then(data => {
            if (data.success) {
                showToast('✅ ' + ids.length + ' آیتم unhide شد', 'success');
                ids.forEach(id => hiddenIds.delete(id));
                localStorage.setItem('hiddenIds_' + USER_ID, JSON.stringify([...hiddenIds]));
                loadInventory();
            } else {
                showToast('خطا: ' + data.error, 'error');
            }
        }).catch(() => showToast('❌ خطا در ارتباط با سرور', 'error'));
    }

    function deleteSelectedItems() {
        const ids = getSelectedItemIds();
        if (ids.length === 0) { showToast('هیچ آیتمی انتخاب نشده است', 'error'); return; }
        if (!confirm('آیا از حذف ' + ids.length + ' آیتم انتخاب شده اطمینان دارید؟')) return;
        fetch('/api/delete_inventory_items', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ item_ids: ids })
        }).then(r => r.json()).then(data => {
            if (data.success) {
                showToast('✅ ' + ids.length + ' آیتم حذف شد', 'success');
                loadInventory();
            } else {
                showToast('خطا: ' + data.error, 'error');
            }
        }).catch(() => showToast('❌ خطا در ارتباط با سرور', 'error'));
    }

    function deleteSingleItem(id) {
        if (!confirm('آیا از حذف این آیتم اطمینان دارید؟')) return;
        fetch('/api/delete_inventory_item/' + id, { method: 'POST' })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    showToast('✅ آیتم حذف شد', 'success');
                    loadInventory();
                } else {
                    showToast('خطا: ' + data.error, 'error');
                }
            })
            .catch(() => showToast('❌ خطا در ارتباط با سرور', 'error'));
    }

    function renderInventory() {
        const container = document.getElementById('inventoryContainer');
        if (!container) return;
        const filtered = inventoryData.filter(tab => {
            if (!currentFilter) return true;
            return tab.pharmacies.some(ph =>
                ph.drugs.some(d => d.name.toLowerCase().includes(currentFilter))
            );
        });
        let totalVisible = 0;
        filtered.forEach(tab => {
            tab.pharmacies.forEach(ph => {
                ph.drugs.forEach(d => {
                    if ((!d.hidden || showHidden) && d.name.toLowerCase().includes(currentFilter)) totalVisible += d.quantity;
                });
            });
        });
        document.getElementById('stats').innerHTML = '<div class="stat-card"><div class="number">' + filtered.length + '</div><div class="label">تاریخ انقضا</div></div>' +
            '<div class="stat-card"><div class="number">' + totalVisible + '</div><div class="label">مجموع اقلام</div></div>';
        if (filtered.length === 0) {
            container.innerHTML = '<p style="text-align:center;padding:40px;color:#999">انبار خالی است</p>';
            return;
        }
        let html = '';
        filtered.forEach((tab, idx) => {
            const status = getExpiryStatusText(tab.expiry_date);
            const isOpen = idx === 0 ? 'show' : '';
            html += '<div class="expiry-tab">';
            html += '<div class="expiry-tab-header" style="background:' + (status.class === 'expired' ? '#f8d7da' : status.class === 'expiring-soon' ? '#fff3cd' : '#d4edda') + '" onclick="toggleTab(this)">';
            html += '<span class="expiry-date">📅 ' + tab.expiry_date + '</span>';
            html += '<span><span class="expiry-status ' + status.class + '">' + status.text + '</span>';
            let totalQty = 0;
            tab.pharmacies.forEach(ph => ph.drugs.forEach(d => { if ((!d.hidden || showHidden) && d.name.toLowerCase().includes(currentFilter)) totalQty += d.quantity; }));
            html += ' | 🏥 ' + tab.pharmacies.length + ' داروخانه | 📦 ' + totalQty + ' عدد</span>';
            html += '</div>';
            html += '<div class="expiry-tab-body ' + isOpen + '">';
            tab.pharmacies.forEach((ph, phIdx) => {
                const visibleDrugs = ph.drugs.filter(d => (!d.hidden || showHidden) && d.name.toLowerCase().includes(currentFilter));
                if (visibleDrugs.length === 0) return;
                const isPhOpen = phIdx === 0 ? 'show' : '';
                html += '<div class="pharmacy-group">';
                html += '<div class="pharmacy-group-header" onclick="togglePharmacyGroup(this)">';
                html += '<span>🏥 ' + ph.pharmacy_name + '</span>';
                html += '<span>📦 ' + visibleDrugs.reduce((a,b) => a + b.quantity, 0) + ' عدد</span>';
                html += '</div>';
                html += '<div class="pharmacy-group-body ' + isPhOpen + '">';
                visibleDrugs.forEach(d => {
                    const locText = d.location === 'warehouse' ? 'انبار' : 'داروخانه';
                    const locClass = d.location === 'warehouse' ? 'location-warehouse' : 'location-pharmacy';
                    html += '<div class="drug-item">';
                    html += '<input type="checkbox" class="item-checkbox" data-id="' + d.id + '">';
                    html += '<span class="drug-name">' + d.name + '</span>';
                    html += '<span class="drug-qty">' + d.quantity + ' عدد</span>';
                    html += '<span class="drug-location ' + locClass + '">' + locText + '</span>';
                    html += '<span style="font-size:11px;color:#999;">انقضا: ' + (d.expiry_date || '-') + '</span>';
                    if (d.hidden) html += '<span style="font-size:11px;color:#dc3545;">🙈 هاید</span>';
                    html += '<div class="drug-actions">';
                    html += '<button onclick="deleteSingleItem(' + d.id + ')" class="btn-danger btn-sm">🗑️</button>';
                    html += '</div>';
                    html += '</div>';
                });
                html += '</div></div>';
            });
            html += '</div></div>';
        });
        container.innerHTML = html;
    }

    function toggleTab(header) { const body = header.nextElementSibling; body.classList.toggle('show'); }
    function togglePharmacyGroup(header) { const body = header.nextElementSibling; body.classList.toggle('show'); }

    function loadInventory() {
        fetch('/api/get_inventory_grouped_by_expiry', {
            headers: {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
        })
        .then(r => r.json())
        .then(data => {
            inventoryData = data.data || [];
            loadHiddenItems();
        })
        .catch(err => {
            console.error('Error loading inventory:', err);
            document.getElementById('inventoryContainer').innerHTML = '<p style="text-align:center;padding:40px;color:#dc3545">❌ خطا در بارگذاری</p>';
            showToast('❌ خطا در بارگذاری انبار', 'error');
        });
    }

    function searchDrugsInv(query) {
        const suggestions = document.getElementById('suggestionsInv');
        if (query.length < 2) { suggestions.style.display = 'none'; return; }
        fetch('/api/search_with_stock?q=' + encodeURIComponent(query))
            .then(r => r.json())
            .then(data => {
                if (data.length > 0) {
                    let html = '';
                    data.forEach(drug => {
                        html += '<div onclick="selectDrugInv(\\'' + drug.name + '\\')"><strong>' + drug.name + '</strong><div class="stock-info">🏭 انبار: ' + drug.warehouse_qty + ' | 🏪 داروخانه: ' + drug.pharmacy_qty + ' | 📅 نزدیک‌ترین انقضا: ' + (drug.nearest_expiry || '-') + '</div></div>';
                    });
                    suggestions.innerHTML = html;
                    suggestions.style.display = 'block';
                } else { suggestions.style.display = 'none'; }
            })
            .catch(() => { suggestions.style.display = 'none'; });
    }

    function searchDrugsForSale(query) {
        const suggestions = document.getElementById('suggestionsSale');
        if (query.length < 2) { suggestions.style.display = 'none'; return; }
        fetch('/api/search_with_stock?q=' + encodeURIComponent(query))
            .then(r => r.json())
            .then(data => {
                if (data.length > 0) {
                    let html = '';
                    data.forEach(drug => {
                        html += '<div onclick="selectDrugForSale(\\'' + drug.name + '\\')"><strong>' + drug.name + '</strong><div class="stock-info">🏭 انبار: ' + drug.warehouse_qty + ' | 🏪 داروخانه: ' + drug.pharmacy_qty + ' | 📅 نزدیک‌ترین انقضا: ' + (drug.nearest_expiry || '-') + '</div></div>';
                    });
                    suggestions.innerHTML = html;
                    suggestions.style.display = 'block';
                } else { suggestions.style.display = 'none'; }
            })
            .catch(() => { suggestions.style.display = 'none'; });
    }

    function searchDrugsMove(query) {
        const suggestions = document.getElementById('suggestionsMove');
        if (query.length < 2) { suggestions.style.display = 'none'; return; }
        fetch('/api/search_with_stock?q=' + encodeURIComponent(query))
            .then(r => r.json())
            .then(data => {
                if (data.length > 0) {
                    let html = '';
                    data.forEach(drug => {
                        html += '<div onclick="selectDrugMove(\\'' + drug.name + '\\')"><strong>' + drug.name + '</strong><div class="stock-info">🏭 انبار: ' + drug.warehouse_qty + ' | 🏪 داروخانه: ' + drug.pharmacy_qty + ' | 📅 نزدیک‌ترین انقضا: ' + (drug.nearest_expiry || '-') + '</div></div>';
                    });
                    suggestions.innerHTML = html;
                    suggestions.style.display = 'block';
                } else { suggestions.style.display = 'none'; }
            })
            .catch(() => { suggestions.style.display = 'none'; });
    }

    function selectDrugInv(name) { document.getElementById('invName').value = name; document.getElementById('suggestionsInv').style.display = 'none'; }
    function selectDrugForSale(name) { document.getElementById('saleDrugName').value = name; document.getElementById('suggestionsSale').style.display = 'none'; }
    function selectDrugMove(name) { document.getElementById('moveDrug').value = name; document.getElementById('suggestionsMove').style.display = 'none'; }

    function getExpiryFromSelectors(formRow) {
        const yearEl = formRow ? formRow.querySelector('.expiry-year') : null;
        const monthEl = formRow ? formRow.querySelector('.expiry-month') : null;
        const year = yearEl ? yearEl.value : new Date().getFullYear();
        const month = monthEl ? monthEl.value : '01';
        return year + '.' + month;
    }

    function addInventory() {
        const name = document.getElementById('invName').value;
        const qty = document.getElementById('invQty').value;
        const formRow = document.getElementById('invName').closest('.form-row');
        const expiry = getExpiryFromSelectors(formRow);
        if (!name || !qty || !expiry) {
            showToast('نام دارو، تعداد و تاریخ انقضا اجباری است', 'error');
            return;
        }
        const fd = new FormData();
        fd.append('name', name);
        fd.append('quantity', qty);
        fd.append('expiry_date', expiry);
        fd.append('location', document.getElementById('location').value);
        fd.append('supplier', document.getElementById('supplier').value);
        fd.append('purchase_price', document.getElementById('price').value);
        fetch('/api/add_inventory', {
            method: 'POST',
            body: fd
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                showToast('✅ دارو ثبت شد', 'success');
                loadInventory();
                document.getElementById('invName').value = '';
                document.getElementById('invQty').value = '1';
                document.getElementById('supplier').value = '';
                document.getElementById('price').value = '';
            } else {
                showToast('خطا: ' + data.error, 'error');
            }
        })
        .catch(err => {
            showToast('❌ خطا در ارتباط با سرور', 'error');
        });
    }

    function registerSale() {
        const name = document.getElementById('saleDrugName').value;
        const qty = document.getElementById('saleQty').value;
        const formRow = document.getElementById('saleDrugName').closest('.form-row');
        const expiry = getExpiryFromSelectors(formRow);
        if (!name || !qty || !expiry) { showToast('نام دارو، تعداد و تاریخ انقضا اجباری است', 'error'); return; }
        fetch('/api/register_sale', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                drug_name: name,
                quantity: parseInt(qty),
                expiry_date: expiry,
                customer_name: document.getElementById('customerName').value,
                price: parseFloat(document.getElementById('salePrice').value) || 0,
                location: document.getElementById('saleLocation').value
            })
        })
        .then(r => r.json())
        .then(res => {
            if (res.success) {
                showToast('✅ فروش ثبت شد', 'success');
                loadInventory();
            } else {
                showToast('خطا: ' + res.error, 'error');
            }
        })
        .catch(() => showToast('❌ خطا در ارتباط با سرور', 'error'));
    }

    function moveDrug() {
        const name = document.getElementById('moveDrug').value;
        const qty = document.getElementById('moveQty').value;
        const fromLoc = document.getElementById('moveFromLocation').value;
        const toLoc = document.getElementById('moveToLocation').value;
        const formRow = document.getElementById('moveDrug').closest('.form-row');
        const expiry = getExpiryFromSelectors(formRow);
        if (!name || !qty || !expiry) { showToast('نام دارو، تعداد و تاریخ انقضا را وارد کنید', 'error'); return; }
        fetch('/api/move_inventory', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, quantity: parseInt(qty), from_location: fromLoc, to_location: toLoc, expiry_date: expiry })
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                showToast('✅ انتقال انجام شد', 'success');
                loadInventory();
            } else {
                showToast('خطا: ' + data.error, 'error');
            }
        })
        .catch(() => showToast('❌ خطا در ارتباط با سرور', 'error'));
    }

    document.addEventListener('change', function(e) {
        if (e.target.classList.contains('expiry-year') || e.target.classList.contains('expiry-month')) {
            const row = e.target.closest('.form-row');
            if (row) {
                const year = row.querySelector('.expiry-year');
                const month = row.querySelector('.expiry-month');
                const preview = row.querySelector('.expiry-preview');
                if (year && month && preview) {
                    preview.textContent = year.value + '.' + month.value;
                }
            }
        }
    });

    document.addEventListener('click', function(e) {
        if (!e.target.closest('.search-container')) {
            ['suggestionsInv', 'suggestionsSale', 'suggestionsMove'].forEach(id => { const s = document.getElementById(id); if (s) s.style.display = 'none'; });
        }
    });

    loadInventory();
    </script>
    `;

    res.render('layout', {
        content,
        pageTitle: '📦 انبارداری',
        session: req.session
    });
});

// ===== ادامه در بخش بعدی =====
// ===== Exchange =====
app.get('/exchange', loginRequired, async (req, res) => {
    try {
        const userId = req.session.userId;

        const pharmacies = await dbManager.all(
            'SELECT id, pharmacy_display_name FROM users WHERE id != ? AND is_approved = 1',
            [userId]
        );

        let pharmacyOptions = '';
        for (const p of pharmacies) {
            pharmacyOptions += `<option value="${p.id}">${p.pharmacy_display_name}</option>`;
        }

        const userCat = await dbManager.get(
            'SELECT categories FROM user_categories WHERE user_id = ?',
            [userId]
        );
        const userCategories = (userCat && userCat.categories) ? userCat.categories.split(',') : [];

        const catMap = {
            'heart': '❤️ قلب',
            'respiratory': '🌬️ تنفس',
            'women': '👩 زنان',
            'orthopedic': '🦵 ارتوپد',
            'urology': '🚽 ارولوژی',
            'endocrine': '🧬 غدد',
            'neurology': '🧠 مغز و اعصاب',
            'dermatology': '🧴 پوست',
            'pediatric': '👶 کودکان',
            'eye': '👁️ چشم',
            'other': '📦 سایر'
        };

        let catChecks = '';
        for (const [key, label] of Object.entries(catMap)) {
            const checked = userCategories.includes(key) ? 'checked' : '';
            catChecks += `<label><input type="checkbox" value="${key}" ${checked}> ${label}</label>`;
        }

        const content = `
        <div class="exchange-tab">
            <button class="active" onclick="showExchangeTab('register')">🔄 ثبت تبادل</button>
            <button onclick="showExchangeTab('list')">📋 تبادلات من</button>
            <button onclick="showExchangeTab('pending')">⏳ درخواست‌های دریافتی</button>
        </div>

        <div id="registerTab" class="tab-content active">
            <div class="card">
                <div class="card-title">📋 دسته‌بندی مصرفی</div>
                <div class="category-checkboxes" id="categoryCheckboxes" style="display:flex;flex-wrap:wrap;gap:10px;padding:10px;background:#f8f9fa;border-radius:10px;">
                    ${catChecks}
                </div>
                <button onclick="saveUserCategories()" class="btn-success" style="margin-top:10px;">💾 ذخیره دسته‌بندی</button>
            </div>

            <div class="card">
                <div class="card-title">🔍 جستجوی دارو در تمام داروخانه‌ها</div>
                <div class="form-row">
                    <input type="text" id="drugFilter" placeholder="🔍 نام دارو..." onkeyup="filterExchangeDrugs()" style="flex:2;padding:8px 10px;border:1px solid #ddd;border-radius:6px;font-size:13px;">
                    <select id="targetPharmacySelect" style="flex:1;" onchange="filterExchangeDrugs()">
                        <option value="all">همه داروخانه‌ها</option>
                        ${pharmacyOptions}
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
        const USER_ID = ${userId};
        var selectedTargetPharmacy = null;
        var selectedTargetPharmacyName = '';
        var myDrugs = [];
        var targetDrugs = [];
        var selectedItems = [];
        var userCategories = [];
        var allMyExchanges = [];
        var exchangeAllDrugsData = [];
        var hiddenIds = new Set();

        function showToast(message, type) {
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.className = 'toast-message ' + (type || 'info');
            toast.style.display = 'block';
            setTimeout(() => { toast.style.display = 'none'; }, 3000);
        }

        function loadHiddenItems() {
            fetch('/api/get_hidden_items').then(r=>r.json()).then(data=>{
                hiddenIds = new Set(data.hidden_ids || []);
                renderExchangeAllDrugs();
            }).catch(()=>{ hiddenIds = new Set(); renderExchangeAllDrugs(); });
        }

        function loadUserCategories() {
            fetch('/api/get_user_categories').then(r=>r.json()).then(data=>{
                userCategories = data.categories || [];
                document.querySelectorAll('#categoryCheckboxes input').forEach(cb => {
                    cb.checked = userCategories.includes(cb.value);
                });
            }).catch(()=>{});
        }

        function saveUserCategories() {
            const categories = [];
            document.querySelectorAll('#categoryCheckboxes input:checked').forEach(cb => {
                categories.push(cb.value);
            });
            fetch('/api/save_user_categories', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ categories: categories })
            }).then(r=>r.json()).then(data=>{
                if (data.success) {
                    showToast('✅ دسته‌بندی مصرفی ذخیره شد', 'success');
                    userCategories = categories;
                } else {
                    showToast('خطا: ' + data.error, 'error');
                }
            }).catch(()=> showToast('❌ خطا در ارتباط با سرور', 'error'));
        }

        function getExpiryStatusText(expiryDate) {
            if (!expiryDate) return { text: 'نامشخص', class: '' };
            try {
                const parts = expiryDate.split('.');
                if (parts.length !== 2) return { text: 'نامشخص', class: '' };
                const now = new Date();
                const expYear = parseInt(parts[0]);
                const expMonth = parseInt(parts[1]) - 1;
                const exp = new Date(expYear, expMonth, 1);
                const monthsLeft = (exp.getFullYear() - now.getFullYear()) * 12 + (exp.getMonth() - now.getMonth());
                if (monthsLeft < 0) return { text: '🔴 منقضی', class: 'expired' };
                if (monthsLeft <= 3) return { text: '🟡 ' + monthsLeft + ' ماه مانده', class: 'expiring-soon' };
                return { text: '🟢 ' + monthsLeft + ' ماه مانده', class: 'good-expiry' };
            } catch(e) { return { text: 'نامشخص', class: '' }; }
        }

        function sortByExpiryDate(drugs) {
            return [...drugs].sort((a, b) => {
                if (!a.expiry_date && !b.expiry_date) return 0;
                if (!a.expiry_date) return 1;
                if (!b.expiry_date) return -1;
                const aParts = a.expiry_date.split('.');
                const bParts = b.expiry_date.split('.');
                if (aParts.length !== 2 && bParts.length !== 2) return 0;
                if (aParts.length !== 2) return 1;
                if (bParts.length !== 2) return -1;
                return (parseInt(aParts[0]) * 12 + parseInt(aParts[1])) - (parseInt(bParts[0]) * 12 + parseInt(bParts[1]));
            });
        }

        function loadExchangeAllDrugs() {
            const container = document.getElementById('exchangeAllDrugsContainer');
            container.innerHTML = '<div style="text-align:center;padding:20px;color:#666">🔄 در حال بارگذاری...</div>';
            fetch('/api/get_all_pharmacies_drugs_grouped_by_expiry')
                .then(r => r.json())
                .then(data => {
                    exchangeAllDrugsData = data.data || [];
                    loadHiddenItems();
                })
                .catch(err => {
                    console.error('Error:', err);
                    container.innerHTML = '<div style="text-align:center;padding:20px;color:#dc3545">❌ خطا در بارگذاری</div>';
                    showToast('❌ خطا در بارگذاری', 'error');
                });
        }

        function renderExchangeAllDrugs() {
            const container = document.getElementById('exchangeAllDrugsContainer');
            const filter = document.getElementById('drugFilter').value.toLowerCase();
            const targetPharmacy = document.getElementById('targetPharmacySelect').value;
            let filtered = exchangeAllDrugsData.filter(tab => {
                if (!filter) return true;
                return tab.pharmacies.some(ph =>
                    ph.drugs.some(d => d.name.toLowerCase().includes(filter) && !hiddenIds.has(d.id))
                );
            });
            if (targetPharmacy !== 'all') {
                filtered = filtered.map(tab => {
                    const newPh = tab.pharmacies.filter(ph => ph.pharmacy_id == targetPharmacy);
                    return { ...tab, pharmacies: newPh };
                }).filter(tab => tab.pharmacies.length > 0);
            }
            if (filtered.length === 0) {
                container.innerHTML = '<div style="text-align:center;padding:30px;color:#999">هیچ دارویی یافت نشد</div>';
                return;
            }
            let html = '';
            filtered.forEach((tab, idx) => {
                const status = getExpiryStatusText(tab.expiry_date);
                const isOpen = idx === 0 ? 'show' : '';
                html += '<div class="expiry-tab">';
                html += '<div class="expiry-tab-header" style="background:' + (status.class === 'expired' ? '#f8d7da' : status.class === 'expiring-soon' ? '#fff3cd' : '#d4edda') + '" onclick="toggleExchangeTab(this)">';
                html += '<span class="expiry-date">📅 ' + tab.expiry_date + '</span>';
                html += '<span><span class="expiry-status ' + status.class + '">' + status.text + '</span>';
                let totalQty = 0;
                tab.pharmacies.forEach(ph => ph.drugs.forEach(d => { if (!hiddenIds.has(d.id) && d.name.toLowerCase().includes(filter)) totalQty += d.quantity; }));
                html += ' | 🏥 ' + tab.pharmacies.length + ' داروخانه | 📦 ' + totalQty + ' عدد</span>';
                html += '</div>';
                html += '<div class="expiry-tab-body ' + isOpen + '">';
                tab.pharmacies.forEach((ph, phIdx) => {
                    const visibleDrugs = ph.drugs.filter(d => !hiddenIds.has(d.id) && d.name.toLowerCase().includes(filter));
                    if (visibleDrugs.length === 0) return;
                    const isPhOpen = phIdx === 0 ? 'show' : '';
                    const isMyPharmacy = ph.pharmacy_id == USER_ID;
                    html += '<div class="pharmacy-group">';
                    html += '<div class="pharmacy-group-header" onclick="toggleExchangePharmacyGroup(this)">';
                    html += '<span>🏥 ' + ph.pharmacy_name + (isMyPharmacy ? ' (من)' : '') + '</span>';
                    html += '<span>📦 ' + visibleDrugs.reduce((a,b) => a + b.quantity, 0) + ' عدد</span>';
                    html += '</div>';
                    html += '<div class="pharmacy-group-body ' + isPhOpen + '">';
                    visibleDrugs.forEach(d => {
                        const locText = d.location === 'warehouse' ? 'انبار' : 'داروخانه';
                        const locClass = d.location === 'warehouse' ? 'location-warehouse' : 'location-pharmacy';
                        const isSelected = selectedItems.some(item => item.pharmacy_id === ph.pharmacy_id && item.id === d.id);
                        html += '<div class="drug-item" style="' + (isSelected ? 'background:#d4edda;' : '') + '">';
                        html += '<span class="drug-name">' + d.name + '</span>';
                        html += '<span class="drug-qty">' + d.quantity + ' عدد</span>';
                        html += '<span class="drug-location ' + locClass + '">' + locText + '</span>';
                        html += '<button class="btn-exchange-select ' + (isSelected ? 'selected' : '') + '" onclick="event.stopPropagation(); selectDrugFromExchange(' + ph.pharmacy_id + ', \\'' + ph.pharmacy_name.replace(/'/g, "\\\\'") + '\\', \\'' + d.name.replace(/'/g, "\\\\'") + '\\', ' + d.quantity + ', \\'' + (d.expiry_date || '') + '\\', ' + d.id + ')">' + (isSelected ? '✅ انتخاب شده' : '🔹 انتخاب') + '</button>';
                        html += '</div>';
                    });
                    html += '</div></div>';
                });
                html += '</div></div>';
            });
            container.innerHTML = html;
        }

        function filterExchangeDrugs() {
            renderExchangeAllDrugs();
        }

        function toggleExchangeTab(header) { const body = header.nextElementSibling; body.classList.toggle('show'); }
        function toggleExchangePharmacyGroup(header) { const body = header.nextElementSibling; body.classList.toggle('show'); }

        function selectDrugFromExchange(pharmacyId, pharmacyName, drugName, quantity, expiryDate, drugId) {
            if (selectedTargetPharmacy !== null && selectedTargetPharmacy !== pharmacyId && pharmacyId != USER_ID) {
                showToast('❌ شما نمی‌توانید از دو داروخانه مختلف به طور همزمان انتخاب کنید.', 'error');
                return;
            }
            if (pharmacyId == USER_ID) {
                if (selectedTargetPharmacy !== null && selectedTargetPharmacy != USER_ID) {
                    showToast('❌ شما در حال انتخاب از داروهای خود هستید، اما قبلاً داروخانه هدف دیگری انتخاب کرده‌اید.', 'error');
                    return;
                }
                selectedTargetPharmacy = null;
                selectedTargetPharmacyName = '';
                const drug = myDrugs.find(d => d.id === drugId);
                if (drug) {
                    toggleDrugSelection('my', drugId, drugName, drug.quantity, expiryDate, USER_ID);
                    document.getElementById('exchangeDualView').style.display = 'block';
                    loadDrugsForExchange();
                } else {
                    fetch('/api/get_my_drugs_for_exchange')
                        .then(r=>r.json())
                        .then(data=>{
                            myDrugs = sortByExpiryDate(data.drugs || []);
                            renderMyDrugsList();
                            const newDrug = myDrugs.find(d => d.id === drugId);
                            if (newDrug) {
                                toggleDrugSelection('my', drugId, drugName, newDrug.quantity, expiryDate, USER_ID);
                                document.getElementById('exchangeDualView').style.display = 'block';
                                loadDrugsForExchange();
                            } else {
                                showToast('این دارو در لیست داروهای من موجود نیست', 'error');
                            }
                        })
                        .catch(()=> showToast('❌ خطا در دریافت داروهای من', 'error'));
                    return;
                }
            } else {
                if (selectedTargetPharmacy === null) {
                    selectedTargetPharmacy = pharmacyId;
                    selectedTargetPharmacyName = pharmacyName;
                } else if (selectedTargetPharmacy !== pharmacyId) {
                    showToast('❌ شما نمی‌توانید از دو داروخانه مختلف انتخاب کنید.', 'error');
                    return;
                }
                const drug = targetDrugs.find(d => d.id === drugId);
                if (drug) {
                    toggleDrugSelection('target', drugId, drugName, drug.quantity, expiryDate, pharmacyId);
                    document.getElementById('exchangeDualView').style.display = 'block';
                    loadDrugsForExchange();
                } else {
                    fetch('/api/get_pharmacy_drugs?pharmacy_id=' + pharmacyId)
                        .then(r=>r.json())
                        .then(data=>{
                            targetDrugs = sortByExpiryDate(data.drugs || []);
                            renderTargetDrugsList();
                            const newDrug = targetDrugs.find(d => d.id === drugId);
                            if (newDrug) {
                                toggleDrugSelection('target', drugId, drugName, newDrug.quantity, expiryDate, pharmacyId);
                                document.getElementById('exchangeDualView').style.display = 'block';
                                loadDrugsForExchange();
                            } else {
                                showToast('این دارو در داروخانه هدف موجود نیست', 'error');
                            }
                        })
                        .catch(()=> showToast('❌ خطا در دریافت اطلاعات', 'error'));
                    return;
                }
            }
            renderExchangeAllDrugs();
        }

        function loadDrugsForExchange() {
            fetch('/api/get_my_drugs_for_exchange')
                .then(r=>r.json()).then(data=>{ myDrugs = sortByExpiryDate(data.drugs || []); renderMyDrugsList(); })
                .catch(()=> showToast('❌ خطا در دریافت داروهای من', 'error'));
            if (selectedTargetPharmacy) {
                fetch('/api/get_pharmacy_drugs_for_exchange?pharmacy_id=' + selectedTargetPharmacy)
                    .then(r=>r.json()).then(data=>{ targetDrugs = sortByExpiryDate(data.drugs || []); renderTargetDrugsList(); })
                    .catch(()=> showToast('❌ خطا در دریافت داروهای هدف', 'error'));
            } else { targetDrugs = []; renderTargetDrugsList(); }
            document.getElementById('exchangeDualView').style.display = 'block';
            renderSummary();
        }

        function renderMyDrugsList() {
            const container = document.getElementById('myDrugsList');
            if (myDrugs.length === 0) { container.innerHTML = '<div style="padding:20px;text-align:center;color:#999">هیچ دارویی موجود نیست</div>'; return; }
            let html = '';
            myDrugs.forEach(drug => {
                const isSelected = selectedItems.some(item => item.source === 'my' && item.id === drug.id);
                const status = getExpiryStatusText(drug.expiry_date);
                const safeName = drug.name.replace(/'/g, "\\\\'").replace(/"/g, '&quot;');
                html += '<div class="exchange-drug-item ' + (isSelected ? 'selected' : '') + '" onclick="toggleDrugSelection(\\'my\\', ' + drug.id + ', \\'' + safeName + '\\', ' + drug.quantity + ', \\'' + (drug.expiry_date || '') + '\\', ' + USER_ID + ')">';
                html += '<input type="checkbox" class="exchange-drug-check" ' + (isSelected ? 'checked' : '') + ' onchange="event.stopPropagation(); toggleDrugSelection(\\'my\\', ' + drug.id + ', \\'' + safeName + '\\', ' + drug.quantity + ', \\'' + (drug.expiry_date || '') + '\\', ' + USER_ID + ')">';
                html += '<div class="exchange-drug-info"><div class="exchange-drug-name">' + drug.name + '</div>';
                html += '<div class="exchange-drug-detail">📦 ' + drug.quantity + ' عدد | 📅 ' + (drug.expiry_date || 'نامشخص') + ' ' + status.text + '</div></div>';
                if (isSelected) {
                    const selectedItem = selectedItems.find(item => item.source === 'my' && item.id === drug.id);
                    const qty = selectedItem ? selectedItem.quantity : drug.quantity;
                    html += '<input type="number" class="exchange-qty-input" value="' + qty + '" min="1" max="' + drug.quantity + '" onchange="updateSelectedQuantity(\\'my\\', ' + drug.id + ', this.value)" onclick="event.stopPropagation()">';
                }
                html += '</div>';
            });
            container.innerHTML = html;
        }

        function renderTargetDrugsList() {
            const container = document.getElementById('targetDrugsList');
            if (!selectedTargetPharmacy) { container.innerHTML = '<div style="padding:20px;text-align:center;color:#999">ابتدا دارویی از داروخانه هدف انتخاب کنید</div>'; return; }
            if (targetDrugs.length === 0) { container.innerHTML = '<div style="padding:20px;text-align:center;color:#999">هیچ دارویی در داروخانه هدف موجود نیست</div>'; return; }
            let html = '';
            targetDrugs.forEach(drug => {
                const isSelected = selectedItems.some(item => item.source === 'target' && item.id === drug.id);
                const status = getExpiryStatusText(drug.expiry_date);
                const safeName = drug.name.replace(/'/g, "\\\\'").replace(/"/g, '&quot;');
                html += '<div class="exchange-drug-item ' + (isSelected ? 'selected' : '') + '" onclick="toggleDrugSelection(\\'target\\', ' + drug.id + ', \\'' + safeName + '\\', ' + drug.quantity + ', \\'' + (drug.expiry_date || '') + '\\', ' + selectedTargetPharmacy + ')">';
                html += '<input type="checkbox" class="exchange-drug-check" ' + (isSelected ? 'checked' : '') + ' onchange="event.stopPropagation(); toggleDrugSelection(\\'target\\', ' + drug.id + ', \\'' + safeName + '\\', ' + drug.quantity + ', \\'' + (drug.expiry_date || '') + '\\', ' + selectedTargetPharmacy + ')">';
                html += '<div class="exchange-drug-info"><div class="exchange-drug-name">' + drug.name + '</div>';
                html += '<div class="exchange-drug-detail">📦 ' + drug.quantity + ' عدد | 📅 ' + (drug.expiry_date || 'نامشخص') + ' ' + status.text + '</div></div>';
                if (isSelected) {
                    const selectedItem = selectedItems.find(item => item.source === 'target' && item.id === drug.id);
                    const qty = selectedItem ? selectedItem.quantity : drug.quantity;
                    html += '<input type="number" class="exchange-qty-input" value="' + qty + '" min="1" max="' + drug.quantity + '" onchange="updateSelectedQuantity(\\'target\\', ' + drug.id + ', this.value)" onclick="event.stopPropagation()">';
                }
                html += '</div>';
            });
            container.innerHTML = html;
        }

        function toggleDrugSelection(source, id, name, maxQty, expiryDate, pharmacyId) {
            const existingIndex = selectedItems.findIndex(item => item.source === source && item.id === id);
            if (existingIndex !== -1) {
                selectedItems.splice(existingIndex, 1);
            } else {
                selectedItems.push({ source: source, id: id, name: name, quantity: maxQty, max_quantity: maxQty, expiry_date: expiryDate, pharmacy_id: pharmacyId });
            }
            if (source === 'my') renderMyDrugsList();
            else renderTargetDrugsList();
            renderSummary();
            renderExchangeAllDrugs();
        }

        function updateSelectedQuantity(source, id, newQuantity) {
            const item = selectedItems.find(item => item.source === source && item.id === id);
            if (item) {
                let qty = parseInt(newQuantity);
                if (isNaN(qty)) qty = item.max_quantity;
                if (qty < 1) qty = 1;
                if (qty > item.max_quantity) qty = item.max_quantity;
                item.quantity = qty;
            }
            renderSummary();
            if (source === 'my') renderMyDrugsList();
            else renderTargetDrugsList();
            renderExchangeAllDrugs();
        }

        function switchToMyList() { document.getElementById('myListHeader').classList.add('active'); document.getElementById('targetListHeader').classList.remove('active'); }
        function switchToTargetList() { document.getElementById('targetListHeader').classList.add('active'); document.getElementById('myListHeader').classList.remove('active'); }

        function renderSummary() {
            const myItems = selectedItems.filter(item => item.source === 'my');
            const targetItems = selectedItems.filter(item => item.source === 'target');
            if (selectedItems.length === 0) { document.getElementById('summaryText').innerHTML = 'هیچ دارویی انتخاب نشده است'; return; }
            let html = '';
            if (myItems.length > 0) { html += '<strong>📦 داروهایی که می‌دهم:</strong><br>'; myItems.forEach(item => { html += '• ' + item.name + ' - ' + item.quantity + ' عدد (📅 ' + (item.expiry_date || 'نامشخص') + ')<br>'; }); }
            if (targetItems.length > 0) { html += '<br><strong>🏥 داروهایی که می‌گیرم (از ' + selectedTargetPharmacyName + '):</strong><br>'; targetItems.forEach(item => { html += '• ' + item.name + ' - ' + item.quantity + ' عدد (📅 ' + (item.expiry_date || 'نامشخص') + ')<br>'; }); }
            document.getElementById('summaryText').innerHTML = html;
        }

        function resetExchangeSelection() {
            selectedItems = [];
            selectedTargetPharmacy = null;
            selectedTargetPharmacyName = '';
            renderMyDrugsList();
            renderTargetDrugsList();
            renderSummary();
            renderExchangeAllDrugs();
            document.getElementById('exchangeDualView').style.display = 'none';
        }

        function confirmExchangeFinal() {
            const myItems = selectedItems.filter(item => item.source === 'my');
            const targetItems = selectedItems.filter(item => item.source === 'target');
            if (myItems.length === 0 && targetItems.length === 0) { showToast('هیچ دارویی برای تبادل انتخاب نشده است', 'error'); return; }
            if (!selectedTargetPharmacy) { showToast('لطفا داروخانه هدف را انتخاب کنید', 'error'); return; }
            let summary = '';
            if (myItems.length > 0) { summary += '📦 داروهایی که می‌دهم:\n'; myItems.forEach(i => summary += '- ' + i.name + ': ' + i.quantity + ' عدد\n'); }
            if (targetItems.length > 0) { summary += '\n🏥 داروهایی که می‌گیرم:\n'; targetItems.forEach(i => summary += '- ' + i.name + ': ' + i.quantity + ' عدد (از ' + selectedTargetPharmacyName + ')\n'); }
            if (!confirm('آیا از ارسال درخواست تبادل اطمینان دارید؟\n\n' + summary)) return;
            const data = { target_pharmacy_id: selectedTargetPharmacy, my_items: myItems, target_items: targetItems };
            fetch('/api/register_exchange', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache',
                    'Expires': '0'
                },
                body: JSON.stringify(data)
            })
            .then(r=>r.json())
            .then(res => {
                if (res.success) {
                    showToast('✅ درخواست تبادل با موفقیت ارسال شد', 'success');
                    resetExchangeSelection();
                    loadDrugsForExchange();
                    loadExchanges();
                    loadPendingExchanges();
                    loadExchangeAllDrugs();
                } else {
                    showToast('❌ خطا: ' + res.error, 'error');
                }
            })
            .catch(()=> showToast('❌ خطا در ارتباط با سرور', 'error'));
        }

        function loadExchanges() {
            fetch('/api/get_exchanges', {
                headers: {
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache',
                    'Expires': '0'
                }
            })
            .then(r => r.json())
            .then(data => {
                allMyExchanges = data.exchanges || [];
                renderMyExchangesList(allMyExchanges);
            })
            .catch(err => {
                showToast('❌ خطا در دریافت تبادلات', 'error');
            });
        }

        function loadPendingExchanges() {
            fetch('/api/get_pending_exchanges', {
                headers: {
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache',
                    'Expires': '0'
                }
            })
            .then(r=>r.json())
            .then(d=>{
                const exchanges = d.exchanges || [];
                if (exchanges.length === 0) {
                    document.getElementById('pendingExchangesList').innerHTML = '<p style="text-align:center;padding:30px;color:#999">هیچ تبادل دریافتی در انتظار تایید نیست</p>';
                    return;
                }
                let html = '';
                exchanges.forEach(ex => {
                    const date = new Date(ex.exchange_date + 'Z');
                    const myItems = ex.my_items_json ? JSON.parse(ex.my_items_json) : [];
                    const targetItems = ex.target_items_json ? JSON.parse(ex.target_items_json) : [];
                    const sourceName = ex.source_pharmacy_name || 'داروخانه';
                    html += '<div class="exchange-card"><div class="exchange-card-header"><h4>🏥 ' + sourceName + ' به شما پیشنهاد تبادل داده است</h4><div class="date">' + date.toLocaleDateString('fa-IR') + ' ' + date.toLocaleTimeString('fa-IR') + '</div></div>';
                    html += '<div class="exchange-card-body">';
                    if (targetItems.length > 0) {
                        html += '<div class="exchange-section"><div class="exchange-section-title" style="color:#dc3545;">📦 داروهایی که از شما درخواست کرده:</div><ul class="exchange-drug-list">';
                        html += targetItems.map(i => '<li><strong>' + i.name + '</strong> <span>' + i.quantity + ' عدد (انقضا: ' + (i.expiry_date || '-') + ')</span></li>').join('');
                        html += '</ul></div>';
                    }
                    if (myItems.length > 0) {
                        html += '<div class="exchange-section"><div class="exchange-section-title" style="color:#28a745;">📦 داروهایی که به شما می‌دهد:</div><ul class="exchange-drug-list">';
                        html += myItems.map(i => '<li><strong>' + i.name + '</strong> <span>' + i.quantity + ' عدد (انقضا: ' + (i.expiry_date || '-') + ')</span></li>').join('');
                        html += '</ul></div>';
                    }
                    html += '</div>';
                    html += '<div class="exchange-card-footer">';
                    html += '<button class="btn-success" onclick="confirmPendingExchange(' + ex.id + ')">✅ تایید تبادل</button>';
                    html += '<button class="btn-danger" onclick="rejectPendingExchange(' + ex.id + ')">❌ رد درخواست</button>';
                    html += '</div></div>';
                });
                document.getElementById('pendingExchangesList').innerHTML = html;
            })
            .catch(()=> showToast('❌ خطا در دریافت تبادلات', 'error'));
        }

        function filterMyExchanges() {
            const filter = document.getElementById('exchangePharmacyFilter').value.toLowerCase();
            const filtered = allMyExchanges.filter(ex => ex.buyer_name.toLowerCase().includes(filter));
            renderMyExchangesList(filtered);
        }

        function renderMyExchangesList(exchanges) {
            const container = document.getElementById('myExchangesList');
            if (!container) return;
            if (!exchanges || exchanges.length === 0) {
                container.innerHTML = '<p style="text-align:center;padding:30px;color:#999;">هیچ تبادلی ثبت نشده است</p>';
                return;
            }
            let html = '<div style="max-height:500px;overflow-y:auto;">';
            exchanges.forEach(function(ex) {
                const statusText = ex.status === 'confirmed' ? '✅ تایید شده' : '⏳ در انتظار';
                const statusColor = ex.status === 'confirmed' ? '#28a745' : '#ffc107';
                const date = new Date(ex.exchange_date + 'Z');
                let pharmacyName = ex.buyer_name || 'نامشخص';
                if (ex.source_pharmacy_id && ex.source_pharmacy_id != 1) {
                    pharmacyName = ex.source_pharmacy_name || pharmacyName;
                }
                html += '<div style="border:1px solid #e0e0e0;border-radius:8px;padding:12px;margin:8px 0;background:white;box-shadow:0 1px 3px rgba(0,0,0,0.05);">';
                html += '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">';
                html += '<div><strong style="font-size:14px;">💊 ' + ex.drug_name + '</strong>';
                html += '<span style="margin:0 8px;color:#666;">|</span>';
                html += '<span>📦 ' + ex.quantity + ' عدد</span></div>';
                html += '<div><span style="background:' + statusColor + ';color:white;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:bold;">' + statusText + '</span></div>';
                html += '</div>';
                html += '<div style="font-size:12px;color:#999;margin-top:6px;display:flex;gap:12px;flex-wrap:wrap;">';
                html += '<span>🏥 ' + pharmacyName + '</span>';
                html += '<span>📅 ' + date.toLocaleDateString('fa-IR') + ' ' + date.toLocaleTimeString('fa-IR') + '</span>';
                if (ex.expiry_date) {
                    html += '<span>📅 انقضا: ' + ex.expiry_date + '</span>';
                }
                html += '</div>';
                if (ex.status === 'pending') {
                    html += '<div style="margin-top:8px;">';
                    html += '<button onclick="cancelExchange(' + ex.id + ')" class="btn-danger btn-sm" style="font-size:11px;padding:2px 8px;">❌ لغو درخواست</button>';
                    html += '</div>';
                }
                html += '</div>';
            });
            html += '</div>';
            container.innerHTML = html;
        }

        function cancelExchange(exchangeId) {
            if (!confirm('آیا از لغو این درخواست تبادل اطمینان دارید؟')) return;
            fetch('/api/reject_exchange/' + exchangeId, { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        showToast('✅ درخواست تبادل لغو شد', 'success');
                        loadExchanges();
                        loadPendingExchanges();
                    } else {
                        showToast('❌ خطا: ' + data.error, 'error');
                    }
                })
                .catch(() => showToast('❌ خطا در ارتباط با سرور', 'error'));
        }

        function confirmPendingExchange(exchangeId) {
            if (confirm('آیا از تایید این تبادل اطمینان دارید؟')) {
                fetch('/api/confirm_exchange/' + exchangeId, { method: 'POST' }).then(r=>r.json()).then(data=>{
                    if (data.success) {
                        showToast('✅ تبادل با موفقیت تایید شد', 'success');
                        loadPendingExchanges();
                        loadExchanges();
                    } else {
                        showToast('❌ خطا: ' + data.error, 'error');
                    }
                }).catch(()=> showToast('❌ خطا در ارتباط با سرور', 'error'));
            }
        }

        function rejectPendingExchange(exchangeId) {
            if (confirm('آیا از رد این تبادل اطمینان دارید؟')) {
                fetch('/api/reject_exchange/' + exchangeId, { method: 'POST' }).then(r=>r.json()).then(data=>{
                    if (data.success) {
                        showToast('✅ درخواست تبادل رد شد', 'success');
                        loadPendingExchanges();
                    } else {
                        showToast('❌ خطا: ' + data.error, 'error');
                    }
                }).catch(()=> showToast('❌ خطا در ارتباط با سرور', 'error'));
            }
        }

        function showExchangeTab(tab) {
            document.querySelectorAll('#registerTab, #listTab, #pendingTab').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.exchange-tab button').forEach(btn => btn.classList.remove('active'));
            if (tab === 'register') {
                document.getElementById('registerTab').classList.add('active');
                document.querySelector('.exchange-tab button:first-child').classList.add('active');
                loadExchangeAllDrugs();
            } else if (tab === 'list') {
                document.getElementById('listTab').classList.add('active');
                document.querySelector('.exchange-tab button:nth-child(2)').classList.add('active');
                loadExchanges();
            } else {
                document.getElementById('pendingTab').classList.add('active');
                document.querySelector('.exchange-tab button:nth-child(3)').classList.add('active');
                loadPendingExchanges();
            }
        }

        loadUserCategories();
        loadExchanges();
        loadPendingExchanges();
        loadExchangeAllDrugs();
        </script>
        `;

        res.render('layout', {
            content,
            pageTitle: '🔄 تبادل دارو',
            session: req.session
        });
    } catch (err) {
        console.error(err);
        res.status(500).send('خطا در بارگذاری صفحه تبادل');
    }
});

// ===== Deficit =====
app.get('/deficit', loginRequired, (req, res) => {
    const content = `
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
    const USER_ID = ${req.session.userId};

    function showToast(message, type) {
        const toast = document.getElementById('toast');
        toast.textContent = message;
        toast.className = 'toast-message ' + (type || 'info');
        toast.style.display = 'block';
        setTimeout(() => { toast.style.display = 'none'; }, 3000);
    }

    function searchDrugs(query) {
        const suggestions = document.getElementById('suggestions');
        if (query.length < 1) { suggestions.style.display = 'none'; return; }
        fetch('/api/search_with_stock?q=' + encodeURIComponent(query))
            .then(r => r.json())
            .then(data => {
                let html = '';
                if (data.length > 0) {
                    data.forEach(drug => {
                        const totalStock = drug.warehouse_qty + drug.pharmacy_qty;
                        let stockStatus = '';
                        if (totalStock > 0) {
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
                        if (drug.nearest_expiry && drug.nearest_expiry !== '-') {
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
        const name = document.getElementById('drugName').value.trim();
        const qty = document.getElementById('qty').value;
        const type = document.getElementById('type').value;
        const priority = document.getElementById('priority').value;
        if (!name) { showToast('❌ لطفاً نام دارو را وارد کنید', 'error'); return; }
        if (!qty || parseInt(qty) <= 0) { showToast('❌ تعداد معتبر وارد کنید', 'error'); return; }
        fetch('/api/add_drug', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, quantity: parseInt(qty), type: type, priority: parseInt(priority) })
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
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
        if (allDrugs.length === 0) {
            document.getElementById('list').innerHTML = '<p style="text-align:center;padding:30px;color:#999">لیست کسری خالی است</p>';
            return;
        }
        let html = '<table class="deficit-table"><thead><tr><th><input type="checkbox" id="selectAll" onchange="toggleSelectAll(this)"></th><th>نام دارو</th><th>تعداد</th><th>نوع</th><th>اولویت</th><th>عملیات</th></tr></thead><tbody>';
        allDrugs.forEach(d => {
            const typeText = d.type === 'quota' ? '<span style="color:#28a745">سهمیه ای</span>' : '<span style="color:#17a2b8">عادی</span>';
            html += '<tr data-id="' + d.id + '">';
            html += '<td><input type="checkbox" class="drug-checkbox" data-id="' + d.id + '"></td>';
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
        const ids = [];
        document.querySelectorAll('.drug-checkbox:checked').forEach(cb => {
            ids.push(parseInt(cb.dataset.id));
        });
        return ids;
    }

    function deleteSelectedDrugs() {
        const ids = getSelectedDrugIds();
        if (ids.length === 0) { showToast('حداقل یک دارو را انتخاب کنید', 'error'); return; }
        if (confirm(ids.length + ' دارو حذف شود؟')) {
            fetch('/api/delete_drugs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ drug_ids: ids })
            }).then(r=>r.json()).then(data => {
                if (data.success) { showToast('✅ داروها حذف شدند', 'success'); loadDrugs(); }
                else { showToast('خطا: ' + data.error, 'error'); }
            }).catch(() => showToast('❌ خطا در ارتباط با سرور', 'error'));
        }
    }

    function del(id) {
        if (confirm('حذف شود؟')) fetch('/api/delete_drug/' + id, { method: 'POST' }).then(() => loadDrugs()).catch(() => showToast('❌ خطا', 'error'));
    }

    document.addEventListener('click', function(e) {
        if (!e.target.closest('.search-container')) {
            document.getElementById('suggestions').style.display = 'none';
        }
    });

    loadDrugs();
    </script>
    `;

    res.render('layout', {
        content,
        pageTitle: '📋 دفتر کسری',
        session: req.session
    });
});

// ===== Admin Panel =====
app.get('/admin', adminRequired, async (req, res) => {
    try {
        const totalUsers = await dbManager.get('SELECT COUNT(*) as count FROM users');
        const pendingUsers = await dbManager.get('SELECT COUNT(*) as count FROM users WHERE is_approved = 0');
        const totalDrugs = await dbManager.get('SELECT COUNT(*) as count FROM drugs');
        const totalInventory = await dbManager.get('SELECT SUM(quantity) as total FROM inventory');

        const users = await dbManager.all('SELECT * FROM users ORDER BY created_at DESC');
        const interviews = await dbManager.all('SELECT * FROM interviews ORDER BY created_at DESC');
        const announcements = await dbManager.all('SELECT * FROM announcements ORDER BY created_at DESC');

        let usersHtml = '';
        for (const u of users) {
            let statusBadge = '';
            if (u.username === 'admin') {
                statusBadge = '<span class="badge badge-danger">ادمین</span>';
            } else {
                const isApproved = u.is_approved !== undefined ? u.is_approved : 1;
                if (isApproved === 0) {
                    statusBadge = '<span class="badge badge-warning">⏳ در انتظار تأیید</span>';
                } else if (isApproved === 2) {
                    statusBadge = '<span class="badge badge-danger">❌ رد شده</span>';
                } else if (u.is_full_user) {
                    statusBadge = '<span class="badge badge-success">کاربر کامل</span>';
                } else {
                    statusBadge = '<span class="badge badge-info">کاربر عادی</span>';
                }
            }

            let actions = '';
            if (u.username !== 'admin') {
                const isApproved = u.is_approved !== undefined ? u.is_approved : 1;
                if (isApproved === 0) {
                    actions += `<button onclick="approveUser(${u.id})" class="btn-success btn-sm">✅ تأیید</button> `;
                    actions += `<button onclick="rejectUser(${u.id})" class="btn-danger btn-sm">❌ رد</button> `;
                }
                actions += `<button onclick="deleteUser(${u.id})" class="btn-danger btn-sm">🗑️</button>`;
            } else {
                actions = '<span style="color:#999;font-size:11px;">غیرقابل حذف</span>';
            }

            const phone = u.phone_number || '-';
            const addr = u.address || '-';

            usersHtml += `
            <tr>
                <td>${u.id}</td>
                <td><strong>${u.username}</strong></td>
                <td>${u.pharmacy_display_name}</td>
                <td>${phone}</td>
                <td>${addr}</td>
                <td>${statusBadge}</td>
                <td>${u.created_at.slice(0, 10)}</td>
                <td>${actions}</td>
            </tr>
            `;
        }

        let interviewsHtml = '';
        for (const i of interviews) {
            const status = i.is_published ? '✅ منتشر شده' : '⏳ پیش‌نویس';
            const statusClass = i.is_published ? 'badge-success' : 'badge-warning';
            interviewsHtml += `
            <tr>
                <td>${i.id}</td>
                <td><strong>${i.title}</strong></td>
                <td>${i.pharmacist_name}</td>
                <td>${i.pharmacy_name}</td>
                <td><span class="badge ${statusClass}">${status}</span></td>
                <td>${i.created_at.slice(0, 10)}</td>
                <td>
                    <button onclick="toggleInterview(${i.id})" class="btn-warning btn-sm">${i.is_published ? '🔒 غیرفعال' : '✅ فعال'}</button>
                    <button onclick="deleteInterview(${i.id})" class="btn-danger btn-sm">🗑️</button>
                </td>
            </tr>
            `;
        }

        let announcementsHtml = '';
        for (const a of announcements) {
            const status = a.is_active ? '✅ فعال' : '⏳ غیرفعال';
            const statusClass = a.is_active ? 'badge-success' : 'badge-warning';
            announcementsHtml += `
            <tr>
                <td>${a.id}</td>
                <td><strong>${a.title}</strong></td>
                <td>${a.content.slice(0, 50)}${a.content.length > 50 ? '...' : ''}</td>
                <td><span class="badge ${statusClass}">${status}</span></td>
                <td>${a.created_at.slice(0, 10)}</td>
                <td>
                    <button onclick="toggleAnnouncement(${a.id})" class="btn-warning btn-sm">${a.is_active ? '🔒 غیرفعال' : '✅ فعال'}</button>
                    <button onclick="deleteAnnouncement(${a.id})" class="btn-danger btn-sm">🗑️</button>
                </td>
            </tr>
            `;
        }

        const content = `
        <div class="stats-grid">
            <div class="stat-card"><div class="number">${totalUsers.count}</div><div class="label">👤 کل کاربران</div></div>
            <div class="stat-card"><div class="number">${pendingUsers.count}</div><div class="label" style="color:#856404;">⏳ در انتظار تأیید</div></div>
            <div class="stat-card"><div class="number">${totalDrugs.count}</div><div class="label">💊 داروهای کسری</div></div>
            <div class="stat-card"><div class="number">${totalInventory.total || 0}</div><div class="label">📦 موجودی انبار</div></div>
        </div>

        <div class="card">
            <div class="card-title">👤 مدیریت کاربران</div>
            <div class="table-responsive">
                <table>
                    <thead><tr><th>#</th><th>نام کاربری</th><th>نام داروخانه</th><th>شماره همراه</th><th>آدرس</th><th>وضعیت</th><th>تاریخ ثبت</th><th>عملیات</th></tr></thead>
                    <tbody>${usersHtml}</tbody>
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
                    <tbody>${interviewsHtml}</tbody>
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
                    <tbody>${announcementsHtml}</tbody>
                </table>
            </div>
        </div>

        <script>
        function showToast(message, type) {
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.className = 'toast-message ' + (type || 'info');
            toast.style.display = 'block';
            setTimeout(() => { toast.style.display = 'none'; }, 3000);
        }

        function approveUser(id) {
            if (confirm('آیا از تأیید این کاربر اطمینان دارید؟')) {
                fetch('/admin/approve_user/' + id, { method: 'POST' }).then(r => r.json()).then(data => {
                    if (data.success) { showToast('✅ کاربر تأیید شد', 'success'); location.reload(); }
                    else { showToast('❌ خطا: ' + data.error, 'error'); }
                }).catch(() => showToast('❌ خطا در ارتباط با سرور', 'error'));
            }
        }

        function rejectUser(id) {
            if (confirm('آیا از رد این کاربر اطمینان دارید؟')) {
                fetch('/admin/reject_user/' + id, { method: 'POST' }).then(r => r.json()).then(data => {
                    if (data.success) { showToast('✅ کاربر رد شد', 'success'); location.reload(); }
                    else { showToast('❌ خطا: ' + data.error, 'error'); }
                }).catch(() => showToast('❌ خطا در ارتباط با سرور', 'error'));
            }
        }

        function deleteUser(id) {
            if (confirm('آیا از حذف این کاربر اطمینان دارید؟')) {
                fetch('/admin/delete_user/' + id, { method: 'POST' }).then(r => r.json()).then(data => {
                    if (data.success) { showToast('✅ کاربر حذف شد', 'success'); location.reload(); }
                    else { showToast('❌ خطا: ' + data.error, 'error'); }
                }).catch(() => showToast('❌ خطا در ارتباط با سرور', 'error'));
            }
        }

        function toggleInterview(id) {
            fetch('/admin/toggle_interview/' + id, { method: 'POST' }).then(r => r.json()).then(data => {
                if (data.success) location.reload();
                else showToast('❌ خطا: ' + data.error, 'error');
            }).catch(() => showToast('❌ خطا در ارتباط با سرور', 'error'));
        }

        function deleteInterview(id) {
            if (confirm('آیا از حذف این مصاحبه اطمینان دارید؟')) {
                fetch('/admin/delete_interview/' + id, { method: 'POST' }).then(r => r.json()).then(data => {
                    if (data.success) { showToast('✅ مصاحبه حذف شد', 'success'); location.reload(); }
                    else { showToast('❌ خطا: ' + data.error, 'error'); }
                }).catch(() => showToast('❌ خطا در ارتباط با سرور', 'error'));
            }
        }

        function toggleAnnouncement(id) {
            fetch('/admin/toggle_announcement/' + id, { method: 'POST' }).then(r => r.json()).then(data => {
                if (data.success) location.reload();
                else showToast('❌ خطا: ' + data.error, 'error');
            }).catch(() => showToast('❌ خطا در ارتباط با سرور', 'error'));
        }

        function deleteAnnouncement(id) {
            if (confirm('آیا از حذف این اطلاعیه اطمینان دارید؟')) {
                fetch('/admin/delete_announcement/' + id, { method: 'POST' }).then(r => r.json()).then(data => {
                    if (data.success) { showToast('✅ اطلاعیه حذف شد', 'success'); location.reload(); }
                    else { showToast('❌ خطا: ' + data.error, 'error'); }
                }).catch(() => showToast('❌ خطا در ارتباط با سرور', 'error'));
            }
        }
        </script>
        `;

        res.render('layout', {
            content,
            pageTitle: '👑 پنل ادمین',
            session: req.session
        });
    } catch (err) {
        console.error(err);
        res.status(500).send('خطا در بارگذاری پنل ادمین');
    }
});

// ===== Admin API Routes =====
app.post('/admin/approve_user/:userId', adminRequired, async (req, res) => {
    try {
        const { userId } = req.params;
        await dbManager.run('UPDATE users SET is_approved = 1 WHERE id = ? AND username != "admin"', [userId]);
        res.json({ success: true });
    } catch (err) {
        console.error(err);
        res.json({ success: false, error: err.message });
    }
});

app.post('/admin/reject_user/:userId', adminRequired, async (req, res) => {
    try {
        const { userId } = req.params;
        await dbManager.run('UPDATE users SET is_approved = 2 WHERE id = ? AND username != "admin"', [userId]);
        res.json({ success: true });
    } catch (err) {
        console.error(err);
        res.json({ success: false, error: err.message });
    }
});

app.post('/admin/delete_user/:userId', adminRequired, async (req, res) => {
    try {
        const { userId } = req.params;
        const user = await dbManager.get('SELECT username FROM users WHERE id = ?', [userId]);
        if (!user) return res.json({ success: false, error: 'کاربر یافت نشد' });
        if (user.username === 'admin') return res.json({ success: false, error: 'نمی‌توان ادمین را حذف کرد' });

        await dbManager.run('DELETE FROM users WHERE id = ?', [userId]);
        await dbManager.run('DELETE FROM drugs WHERE user_id = ?', [userId]);
        await dbManager.run('DELETE FROM inventory WHERE user_id = ?', [userId]);
        await dbManager.run('DELETE FROM orders WHERE user_id = ?', [userId]);
        await dbManager.run('DELETE FROM sales WHERE user_id = ?', [userId]);
        await dbManager.run('DELETE FROM exchanges WHERE user_id = ?', [userId]);
        await dbManager.run('DELETE FROM user_categories WHERE user_id = ?', [userId]);
        await dbManager.run('DELETE FROM hidden_items WHERE user_id = ?', [userId]);

        res.json({ success: true });
    } catch (err) {
        console.error(err);
        res.json({ success: false, error: err.message });
    }
});

app.post('/admin/add_interview', adminRequired, async (req, res) => {
    try {
        const { pharmacist_name, pharmacy_name, title, content, image_url, audio_url } = req.body;
        if (!pharmacist_name || !pharmacy_name || !title || !content) {
            return res.status(400).send('❌ همه فیلدها اجباری هستند');
        }
        await dbManager.run(
            'INSERT INTO interviews (pharmacist_name, pharmacy_name, title, content, image_url, audio_url, created_at, is_published) VALUES (?, ?, ?, ?, ?, ?, ?, 1)',
            [pharmacist_name, pharmacy_name, title, content, image_url || '', audio_url || '', new Date().toISOString()]
        );
        res.redirect('/admin');
    } catch (err) {
        console.error(err);
        res.status(500).send('خطا در افزودن مصاحبه');
    }
});

app.post('/admin/toggle_interview/:id', adminRequired, async (req, res) => {
    try {
        const { id } = req.params;
        const interview = await dbManager.get('SELECT is_published FROM interviews WHERE id = ?', [id]);
        if (!interview) return res.json({ success: false, error: 'مصاحبه یافت نشد' });
        const newStatus = interview.is_published ? 0 : 1;
        await dbManager.run('UPDATE interviews SET is_published = ? WHERE id = ?', [newStatus, id]);
        res.json({ success: true });
    } catch (err) {
        console.error(err);
        res.json({ success: false, error: err.message });
    }
});

app.post('/admin/delete_interview/:id', adminRequired, async (req, res) => {
    try {
        const { id } = req.params;
        await dbManager.run('DELETE FROM interviews WHERE id = ?', [id]);
        res.json({ success: true });
    } catch (err) {
        console.error(err);
        res.json({ success: false, error: err.message });
    }
});

app.post('/admin/add_announcement', adminRequired, async (req, res) => {
    try {
        const { title, content } = req.body;
        if (!title || !content) return res.status(400).send('❌ همه فیلدها اجباری هستند');
        await dbManager.run(
            'INSERT INTO announcements (title, content, created_at, is_active) VALUES (?, ?, ?, 1)',
            [title, content, new Date().toISOString()]
        );
        res.redirect('/admin');
    } catch (err) {
        console.error(err);
        res.status(500).send('خطا در افزودن اطلاعیه');
    }
});

app.post('/admin/toggle_announcement/:id', adminRequired, async (req, res) => {
    try {
        const { id } = req.params;
        const announcement = await dbManager.get('SELECT is_active FROM announcements WHERE id = ?', [id]);
        if (!announcement) return res.json({ success: false, error: 'اطلاعیه یافت نشد' });
        const newStatus = announcement.is_active ? 0 : 1;
        await dbManager.run('UPDATE announcements SET is_active = ? WHERE id = ?', [newStatus, id]);
        res.json({ success: true });
    } catch (err) {
        console.error(err);
        res.json({ success: false, error: err.message });
    }
});

app.post('/admin/delete_announcement/:id', adminRequired, async (req, res) => {
    try {
        const { id } = req.params;
        await dbManager.run('DELETE FROM announcements WHERE id = ?', [id]);
        res.json({ success: true });
    } catch (err) {
        console.error(err);
        res.json({ success: false, error: err.message });
    }
});

// ===== API Routes =====

app.get('/api/get_current_user', loginRequired, (req, res) => {
    const user = req.session.user;
    if (!user) return res.status(404).json({ error: 'user not found' });
    res.json({
        id: user.id,
        username: user.username,
        is_full_user: user.is_full_user,
        pharmacy_display_name: user.pharmacy_display_name,
        is_approved: user.is_approved || 1
    });
});

app.get('/api/get_drugs', loginRequired, async (req, res) => {
    try {
        const userId = req.session.userId;
        const drugs = await dbManager.all('SELECT * FROM drugs WHERE user_id = ? AND ordered = 0 ORDER BY priority ASC, created_at DESC', [userId]);
        res.json({ drugs });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/get_all_drugs', loginRequired, async (req, res) => {
    try {
        const userId = req.session.userId;
        const drugs = await dbManager.all('SELECT * FROM drugs WHERE user_id = ? ORDER BY created_at DESC', [userId]);
        res.json({ drugs });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/get_orders', loginRequired, async (req, res) => {
    try {
        const userId = req.session.userId;
        const orders = await dbManager.all('SELECT * FROM orders WHERE user_id = ? ORDER BY ordered_at DESC', [userId]);
        res.json({ orders });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/get_inventory', loginRequired, async (req, res) => {
    try {
        const userId = req.session.userId;
        const items = await dbManager.all('SELECT * FROM inventory WHERE user_id = ? AND quantity > 0 ORDER BY created_at DESC', [userId]);
        res.json({ items });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/get_pharmacy_drugs', loginRequired, async (req, res) => {
    try {
        const pharmacyId = req.query.pharmacy_id;
        if (!pharmacyId) return res.json({ drugs: [] });
        const drugs = await dbManager.all('SELECT id, name, quantity, expiry_date, location FROM inventory WHERE user_id = ? AND quantity > 0', [pharmacyId]);
        res.json({ drugs });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/get_all_pharmacies', loginRequired, async (req, res) => {
    try {
        const userId = req.session.userId;
        const pharmacies = await dbManager.all('SELECT id, pharmacy_display_name FROM users WHERE id != ? AND is_approved = 1', [userId]);
        const isPending = req.session.isApproved === 0;
        const result = pharmacies.map(p => ({
            id: p.id,
            name: isPending ? maskPharmacyName(p.pharmacy_display_name) : p.pharmacy_display_name
        }));
        res.json({ pharmacies: result });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

app.post('/api/delete_drug/:id', loginRequired, async (req, res) => {
    try {
        const userId = req.session.userId;
        const { id } = req.params;
        await dbManager.run('DELETE FROM drugs WHERE id = ? AND user_id = ?', [id, userId]);
        res.json({ success: true });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

app.post('/api/delete_drugs', loginRequired, async (req, res) => {
    try {
        const userId = req.session.userId;
        const { drug_ids } = req.body;
        if (!drug_ids || drug_ids.length === 0) {
            return res.json({ success: false, error: 'هیچ دارویی انتخاب نشده است' });
        }
        const placeholders = drug_ids.map(() => '?').join(',');
        await dbManager.run(`DELETE FROM drugs WHERE id IN (${placeholders}) AND user_id = ?`, [...drug_ids, userId]);
        res.json({ success: true });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

app.post('/api/delete_inventory_item/:id', loginRequired, async (req, res) => {
    try {
        const userId = req.session.userId;
        const { id } = req.params;
        await dbManager.run('DELETE FROM inventory WHERE id = ? AND user_id = ?', [id, userId]);
        res.json({ success: true });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

app.post('/api/delete_inventory_items', loginRequired, async (req, res) => {
    try {
        const userId = req.session.userId;
        const { item_ids } = req.body;
        if (!item_ids || item_ids.length === 0) {
            return res.json({ success: false, error: 'هیچ آیتمی انتخاب نشده است' });
        }
        const placeholders = item_ids.map(() => '?').join(',');
        await dbManager.run(`DELETE FROM inventory WHERE id IN (${placeholders}) AND user_id = ?`, [...item_ids, userId]);
        res.json({ success: true });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

app.post('/api/register_sale', loginRequired, async (req, res) => {
    try {
        const userId = req.session.userId;
        const { drug_name, quantity, expiry_date, sale_date, customer_name, price, location } = req.body;

        if (!drug_name || !quantity || !expiry_date) {
            return res.json({ success: false, error: 'نام دارو، تعداد و تاریخ انقضا اجباری است' });
        }
        if (!validateExpiryDate(expiry_date)) {
            return res.json({ success: false, error: 'فرمت تاریخ انقضا نامعتبر است' });
        }

        const items = await dbManager.all(
            'SELECT * FROM inventory WHERE user_id = ? AND name = ? AND location = ? AND expiry_date = ?',
            [userId, drug_name, location || 'pharmacy', expiry_date]
        );

        const totalAvailable = items.reduce((sum, i) => sum + i.quantity, 0);
        if (totalAvailable < quantity) {
            return res.json({ success: false, error: `موجودی دارو کافی نیست. فقط ${totalAvailable} عدد موجود است` });
        }

        let remaining = quantity;
        for (const item of items) {
            if (remaining <= 0) break;
            const take = Math.min(item.quantity, remaining);
            if (take > 0) {
                await dbManager.run('UPDATE inventory SET quantity = quantity - ? WHERE id = ?', [take, item.id]);
                if (item.quantity - take === 0) {
                    await dbManager.run('DELETE FROM inventory WHERE id = ?', [item.id]);
                }
                remaining -= take;
            }
        }

        await dbManager.run(
            'INSERT INTO sales (user_id, drug_name, quantity, sale_date, expiry_date, customer_name, price, location, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            [userId, drug_name, quantity, sale_date || null, expiry_date, customer_name || '', price || 0, location || 'pharmacy', new Date().toISOString()]
        );

        res.json({ success: true });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

app.post('/api/add_drug', loginRequired, async (req, res) => {
    try {
        const userId = req.session.userId;
        const { name, quantity, type, priority } = req.body;

        if (!name || !name.trim()) {
            return res.json({ success: false, error: 'نام دارو را وارد کنید' });
        }
        if (!quantity || quantity <= 0) {
            return res.json({ success: false, error: 'تعداد معتبر وارد کنید' });
        }

        await dbManager.run(
            'INSERT INTO drugs (user_id, name, quantity, type, priority, created_at, ordered) VALUES (?, ?, ?, ?, ?, ?, ?)',
            [userId, name.trim(), quantity, type || 'normal', priority || 4, new Date().toISOString(), 0]
        );

        res.json({ success: true });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

app.post('/api/place_order', loginRequired, async (req, res) => {
    try {
        const userId = req.session.userId;
        const { selected_ids, company, quantities } = req.body;

        if (!selected_ids || selected_ids.length === 0) {
            return res.json({ success: false, error: 'هیچ دارویی انتخاب نشده است' });
        }

        for (const drugId of selected_ids) {
            const drug = await dbManager.get('SELECT * FROM drugs WHERE id = ? AND user_id = ?', [drugId, userId]);
            if (drug) {
                const qty = quantities ? parseInt(quantities[String(drugId)]) || drug.quantity : drug.quantity;
                await dbManager.run(
                    'INSERT INTO orders (user_id, company, drug_name, quantity, ordered_at) VALUES (?, ?, ?, ?, ?)',
                    [userId, company, drug.name, qty, new Date().toISOString()]
                );
                if (drug.type !== 'quota') {
                    await dbManager.run('UPDATE drugs SET ordered = 1 WHERE id = ?', [drugId]);
                }
            }
        }

        await dbManager.run("DELETE FROM drugs WHERE ordered = 1 AND user_id = ? AND type != 'quota'", [userId]);

        res.json({ success: true });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/search_with_stock', loginRequired, async (req, res) => {
    try {
        const userId = req.session.userId;
        const q = req.query.q || '';

        const names = await dbManager.all(
            'SELECT DISTINCT name FROM inventory WHERE user_id = ? AND name LIKE ? LIMIT 10',
            [userId, `%${q}%`]
        );

        const result = [];
        for (const row of names) {
            const name = row.name;
            const warehouse = await dbManager.get(
                'SELECT SUM(quantity) as total FROM inventory WHERE user_id = ? AND name = ? AND location = "warehouse"',
                [userId, name]
            );
            const pharmacy = await dbManager.get(
                'SELECT SUM(quantity) as total FROM inventory WHERE user_id = ? AND name = ? AND location = "pharmacy"',
                [userId, name]
            );
            const nearest = await dbManager.get(
                'SELECT expiry_date FROM inventory WHERE user_id = ? AND name = ? AND expiry_date IS NOT NULL AND expiry_date != "" ORDER BY expiry_date ASC LIMIT 1',
                [userId, name]
            );
            result.push({
                name: name,
                warehouse_qty: warehouse.total || 0,
                pharmacy_qty: pharmacy.total || 0,
                nearest_expiry: nearest ? nearest.expiry_date : '-'
            });
        }

        res.json(result);
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/get_inventory_grouped_by_expiry', loginRequired, async (req, res) => {
    try {
        const userId = req.session.userId;

        const hidden = await dbManager.all('SELECT item_id FROM hidden_items WHERE user_id = ?', [userId]);
        const hiddenIds = hidden.map(row => row.item_id);

        const items = await dbManager.all(
            `SELECT id, name, quantity, expiry_date, location, created_at
             FROM inventory
             WHERE user_id = ? AND quantity > 0
             ORDER BY
                 CASE WHEN expiry_date IS NULL OR expiry_date = '' THEN 1 ELSE 0 END,
                 substr(expiry_date, 1, 4) ASC,
                 substr(expiry_date, 6, 2) ASC`,
            [userId]
        );

        const user = await dbManager.get('SELECT pharmacy_display_name FROM users WHERE id = ?', [userId]);
        const pharmacyName = user ? user.pharmacy_display_name : 'داروخانه من';

        const expiryGroups = {};
        for (const item of items) {
            const expiry = item.expiry_date || 'نامشخص';
            if (!expiryGroups[expiry]) expiryGroups[expiry] = [];
            expiryGroups[expiry].push(item);
        }

        const result = [];
        for (const [expiryDate, drugs] of Object.entries(expiryGroups)) {
            drugs.sort((a, b) => (a.created_at || '').localeCompare(b.created_at || ''));
            const pharmacies = [{
                pharmacy_id: userId,
                pharmacy_name: pharmacyName,
                last_update: drugs[0] && drugs[0].created_at ? convertDateToJalali(drugs[0].created_at) : '',
                drugs: drugs.map(d => ({
                    id: d.id,
                    name: d.name,
                    quantity: d.quantity,
                    expiry_date: d.expiry_date,
                    location: d.location,
                    location_text: d.location === 'warehouse' ? 'انبار' : 'داروخانه',
                    hidden: hiddenIds.includes(d.id)
                }))
            }];
            result.push({
                expiry_date: expiryDate,
                status_text: getExpiryStatus(expiryDate).text,
                pharmacies: pharmacies
            });
        }

        result.sort((a, b) => parseExpiryNumber(a.expiry_date) - parseExpiryNumber(b.expiry_date));

        res.json({ data: result });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/get_all_pharmacies_drugs_grouped_by_expiry', loginRequired, async (req, res) => {
    try {
        const userId = req.session.userId;

        const hidden = await dbManager.all('SELECT item_id FROM hidden_items WHERE user_id = ?', [userId]);
        const hiddenIds = hidden.map(row => row.item_id);

        const otherPharmacies = await dbManager.all(
            'SELECT id, pharmacy_display_name FROM users WHERE id != ? AND is_approved = 1',
            [userId]
        );

        const myUser = await dbManager.get('SELECT pharmacy_display_name FROM users WHERE id = ?', [userId]);
        const myPharmacyName = myUser ? myUser.pharmacy_display_name : 'داروخانه من';

        const allPharmacies = [{ id: userId, pharmacy_display_name: myPharmacyName }, ...otherPharmacies];

        const expiryGroups = {};

        for (const ph of allPharmacies) {
            const drugs = await dbManager.all(
                'SELECT id, name, quantity, expiry_date, location, created_at FROM inventory WHERE user_id = ? AND quantity > 0',
                [ph.id]
            );

            for (const drug of drugs) {
                if (ph.id === userId && hiddenIds.includes(drug.id)) continue;

                const expiry = drug.expiry_date || 'نامشخص';
                if (!expiryGroups[expiry]) expiryGroups[expiry] = {};
                if (!expiryGroups[expiry][ph.id]) {
                    expiryGroups[expiry][ph.id] = {
                        pharmacy_id: ph.id,
                        pharmacy_name: ph.pharmacy_display_name,
                        drugs: [],
                        last_update: ''
                    };
                }

                expiryGroups[expiry][ph.id].drugs.push({
                    id: drug.id,
                    name: drug.name,
                    quantity: drug.quantity,
                    expiry_date: drug.expiry_date,
                    location: drug.location,
                    hidden: hiddenIds.includes(drug.id)
                });

                if (drug.created_at && drug.created_at > expiryGroups[expiry][ph.id].last_update) {
                    expiryGroups[expiry][ph.id].last_update = convertDateToJalali(drug.created_at);
                }
            }
        }

        const result = [];
        for (const [expiryDate, pharmaciesDict] of Object.entries(expiryGroups)) {
            const pharmacies = Object.values(pharmaciesDict);
            pharmacies.sort((a, b) => (b.last_update || '').localeCompare(a.last_update || ''));
            result.push({
                expiry_date: expiryDate,
                status_text: getExpiryStatus(expiryDate).text,
                pharmacies: pharmacies
            });
        }

        result.sort((a, b) => parseExpiryNumber(a.expiry_date) - parseExpiryNumber(b.expiry_date));

        res.json({ data: result });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/get_my_drugs_for_exchange', loginRequired, async (req, res) => {
    try {
        const userId = req.session.userId;
        const drugs = await dbManager.all(
            'SELECT id, name, quantity, expiry_date, location FROM inventory WHERE user_id = ? AND quantity > 0',
            [userId]
        );
        res.json({ drugs });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/get_pharmacy_drugs_for_exchange', loginRequired, async (req, res) => {
    try {
        const pharmacyId = req.query.pharmacy_id;
        if (!pharmacyId) return res.json({ drugs: [] });
        const drugs = await dbManager.all(
            'SELECT id, name, quantity, expiry_date, location FROM inventory WHERE user_id = ? AND quantity > 0 ORDER BY name',
            [pharmacyId]
        );
        res.json({ drugs });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

app.post('/api/add_inventory', loginRequired, upload.none(), async (req, res) => {
    try {
        const userId = req.session.userId;
        const { name, quantity, expiry_date, location, supplier, purchase_price } = req.body;

        console.log(`🚀 add_inventory called by user_id=${userId}`);
        console.log(`📦 Data: name=${name}, qty=${quantity}, expiry=${expiry_date}, loc=${location}`);

        if (!name || !quantity || quantity <= 0 || !expiry_date) {
            return res.json({ success: false, error: 'نام، تعداد و تاریخ انقضا اجباری است' });
        }
        if (!validateExpiryDate(expiry_date)) {
            return res.json({ success: false, error: 'تاریخ انقضا نامعتبر است' });
        }

        const existing = await dbManager.get(
            'SELECT id, quantity FROM inventory WHERE user_id = ? AND name = ? AND expiry_date = ? AND location = ?',
            [userId, name, expiry_date, location || 'warehouse']
        );

        if (existing) {
            await dbManager.run('UPDATE inventory SET quantity = quantity + ? WHERE id = ?', [parseInt(quantity), existing.id]);
        } else {
            await dbManager.run(
                'INSERT INTO inventory (user_id, name, quantity, expiry_date, location, created_at, supplier, purchase_price) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                [userId, name, parseInt(quantity), expiry_date, location || 'warehouse', new Date().toISOString(), supplier || '', parseFloat(purchase_price) || 0]
            );
        }

        console.log(`✅ Successfully added/updated inventory for ${name}`);
        res.json({ success: true });
    } catch (err) {
        console.error('❌ Exception in add_inventory:', err);
        res.status(500).json({ success: false, error: err.message });
    }
});

app.post('/api/move_inventory', loginRequired, async (req, res) => {
    try {
        const userId = req.session.userId;
        const { name, quantity, from_location, to_location, expiry_date } = req.body;

        if (!name || !quantity || !expiry_date) {
            return res.json({ success: false, error: 'نام، تعداد و تاریخ انقضا اجباری است' });
        }
        if (!validateExpiryDate(expiry_date)) {
            return res.json({ success: false, error: 'تاریخ انقضا نامعتبر است' });
        }

        const sources = await dbManager.all(
            'SELECT * FROM inventory WHERE user_id = ? AND name = ? AND location = ? AND expiry_date = ?',
            [userId, name, from_location, expiry_date]
        );

        const totalAvailable = sources.reduce((sum, s) => sum + s.quantity, 0);
        if (totalAvailable < quantity) {
            return res.json({ success: false, error: `موجودی ناکافی. فقط ${totalAvailable} عدد موجود است` });
        }

        let remaining = quantity;
        for (const source of sources) {
            if (remaining <= 0) break;
            const take = Math.min(source.quantity, remaining);
            if (take > 0) {
                await dbManager.run('UPDATE inventory SET quantity = quantity - ? WHERE id = ?', [take, source.id]);
                if (source.quantity - take === 0) {
                    await dbManager.run('DELETE FROM inventory WHERE id = ?', [source.id]);
                }

                const dest = await dbManager.get(
                    'SELECT id FROM inventory WHERE user_id = ? AND name = ? AND expiry_date = ? AND location = ?',
                    [userId, name, expiry_date, to_location]
                );

                if (dest) {
                    await dbManager.run('UPDATE inventory SET quantity = quantity + ? WHERE id = ?', [take, dest.id]);
                } else {
                    await dbManager.run(
                        'INSERT INTO inventory (user_id, name, quantity, expiry_date, location, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                        [userId, name, take, expiry_date, to_location, new Date().toISOString()]
                    );
                }
                remaining -= take;
            }
        }

        res.json({ success: true });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

// ===== Exchange API =====
app.post('/api/register_exchange', loginRequired, async (req, res) => {
    try {
        const userId = req.session.userId;
        const { target_pharmacy_id, my_items, target_items } = req.body;

        if (!target_pharmacy_id) {
            return res.json({ success: false, error: 'Target pharmacy not selected' });
        }

        const userCat = await dbManager.get('SELECT categories FROM user_categories WHERE user_id = ?', [userId]);
        const senderCategories = (userCat && userCat.categories) ? userCat.categories : '';

        const sender = await dbManager.get('SELECT pharmacy_display_name FROM users WHERE id = ?', [userId]);
        const senderName = sender ? sender.pharmacy_display_name : 'My Pharmacy';

        const target = await dbManager.get('SELECT pharmacy_display_name FROM users WHERE id = ?', [target_pharmacy_id]);
        const targetName = target ? target.pharmacy_display_name : 'Target Pharmacy';

        const nowIran = dbManager.getIranTimeISO();

        if (target_items) {
            for (const item of target_items) {
                await dbManager.run(
                    `INSERT INTO exchanges (
                        user_id, buyer_name, drug_name, quantity, expiry_date, location,
                        exchange_date, status, target_pharmacy_id, sender_categories,
                        my_items_json, target_items_json, source_pharmacy_id, source_pharmacy_name
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?)`,
                    [
                        target_pharmacy_id, senderName, item.name, item.quantity,
                        item.expiry_date || '', 'pharmacy', nowIran, userId,
                        senderCategories, JSON.stringify(my_items), JSON.stringify(target_items),
                        userId, senderName
                    ]
                );
            }
        }

        if (my_items) {
            for (const item of my_items) {
                await dbManager.run(
                    `INSERT INTO exchanges (
                        user_id, buyer_name, drug_name, quantity, expiry_date, location,
                        exchange_date, status, target_pharmacy_id, sender_categories,
                        my_items_json, target_items_json, source_pharmacy_id, source_pharmacy_name
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?)`,
                    [
                        userId, targetName, item.name, item.quantity,
                        item.expiry_date || '', 'pharmacy', nowIran, target_pharmacy_id,
                        senderCategories, JSON.stringify(my_items), JSON.stringify(target_items),
                        userId, senderName
                    ]
                );
            }
        }

        res.json({ success: true });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/get_exchanges', loginRequired, async (req, res) => {
    try {
        const userId = req.session.userId;
        const exchanges = await dbManager.all(
            `SELECT * FROM exchanges
             WHERE user_id = ? OR target_pharmacy_id = ? OR source_pharmacy_id = ?
             ORDER BY exchange_date DESC`,
            [userId, userId, userId]
        );

        const result = exchanges.map(ex => {
            if (ex.exchange_date) {
                try {
                    const dt = new Date(ex.exchange_date);
                    const iranTime = new Date(dt.getTime() + 3.5 * 60 * 60 * 1000);
                    ex.exchange_date = iranTime.toISOString();
                } catch (e) {}
            }
            return ex;
        });

        res.json({ exchanges: result });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/get_pending_exchanges', loginRequired, async (req, res) => {
    try {
        const userId = req.session.userId;
        const exchanges = await dbManager.all(
            `SELECT * FROM exchanges
             WHERE (user_id = ? OR target_pharmacy_id = ?)
             AND status = 'pending'
             AND source_pharmacy_id IS NOT NULL
             AND source_pharmacy_id != ?
             ORDER BY exchange_date DESC`,
            [userId, userId, userId]
        );

        const result = exchanges.map(ex => {
            if (ex.exchange_date) {
                try {
                    const dt = new Date(ex.exchange_date);
                    const iranTime = new Date(dt.getTime() + 3.5 * 60 * 60 * 1000);
                    ex.exchange_date = iranTime.toISOString();
                } catch (e) {}
            }
            return ex;
        });

        res.json({ exchanges: result });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

app.post('/api/confirm_exchange/:id', loginRequired, async (req, res) => {
    try {
        const userId = req.session.userId;
        const { id } = req.params;

        const exchange = await dbManager.get(
            'SELECT * FROM exchanges WHERE id = ? AND user_id = ? AND status = "pending"',
            [id, userId]
        );

        if (!exchange) {
            return res.json({ success: false, error: 'تبادل یافت نشد یا قبلا پردازش شده است' });
        }

        if (exchange.source_pharmacy_id && exchange.source_pharmacy_id !== userId) {
            const targetItems = exchange.target_items_json ? JSON.parse(exchange.target_items_json) : [];
            const myItems = exchange.my_items_json ? JSON.parse(exchange.my_items_json) : [];

            for (const item of targetItems) {
                const drugName = item.name;
                const expiryDate = item.expiry_date || '';
                const quantity = item.quantity;

                const invItems = await dbManager.all(
                    'SELECT * FROM inventory WHERE user_id = ? AND name = ? AND expiry_date = ? AND quantity > 0',
                    [userId, drugName, expiryDate]
                );

                const totalAvailable = invItems.reduce((sum, i) => sum + i.quantity, 0);
                if (totalAvailable < quantity) {
                    return res.json({ success: false, error: `موجودی ${drugName} با تاریخ ${expiryDate} کافی نیست` });
                }

                let remaining = quantity;
                for (const invItem of invItems) {
                    if (remaining <= 0) break;
                    const take = Math.min(invItem.quantity, remaining);
                    const newQty = invItem.quantity - take;
                    if (newQty === 0) {
                        await dbManager.run('DELETE FROM inventory WHERE id = ?', [invItem.id]);
                    } else {
                        await dbManager.run('UPDATE inventory SET quantity = ? WHERE id = ?', [newQty, invItem.id]);
                    }
                    remaining -= take;
                }
            }

            for (const item of myItems) {
                const drugName = item.name;
                const expiryDate = item.expiry_date || '';
                const quantity = item.quantity;

                const invItem = await dbManager.get(
                    'SELECT * FROM inventory WHERE user_id = ? AND name = ? AND expiry_date = ? AND location = "pharmacy"',
                    [userId, drugName, expiryDate]
                );

                if (invItem) {
                    await dbManager.run('UPDATE inventory SET quantity = quantity + ? WHERE id = ?', [quantity, invItem.id]);
                } else {
                    await dbManager.run(
                        'INSERT INTO inventory (user_id, name, quantity, expiry_date, location, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                        [userId, drugName, quantity, expiryDate, 'pharmacy', dbManager.getIranTimeISO()]
                    );
                }
            }
        }

        await dbManager.run("UPDATE exchanges SET status = 'confirmed' WHERE id = ?", [id]);

        if (exchange.source_pharmacy_id) {
            await dbManager.run(
                "UPDATE exchanges SET status = 'confirmed' WHERE source_pharmacy_id = ? AND target_pharmacy_id = ? AND status = 'pending'",
                [exchange.source_pharmacy_id, userId]
            );
        }

        res.json({ success: true });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

app.post('/api/reject_exchange/:id', loginRequired, async (req, res) => {
    try {
        const userId = req.session.userId;
        const { id } = req.params;

        const exchange = await dbManager.get(
            'SELECT * FROM exchanges WHERE id = ? AND user_id = ? AND status = "pending"',
            [id, userId]
        );

        if (!exchange) {
            return res.json({ success: false, error: 'تبادل یافت نشد یا قبلا پردازش شده است' });
        }

        await dbManager.run('DELETE FROM exchanges WHERE id = ?', [id]);

        if (exchange.source_pharmacy_id) {
            await dbManager.run(
                "DELETE FROM exchanges WHERE source_pharmacy_id = ? AND target_pharmacy_id = ? AND status = 'pending'",
                [exchange.source_pharmacy_id, userId]
            );
        }

        res.json({ success: true });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/get_user_categories', loginRequired, async (req, res) => {
    try {
        const userId = req.session.userId;
        const row = await dbManager.get('SELECT categories FROM user_categories WHERE user_id = ?', [userId]);
        const categories = (row && row.categories) ? row.categories.split(',') : [];
        res.json({ categories });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

app.post('/api/save_user_categories', loginRequired, async (req, res) => {
    try {
        const userId = req.session.userId;
        const { categories } = req.body;
        const categoriesStr = categories.join(',');
        await dbManager.run(
            'INSERT OR REPLACE INTO user_categories (user_id, categories) VALUES (?, ?)',
            [userId, categoriesStr]
        );
        res.json({ success: true });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/get_hidden_items', loginRequired, async (req, res) => {
    try {
        const userId = req.session.userId;
        const rows = await dbManager.all('SELECT item_id FROM hidden_items WHERE user_id = ?', [userId]);
        res.json({ hidden_ids: rows.map(row => row.item_id) });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

app.post('/api/toggle_hidden_items', loginRequired, async (req, res) => {
    try {
        const userId = req.session.userId;
        const { item_ids, hidden } = req.body;

        if (!item_ids || item_ids.length === 0) {
            return res.json({ success: false, error: 'هیچ آیتمی انتخاب نشده است' });
        }

        if (hidden) {
            for (const itemId of item_ids) {
                await dbManager.run(
                    'INSERT OR IGNORE INTO hidden_items (user_id, item_id) VALUES (?, ?)',
                    [userId, itemId]
                );
            }
        } else {
            const placeholders = item_ids.map(() => '?').join(',');
            await dbManager.run(
                `DELETE FROM hidden_items WHERE user_id = ? AND item_id IN (${placeholders})`,
                [userId, ...item_ids]
            );
        }

        res.json({ success: true });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

// ===== Static Files =====
app.use('/uploads', express.static(UPLOAD_FOLDER));

// ===== Start Server =====
app.listen(PORT, '0.0.0.0', () => {
    console.log('=' .repeat(50));
    console.log('✅ داروخانه با موفقیت راه اندازی شد');
    console.log('=' .repeat(50));
    console.log(`🌐 آدرس: http://0.0.0.0:${PORT}`);
    console.log('👑 ادمین: admin / admin123');
    console.log('📝 کاربران نمونه:');
    console.log('   nosratabadi / admin123');
    console.log('   soleymani / soleymani123');
    console.log('   A101 / drsaboori');
    console.log('   A102 / drjafari');
    console.log('=' .repeat(50));
    console.log('⚠️ کاربران جدید پس از ثبت‌نام نیاز به تأیید ادمین دارند');
    console.log('=' .repeat(50));
});
