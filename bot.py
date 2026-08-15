# ============================================
# bot.py - سیستم مدیریت داروخانه با Django
# نسخه کامل - مرداد 1405
# ============================================

import os
import sys
import json
import re
import hashlib
import logging
from datetime import datetime, timedelta
from functools import wraps

# ===== تنظیم Django =====
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bot')
import django
from django.conf import settings
from django.core.management import execute_from_command_line

# ===== تنظیمات Django =====
if not settings.configured:
    settings.configure(
        SECRET_KEY='django-insecure-pharmacy-secret-key-2024',
        DEBUG=True,
        ALLOWED_HOSTS=['*'],
        INSTALLED_APPS=[
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'django.contrib.sessions',
            'django.contrib.messages',
            'django.contrib.staticfiles',
        ],
        MIDDLEWARE=[
            'django.middleware.security.SecurityMiddleware',
            'django.contrib.sessions.middleware.SessionMiddleware',
            'django.middleware.common.CommonMiddleware',
            'django.middleware.csrf.CsrfViewMiddleware',
            'django.contrib.auth.middleware.AuthenticationMiddleware',
            'django.contrib.messages.middleware.MessageMiddleware',
            'django.middleware.clickjacking.XFrameOptionsMiddleware',
        ],
        ROOT_URLCONF='bot',
        TEMPLATES=[{
            'BACKEND': 'django.template.backends.django.DjangoTemplates',
            'DIRS': [],
            'APP_DIRS': True,
            'OPTIONS': {
                'context_processors': [
                    'django.template.context_processors.debug',
                    'django.template.context_processors.request',
                    'django.contrib.auth.context_processors.auth',
                    'django.contrib.messages.context_processors.messages',
                ],
            },
        }],
        DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': 'pharmacy.db',
            }
        },
        LANGUAGE_CODE='fa-ir',
        TIME_ZONE='Asia/Tehran',
        USE_I18N=True,
        USE_TZ=True,
        STATIC_URL='/static/',
        DEFAULT_AUTO_FIELD='django.db.models.BigAutoField',
        LOGIN_URL='login',
        SESSION_ENGINE='django.contrib.sessions.backends.db',
        SESSION_COOKIE_AGE=86400,
        SESSION_EXPIRE_AT_BROWSER_CLOSE=False,
        CSRF_TRUSTED_ORIGINS=['http://localhost:8000', 'http://127.0.0.1:8000'],
        CSRF_COOKIE_SECURE=False,
    )

django.setup()

# ===== ایمپورت‌های Django =====
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.core.management import call_command

# ===== مدل‌ها =====
class User(AbstractUser):
    pharmacy_display_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    is_full_user = models.BooleanField(default=False)
    is_approved = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'users'
        app_label = 'bot'

    def __str__(self):
        return self.pharmacy_display_name

class Drug(models.Model):
    TYPE_CHOICES = [('normal', 'عادی'), ('quota', 'سهمیه ای')]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='drugs')
    name = models.CharField(max_length=255)
    quantity = models.IntegerField(default=0)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='normal')
    priority = models.IntegerField(default=4)
    ordered = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'drugs'
        app_label = 'bot'
        ordering = ['priority', '-created_at']

class Order(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    company = models.CharField(max_length=100)
    drug_name = models.CharField(max_length=255)
    quantity = models.IntegerField()
    ordered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'orders'
        app_label = 'bot'
        ordering = ['-ordered_at']

class Inventory(models.Model):
    LOCATION_CHOICES = [('warehouse', 'انبار'), ('pharmacy', 'داروخانه')]
    CATEGORY_CHOICES = [
        ('heart', 'قلب'), ('respiratory', 'تنفس'), ('women', 'زنان'),
        ('orthopedic', 'ارتوپد'), ('urology', 'ارولوژی'), ('endocrine', 'غدد'),
        ('neurology', 'مغز و اعصاب'), ('dermatology', 'پوست'), ('pediatric', 'کودکان'),
        ('eye', 'چشم'), ('other', 'سایر')
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='inventory_items')
    name = models.CharField(max_length=255)
    quantity = models.IntegerField(default=0)
    batch_number = models.CharField(max_length=100, blank=True, null=True)
    expiry_date = models.CharField(max_length=10, blank=True, null=True)
    manufacturer = models.CharField(max_length=255, blank=True, null=True)
    location = models.CharField(max_length=20, choices=LOCATION_CHOICES, default='warehouse')
    invoice_number = models.CharField(max_length=100, blank=True, null=True)
    supplier = models.CharField(max_length=255, blank=True, null=True)
    purchase_price = models.FloatField(default=0)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='other')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'inventory'
        app_label = 'bot'
        ordering = ['-created_at']

class Sale(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sales')
    drug_name = models.CharField(max_length=255)
    quantity = models.IntegerField()
    sale_date = models.DateTimeField(null=True, blank=True)
    expiry_date = models.CharField(max_length=10, blank=True, null=True)
    invoice_number = models.CharField(max_length=100, blank=True, null=True)
    customer_name = models.CharField(max_length=255, blank=True, null=True)
    price = models.FloatField(default=0)
    location = models.CharField(max_length=20, default='pharmacy')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sales'
        app_label = 'bot'
        ordering = ['-created_at']

class Company(models.Model):
    name = models.CharField(max_length=255, unique=True)

    class Meta:
        db_table = 'companies'
        app_label = 'bot'

class Exchange(models.Model):
    STATUS_CHOICES = [('pending', 'در انتظار'), ('confirmed', 'تایید شده')]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='exchanges')
    buyer_name = models.CharField(max_length=255)
    drug_name = models.CharField(max_length=255)
    quantity = models.IntegerField()
    expiry_date = models.CharField(max_length=10, blank=True, null=True)
    location = models.CharField(max_length=50, blank=True, null=True)
    exchange_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    batch_number = models.CharField(max_length=100, blank=True, null=True)
    invoice_number = models.CharField(max_length=100, blank=True, null=True)
    target_pharmacy_id = models.IntegerField(null=True, blank=True)
    category = models.CharField(max_length=50, default='other')
    sender_categories = models.TextField(default='')
    my_items_json = models.TextField(default='')
    target_items_json = models.TextField(default='')
    source_pharmacy_id = models.IntegerField(null=True, blank=True)
    source_pharmacy_name = models.CharField(max_length=255, default='')

    class Meta:
        db_table = 'exchanges'
        app_label = 'bot'
        ordering = ['-exchange_date']

class UserCategory(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='user_categories')
    categories = models.TextField(default='')

    class Meta:
        db_table = 'user_categories'
        app_label = 'bot'

class HiddenItem(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='hidden_items')
    item_id = models.IntegerField()

    class Meta:
        db_table = 'hidden_items'
        app_label = 'bot'
        unique_together = ['user', 'item_id']

class Interview(models.Model):
    pharmacist_name = models.CharField(max_length=255)
    pharmacy_name = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    content = models.TextField()
    image_url = models.CharField(max_length=500, blank=True, default='')
    audio_url = models.CharField(max_length=500, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    is_published = models.BooleanField(default=True)
    views = models.IntegerField(default=0)

    class Meta:
        db_table = 'interviews'
        app_label = 'bot'
        ordering = ['-created_at']

class Announcement(models.Model):
    title = models.CharField(max_length=255)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'announcements'
        app_label = 'bot'
        ordering = ['-created_at']

# ===== ایجاد جدول‌ها =====
def init_db():
    from django.db import connection
    from django.core.management import call_command
    
    # ایجاد جدول‌ها
    with connection.schema_editor() as schema_editor:
        if not connection.introspection.table_names():
            models.get_models()
    
    # ایجاد کاربران پیش‌فرض
    users = [
        ('admin', 'admin123', 'مدیر سیستم', 1, 1),
        ('nosratabadi', 'admin123', 'داروخانه نصرت‌آبادی', 1, 1),
        ('soleymani', 'soleymani123', 'داروخانه سلیمانی', 1, 1),
        ('A101', 'drsaboori', 'داروخانه A101', 1, 1),
        ('A102', 'drjafari', 'داروخانه A102', 1, 1),
    ]
    
    for username, password, display, is_full, approved in users:
        if not User.objects.filter(username=username).exists():
            user = User.objects.create_user(
                username=username,
                password=password,
                pharmacy_display_name=display,
                is_full_user=is_full,
                is_approved=approved,
                is_staff=(username == 'admin'),
                is_superuser=(username == 'admin')
            )
    
    # ایجاد شرکت‌ها
    companies = ['داروپخش', 'البرز', 'اکسیر', 'رازی']
    for c in companies:
        Company.objects.get_or_create(name=c)
    
    # ایجاد دسته‌بندی برای کاربران
    for user in User.objects.all():
        UserCategory.objects.get_or_create(user=user, defaults={'categories': ''})
    
    # داده‌های نمونه
    for user in User.objects.all():
        if not Inventory.objects.filter(user=user).exists():
            sample_data = [
                ('آسپرین', 100, '2026.03', 'warehouse'),
                ('آسپرین', 50, '2025.12', 'pharmacy'),
                ('ایبوپروفن', 75, '2025.09', 'pharmacy'),
                ('ایبوپروفن', 30, '2026.01', 'warehouse'),
                ('آمپی سیلین', 40, '2025.06', 'warehouse'),
                ('آمپی سیلین', 20, '2025.08', 'pharmacy'),
                ('دیازپام', 60, '2026.02', 'pharmacy'),
                ('دیازپام', 25, '2026.04', 'warehouse'),
                ('لوزارتان', 45, '2026.05', 'pharmacy'),
                ('مترونیدازول', 80, '2025.11', 'warehouse'),
                ('سفالکسین', 35, '2025.10', 'pharmacy'),
                ('آموکسی سیلین', 120, '2026.08', 'warehouse'),
            ]
            for name, qty, expiry, loc in sample_data:
                Inventory.objects.create(
                    user=user,
                    name=name,
                    quantity=qty,
                    expiry_date=expiry,
                    location=loc
                )

# ===== توابع کمکی =====
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_iran_time_iso():
    iran_time = datetime.utcnow() + timedelta(hours=3, minutes=30)
    return iran_time.isoformat()

def gregorian_to_jalali(gy, gm, gd):
    g_days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
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
    return f"{jy:04d}/{jm:02d}/{jd:02d}"

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

# ===== دکوراتورها =====
def admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if request.user.username != 'admin':
            return HttpResponse("⛔ دسترسی غیرمجاز. فقط ادمین می‌تواند وارد این بخش شود.", status=403)
        return view_func(request, *args, **kwargs)
    return wrapper

# ===== قالب HTML پایه =====
BASE_TEMPLATE = '''<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
    <title>{% block title %}داروخانه{% endblock %}</title>
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
        .exchange-card { background: white; border-radius: 10px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow: hidden; border: 1px solid #e0e0e0; }
        .exchange-card-header { background: #1a1a1a; color: white; padding: 10px 14px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px; font-size: 13px; }
        .exchange-card-footer { padding: 8px 14px; background: #f8f9fa; display: flex; gap: 8px; justify-content: flex-end; border-top: 1px solid #e0e0e0; }
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
        .drug-item .drug-actions { display: flex; gap: 4px; align-items: center; }
        .drug-item .drug-actions button { padding: 2px 6px; font-size: 10px; border-radius: 4px; }
        .exchange-drug-check { margin-left: 8px; }
        .exchange-drug-info { flex: 1; }
        .exchange-drug-name { font-weight: bold; font-size: 13px; }
        .exchange-drug-detail { font-size: 11px; color: #666; margin-top: 2px; }
        .exchange-qty-input { width: 60px; padding: 3px 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px; }
        .btn-exchange-select { padding: 2px 10px; font-size: 11px; border-radius: 4px; background: #007bff; color: white; border: none; cursor: pointer; }
        .btn-exchange-select.selected { background: #28a745; }
        .exchange-section { margin: 10px 0; padding: 10px; background: #f8f9fa; border-radius: 8px; }
        .exchange-section-title { font-weight: bold; margin-bottom: 6px; }
        .exchange-drug-list { list-style: none; padding: 0; }
        .exchange-drug-list li { padding: 4px 0; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; }
        @media (max-width: 768px) {
            .sidebar { width: 55px; }
            .sidebar .menu-text { display: none; }
            .main-content { margin-right: 55px; padding: 10px; }
            .topbar .brand { font-size: 13px; }
            .topbar .nav-links a { font-size: 10px; padding: 2px 6px; }
            .exchange-dual-container { flex-direction: column; }
        }
    </style>
    {% block extra_css %}{% endblock %}
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
            {% if user.is_authenticated and user.username == 'admin' %}
                <a href="/admin-panel" style="color:#ffc107;">👑 ادمین</a>
            {% endif %}
            {% if user.is_authenticated %}
                <span class="user-badge">👤 <strong>{{ user.pharmacy_display_name }}</strong></span>
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
            {% if user.is_authenticated and user.username == 'admin' %}
                <li><a href="/admin-panel" class="admin-link"><span>👑</span> <span class="menu-text">پنل ادمین</span></a></li>
            {% endif %}
        </ul>
    </div>
    <div class="main-content">
        <div class="header">
            <div class="page-title">{% block page_title %}صفحه اصلی{% endblock %}</div>
            <div class="user-info">
                {% if user.is_authenticated %}
                    <span>👤 {{ user.pharmacy_display_name }}</span>
                {% else %}
                    <span>👤 مهمان</span>
                {% endif %}
            </div>
        </div>
        {% if messages %}
            <div class="messages">
                {% for message in messages %}
                    <div class="alert alert-{{ message.tags }}">{{ message }}</div>
                {% endfor %}
            </div>
        {% endif %}
        {% block content %}{% endblock %}
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
        function getCookie(name) {
            var value = "; " + document.cookie;
            var parts = value.split("; " + name + "=");
            if (parts.length == 2) return parts.pop().split(";").shift();
        }
        function csrfSafeMethod(method) {
            return (/^(GET|HEAD|OPTIONS|TRACE)$/.test(method));
        }
        $.ajaxSetup({
            beforeSend: function(xhr, settings) {
                if (!csrfSafeMethod(settings.type) && !this.crossDomain) {
                    xhr.setRequestHeader("X-CSRFToken", getCookie('csrftoken'));
                }
            }
        });
    </script>
    {% block extra_js %}{% endblock %}
</body>
</html>
'''

# ===== ویوها =====

def index(request):
    interviews = Interview.objects.filter(is_published=True)
    announcements = Announcement.objects.filter(is_active=True)[:3]
    
    context = {
        'interviews': interviews,
        'announcements': announcements,
    }
    
    html = BASE_TEMPLATE.replace('{% block title %}داروخانه{% endblock %}', '{% block title %}صفحه اصلی - داروخانه{% endblock %}')
    html = html.replace('{% block page_title %}صفحه اصلی{% endblock %}', '{% block page_title %}صفحه اصلی{% endblock %}')
    
    content = '<div class="card"><div class="card-title">🎙️ مصاحبه با داروسازان</div>'
    if interviews:
        for i in interviews:
            content += f'''
            <div class="interview-card">
                <h3>{i.title}</h3>
                <div class="meta">👤 {i.pharmacist_name} | 🏥 {i.pharmacy_name} | 📅 {i.created_at.strftime('%Y-%m-%d')}</div>
                <div class="content">{i.content}</div>
                <div class="media">
                    {f'<img src="{i.image_url}" alt="{i.title}" style="max-width:100%;border-radius:6px;max-height:300px;">' if i.image_url else ''}
                    {f'<audio controls style="width:100%;"><source src="{i.audio_url}"></audio>' if i.audio_url else ''}
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
                <strong>{a.title}</strong>
                <p style="font-size:13px;color:#555;margin-top:4px;">{a.content}</p>
                <span style="font-size:11px;color:#999;">{a.created_at.strftime('%Y-%m-%d')}</span>
            </div>
            '''
        content += '</div>'
    
    html = html.replace('{% block content %}{% endblock %}', f'{{% block content %}}{content}{{% endblock %}}')
    
    return render(request, 'bot/base.html', {'content': content, 'user': request.user})
    # استفاده از پاسخ مستقیم
    return HttpResponse(html.replace('{% block content %}', content).replace('{% endblock %}', ''))

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        from django.contrib.auth import authenticate
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            if user.is_approved == 0:
                return HttpResponse('''
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
                ''')
            if user.is_approved == 2:
                return HttpResponse('''
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
                ''')
            
            auth_login(request, user)
            return redirect('index')
        
        return HttpResponse('''
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
        ''')
    
    return HttpResponse('''
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
    ''')

def register_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        pharmacy_name = request.POST.get('pharmacy_name')
        phone_number = request.POST.get('phone_number')
        address = request.POST.get('address')
        
        if not username or not password or not pharmacy_name:
            return HttpResponse('❌ همه فیلدهای اجباری را پر کنید')
        if len(username) < 3:
            return HttpResponse('❌ نام کاربری باید حداقل 3 کاراکتر باشد')
        if len(password) < 4:
            return HttpResponse('❌ رمز عبور باید حداقل 4 کاراکتر باشد')
        if password != confirm_password:
            return HttpResponse('❌ رمز عبور و تکرار آن مطابقت ندارند')
        if ' ' in username:
            return HttpResponse('❌ نام کاربری نباید شامل فاصله باشد')
        if phone_number and not re.match(r'^09[0-9]{9}$', phone_number):
            return HttpResponse('❌ شماره همراه نامعتبر است. فرمت صحیح: 09121234567')
        
        if User.objects.filter(username=username).exists():
            return HttpResponse('❌ این نام کاربری قبلاً ثبت شده است')
        
        user = User.objects.create_user(
            username=username,
            password=password,
            pharmacy_display_name=pharmacy_name,
            phone_number=phone_number,
            address=address,
            is_approved=0
        )
        UserCategory.objects.create(user=user, categories='')
        
        return HttpResponse('''
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
        ''')
    
    return HttpResponse('''
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
    ''')

def logout_view(request):
    auth_logout(request)
    return redirect('index')

# ===== ادامه ویوها =====

@login_required
def dashboard(request):
    user_id = request.user.id
    
    total_drugs = Drug.objects.filter(user_id=user_id, ordered=False).count()
    total_orders = Order.objects.filter(user_id=user_id).count()
    total_inventory = Inventory.objects.filter(user_id=user_id).aggregate(total=models.Sum('quantity'))['total'] or 0
    total_exchanges = Exchange.objects.filter(user_id=user_id).count()
    
    drugs = Drug.objects.filter(user_id=user_id, ordered=False).order_by('priority', '-created_at')
    
    quota_html = ''
    normal_html = ''
    for d in drugs:
        drug_html = f'''
        <div style="padding:8px;margin:5px 0;background:#f8f8f8;border-radius:8px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            <input type="checkbox" class="chk" data-id="{d.id}">
            <span style="flex:1"><strong>{d.name}</strong> - {d.quantity} عدد</span>
            <input type="number" class="qty-{d.id}" value="{d.quantity}" style="width:70px;padding:4px">
        </div>
        '''
        if d.type == 'quota':
            quota_html += drug_html
        else:
            normal_html += drug_html
    
    orders = Order.objects.filter(user_id=user_id).order_by('-ordered_at')
    
    orders_html = ''
    if orders:
        for o in orders:
            orders_html += f'''
            <tr>
                <td>{o.company}</td>
                <td><strong>{o.drug_name}</strong></td>
                <td>{o.quantity}</td>
                <td>{o.ordered_at.strftime('%Y-%m-%d')}</td>
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
            <div class="stat-card"><div class="number">{Drug.objects.filter(user_id=user_id, ordered=False, type='quota').count()}</div><div class="label">📦 سهمیه ای</div></div>
            <div class="stat-card"><div class="number">{Drug.objects.filter(user_id=user_id, ordered=False, type='normal').count()}</div><div class="label">📦 عادی</div></div>
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
    const USER_ID = {user_id};
    const csrftoken = getCookie('csrftoken');
    
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
        fetch('/api/place_order', {{ method:'POST', headers:{{'Content-Type':'application/json', 'X-CSRFToken': csrftoken}}, body:JSON.stringify({{selected_ids:ids, company:company, quantities:qty}}) }})
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
    
    html = BASE_TEMPLATE
    html = html.replace('{% block title %}داروخانه{% endblock %}', '{% block title %}داشبورد - داروخانه{% endblock %}')
    html = html.replace('{% block page_title %}صفحه اصلی{% endblock %}', '{% block page_title %}📊 داشبورد{% endblock %}')
    html = html.replace('{% block content %}{% endblock %}', f'{{% block content %}}{content}{{% endblock %}}')
    
    return HttpResponse(html)

@login_required
def inventory_view(request):
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
                {get_year_month_selectors()}
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
                {get_year_month_selectors()}
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
    const USER_ID = {request.user.id};
    const csrftoken = getCookie('csrftoken');
    let inventoryData = [];
    let currentFilter = '';
    let showHidden = false;
    let hiddenIds = new Set();
    
    try {{
        var saved = localStorage.getItem('hiddenIds_' + USER_ID);
        if(saved) {{
            hiddenIds = new Set(JSON.parse(saved));
        }}
    }} catch(e) {{
        hiddenIds = new Set();
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
                        text += "• " + d.name + ": " + d.quantity + " عدد (" + (d.location === 'warehouse' ? 'انبار' : 'داروخانه') + ") - انقضا: " + (d.expiry_date || 'نامشخص') + "\\n";
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
            headers: {{'Content-Type': 'application/json', 'X-CSRFToken': csrftoken}},
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
            headers: {{'Content-Type': 'application/json', 'X-CSRFToken': csrftoken}},
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
            headers: {{'Content-Type': 'application/json', 'X-CSRFToken': csrftoken}},
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
        fetch('/api/delete_inventory_item/' + id, {{ method: 'POST', headers: {{'X-CSRFToken': csrftoken}} }})
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
                    var locText = d.location === 'warehouse' ? 'انبار' : 'داروخانه';
                    var locClass = d.location === 'warehouse' ? 'location-warehouse' : 'location-pharmacy';
                    html += '<div class="drug-item">';
                    html += '<input type="checkbox" class="item-checkbox" data-id="' + d.id + '">';
                    html += '<span class="drug-name">' + d.name + '</span>';
                    html += '<span class="drug-qty">' + d.quantity + ' عدد</span>';
                    html += '<span class="drug-location ' + locClass + '">' + locText + '</span>';
                    html += '<span style="font-size:11px;color:#999;">انقضا: ' + (d.expiry_date || '-') + '</span>';
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
    
    function searchDrugsForSale(query) {{
        var suggestions = document.getElementById('suggestionsSale');
        if(query.length < 2) {{ suggestions.style.display = 'none'; return; }}
        fetch('/api/search_with_stock?q=' + encodeURIComponent(query))
            .then(r => r.json())
            .then(data => {{
                if(data.length > 0) {{
                    var html = '';
                    data.forEach(drug => {{
                        html += '<div onclick="selectDrugForSale(\\'' + drug.name + '\\')"><strong>' + drug.name + '</strong><div class="stock-info">🏭 انبار: ' + drug.warehouse_qty + ' | 🏪 داروخانه: ' + drug.pharmacy_qty + ' | 📅 نزدیک‌ترین انقضا: ' + (drug.nearest_expiry || '-') + '</div></div>';
                    }});
                    suggestions.innerHTML = html;
                    suggestions.style.display = 'block';
                }} else {{ suggestions.style.display = 'none'; }}
            }})
            .catch(() => {{ suggestions.style.display = 'none'; }});
    }}
    
    function searchDrugsMove(query) {{
        var suggestions = document.getElementById('suggestionsMove');
        if(query.length < 2) {{ suggestions.style.display = 'none'; return; }}
        fetch('/api/search_with_stock?q=' + encodeURIComponent(query))
            .then(r => r.json())
            .then(data => {{
                if(data.length > 0) {{
                    var html = '';
                    data.forEach(drug => {{
                        html += '<div onclick="selectDrugMove(\\'' + drug.name + '\\')"><strong>' + drug.name + '</strong><div class="stock-info">🏭 انبار: ' + drug.warehouse_qty + ' | 🏪 داروخانه: ' + drug.pharmacy_qty + ' | 📅 نزدیک‌ترین انقضا: ' + (drug.nearest_expiry || '-') + '</div></div>';
                    }});
                    suggestions.innerHTML = html;
                    suggestions.style.display = 'block';
                }} else {{ suggestions.style.display = 'none'; }}
            }})
            .catch(() => {{ suggestions.style.display = 'none'; }});
    }}
    
    function selectDrugInv(name) {{ document.getElementById('invName').value = name; document.getElementById('suggestionsInv').style.display = 'none'; }}
    function selectDrugForSale(name) {{ document.getElementById('saleDrugName').value = name; document.getElementById('suggestionsSale').style.display = 'none'; }}
    function selectDrugMove(name) {{ document.getElementById('moveDrug').value = name; document.getElementById('suggestionsMove').style.display = 'none'; }}
    
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
        if(!name || !qty || !expiry) {{
            showToast('نام دارو، تعداد و تاریخ انقضا اجباری است', 'error');
            return;
        }}
        var fd = new FormData();
        fd.append('name', name);
        fd.append('quantity', qty);
        fd.append('expiry_date', expiry);
        fd.append('location', document.getElementById('location').value);
        fd.append('supplier', document.getElementById('supplier').value);
        fd.append('purchase_price', document.getElementById('price').value);
        fetch('/api/add_inventory', {{
            method: 'POST',
            headers: {{'X-CSRFToken': csrftoken}},
            body: fd
        }})
        .then(r => r.json())
        .then(data => {{
            if(data.success) {{ 
                showToast('✅ دارو ثبت شد', 'success');
                loadInventory();
                document.getElementById('invName').value = '';
                document.getElementById('invQty').value = '1';
                document.getElementById('supplier').value = '';
                document.getElementById('price').value = '';
            }} else {{ 
                showToast('خطا: ' + data.error, 'error'); 
            }} 
        }})
        .catch(err => {{
            showToast('❌ خطا در ارتباط با سرور', 'error');
        }});
    }}
    
    function registerSale() {{
        var name = document.getElementById('saleDrugName').value;
        var qty = document.getElementById('saleQty').value;
        var formRow = document.getElementById('saleDrugName').closest('.form-row');
        var expiry = getExpiryFromSelectors(formRow);
        if(!name || !qty || !expiry) {{ showToast('نام دارو، تعداد و تاریخ انقضا اجباری است', 'error'); return; }}
        fetch('/api/register_sale', {{ method: 'POST', headers: {{'Content-Type': 'application/json', 'X-CSRFToken': csrftoken}}, body: JSON.stringify({{
            drug_name: name, quantity: parseInt(qty), expiry_date: expiry,
            customer_name: document.getElementById('customerName').value,
            price: parseFloat(document.getElementById('salePrice').value) || 0,
            location: document.getElementById('saleLocation').value
        }}) }})
        .then(r=>r.json())
        .then(res => {{ 
            if(res.success) {{ 
                showToast('✅ فروش ثبت شد', 'success'); 
                loadInventory();
            }} else {{ 
                showToast('خطا: ' + res.error, 'error'); 
            }} 
        }})
        .catch(() => showToast('❌ خطا در ارتباط با سرور', 'error'));
    }}
    
    function moveDrug() {{
        var name = document.getElementById('moveDrug').value;
        var qty = document.getElementById('moveQty').value;
        var fromLoc = document.getElementById('moveFromLocation').value;
        var toLoc = document.getElementById('moveToLocation').value;
        var formRow = document.getElementById('moveDrug').closest('.form-row');
        var expiry = getExpiryFromSelectors(formRow);
        if(!name || !qty || !expiry){{ showToast('نام دارو، تعداد و تاریخ انقضا را وارد کنید', 'error'); return; }}
        fetch('/api/move_inventory', {{ method:'POST', headers:{{'Content-Type':'application/json', 'X-CSRFToken': csrftoken}}, body:JSON.stringify({{name:name, quantity:parseInt(qty), from_location:fromLoc, to_location:toLoc, expiry_date:expiry}}) }})
            .then(r=>r.json())
            .then(data=>{{ 
                if(data.success) {{ 
                    showToast('✅ انتقال انجام شد', 'success'); 
                    loadInventory();
                }} else {{ 
                    showToast('خطا: '+data.error, 'error'); 
                }} 
            }})
            .catch(() => showToast('❌ خطا در ارتباط با سرور', 'error'));
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
            ['suggestionsInv','suggestionsSale','suggestionsMove'].forEach(id => {{ var s = document.getElementById(id); if(s) s.style.display = 'none'; }});
        }}
    }});
    
    loadInventory();
    </script>
    '''
    
    html = BASE_TEMPLATE
    html = html.replace('{% block title %}داروخانه{% endblock %}', '{% block title %}انبارداری - داروخانه{% endblock %}')
    html = html.replace('{% block page_title %}صفحه اصلی{% endblock %}', '{% block page_title %}📦 انبارداری{% endblock %}')
    html = html.replace('{% block content %}{% endblock %}', f'{{% block content %}}{content}{{% endblock %}}')
    
    return HttpResponse(html)

# ===== API ویوها =====

@csrf_exempt
@login_required
def api_place_order(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})
    
    data = json.loads(request.body)
    selected_ids = data.get('selected_ids', [])
    company = data.get('company')
    quantities = data.get('quantities', {})
    
    if not selected_ids:
        return JsonResponse({'success': False, 'error': 'هیچ دارویی انتخاب نشده است'})
    
    for drug_id in selected_ids:
        drug = Drug.objects.filter(id=drug_id, user=request.user).first()
        if drug:
            qty = int(quantities.get(str(drug_id), drug.quantity))
            Order.objects.create(
                user=request.user,
                company=company,
                drug_name=drug.name,
                quantity=qty
            )
            if drug.type != 'quota':
                drug.ordered = True
                drug.save()
    
    Drug.objects.filter(user=request.user, ordered=True).exclude(type='quota').delete()
    return JsonResponse({'success': True})

@csrf_exempt
@login_required
def api_add_inventory(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})
    
    name = request.POST.get('name')
    quantity = int(request.POST.get('quantity', 0))
    expiry_date = request.POST.get('expiry_date')
    location = request.POST.get('location', 'warehouse')
    supplier = request.POST.get('supplier', '')
    price_str = request.POST.get('purchase_price', '0')
    
    if not name or quantity <= 0 or not expiry_date:
        return JsonResponse({'success': False, 'error': 'نام، تعداد و تاریخ انقضا اجباری است'})
    if not validate_expiry_date(expiry_date):
        return JsonResponse({'success': False, 'error': 'تاریخ انقضا نامعتبر است'})
    
    existing = Inventory.objects.filter(
        user=request.user,
        name=name,
        expiry_date=expiry_date,
        location=location
    ).first()
    
    if existing:
        existing.quantity += quantity
        existing.save()
    else:
        Inventory.objects.create(
            user=request.user,
            name=name,
            quantity=quantity,
            expiry_date=expiry_date,
            location=location,
            supplier=supplier,
            purchase_price=float(price_str) if price_str else 0
        )
    
    return JsonResponse({'success': True})

@csrf_exempt
@login_required
def api_register_sale(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})
    
    data = json.loads(request.body)
    drug_name = data.get('drug_name')
    quantity = data.get('quantity')
    expiry_date = data.get('expiry_date')
    customer_name = data.get('customer_name', '')
    price = data.get('price', 0)
    location = data.get('location', 'pharmacy')
    
    if not drug_name or not quantity or not expiry_date:
        return JsonResponse({'success': False, 'error': 'نام دارو، تعداد و تاریخ انقضا اجباری است'})
    if not validate_expiry_date(expiry_date):
        return JsonResponse({'success': False, 'error': 'تاریخ انقضا نامعتبر است'})
    
    items = Inventory.objects.filter(
        user=request.user,
        name=drug_name,
        location=location,
        expiry_date=expiry_date
    )
    
    total_available = sum(i.quantity for i in items)
    if total_available < quantity:
        return JsonResponse({'success': False, 'error': f'موجودی دارو کافی نیست. فقط {total_available} عدد موجود است'})
    
    remaining = quantity
    for item in items:
        if remaining <= 0:
            break
        take = min(item.quantity, remaining)
        if take > 0:
            item.quantity -= take
            if item.quantity == 0:
                item.delete()
            else:
                item.save()
            remaining -= take
    
    Sale.objects.create(
        user=request.user,
        drug_name=drug_name,
        quantity=quantity,
        expiry_date=expiry_date,
        customer_name=customer_name,
        price=price,
        location=location
    )
    
    return JsonResponse({'success': True})

@csrf_exempt
@login_required
def api_move_inventory(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})
    
    data = json.loads(request.body)
    name = data.get('name')
    quantity = data.get('quantity')
    from_location = data.get('from_location')
    to_location = data.get('to_location')
    expiry_date = data.get('expiry_date')
    
    if not name or not quantity or not expiry_date:
        return JsonResponse({'success': False, 'error': 'نام، تعداد و تاریخ انقضا اجباری است'})
    if not validate_expiry_date(expiry_date):
        return JsonResponse({'success': False, 'error': 'تاریخ انقضا نامعتبر است'})
    
    sources = Inventory.objects.filter(
        user=request.user,
        name=name,
        location=from_location,
        expiry_date=expiry_date
    )
    
    total_available = sum(s.quantity for s in sources)
    if total_available < quantity:
        return JsonResponse({'success': False, 'error': f'موجودی ناکافی. فقط {total_available} عدد موجود است'})
    
    remaining = quantity
    for source in sources:
        if remaining <= 0:
            break
        take = min(source.quantity, remaining)
        if take > 0:
            source.quantity -= take
            if source.quantity == 0:
                source.delete()
            else:
                source.save()
            
            dest = Inventory.objects.filter(
                user=request.user,
                name=name,
                expiry_date=expiry_date,
                location=to_location
            ).first()
            
            if dest:
                dest.quantity += take
                dest.save()
            else:
                Inventory.objects.create(
                    user=request.user,
                    name=name,
                    quantity=take,
                    expiry_date=expiry_date,
                    location=to_location
                )
            remaining -= take
    
    return JsonResponse({'success': True})

@login_required
def api_get_inventory_grouped_by_expiry(request):
    hidden_ids = HiddenItem.objects.filter(user=request.user).values_list('item_id', flat=True)
    
    items = Inventory.objects.filter(
        user=request.user,
        quantity__gt=0
    ).order_by('expiry_date')
    
    expiry_groups = {}
    for item in items:
        expiry = item.expiry_date or 'نامشخص'
        if expiry not in expiry_groups:
            expiry_groups[expiry] = []
        expiry_groups[expiry].append({
            'id': item.id,
            'name': item.name,
            'quantity': item.quantity,
            'expiry_date': item.expiry_date,
            'location': item.location,
            'created_at': item.created_at.isoformat() if item.created_at else '',
            'hidden': item.id in hidden_ids
        })
    
    result = []
    for expiry_date, drugs in expiry_groups.items():
        result.append({
            'expiry_date': expiry_date,
            'status_text': get_expiry_status(expiry_date)['text'],
            'pharmacies': [{
                'pharmacy_id': request.user.id,
                'pharmacy_name': request.user.pharmacy_display_name,
                'drugs': drugs
            }]
        })
    
    result.sort(key=lambda x: parse_expiry_number(x['expiry_date']))
    return JsonResponse({'data': result})

@login_required
def api_get_all_pharmacies_drugs_grouped_by_expiry(request):
    hidden_ids = HiddenItem.objects.filter(user=request.user).values_list('item_id', flat=True)
    
    other_pharmacies = User.objects.filter(is_approved=1).exclude(id=request.user.id)
    all_pharmacies = list(other_pharmacies) + [request.user]
    
    expiry_groups = {}
    for ph in all_pharmacies:
        items = Inventory.objects.filter(user=ph, quantity__gt=0)
        if not items:
            continue
        for item in items:
            if ph.id == request.user.id and item.id in hidden_ids:
                continue
            expiry = item.expiry_date or 'نامشخص'
            if expiry not in expiry_groups:
                expiry_groups[expiry] = {}
            if ph.id not in expiry_groups[expiry]:
                expiry_groups[expiry][ph.id] = {
                    'pharmacy_id': ph.id,
                    'pharmacy_name': ph.pharmacy_display_name,
                    'drugs': []
                }
            expiry_groups[expiry][ph.id]['drugs'].append({
                'id': item.id,
                'name': item.name,
                'quantity': item.quantity,
                'expiry_date': item.expiry_date,
                'location': item.location,
                'hidden': item.id in hidden_ids
            })
    
    result = []
    for expiry_date, pharmacies_dict in expiry_groups.items():
        result.append({
            'expiry_date': expiry_date,
            'status_text': get_expiry_status(expiry_date)['text'],
            'pharmacies': list(pharmacies_dict.values())
        })
    
    result.sort(key=lambda x: parse_expiry_number(x['expiry_date']))
    return JsonResponse({'data': result})

@login_required
def api_search_with_stock(request):
    q = request.GET.get('q', '')
    names = Inventory.objects.filter(
        user=request.user,
        name__icontains=q
    ).values_list('name', flat=True).distinct()[:10]
    
    result = []
    for name in names:
        warehouse_qty = Inventory.objects.filter(
            user=request.user,
            name=name,
            location='warehouse'
        ).aggregate(total=models.Sum('quantity'))['total'] or 0
        
        pharmacy_qty = Inventory.objects.filter(
            user=request.user,
            name=name,
            location='pharmacy'
        ).aggregate(total=models.Sum('quantity'))['total'] or 0
        
        nearest = Inventory.objects.filter(
            user=request.user,
            name=name
        ).exclude(expiry_date__isnull=True).exclude(expiry_date='').order_by('expiry_date').first()
        
        result.append({
            'name': name,
            'warehouse_qty': warehouse_qty,
            'pharmacy_qty': pharmacy_qty,
            'nearest_expiry': nearest.expiry_date if nearest else '-'
        })
    
    return JsonResponse(result, safe=False)

@csrf_exempt
@login_required
def api_delete_inventory_item(request, item_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})
    
    Inventory.objects.filter(id=item_id, user=request.user).delete()
    return JsonResponse({'success': True})

@csrf_exempt
@login_required
def api_delete_inventory_items(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})
    
    data = json.loads(request.body)
    item_ids = data.get('item_ids', [])
    if not item_ids:
        return JsonResponse({'success': False, 'error': 'هیچ آیتمی انتخاب نشده است'})
    
    Inventory.objects.filter(id__in=item_ids, user=request.user).delete()
    return JsonResponse({'success': True})

@login_required
def api_get_hidden_items(request):
    hidden_ids = HiddenItem.objects.filter(user=request.user).values_list('item_id', flat=True)
    return JsonResponse({'hidden_ids': list(hidden_ids)})

@csrf_exempt
@login_required
def api_toggle_hidden_items(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})
    
    data = json.loads(request.body)
    item_ids = data.get('item_ids', [])
    hidden = data.get('hidden', False)
    
    if not item_ids:
        return JsonResponse({'success': False, 'error': 'هیچ آیتمی انتخاب نشده است'})
    
    if hidden:
        for item_id in item_ids:
            HiddenItem.objects.get_or_create(user=request.user, item_id=item_id)
    else:
        HiddenItem.objects.filter(user=request.user, item_id__in=item_ids).delete()
    
    return JsonResponse({'success': True})

@csrf_exempt
@login_required
def api_add_drug(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})
    
    if request.content_type == 'application/json':
        data = json.loads(request.body)
        name = data.get('name')
        quantity = data.get('quantity', 0)
        drug_type = data.get('type', 'normal')
        priority = data.get('priority', 4)
    else:
        name = request.POST.get('name')
        quantity = int(request.POST.get('quantity', 0))
        drug_type = request.POST.get('type', 'normal')
        priority = int(request.POST.get('priority', 4))
    
    if not name or not name.strip():
        return JsonResponse({'success': False, 'error': 'نام دارو را وارد کنید'})
    if not quantity or quantity <= 0:
        return JsonResponse({'success': False, 'error': 'تعداد معتبر وارد کنید'})
    
    Drug.objects.create(
        user=request.user,
        name=name.strip(),
        quantity=quantity,
        type=drug_type,
        priority=priority
    )
    
    return JsonResponse({'success': True})

@login_required
def api_get_drugs(request):
    drugs = Drug.objects.filter(user=request.user, ordered=False).order_by('priority', '-created_at')
    return JsonResponse({'drugs': list(drugs.values())})

@csrf_exempt
@login_required
def api_delete_drug(request, drug_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})
    
    Drug.objects.filter(id=drug_id, user=request.user).delete()
    return JsonResponse({'success': True})

@csrf_exempt
@login_required
def api_delete_drugs(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})
    
    data = json.loads(request.body)
    drug_ids = data.get('drug_ids', [])
    if not drug_ids:
        return JsonResponse({'success': False, 'error': 'هیچ دارویی انتخاب نشده است'})
    
    Drug.objects.filter(id__in=drug_ids, user=request.user).delete()
    return JsonResponse({'success': True})

# ===== تبادل =====

@csrf_exempt
@login_required
def api_register_exchange(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})
    
    data = json.loads(request.body)
    target_pharmacy_id = data.get('target_pharmacy_id')
    my_items = data.get('my_items', [])
    target_items = data.get('target_items', [])
    
    if not target_pharmacy_id:
        return JsonResponse({'success': False, 'error': 'Target pharmacy not selected'})
    
    user_cat = UserCategory.objects.filter(user=request.user).first()
    sender_categories = user_cat.categories if user_cat else ''
    sender_name = request.user.pharmacy_display_name
    
    target_user = User.objects.get(id=target_pharmacy_id)
    target_name = target_user.pharmacy_display_name
    
    now_iran = get_iran_time_iso()
    
    for item in target_items:
        Exchange.objects.create(
            user=target_user,
            buyer_name=sender_name,
            drug_name=item['name'],
            quantity=item['quantity'],
            expiry_date=item.get('expiry_date', ''),
            location='pharmacy',
            status='pending',
            target_pharmacy_id=request.user.id,
            sender_categories=sender_categories,
            my_items_json=json.dumps(my_items),
            target_items_json=json.dumps(target_items),
            source_pharmacy_id=request.user.id,
            source_pharmacy_name=sender_name
        )
    
    for item in my_items:
        Exchange.objects.create(
            user=request.user,
            buyer_name=target_name,
            drug_name=item['name'],
            quantity=item['quantity'],
            expiry_date=item.get('expiry_date', ''),
            location='pharmacy',
            status='pending',
            target_pharmacy_id=target_pharmacy_id,
            sender_categories=sender_categories,
            my_items_json=json.dumps(my_items),
            target_items_json=json.dumps(target_items),
            source_pharmacy_id=request.user.id,
            source_pharmacy_name=sender_name
        )
    
    return JsonResponse({'success': True})

@login_required
def api_get_exchanges(request):
    exchanges = Exchange.objects.filter(
        models.Q(user=request.user) | 
        models.Q(target_pharmacy_id=request.user.id) |
        models.Q(source_pharmacy_id=request.user.id)
    ).order_by('-exchange_date')
    
    return JsonResponse({'exchanges': list(exchanges.values())})

@login_required
def api_get_pending_exchanges(request):
    exchanges = Exchange.objects.filter(
        models.Q(user=request.user) | models.Q(target_pharmacy_id=request.user.id),
        status='pending'
    ).exclude(source_pharmacy_id=request.user.id).order_by('-exchange_date')
    
    return JsonResponse({'exchanges': list(exchanges.values())})

@csrf_exempt
@login_required
def api_confirm_exchange(request, exchange_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})
    
    exchange = Exchange.objects.filter(id=exchange_id, user=request.user, status='pending').first()
    if not exchange:
        return JsonResponse({'success': False, 'error': 'تبادل یافت نشد یا قبلا پردازش شده است'})
    
    try:
        target_items = json.loads(exchange.target_items_json) if exchange.target_items_json else []
        my_items = json.loads(exchange.my_items_json) if exchange.my_items_json else []
        
        # پردازش تبادل
        for item in target_items:
            inv_items = Inventory.objects.filter(
                user=request.user,
                name=item['name'],
                expiry_date=item.get('expiry_date', ''),
                quantity__gt=0
            )
            total_available = sum(i.quantity for i in inv_items)
            if total_available < item['quantity']:
                return JsonResponse({'success': False, 'error': f'موجودی {item["name"]} با تاریخ {item.get("expiry_date", "")} کافی نیست'})
            
            remaining = item['quantity']
            for inv_item in inv_items:
                if remaining <= 0:
                    break
                take = min(inv_item.quantity, remaining)
                inv_item.quantity -= take
                if inv_item.quantity == 0:
                    inv_item.delete()
                else:
                    inv_item.save()
                remaining -= take
        
        for item in my_items:
            dest = Inventory.objects.filter(
                user=request.user,
                name=item['name'],
                expiry_date=item.get('expiry_date', ''),
                location='pharmacy'
            ).first()
            
            if dest:
                dest.quantity += item['quantity']
                dest.save()
            else:
                Inventory.objects.create(
                    user=request.user,
                    name=item['name'],
                    quantity=item['quantity'],
                    expiry_date=item.get('expiry_date', ''),
                    location='pharmacy'
                )
        
        exchange.status = 'confirmed'
        exchange.save()
        
        # تایید تبادلات مرتبط
        if exchange.source_pharmacy_id:
            Exchange.objects.filter(
                source_pharmacy_id=exchange.source_pharmacy_id,
                target_pharmacy_id=request.user.id,
                status='pending'
            ).update(status='confirmed')
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@csrf_exempt
@login_required
def api_reject_exchange(request, exchange_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})
    
    exchange = Exchange.objects.filter(id=exchange_id, user=request.user, status='pending').first()
    if not exchange:
        return JsonResponse({'success': False, 'error': 'تبادل یافت نشد یا قبلا پردازش شده است'})
    
    exchange.delete()
    
    if exchange.source_pharmacy_id:
        Exchange.objects.filter(
            source_pharmacy_id=exchange.source_pharmacy_id,
            target_pharmacy_id=request.user.id,
            status='pending'
        ).delete()
    
    return JsonResponse({'success': True})

@login_required
def api_get_my_drugs_for_exchange(request):
    drugs = Inventory.objects.filter(user=request.user, quantity__gt=0)
    return JsonResponse({'drugs': list(drugs.values('id', 'name', 'quantity', 'expiry_date', 'location'))})

@login_required
def api_get_pharmacy_drugs_for_exchange(request):
    pharmacy_id = request.GET.get('pharmacy_id')
    if not pharmacy_id:
        return JsonResponse({'drugs': []})
    
    drugs = Inventory.objects.filter(user_id=pharmacy_id, quantity__gt=0)
    return JsonResponse({'drugs': list(drugs.values('id', 'name', 'quantity', 'expiry_date', 'location'))})

@login_required
def api_get_user_categories(request):
    user_cat = UserCategory.objects.filter(user=request.user).first()
    categories = user_cat.categories.split(',') if user_cat and user_cat.categories else []
    return JsonResponse({'categories': categories})

@csrf_exempt
@login_required
def api_save_user_categories(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})
    
    data = json.loads(request.body)
    categories = data.get('categories', [])
    categories_str = ','.join(categories)
    
    UserCategory.objects.update_or_create(
        user=request.user,
        defaults={'categories': categories_str}
    )
    
    return JsonResponse({'success': True})

# ===== پنل ادمین =====

@admin_required
def admin_panel(request):
    total_users = User.objects.count()
    pending_users = User.objects.filter(is_approved=0).count()
    total_drugs = Drug.objects.count()
    total_inventory = Inventory.objects.aggregate(total=models.Sum('quantity'))['total'] or 0
    
    users = User.objects.all().order_by('-created_at')
    interviews = Interview.objects.all().order_by('-created_at')
    announcements = Announcement.objects.all().order_by('-created_at')
    
    users_html = ''
    for u in users:
        status_badge = ''
        if u.username == 'admin':
            status_badge = '<span class="badge badge-danger">ادمین</span>'
        else:
            if u.is_approved == 0:
                status_badge = '<span class="badge badge-warning">⏳ در انتظار تأیید</span>'
            elif u.is_approved == 2:
                status_badge = '<span class="badge badge-danger">❌ رد شده</span>'
            elif u.is_full_user:
                status_badge = '<span class="badge badge-success">کاربر کامل</span>'
            else:
                status_badge = '<span class="badge badge-info">کاربر عادی</span>'
        
        actions = ''
        if u.username != 'admin':
            if u.is_approved == 0:
                actions += f'<button onclick="approveUser({u.id})" class="btn-success btn-sm">✅ تأیید</button> '
                actions += f'<button onclick="rejectUser({u.id})" class="btn-danger btn-sm">❌ رد</button> '
            actions += f'<button onclick="deleteUser({u.id})" class="btn-danger btn-sm">🗑️</button>'
        else:
            actions = '<span style="color:#999;font-size:11px;">غیرقابل حذف</span>'
        
        users_html += f'''
        <tr>
            <td>{u.id}</td>
            <td><strong>{u.username}</strong></td>
            <td>{u.pharmacy_display_name}</td>
            <td>{u.phone_number or '-'}</td>
            <td>{u.address or '-'}</td>
            <td>{status_badge}</td>
            <td>{u.created_at.strftime('%Y-%m-%d')}</td>
            <td>{actions}</td>
        </tr>
        '''
    
    interviews_html = ''
    for i in interviews:
        status = '✅ منتشر شده' if i.is_published else '⏳ پیش‌نویس'
        status_class = 'badge-success' if i.is_published else 'badge-warning'
        interviews_html += f'''
        <tr>
            <td>{i.id}</td>
            <td><strong>{i.title}</strong></td>
            <td>{i.pharmacist_name}</td>
            <td>{i.pharmacy_name}</td>
            <td><span class="badge {status_class}">{status}</span></td>
            <td>{i.created_at.strftime('%Y-%m-%d')}</td>
            <td>
                <button onclick="toggleInterview({i.id})" class="btn-warning btn-sm">{'🔒 غیرفعال' if i.is_published else '✅ فعال'}</button>
                <button onclick="deleteInterview({i.id})" class="btn-danger btn-sm">🗑️</button>
            </td>
        </tr>
        '''
    
    announcements_html = ''
    for a in announcements:
        status = '✅ فعال' if a.is_active else '⏳ غیرفعال'
        status_class = 'badge-success' if a.is_active else 'badge-warning'
        announcements_html += f'''
        <tr>
            <td>{a.id}</td>
            <td><strong>{a.title}</strong></td>
            <td>{a.content[:50]}{'...' if len(a.content) > 50 else ''}</td>
            <td><span class="badge {status_class}">{status}</span></td>
            <td>{a.created_at.strftime('%Y-%m-%d')}</td>
            <td>
                <button onclick="toggleAnnouncement({a.id})" class="btn-warning btn-sm">{'🔒 غیرفعال' if a.is_active else '✅ فعال'}</button>
                <button onclick="deleteAnnouncement({a.id})" class="btn-danger btn-sm">🗑️</button>
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
    const csrftoken = getCookie('csrftoken');
    
    function approveUser(id) {{
        if(confirm('آیا از تأیید این کاربر اطمینان دارید؟')) {{
            fetch('/admin/approve_user/'+id, {{method:'POST', headers:{{'X-CSRFToken': csrftoken}}}})
                .then(r=>r.json()).then(data=>{{
                    if(data.success) {{ showToast('✅ کاربر تأیید شد', 'success'); location.reload(); }}
                    else {{ showToast('❌ خطا: ' + data.error, 'error'); }}
                }}).catch(()=> showToast('❌ خطا در ارتباط با سرور', 'error'));
        }}
    }}
    
    function rejectUser(id) {{
        if(confirm('آیا از رد این کاربر اطمینان دارید؟')) {{
            fetch('/admin/reject_user/'+id, {{method:'POST', headers:{{'X-CSRFToken': csrftoken}}}})
                .then(r=>r.json()).then(data=>{{
                    if(data.success) {{ showToast('✅ کاربر رد شد', 'success'); location.reload(); }}
                    else {{ showToast('❌ خطا: ' + data.error, 'error'); }}
                }}).catch(()=> showToast('❌ خطا در ارتباط با سرور', 'error'));
        }}
    }}
    
    function deleteUser(id) {{
        if(confirm('آیا از حذف این کاربر اطمینان دارید؟')) {{
            fetch('/admin/delete_user/'+id, {{method:'POST', headers:{{'X-CSRFToken': csrftoken}}}})
                .then(r=>r.json()).then(data=>{{
                    if(data.success) {{ showToast('✅ کاربر حذف شد', 'success'); location.reload(); }}
                    else {{ showToast('❌ خطا: ' + data.error, 'error'); }}
                }}).catch(()=> showToast('❌ خطا در ارتباط با سرور', 'error'));
        }}
    }}
    
    function toggleInterview(id) {{
        fetch('/admin/toggle_interview/'+id, {{method:'POST', headers:{{'X-CSRFToken': csrftoken}}}})
            .then(r=>r.json()).then(data=>{{
                if(data.success) location.reload();
                else showToast('❌ خطا: ' + data.error, 'error');
            }}).catch(()=> showToast('❌ خطا در ارتباط با سرور', 'error'));
    }}
    
    function deleteInterview(id) {{
        if(confirm('آیا از حذف این مصاحبه اطمینان دارید؟')) {{
            fetch('/admin/delete_interview/'+id, {{method:'POST', headers:{{'X-CSRFToken': csrftoken}}}})
                .then(r=>r.json()).then(data=>{{
                    if(data.success) {{ showToast('✅ مصاحبه حذف شد', 'success'); location.reload(); }}
                    else {{ showToast('❌ خطا: ' + data.error, 'error'); }}
                }}).catch(()=> showToast('❌ خطا در ارتباط با سرور', 'error'));
        }}
    }}
    
    function toggleAnnouncement(id) {{
        fetch('/admin/toggle_announcement/'+id, {{method:'POST', headers:{{'X-CSRFToken': csrftoken}}}})
            .then(r=>r.json()).then(data=>{{
                if(data.success) location.reload();
                else showToast('❌ خطا: ' + data.error, 'error');
            }}).catch(()=> showToast('❌ خطا در ارتباط با سرور', 'error'));
    }}
    
    function deleteAnnouncement(id) {{
        if(confirm('آیا از حذف این اطلاعیه اطمینان دارید؟')) {{
            fetch('/admin/delete_announcement/'+id, {{method:'POST', headers:{{'X-CSRFToken': csrftoken}}}})
                .then(r=>r.json()).then(data=>{{
                    if(data.success) {{ showToast('✅ اطلاعیه حذف شد', 'success'); location.reload(); }}
                    else {{ showToast('❌ خطا: ' + data.error, 'error'); }}
                }}).catch(()=> showToast('❌ خطا در ارتباط با سرور', 'error'));
        }}
    }}
    </script>
    '''
    
    html = BASE_TEMPLATE
    html = html.replace('{% block title %}داروخانه{% endblock %}', '{% block title %}پنل ادمین - داروخانه{% endblock %}')
    html = html.replace('{% block page_title %}صفحه اصلی{% endblock %}', '{% block page_title %}👑 پنل ادمین{% endblock %}')
    html = html.replace('{% block content %}{% endblock %}', f'{{% block content %}}{content}{{% endblock %}}')
    
    return HttpResponse(html)

@csrf_exempt
@admin_required
def admin_approve_user(request, user_id):
    User.objects.filter(id=user_id).exclude(username='admin').update(is_approved=1)
    return JsonResponse({'success': True})

@csrf_exempt
@admin_required
def admin_reject_user(request, user_id):
    User.objects.filter(id=user_id).exclude(username='admin').update(is_approved=2)
    return JsonResponse({'success': True})

@csrf_exempt
@admin_required
def admin_delete_user(request, user_id):
    user = User.objects.filter(id=user_id).exclude(username='admin').first()
    if not user:
        return JsonResponse({'success': False, 'error': 'کاربر یافت نشد'})
    user.delete()
    return JsonResponse({'success': True})

@admin_required
def admin_add_interview(request):
    if request.method != 'POST':
        return redirect('admin_panel')
    
    Interview.objects.create(
        pharmacist_name=request.POST.get('pharmacist_name'),
        pharmacy_name=request.POST.get('pharmacy_name'),
        title=request.POST.get('title'),
        content=request.POST.get('content'),
        image_url=request.POST.get('image_url', ''),
        audio_url=request.POST.get('audio_url', ''),
        is_published=True
    )
    return redirect('admin_panel')

@csrf_exempt
@admin_required
def admin_toggle_interview(request, interview_id):
    interview = Interview.objects.filter(id=interview_id).first()
    if not interview:
        return JsonResponse({'success': False, 'error': 'مصاحبه یافت نشد'})
    interview.is_published = not interview.is_published
    interview.save()
    return JsonResponse({'success': True})

@csrf_exempt
@admin_required
def admin_delete_interview(request, interview_id):
    Interview.objects.filter(id=interview_id).delete()
    return JsonResponse({'success': True})

@admin_required
def admin_add_announcement(request):
    if request.method != 'POST':
        return redirect('admin_panel')
    
    Announcement.objects.create(
        title=request.POST.get('title'),
        content=request.POST.get('content'),
        is_active=True
    )
    return redirect('admin_panel')

@csrf_exempt
@admin_required
def admin_toggle_announcement(request, announcement_id):
    announcement = Announcement.objects.filter(id=announcement_id).first()
    if not announcement:
        return JsonResponse({'success': False, 'error': 'اطلاعیه یافت نشد'})
    announcement.is_active = not announcement.is_active
    announcement.save()
    return JsonResponse({'success': True})

@csrf_exempt
@admin_required
def admin_delete_announcement(request, announcement_id):
    Announcement.objects.filter(id=announcement_id).delete()
    return JsonResponse({'success': True})

# ===== ویوهای اضافی =====

@login_required
def exchange_view(request):
    pharmacies = User.objects.filter(is_approved=1).exclude(id=request.user.id)
    
    pharmacy_options = ''
    for p in pharmacies:
        pharmacy_options += f'<option value="{p.id}">{p.pharmacy_display_name}</option>'
    
    user_cat = UserCategory.objects.filter(user=request.user).first()
    user_categories = user_cat.categories.split(',') if user_cat and user_cat.categories else []
    
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
    <div class="exchange-tab">
        <button class="active" onclick="showExchangeTab('register')">🔄 ثبت تبادل</button>
        <button onclick="showExchangeTab('list')">📋 تبادلات من</button>
        <button onclick="showExchangeTab('pending')">⏳ درخواست‌های دریافتی</button>
    </div>
    
    <div id="registerTab" class="tab-content active">
        <div class="card">
            <div class="card-title">📋 دسته‌بندی مصرفی</div>
            <div class="category-checkboxes" id="categoryCheckboxes" style="display:flex;flex-wrap:wrap;gap:10px;padding:10px;background:#f8f9fa;border-radius:10px;">
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
    const USER_ID = {request.user.id};
    const csrftoken = getCookie('csrftoken');
    var selectedTargetPharmacy = null;
    var selectedTargetPharmacyName = '';
    var myDrugs = [];
    var targetDrugs = [];
    var selectedItems = [];
    var userCategories = [];
    var allMyExchanges = [];
    var exchangeAllDrugsData = [];
    var hiddenIds = new Set();
    
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
            headers: {{'Content-Type': 'application/json', 'X-CSRFToken': csrftoken}},
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
                'X-CSRFToken': csrftoken
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
        fetch('/api/get_exchanges')
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
        fetch('/api/get_pending_exchanges')
            .then(r=>r.json())
            .then(d=>{{
                var exchanges = d.exchanges || [];
                if(exchanges.length===0){{
                    document.getElementById('pendingExchangesList').innerHTML = '<p style="text-align:center;padding:30px;color:#999">هیچ تبادل دریافتی در انتظار تایید نیست</p>';
                    return;
                }}
                var html = '';
                exchanges.forEach(ex => {{
                    var date = new Date(ex.exchange_date);
                    var myItems = ex.my_items_json ? JSON.parse(ex.my_items_json) : [];
                    var targetItems = ex.target_items_json ? JSON.parse(ex.target_items_json) : [];
                    var sourceName = ex.source_pharmacy_name || 'داروخانه';
                    html += '<div class="exchange-card"><div class="exchange-card-header"><h4>🏥 ' + sourceName + ' به شما پیشنهاد تبادل داده است</h4><div class="date">' + date.toLocaleDateString('fa-IR') + ' ' + date.toLocaleTimeString('fa-IR') + '</div></div>';
                    html += '<div class="exchange-card-body">';
                    if(targetItems.length > 0) {{
                        html += '<div class="exchange-section"><div class="exchange-section-title" style="color:#dc3545;">📦 داروهایی که از شما درخواست کرده:</div><ul class="exchange-drug-list">';
                        html += targetItems.map(i => '<li><strong>' + i.name + '</strong> <span>' + i.quantity + ' عدد (انقضا: ' + (i.expiry_date || '-') + ')</span></li>').join('');
                        html += '</ul></div>';
                    }}
                    if(myItems.length > 0) {{
                        html += '<div class="exchange-section"><div class="exchange-section-title" style="color:#28a745;">📦 داروهایی که به شما می‌دهد:</div><ul class="exchange-drug-list">';
                        html += myItems.map(i => '<li><strong>' + i.name + '</strong> <span>' + i.quantity + ' عدد (انقضا: ' + (i.expiry_date || '-') + ')</span></li>').join('');
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
        let html = '<div style="max-height:500px;overflow-y:auto;">';
        exchanges.forEach(function(ex) {{
            const statusText = ex.status === 'confirmed' ? '✅ تایید شده' : '⏳ در انتظار';
            const statusColor = ex.status === 'confirmed' ? '#28a745' : '#ffc107';
            const date = new Date(ex.exchange_date);
            let pharmacyName = ex.buyer_name || 'نامشخص';
            if (ex.source_pharmacy_id && ex.source_pharmacy_id != 1) {{
                pharmacyName = ex.source_pharmacy_name || pharmacyName;
            }}
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
            if (ex.expiry_date) {{
                html += '<span>📅 انقضا: ' + ex.expiry_date + '</span>';
            }}
            html += '</div>';
            if (ex.status === 'pending') {{
                html += '<div style="margin-top:8px;">';
                html += '<button onclick="cancelExchange(' + ex.id + ')" class="btn-danger btn-sm" style="font-size:11px;padding:2px 8px;">❌ لغو درخواست</button>';
                html += '</div>';
            }}
            html += '</div>';
        }});
        html += '</div>';
        container.innerHTML = html;
    }}
    
    function cancelExchange(exchangeId) {{
        if (!confirm('آیا از لغو این درخواست تبادل اطمینان دارید؟')) return;
        fetch('/api/reject_exchange/' + exchangeId, {{ method: 'POST', headers: {{'X-CSRFToken': csrftoken}} }})
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
            fetch('/api/confirm_exchange/' + exchangeId, {{ method: 'POST', headers: {{'X-CSRFToken': csrftoken}} }})
                .then(r=>r.json()).then(data=>{{ 
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
            fetch('/api/reject_exchange/' + exchangeId, {{ method: 'POST', headers: {{'X-CSRFToken': csrftoken}} }})
                .then(r=>r.json()).then(data=>{{ 
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
    
    html = BASE_TEMPLATE
    html = html.replace('{% block title %}داروخانه{% endblock %}', '{% block title %}تبادل - داروخانه{% endblock %}')
    html = html.replace('{% block page_title %}صفحه اصلی{% endblock %}', '{% block page_title %}🔄 تبادل دارو{% endblock %}')
    html = html.replace('{% block content %}{% endblock %}', f'{{% block content %}}{content}{{% endblock %}}')
    
    return HttpResponse(html)

@login_required
def deficit_view(request):
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
    const USER_ID = ''' + str(request.user.id) + ''';
    const csrftoken = getCookie('csrftoken');
    
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
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken },
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
                headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrftoken},
                body: JSON.stringify({drug_ids: ids})
            }).then(r=>r.json()).then(data=>{
                if(data.success) { showToast('✅ داروها حذف شدند', 'success'); loadDrugs(); }
                else { showToast('خطا: ' + data.error, 'error'); }
            }).catch(() => showToast('❌ خطا در ارتباط با سرور', 'error'));
        }
    }
    
    function del(id) {
        if(confirm('حذف شود؟')) fetch('/api/delete_drug/'+id, {method:'POST', headers:{'X-CSRFToken': csrftoken}})
            .then(()=>loadDrugs()).catch(()=>showToast('❌ خطا', 'error'));
    }
    
    document.addEventListener('click', function(e) {
        if(!e.target.closest('.search-container')) {
            document.getElementById('suggestions').style.display = 'none';
        }
    });
    
    loadDrugs();
    </script>
    '''
    
    html = BASE_TEMPLATE
    html = html.replace('{% block title %}داروخانه{% endblock %}', '{% block title %}دفتر کسری - داروخانه{% endblock %}')
    html = html.replace('{% block page_title %}صفحه اصلی{% endblock %}', '{% block page_title %}📋 دفتر کسری{% endblock %}')
    html = html.replace('{% block content %}{% endblock %}', f'{{% block content %}}{content}{{% endblock %}}')
    
    return HttpResponse(html)

# ===== URL ها =====
urlpatterns = [
    # صفحات اصلی
    ('^/$', index),
    ('^/login$', login_view),
    ('^/register$', register_view),
    ('^/logout$', logout_view),
    ('^/dashboard$', dashboard),
    ('^/inventory$', inventory_view),
    ('^/exchange$', exchange_view),
    ('^/deficit$', deficit_view),
    ('^/admin-panel$', admin_panel),
    
    # API
    ('^/api/place_order$', api_place_order),
    ('^/api/add_inventory$', api_add_inventory),
    ('^/api/register_sale$', api_register_sale),
    ('^/api/move_inventory$', api_move_inventory),
    ('^/api/get_inventory_grouped_by_expiry$', api_get_inventory_grouped_by_expiry),
    ('^/api/get_all_pharmacies_drugs_grouped_by_expiry$', api_get_all_pharmacies_drugs_grouped_by_expiry),
    ('^/api/search_with_stock$', api_search_with_stock),
    ('^/api/delete_inventory_item/(\\d+)$', api_delete_inventory_item),
    ('^/api/delete_inventory_items$', api_delete_inventory_items),
    ('^/api/get_hidden_items$', api_get_hidden_items),
    ('^/api/toggle_hidden_items$', api_toggle_hidden_items),
    ('^/api/add_drug$', api_add_drug),
    ('^/api/get_drugs$', api_get_drugs),
    ('^/api/delete_drug/(\\d+)$', api_delete_drug),
    ('^/api/delete_drugs$', api_delete_drugs),
    ('^/api/register_exchange$', api_register_exchange),
    ('^/api/get_exchanges$', api_get_exchanges),
    ('^/api/get_pending_exchanges$', api_get_pending_exchanges),
    ('^/api/confirm_exchange/(\\d+)$', api_confirm_exchange),
    ('^/api/reject_exchange/(\\d+)$', api_reject_exchange),
    ('^/api/get_my_drugs_for_exchange$', api_get_my_drugs_for_exchange),
    ('^/api/get_pharmacy_drugs_for_exchange$', api_get_pharmacy_drugs_for_exchange),
    ('^/api/get_user_categories$', api_get_user_categories),
    ('^/api/save_user_categories$', api_save_user_categories),
    
    # ادمین
    ('^/admin/approve_user/(\\d+)$', admin_approve_user),
    ('^/admin/reject_user/(\\d+)$', admin_reject_user),
    ('^/admin/delete_user/(\\d+)$', admin_delete_user),
    ('^/admin/add_interview$', admin_add_interview),
    ('^/admin/toggle_interview/(\\d+)$', admin_toggle_interview),
    ('^/admin/delete_interview/(\\d+)$', admin_delete_interview),
    ('^/admin/add_announcement$', admin_add_announcement),
    ('^/admin/toggle_announcement/(\\d+)$', admin_toggle_announcement),
    ('^/admin/delete_announcement/(\\d+)$', admin_delete_announcement),
]

# ===== اجرا =====
if __name__ == '__main__':
    # ایجاد دیتابیس
    init_db()
    
    # اجرا
    print("=" * 50)
    print("✅ داروخانه با موفقیت راه اندازی شد")
    print("=" * 50)
    print("🌐 آدرس: http://0.0.0.0:8000")
    print("👑 ادمین: admin / admin123")
    print("📝 کاربران نمونه:")
    print("   nosratabadi / admin123")
    print("   soleymani / soleymani123")
    print("   A101 / drsaboori")
    print("   A102 / drjafari")
    print("=" * 50)
    print("⚠️ کاربران جدید پس از ثبت‌نام نیاز به تأیید ادمین دارند")
    print("=" * 50)
    
    from django.core.management import execute_from_command_line
    execute_from_command_line(['manage.py', 'runserver', '0.0.0.0:8000'])
