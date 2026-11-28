#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Obeida Trading Bot V8.0
نظام تحليل ثلاثي + أكواد تفعيل + تحكم كامل من تيليجرام + إحالة + نقاط
"""
import logging
import base64
import os
import sqlite3
import re
import requests
import threading
import time
import sys
import traceback
import asyncio
import json
import shutil
import hashlib
import secrets
import random
import string
from datetime import datetime, timedelta
from functools import wraps
from contextlib import contextmanager

from telegram import (
    Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)

from flask import (
    Flask, request, render_template_string, session, redirect, url_for
)
from PIL import Image
import pytz

# ============================================
# الإعدادات
# ============================================
TOKEN = os.environ.get('TOKEN')
if not TOKEN:
    raise ValueError("TOKEN مطلوب")

MISTRAL_KEY = os.environ.get('MISTRAL_KEY')
if not MISTRAL_KEY:
    raise ValueError("MISTRAL_KEY مطلوب")

MISTRAL_URL = "https://codex-relay.codes/v1/chat/completions"
MODELS_FOR_ANALYSIS = ["gpt-6.1-sol", "gpt-6-astra", "gpt-6-luna"]
MODEL_CHAT = "gpt-6-luna"

DB_NAME = "abood-gpt.db"
SUBSCRIPTION_DB_NAME = "subscription_system.db"
IMAGE_CACHE_DIR = "image_cache"
BACKUP_DIR = "backups"
MAX_IMAGE_SIZE = (1024, 1024)
IMAGE_QUALITY = 95

ADMIN_ID = int(os.environ.get('ADMIN_ID', '6207431030'))
SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(32))
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'Obeida059')
ADMIN_PASSWORD_RAW = os.environ.get('ADMIN_PASSWORD', 'Obeida059')
ADMIN_PASSWORD = hashlib.sha256(ADMIN_PASSWORD_RAW.encode()).hexdigest()

# القنوات الافتراضية (قابلة للتعديل من تيليجرام)
DEFAULT_CHANNELS = {
    'main': '@ObeidaTrading',
    'support': '@Sz2zv',
    'group': ''
}

CANDLE_SPEEDS = ["S5", "S10", "S15", "S30", "M1", "M2", "M3", "M5", "M10", "M15", "M30", "H1", "H4", "D1"]
TRADE_TIMES = ["قصير (1m-15m)", "متوسط (4h-Daily)", "طويل (Weekly-Monthly)"]

for d in [IMAGE_CACHE_DIR, BACKUP_DIR]:
    if not os.path.exists(d):
        os.makedirs(d)

# حالات المحادثة
(
    MAIN_MENU, SETTINGS_CANDLE, SETTINGS_TIME, CHAT_MODE, ANALYZE_MODE,
    RECOMMENDATION_MODE, CATEGORY_SELECTION, SUPPORT_MODE,
    ACTIVATE_CODE_MODE, ADMIN_MAIN, ADMIN_SETTINGS, ADMIN_USERS,
    ADMIN_GEN_CODE, ADMIN_CHANNELS, ADMIN_BROADCAST, ADMIN_ADD_SUB,
    ADMIN_USER_ACTION
) = range(17)

# ============================================
# الإعدادات الافتراضية
# ============================================
DEFAULT_SETTINGS = {
    'free_analyses_limit': 0,          # 0=قفل صارم
    'analysis_requires_subscription': 1,
    'channel_auto_post': 1,
    'channel_min_confidence': 85,
    'support_enabled': 1,
    'rate_limit_per_minute': 30,
    'referral_points': 10,
    'analysis_points': 1,
    'chat_points': 1,
}

# ============================================
# العملات
# ============================================
CATEGORIES = {
    "أزواج العملات 🏛️": [
        "EUR/USD (OTC)", "GBP/USD (OTC)", "USD/JPY (OTC)", "USD/CHF (OTC)",
        "AUD/USD (OTC)", "USD/CAD (OTC)", "NZD/USD (OTC)", "EUR/GBP (OTC)",
        "EUR/JPY (OTC)", "GBP/JPY (OTC)", "EUR/CHF (OTC)", "AUD/JPY (OTC)",
    ],
    "مؤشرات الأسواق 📊": [
        "S&P 500 (OTC)", "Dow Jones (OTC)", "Nasdaq 100 (OTC)",
        "DAX 40 (OTC)", "CAC 40 (OTC)", "FTSE 100 (OTC)",
    ],
    "سلع وطاقة 🕯️": [
        "Gold (OTC)", "Silver (OTC)", "UKOIL (OTC)",
        "USOIL (OTC)", "Natural Gas (OTC)",
    ],
    "أسهم الشركات 🍎": [
        "Apple (OTC)", "Amazon (OTC)", "Google (OTC)", "Facebook (OTC)",
        "Microsoft (OTC)", "Tesla (OTC)", "Netflix (OTC)", "Intel (OTC)",
    ]
}

TRADINGVIEW_SYMBOLS = {
    "EUR/USD (OTC)": "FX:EURUSD", "GBP/USD (OTC)": "FX:GBPUSD",
    "USD/JPY (OTC)": "FX:USDJPY", "USD/CHF (OTC)": "FX:USDCHF",
    "AUD/USD (OTC)": "FX:AUDUSD", "USD/CAD (OTC)": "FX:USDCAD",
    "NZD/USD (OTC)": "FX:NZDUSD", "EUR/GBP (OTC)": "FX:EURGBP",
    "EUR/JPY (OTC)": "FX:EURJPY", "GBP/JPY (OTC)": "FX:GBPJPY",
    "EUR/CHF (OTC)": "FX:EURCHF", "AUD/JPY (OTC)": "FX:AUDJPY",
    "S&P 500 (OTC)": "SP:SPX", "Dow Jones (OTC)": "DJ:DJI",
    "Nasdaq 100 (OTC)": "NASDAQ:NDX", "DAX 40 (OTC)": "GER30",
    "CAC 40 (OTC)": "FRA40", "FTSE 100 (OTC)": "UK100",
    "Gold (OTC)": "TVC:GOLD", "Silver (OTC)": "TVC:SILVER",
    "UKOIL (OTC)": "TVC:UKOIL", "USOIL (OTC)": "TVC:USOIL",
    "Natural Gas (OTC)": "TVC:NATGAS",
    "Apple (OTC)": "NASDAQ:AAPL", "Amazon (OTC)": "NASDAQ:AMZN",
    "Google (OTC)": "NASDAQ:GOOGL", "Facebook (OTC)": "NASDAQ:META",
    "Microsoft (OTC)": "NASDAQ:MSFT", "Tesla (OTC)": "NASDAQ:TSLA",
    "Netflix (OTC)": "NASDAQ:NFLX", "Intel (OTC)": "NASDAQ:INTC",
}

# ============================================
# أدوات قاعدة البيانات
# ============================================
@contextmanager
def db_conn(db_name=DB_NAME):
    conn = None
    try:
        conn = sqlite3.connect(db_name, timeout=30)
        yield conn
    finally:
        if conn:
            conn.close()


def log_change(action, user_id, details=""):
    try:
        with db_conn() as c:
            cur = c.cursor()
            cur.execute(
                "INSERT INTO data_log (action, user_id, details, timestamp) "
                "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                (action, user_id, details)
            )
            c.commit()
    except Exception:
        pass


# ============================================
# نظام الإعدادات
# ============================================
class SystemSettings:
    @staticmethod
    def init_db():
        with db_conn() as c:
            cur = c.cursor()
            cur.execute('''
                CREATE TABLE IF NOT EXISTS system_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_by INTEGER
                )
            ''')
            for k, v in DEFAULT_SETTINGS.items():
                cur.execute(
                    "INSERT OR IGNORE INTO system_settings (key, value) VALUES (?, ?)",
                    (k, str(v))
                )
            c.commit()

    @staticmethod
    def get(key, default=None):
        try:
            with db_conn() as c:
                cur = c.cursor()
                cur.execute("SELECT value FROM system_settings WHERE key = ?", (key,))
                row = cur.fetchone()
                if row:
                    try:
                        return int(row[0])
                    except ValueError:
                        return row[0]
            return default if default is not None else DEFAULT_SETTINGS.get(key)
        except Exception:
            return DEFAULT_SETTINGS.get(key)

    @staticmethod
    def set(key, value, updated_by=None):
        with db_conn() as c:
            cur = c.cursor()
            cur.execute('''
                INSERT OR REPLACE INTO system_settings (key, value, updated_by, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (key, str(value), updated_by))
            c.commit()
        log_change("settings_update", updated_by or 0, f"{key}={value}")


# ============================================
# نظام القنوات (ديناميكي)
# ============================================
class ChannelSettings:
    @staticmethod
    def init_db():
        with db_conn() as c:
            cur = c.cursor()
            cur.execute('''
                CREATE TABLE IF NOT EXISTS channel_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            for k, v in DEFAULT_CHANNELS.items():
                cur.execute(
                    "INSERT OR IGNORE INTO channel_settings (key, value) VALUES (?, ?)",
                    (k, v)
                )
            c.commit()

    @staticmethod
    def get(key='main'):
        try:
            with db_conn() as c:
                cur = c.cursor()
                cur.execute("SELECT value FROM channel_settings WHERE key = ?", (key,))
                row = cur.fetchone()
                return row[0] if row and row[0] else DEFAULT_CHANNELS.get(key, '')
        except Exception:
            return DEFAULT_CHANNELS.get(key, '')

    @staticmethod
    def set(key, value):
        with db_conn() as c:
            cur = c.cursor()
            cur.execute('''
                INSERT OR REPLACE INTO channel_settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (key, value))
            c.commit()


# ============================================
# نظام أكواد التفعيل
# ============================================
class ActivationCodes:
    SUBSCRIPTION_TYPES = {
        'hourly': {'name': 'ساعة', 'duration': 3600},
        'daily': {'name': 'يوم', 'duration': 86400},
        'weekly': {'name': 'أسبوع', 'duration': 604800},
        'monthly': {'name': 'شهر', 'duration': 2592000},
        'yearly': {'name': 'سنة', 'duration': 31536000},
        'lifetime': {'name': 'مدى الحياة', 'duration': -1},
    }

    @staticmethod
    def init_db():
        with db_conn() as c:
            cur = c.cursor()
            cur.execute('''
                CREATE TABLE IF NOT EXISTS activation_codes (
                    code TEXT PRIMARY KEY,
                    subscription_type TEXT NOT NULL,
                    duration_seconds INTEGER NOT NULL,
                    used_by INTEGER DEFAULT NULL,
                    used_at TIMESTAMP DEFAULT NULL,
                    created_by INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP DEFAULT NULL,
                    assigned_to INTEGER DEFAULT NULL,
                    notes TEXT DEFAULT ''
                )
            ''')
            c.commit()

    @staticmethod
    def generate_code(sub_type, created_by=ADMIN_ID, expires_days=None, assigned_to=None, notes=''):
        if sub_type not in ActivationCodes.SUBSCRIPTION_TYPES:
            return None
        # كود بصيغة OBEIDA-XXXX-XXXX
        parts = ['OBEIDA']
        for _ in range(2):
            parts.append(''.join(random.choices(string.ascii_uppercase + string.digits, k=4)))
        code = '-'.join(parts)
        
        duration = ActivationCodes.SUBSCRIPTION_TYPES[sub_type]['duration']
        expires_at = None
        if expires_days:
            expires_at = (datetime.now() + timedelta(days=expires_days)).isoformat()
        
        with db_conn() as c:
            cur = c.cursor()
            try:
                cur.execute('''
                    INSERT INTO activation_codes
                    (code, subscription_type, duration_seconds, created_by, expires_at, assigned_to, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (code, sub_type, duration, created_by, expires_at, assigned_to, notes))
                c.commit()
                return {
                    'code': code, 'sub_type': sub_type,
                    'duration': duration, 'expires_at': expires_at,
                    'assigned_to': assigned_to
                }
            except sqlite3.IntegrityError:
                # كود مكرر - أعد المحاولة
                return ActivationCodes.generate_code(sub_type, created_by, expires_days, assigned_to, notes)

    @staticmethod
    def validate_and_use(code, user_id):
        """يتحقق من الكود ويستخدمه - يرجع (نجاح، رسالة، بيانات)"""
        with db_conn() as c:
            cur = c.cursor()
            cur.execute("SELECT * FROM activation_codes WHERE code = ?", (code,))
            row = cur.fetchone()
            if not row:
                return False, "❌ كود غير موجود", None
            
            # row: code, sub_type, duration, used_by, used_at, created_by, created_at, expires_at, assigned_to, notes
            (c_code, sub_type, duration, used_by, used_at, created_by,
             created_at, expires_at, assigned_to, notes) = row
            
            if used_by is not None:
                return False, "❌ الكود مستخدم مسبقاً", None
            
            # تحقق من انتهاء صلاحية الكود
            if expires_at:
                try:
                    if datetime.fromisoformat(expires_at) < datetime.now():
                        return False, "❌ انتهت صلاحية الكود", None
                except Exception:
                    pass
            
            # تحقق من مخصص لمستخدم
            if assigned_to and assigned_to != user_id:
                return False, "❌ الكود مخصص لمستخدم آخر", None
            
            # استخدم الكود
            cur.execute('''
                UPDATE activation_codes
                SET used_by = ?, used_at = CURRENT_TIMESTAMP
                WHERE code = ?
            ''', (user_id, code))
            c.commit()
            
            return True, "✅ تم التفعيل", {
                'sub_type': sub_type, 'duration': duration
            }

    @staticmethod
    def get_stats():
        with db_conn() as c:
            cur = c.cursor()
            cur.execute("SELECT COUNT(*) FROM activation_codes")
            total = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM activation_codes WHERE used_by IS NOT NULL")
            used = cur.fetchone()[0]
            return {'total': total, 'used': used, 'available': total - used}

    @staticmethod
    def list_codes(limit=20, only_unused=True):
        with db_conn() as c:
            cur = c.cursor()
            q = "SELECT code, subscription_type, used_by, created_at, expires_at FROM activation_codes"
            if only_unused:
                q += " WHERE used_by IS NULL"
            q += " ORDER BY created_at DESC LIMIT ?"
            cur.execute(q, (limit,))
            return cur.fetchall()


# ============================================
# نظام الإحالة والنقاط
# ============================================
class ReferralSystem:
    @staticmethod
    def init_db():
        with db_conn() as c:
            cur = c.cursor()
            cur.execute('''
                CREATE TABLE IF NOT EXISTS referrals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    referrer_id INTEGER NOT NULL,
                    referred_id INTEGER UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS user_points (
                    user_id INTEGER PRIMARY KEY,
                    points INTEGER DEFAULT 0,
                    total_earned INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            c.commit()

    @staticmethod
    def get_or_create_user(user_id):
        with db_conn() as c:
            cur = c.cursor()
            cur.execute(
                "INSERT OR IGNORE INTO user_points (user_id, points) VALUES (?, 0)",
                (user_id,)
            )
            c.commit()
            cur.execute("SELECT points, total_earned FROM user_points WHERE user_id = ?", (user_id,))
            return cur.fetchone()

    @staticmethod
    def add_points(user_id, points, reason=''):
        with db_conn() as c:
            cur = c.cursor()
            cur.execute('''
                INSERT INTO user_points (user_id, points, total_earned, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    points = points + ?,
                    total_earned = total_earned + ?,
                    updated_at = CURRENT_TIMESTAMP
            ''', (user_id, points, points, points, points))
            c.commit()
        log_change("points_added", user_id, f"{points} ({reason})")

    @staticmethod
    def add_referral(referrer_id, referred_id):
        with db_conn() as c:
            cur = c.cursor()
            try:
                cur.execute(
                    "INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
                    (referrer_id, referred_id)
                )
                c.commit()
                points = SystemSettings.get('referral_points', 10)
                ReferralSystem.add_points(referrer_id, points, f"إحالة {referred_id}")
                return True
            except sqlite3.IntegrityError:
                return False

    @staticmethod
    def get_referral_count(user_id):
        with db_conn() as c:
            cur = c.cursor()
            cur.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
            return cur.fetchone()[0]

    @staticmethod
    def get_referral_link(bot_username, user_id):
        return f"https://t.me/{bot_username}?start=ref_{user_id}"


# ============================================
# نظام الدعم
# ============================================
class SupportSystem:
    @staticmethod
    def init_db():
        with db_conn() as c:
            cur = c.cursor()
            cur.execute('''
                CREATE TABLE IF NOT EXISTS support_tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    subject TEXT,
                    status TEXT DEFAULT 'open',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    admin_reply TEXT,
                    replied_at TIMESTAMP
                )
            ''')
            c.commit()

    @staticmethod
    def create_ticket(user_id, username, subject, message):
        with db_conn() as c:
            cur = c.cursor()
            cur.execute('''
                INSERT INTO support_tickets (user_id, username, subject)
                VALUES (?, ?, ?)
            ''', (user_id, username, f"{subject}: {message[:200]}"))
            tid = cur.lastrowid
            c.commit()
            return tid

    @staticmethod
    def add_reply(ticket_id, reply):
        with db_conn() as c:
            cur = c.cursor()
            cur.execute('''
                UPDATE support_tickets
                SET admin_reply = ?, replied_at = CURRENT_TIMESTAMP, status = 'answered'
                WHERE id = ?
            ''', (reply, ticket_id))
            c.commit()
            cur.execute("SELECT user_id FROM support_tickets WHERE id = ?", (ticket_id,))
            row = cur.fetchone()
            return row[0] if row else None

    @staticmethod
    def get_open():
        with db_conn() as c:
            cur = c.cursor()
            cur.execute('''
                SELECT id, user_id, username, subject, created_at, status
                FROM support_tickets WHERE status IN ('open','answered')
                ORDER BY created_at DESC LIMIT 30
            ''')
            return cur.fetchall()


# ============================================
# نظام الاشتراكات
# ============================================
class SubscriptionSystem:
    @staticmethod
    def init_db():
        with db_conn(SUBSCRIPTION_DB_NAME) as c:
            cur = c.cursor()
            cur.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    language_code TEXT,
                    is_bot BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_blocked BOOLEAN DEFAULT 0,
                    blocked_reason TEXT
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS active_subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    subscription_type TEXT NOT NULL,
                    subscription_name TEXT NOT NULL,
                    start_date TIMESTAMP NOT NULL,
                    end_date TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    added_by INTEGER,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS usage_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    feature TEXT NOT NULL,
                    count INTEGER DEFAULT 0,
                    last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, feature)
                )
            ''')
            c.commit()

    @staticmethod
    def register_user(user_id, username=None, first_name=None, last_name=None, language_code=None, is_bot=False):
        with db_conn(SUBSCRIPTION_DB_NAME) as c:
            cur = c.cursor()
            cur.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            if cur.fetchone():
                cur.execute('''
                    UPDATE users SET last_active = CURRENT_TIMESTAMP,
                        username = COALESCE(?, username),
                        first_name = COALESCE(?, first_name)
                    WHERE user_id = ?
                ''', (username, first_name, user_id))
            else:
                cur.execute('''
                    INSERT INTO users (user_id, username, first_name, last_name, language_code, is_bot)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (user_id, username, first_name, last_name, language_code, is_bot))
            c.commit()

    @staticmethod
    def add_subscription(user_id, sub_type, added_by=ADMIN_ID, duration_seconds=None):
        types = {
            'hourly': {'name': 'ساعة', 'dur': 3600},
            'daily': {'name': 'يوم', 'dur': 86400},
            'weekly': {'name': 'أسبوع', 'dur': 604800},
            'monthly': {'name': 'شهر', 'dur': 2592000},
            'yearly': {'name': 'سنة', 'dur': 31536000},
            'lifetime': {'name': 'مدى الحياة', 'dur': -1},
        }
        if sub_type not in types:
            return False, "نوع غير صالح"
        
        dur = duration_seconds if duration_seconds is not None else types[sub_type]['dur']
        start = datetime.now()
        end = None if dur < 0 else start + timedelta(seconds=dur)
        
        with db_conn(SUBSCRIPTION_DB_NAME) as c:
            cur = c.cursor()
            cur.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            if not cur.fetchone():
                cur.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
            cur.execute('''
                UPDATE active_subscriptions SET is_active = 0
                WHERE user_id = ? AND is_active = 1
            ''', (user_id,))
            cur.execute('''
                INSERT INTO active_subscriptions
                (user_id, subscription_type, subscription_name, start_date, end_date, is_active, added_by)
                VALUES (?, ?, ?, ?, ?, 1, ?)
            ''', (user_id, sub_type, types[sub_type]['name'],
                  start.isoformat(), end.isoformat() if end else None, added_by))
            c.commit()
        
        SubscriptionSystem._sync_main(user_id, end.isoformat() if end else None)
        return True, {'name': types[sub_type]['name'], 'end': end.isoformat() if end else None}

    @staticmethod
    def _sync_main(user_id, end_date):
        try:
            with db_conn() as c:
                cur = c.cursor()
                cur.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
                if cur.fetchone():
                    cur.execute(
                        "UPDATE users SET subscription_end = ? WHERE user_id = ?",
                        (end_date, user_id)
                    )
                else:
                    cur.execute('''
                        INSERT INTO users (user_id, subscription_end, candle, trade_time, country_timezone)
                        VALUES (?, ?, 'M1', 'قصير (1m-15m)', 'Asia/Gaza')
                    ''', (user_id, end_date))
                c.commit()
        except Exception as e:
            print(f"⚠️ sync: {e}")

    @staticmethod
    def check_subscription(user_id):
        try:
            with db_conn(SUBSCRIPTION_DB_NAME) as c:
                cur = c.cursor()
                cur.execute("SELECT is_blocked FROM users WHERE user_id = ?", (user_id,))
                row = cur.fetchone()
                if row and row[0] == 1:
                    return False, "محظور", None
                cur.execute('''
                    SELECT subscription_type, subscription_name, start_date, end_date
                    FROM active_subscriptions
                    WHERE user_id = ? AND is_active = 1
                    ORDER BY id DESC LIMIT 1
                ''', (user_id,))
                row = cur.fetchone()
                if not row:
                    return False, "لا اشتراك", None
                sub_type, name, start, end = row
                if end:
                    try:
                        if datetime.fromisoformat(end) < datetime.now():
                            cur.execute('''
                                UPDATE active_subscriptions SET is_active = 0
                                WHERE user_id = ? AND is_active = 1
                            ''', (user_id,))
                            c.commit()
                            return False, "انتهى", None
                    except Exception:
                        pass
                return True, name, {'type': sub_type, 'name': name,
                                     'start': start, 'end': end}
        except Exception as e:
            return False, str(e), None

    @staticmethod
    def increment_usage(user_id, feature):
        try:
            with db_conn(SUBSCRIPTION_DB_NAME) as c:
                cur = c.cursor()
                cur.execute('''
                    INSERT INTO usage_stats (user_id, feature, count)
                    VALUES (?, ?, 1)
                    ON CONFLICT(user_id, feature) DO UPDATE SET
                        count = count + 1, last_used = CURRENT_TIMESTAMP
                ''', (user_id, feature))
                c.commit()
        except Exception:
            pass

    @staticmethod
    def get_user_stats(user_id):
        try:
            with db_conn(SUBSCRIPTION_DB_NAME) as c:
                cur = c.cursor()
                cur.execute('''
                    SELECT feature, count FROM usage_stats
                    WHERE user_id = ?
                ''', (user_id,))
                return dict(cur.fetchall())
        except Exception:
            return {}

    @staticmethod
    def get_all_users(limit=100):
        with db_conn(SUBSCRIPTION_DB_NAME) as c:
            cur = c.cursor()
            cur.execute('''
                SELECT u.user_id, u.username, u.first_name, u.created_at,
                       u.last_active, u.is_blocked, a.subscription_name, a.end_date
                FROM users u
                LEFT JOIN active_subscriptions a
                ON u.user_id = a.user_id AND a.is_active = 1
                ORDER BY u.created_at DESC LIMIT ?
            ''', (limit,))
            return cur.fetchall()

    @staticmethod
    def get_stats():
        s = {'total_users': 0, 'active_users': 0, 'blocked_users': 0}
        try:
            with db_conn(SUBSCRIPTION_DB_NAME) as c:
                cur = c.cursor()
                cur.execute("SELECT COUNT(*) FROM users")
                s['total_users'] = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM users WHERE is_blocked = 1")
                s['blocked_users'] = cur.fetchone()[0]
                cur.execute('''
                    SELECT COUNT(DISTINCT user_id) FROM active_subscriptions
                    WHERE is_active = 1 AND (end_date IS NULL OR end_date > datetime('now'))
                ''')
                s['active_users'] = cur.fetchone()[0]
        except Exception:
            pass
        return s

    @staticmethod
    def block_user(user_id, reason=""):
        with db_conn(SUBSCRIPTION_DB_NAME) as c:
            cur = c.cursor()
            cur.execute(
                "UPDATE users SET is_blocked = 1, blocked_reason = ? WHERE user_id = ?",
                (reason, user_id)
            )
            cur.execute('''
                UPDATE active_subscriptions SET is_active = 0
                WHERE user_id = ? AND is_active = 1
            ''', (user_id,))
            c.commit()
        return True

    @staticmethod
    def unblock_user(user_id):
        with db_conn(SUBSCRIPTION_DB_NAME) as c:
            cur = c.cursor()
            cur.execute(
                "UPDATE users SET is_blocked = 0, blocked_reason = NULL WHERE user_id = ?",
                (user_id,)
            )
            c.commit()
        return True

    @staticmethod
    def revoke_subscription(user_id):
        with db_conn(SUBSCRIPTION_DB_NAME) as c:
            cur = c.cursor()
            cur.execute('''
                UPDATE active_subscriptions SET is_active = 0
                WHERE user_id = ? AND is_active = 1
            ''', (user_id,))
            c.commit()
        SubscriptionSystem._sync_main(user_id, None)
        return True


# ============================================
# Rate Limiting
# ============================================
class RateLimiter:
    def __init__(self):
        self.calls = {}  # {user_id: [timestamps]}
        self.lock = threading.Lock()

    def is_allowed(self, user_id, limit_per_minute=None):
        if user_id == ADMIN_ID:
            return True
        limit = limit_per_minute or SystemSettings.get('rate_limit_per_minute', 30)
        now = time.time()
        with self.lock:
            user_calls = self.calls.get(user_id, [])
            user_calls = [t for t in user_calls if now - t < 60]
            if len(user_calls) >= limit:
                self.calls[user_id] = user_calls
                return False
            user_calls.append(now)
            self.calls[user_id] = user_calls
            return True


rate_limiter = RateLimiter()


# ============================================
# Cache للتحليل
# ============================================
analysis_cache = {}  # {key: {'result': ..., 'timestamp': ...}}
cache_lock = threading.Lock()


def cache_get(key):
    with cache_lock:
        item = analysis_cache.get(key)
        if item and time.time() - item['timestamp'] < 300:  # 5 دقائق
            return item['result']
        return None


def cache_set(key, result):
    with cache_lock:
        analysis_cache[key] = {'result': result, 'timestamp': time.time()}


# ============================================
# أدوات صور
# ============================================
def compress_image(path, max_size=MAX_IMAGE_SIZE, quality=IMAGE_QUALITY):
    try:
        with Image.open(path) as img:
            if img.mode in ('RGBA', 'LA', 'P'):
                bg = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGB')
                elif img.mode == 'RGBA':
                    bg.paste(img, mask=img.split()[-1])
                    img = bg
                else:
                    img = img.convert('RGB')
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            out = path.replace('.jpg', '_c.jpg').replace('.png', '_c.jpg')
            img.save(out, 'JPEG', quality=quality, optimize=True)
            return out
    except Exception as e:
        print(f"compress: {e}")
        return path


def encode_image(path):
    try:
        with open(path, 'rb') as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return None


# ============================================
# جلسة السوق التلقائية
# ============================================
def get_user_timezone(user_id):
    try:
        with db_conn() as c:
            cur = c.cursor()
            cur.execute("SELECT country_timezone FROM users WHERE user_id = ?", (user_id,))
            row = cur.fetchone()
            return row[0] if row and row[0] else 'Asia/Gaza'
    except Exception:
        return 'Asia/Gaza'


def get_market_session(user_id=None):
    try:
        utc = datetime.now(pytz.UTC)
        h = utc.hour
        if 13 <= h < 17:
            main, vol = "لندن + نيويورك", "عالية جداً 🔥"
        elif 8 <= h < 13:
            main, vol = "لندن", "مرتفعة 📈"
        elif 13 <= h < 22:
            main, vol = "نيويورك", "عالية 📊"
        elif 0 <= h < 9:
            main, vol = "طوكيو/آسيا", "منخفضة 📉"
        else:
            main, vol = "سيدني", "منخفضة 💤"
        
        tz = pytz.timezone(get_user_timezone(user_id) if user_id else 'Asia/Gaza')
        local = datetime.now(tz)
        return {
            'session': main, 'volatility': vol,
            'utc_time': utc.strftime('%H:%M UTC'),
            'local_time': local.strftime('%H:%M'),
            'utc_hour': h,
        }
    except Exception:
        return {'session': 'عالمية', 'volatility': 'متوسطة',
                'utc_time': '--:--', 'local_time': '--:--', 'utc_hour': 12}


# ============================================
# إعدادات المستخدم
# ============================================
def save_user_setting(user_id, col, val):
    with db_conn() as c:
        cur = c.cursor()
        cur.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if not cur.fetchone():
            cur.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        cur.execute(f"UPDATE users SET {col} = ? WHERE user_id = ?", (val, user_id))
        c.commit()


def get_user_setting(user_id):
    try:
        with db_conn() as c:
            cur = c.cursor()
            cur.execute(
                "SELECT candle, trade_time, last_analysis_context, last_analysis_time "
                "FROM users WHERE user_id = ?", (user_id,)
            )
            row = cur.fetchone()
            if row:
                return row
    except Exception:
        pass
    return ("M1", "قصير (1m-15m)", "", None)


def save_analysis_context(user_id, text):
    try:
        with db_conn() as c:
            cur = c.cursor()
            cur.execute(
                "UPDATE users SET last_analysis_context = ?, last_analysis_time = CURRENT_TIMESTAMP "
                "WHERE user_id = ?", (text[:500], user_id)
            )
            c.commit()
    except Exception:
        pass


# ============================================
# سحب الشارت من TradingView
# ============================================
def download_chart(symbol, candle="M1"):
    try:
        tv = TRADINGVIEW_SYMBOLS.get(symbol, "FX:EURUSD")
        interval_map = {"S5":"5S","S10":"10S","S15":"15S","S30":"30S",
                        "M1":"1","M2":"2","M3":"3","M5":"5","M10":"10",
                        "M15":"15","M30":"30","H1":"60","H4":"240","D1":"D"}
        interval = interval_map.get(candle, "1")
        key = os.environ.get('SCREENSHOT_API_KEY', 'c94425')
        chart_url = f"https://www.tradingview.com/chart/?symbol={tv}&interval={interval}&theme=dark"
        api = (f"https://api.screenshotmachine.com/?key={key}"
               f"&url={chart_url}&dimension=1280x800&device=desktop"
               f"&delay=3000&format=png&cacheLimit=0")
        r = requests.get(api, timeout=45)
        if r.status_code == 200 and len(r.content) > 5000:
            ts = int(time.time())
            safe = re.sub(r'[^\w]', '_', symbol)
            p = os.path.join(IMAGE_CACHE_DIR, f"chart_{safe}_{candle}_{ts}.png")
            with open(p, "wb") as f:
                f.write(r.content)
            return p
        return None
    except Exception as e:
        print(f"download: {e}")
        return None


# ============================================
# Backup تلقائي
# ============================================
def backup_databases():
    try:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        for db in [DB_NAME, SUBSCRIPTION_DB_NAME]:
            if os.path.exists(db):
                dst = os.path.join(BACKUP_DIR, f"{db}_{ts}.bak")
                shutil.copy2(db, dst)
        # احتفظ بآخر 7 نسخ فقط
        for db in [DB_NAME, SUBSCRIPTION_DB_NAME]:
            pattern = f"{db}_"
            files = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith(pattern)],
                          reverse=True)
            for old in files[7:]:
                try:
                    os.remove(os.path.join(BACKUP_DIR, old))
                except Exception:
                    pass
        print(f"✅ Backup: {ts}")
    except Exception as e:
        print(f"backup: {e}")


# ============================================
# تهيئة كل قواعد البيانات
# ============================================
def init_all_dbs():
    # main DB
    with db_conn() as c:
        cur = c.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                candle TEXT DEFAULT 'M1',
                trade_time TEXT DEFAULT 'قصير (1m-15m)',
                chat_context TEXT DEFAULT '',
                last_analysis_context TEXT DEFAULT '',
                last_analysis_time DATETIME DEFAULT NULL,
                subscription_start DATETIME DEFAULT NULL,
                subscription_end DATETIME DEFAULT NULL,
                is_admin INTEGER DEFAULT 0,
                country_timezone TEXT DEFAULT 'Asia/Gaza'
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS data_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT, user_id INTEGER, details TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cur.execute("SELECT user_id FROM users WHERE user_id = ?", (ADMIN_ID,))
        if cur.fetchone():
            cur.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (ADMIN_ID,))
        else:
            cur.execute('''
                INSERT INTO users (user_id, username, is_admin, country_timezone)
                VALUES (?, 'Admin', 1, 'Asia/Gaza')
            ''', (ADMIN_ID,))
        c.commit()
    
    SystemSettings.init_db()
    ChannelSettings.init_db()
    ActivationCodes.init_db()
    ReferralSystem.init_db()
    SupportSystem.init_db()
    SubscriptionSystem.init_db()
    print("✅ All DBs initialized")

# ============================================
# برومبتات التحليل الثلاثي
# ============================================
def _build_prompt_sol(symbol, candle, trade_time, candles_count, session):
    duration = {
        "قصير (1m-15m)": "سكالبينج سريع (1-15 دقيقة)",
        "متوسط (4h-Daily)": "سوينج متوسط (4 ساعات - يومي)",
        "طويل (Weekly-Monthly)": "استثماري طويل (أسبوعي - شهري)"
    }.get(trade_time, trade_time)

    return f"""أنت **المحلل البصري الهجومي V8.0** — خبير استخراج البيانات من صور الشارت بدقة بكسل.

📋 **بيانات الجلسة:**
- الأصل: {symbol} | الفريم: {candle} | الشموع: {candles_count}
- المدة: {duration} | الجلسة: {session['session']} ({session['utc_time']}) - {session['volatility']}

🎯 **دورك:** وكيل شراء/بيع — إذا وُجد اتجاه ≥55%، **يجب** إعطاء قرار.
"احتفاظ" مسموح فقط إذا: 3 شموع دوجي متتالية + لا كسر + لا ارتداد.

🔍 **الفحص بالترتيب:**
1) صورة صالحة؟ إذا لا → `• بروتوكول الفشل الذاتي: الصورة غير صالحة - يرجى إرسال صورة أوضح` وتوقف
2) استخراج: السعر الحالي، وقت المنصة، أعلى قمة/أدنى قاع
3) الهيكل: BOS/CHoCH/OB/FVG
4) الزخم: جسم آخر 3 شموع >60% = قوي
5) الثواني المنقضية: 10-40 = داخل النافذة الذهبية
6) القرار: صاعد+زخم+كسر = شراء 🟢 | هابط+زخم+كسر = بيع 🔴 | قمة/قاع+ذيل = فخ 🚨

📤 **أجب بالتنسيق التالي حرفياً فقط:**

📊 التحليل الفني المتقدم:
• بروتوكول الفشل الذاتي: [الصورة صالحة / الصورة غير صالحة - يرجى إرسال صورة أوضح]
• الوقت على المنصة (المرجع): [الوقت المستخرج من الصورة]
• حالة الهيكل: [صاعد/هابط/متذبذب] + (توافق 4/4 إطارات: نعم / لا)
• خريطة السيولة: [أقرب فخ سيولة Inducement] + [مناطق السيولة المستهدفة]
• الثواني المنقضية: [X] ثانية (نافذة التنفيذ: [داخل/خارج] النافذة الذهبية)

🎯 الإشارة التنفيذية:
• السعر الحالي: [السعر الدقيق من الشارت]
• نقطة الدخول المعدلة: [السعر بعد معامل الانزلاق إن وجد - أو نقطة إعادة الاختبار]
• حالة الشمعة: [مفتوحة / مغلقة] [حمراء 🔴 / خضراء 🟢] - الوقت المتبقي: [الوقت الدقيق من ساعة المنصة]
• القرار الفني: [شراء 🟢 / بيع 🔴 / كسر هيكلي 💥 / سحب سيولة 🔄 / انعكاس فوري 🔄 / فخ سيولة 🚨]
• قوة الإشارة: [عالية جدا 💥 / عالية 🔥 / متوسطة ⚡ / ضعيفة ❄️]
• نقطة الدخول: [السعر الدقيق + شرط الدخول - يفضل إعادة اختبار المستوى]
• نوع الدخول 🚨: [دخول مباشر / إعادة اختبار / انعكاس فوري]
• وقت الدخول: [ فوري (Flash) / بعد إغلاق الشمعة الحالية / بعد إعادة اختبار المستوى]
• الأهداف الربحية:
  🎯 TP1: [السعر] - [سحب أول سيولة داخلية] - [احتمالية الوصول: عالية/متوسطة/منخفضة]
  🎯 TP2: [السعر] - [الهدف الرئيسي - منطقة عرض/طلب قوية] - [احتمالية الوصول: عالية/متوسطة/منخفضة]
  🎯 TP3: [السعر] - [سيولة خارجية أو سد فجوة سعرية] - [احتمالية الوصول: عالية/متوسطة/منخفضة]
• وقف الخسارة: [السعر] - [مع 3 طبقات حماية]
• المدة المتوقعة: [عدد الدقائق/الساعات]
• وقت الذروة المتوقع: [خلال الـ X شموع القادمة / بعد X دقيقة]

⚠️ إدارة المخاطر:
• مستوى الثقة: [0-100]٪ = [💥/🔥/⚡/🔄/❄️/🚫]
• نسبة نجاح الصفقة المتوقعة (V8.0): [XX]% - [التقييم: ممتاز/جيد/متوسط/ضعيف]
• 🚨 تنبيه فخ السيولة: [نشط / غير نشط] - [إذا نشط: تفاصيل التنبيه]

الآن حلل الشارت المرفق بتركيز كامل على استخراج البيانات، وأعطني الإجابة بالتنسيق أعلاه فقط.
"""


def _build_prompt_astra(symbol, candle, trade_time, candles_count, session):
    duration = {
        "قصير (1m-15m)": "سكالبينج (1-15 د)",
        "متوسط (4h-Daily)": "سوينج (4h - D)",
        "طويل (Weekly-Monthly)": "استثماري (W - M)"
    }.get(trade_time, trade_time)

    return f"""أنت **المحلل الهيكلي المنطقي V8.0** — خبير SMC/Wyckoff/Volume Profile.

📋 **بيانات الجلسة:**
- الأصل: {symbol} | الفريم: {candle} | الشموع: {candles_count}
- المدة: {duration} | الجلسة: {session['session']} ({session['utc_time']})

🎯 **دورك:** المدقق المنطقي — منع فخاخ السيولة. لكن **لا تُفرط في الحذر**.
"احتفاظ" مسموح فقط عند: تعارض 4/4 إطارات + لا كسر + لا ارتداد.

🔬 **التدقيق بالترتيب:**
1) صورة صالحة؟ إذا لا → `• بروتوكول الفشل الذاتي: الصورة غير صالحة - يرجى إرسال صورة أوضح` وتوقف
2) HH/HL vs LH/LL (آخر 3 قمم + آخر 3 قيعان)
3) BSL/SSL/Inducement/FVG
4) Order Block نشط
5) الزخم المؤسسي (شموع كبيرة متتالية)
6) القرار: BOS صاعد+OB=شراء 🟢 | BOS هابط+OB=بيع 🔴 | كسر بحجم=كسر 💥 | كسر وهمي+ارتداد=سحب 🔄

⚠️ إذا وُجد OB/FVG في اتجاهك → **لا تختر احتفاظ**.

📤 **أجب بالتنسيق التالي حرفياً فقط:**

📊 التحليل الفني المتقدم:
• بروتوكول الفشل الذاتي: [الصورة صالحة / الصورة غير صالحة - يرجى إرسال صورة أوضح]
• الوقت على المنصة (المرجع): [الوقت المستخرج من الصورة]
• حالة الهيكل: [صاعد/هابط/متذبذب] + (توافق 4/4 إطارات: نعم / لا)
• خريطة السيولة: [أقرب فخ سيولة Inducement] + [مناطق السيولة المستهدفة]
• الثواني المنقضية: [X] ثانية (نافذة التنفيذ: [داخل/خارج] النافذة الذهبية)

🎯 الإشارة التنفيذية:
• السعر الحالي: [السعر الدقيق من الشارت]
• نقطة الدخول المعدلة: [السعر بعد معامل الانزلاق إن وجد - أو نقطة إعادة الاختبار]
• حالة الشمعة: [مفتوحة / مغلقة] [حمراء 🔴 / خضراء 🟢] - الوقت المتبقي: [الوقت الدقيق من ساعة المنصة]
• القرار الفني: [شراء 🟢 / بيع 🔴 / كسر هيكلي 💥 / سحب سيولة 🔄 / انعكاس فوري 🔄 / فخ سيولة 🚨]
• قوة الإشارة: [عالية جدا 💥 / عالية 🔥 / متوسطة ⚡ / ضعيفة ❄️]
• نقطة الدخول: [السعر الدقيق + شرط الدخول - يفضل إعادة اختبار المستوى]
• نوع الدخول 🚨: [دخول مباشر / إعادة اختبار / انعكاس فوري]
• وقت الدخول: [ فوري (Flash) / بعد إغلاق الشمعة الحالية / بعد إعادة اختبار المستوى]
• الأهداف الربحية:
  🎯 TP1: [السعر] - [سحب أول سيولة داخلية] - [احتمالية الوصول: عالية/متوسطة/منخفضة]
  🎯 TP2: [السعر] - [الهدف الرئيسي - منطقة عرض/طلب قوية] - [احتمالية الوصول: عالية/متوسطة/منخفضة]
  🎯 TP3: [السعر] - [سيولة خارجية أو سد فجوة سعرية] - [احتمالية الوصول: عالية/متوسطة/منخفضة]
• وقف الخسارة: [السعر] - [مع 3 طبقات حماية]
• المدة المتوقعة: [عدد الدقائق/الساعات]
• وقت الذروة المتوقع: [خلال الـ X شموع القادمة / بعد X دقيقة]

⚠️ إدارة المخاطر:
• مستوى الثقة: [0-100]٪ = [💥/🔥/⚡/🔄/❄️/🚫]
• نسبة نجاح الصفقة المتوقعة (V8.0): [XX]% - [التقييم: ممتاز/جيد/متوسط/ضعيف]
• 🚨 تنبيه فخ السيولة: [نشط / غير نشط] - [إذا نشط: تفاصيل التنبيه]

الآن حلل الشارت المرفق وأعطني الإجابة بالتنسيق أعلاه فقط.
"""


def _build_prompt_luna(symbol, candle, trade_time, candles_count, session):
    duration = {
        "قصير (1m-15m)": "سكالبينج خاطف (1-15 د)",
        "متوسط (4h-Daily)": "سوينج (4h - D)",
        "طويل (Weekly-Monthly)": "استثماري (W - M)"
    }.get(trade_time, trade_time)

    return f"""أنت **صائد الزخم السريع V8.0** — قناص فرص فوري.

📋 **بيانات الجلسة:**
- الأصل: {symbol} | الفريم: {candle} | الشموع: {candles_count}
- المدة: {duration} | الجلسة: {session['session']} ({session['utc_time']})

🎯 **دورك:** القناص السريع — "الفرصة لا تنتظر".
- 3 شموع متتالية بأجسام >60% → **فرصة، ادخل فوراً**.
- "احتفاظ" مسموح فقط عند: دوجي متتالي + لا حجم + لا اتجاه.

⚡ **القنص:**
1) صورة صالحة؟ إذا لا → `• بروتوكول الفشل الذاتي: الصورة غير صالحة - يرجى إرسال صورة أوضح` وتوقف
2) الزخم: 3 شموع >60% جسم = قوي 🔥 | <30% = لا زخم ❄️
3) تسارع: الشمعة الأخيرة أكبر من السابقة = تسارع ✅
4) الفتيلة: ذيل >50% = رفض سعري
5) التوقيت: منتصف الشمعة (10-40 ث) = داخل النافذة ✅
6) القرار: زخم صاعد+تسارع = شراء 🟢 فوري | هابط+تسارع = بيع 🔴 فوري | ذيل+تباطؤ = انعكاس 🔄

⚠️ **لا تنتظر المثالي** — إذا الزخم >60%، ادخل.
⚠️ إذا الشمعة >2x السابقة → احتمال إجهاد → احتفاظ ذكي.

📤 **أجب بالتنسيق التالي حرفياً فقط:**

📊 التحليل الفني المتقدم:
• بروتوكول الفشل الذاتي: [الصورة صالحة / الصورة غير صالحة - يرجى إرسال صورة أوضح]
• الوقت على المنصة (المرجع): [الوقت المستخرج من الصورة]
• حالة الهيكل: [صاعد/هابط/متذبذب] + (توافق 4/4 إطارات: نعم / لا)
• خريطة السيولة: [أقرب فخ سيولة Inducement] + [مناطق السيولة المستهدفة]
• الثواني المنقضية: [X] ثانية (نافذة التنفيذ: [داخل/خارج] النافذة الذهبية)

🎯 الإشارة التنفيذية:
• السعر الحالي: [السعر الدقيق من الشارت]
• نقطة الدخول المعدلة: [السعر بعد معامل الانزلاق إن وجد - أو نقطة إعادة الاختبار]
• حالة الشمعة: [مفتوحة / مغلقة] [حمراء 🔴 / خضراء 🟢] - الوقت المتبقي: [الوقت الدقيق من ساعة المنصة]
• القرار الفني: [شراء 🟢 / بيع 🔴 / كسر هيكلي 💥 / سحب سيولة 🔄 / انعكاس فوري 🔄 / فخ سيولة 🚨]
• قوة الإشارة: [عالية جدا 💥 / عالية 🔥 / متوسطة ⚡ / ضعيفة ❄️]
• نقطة الدخول: [السعر الدقيق + شرط الدخول - يفضل إعادة اختبار المستوى]
• نوع الدخول 🚨: [دخول مباشر / إعادة اختبار / انعكاس فوري]
• وقت الدخول: [ فوري (Flash) / بعد إغلاق الشمعة الحالية / بعد إعادة اختبار المستوى]
• الأهداف الربحية:
  🎯 TP1: [السعر] - [سحب أول سيولة داخلية] - [احتمالية الوصول: عالية/متوسطة/منخفضة]
  🎯 TP2: [السعر] - [الهدف الرئيسي - منطقة عرض/طلب قوية] - [احتمالية الوصول: عالية/متوسطة/منخفضة]
  🎯 TP3: [السعر] - [سيولة خارجية أو سد فجوة سعرية] - [احتمالية الوصول: عالية/متوسطة/منخفضة]
• وقف الخسارة: [السعر] - [مع 3 طبقات حماية]
• المدة المتوقعة: [عدد الدقائق/الساعات]
• وقت الذروة المتوقع: [خلال الـ X شموع القادمة / بعد X دقيقة]

⚠️ إدارة المخاطر:
• مستوى الثقة: [0-100]٪ = [💥/🔥/⚡/🔄/❄️/🚫]
• نسبة نجاح الصفقة المتوقعة (V8.0): [XX]% - [التقييم: ممتاز/جيد/متوسط/ضعيف]
• 🚨 تنبيه فخ السيولة: [نشط / غير نشط] - [إذا نشط: تفاصيل التنبيه]

الآن حلل الشارت المرفق وأعطني الإجابة بالتنسيق أعلاه فقط.
"""


PROMPT_BUILDERS = {
    "gpt-6.1-sol": _build_prompt_sol,
    "gpt-6-astra": _build_prompt_astra,
    "gpt-6-luna": _build_prompt_luna,
}


# ============================================
# محرك التحليل الثلاثي
# ============================================
async def _call_model(model, prompt, image_b64, max_tokens=1800):
    headers = {
        "Authorization": f"Bearer {MISTRAL_KEY}",
        "Content-Type": "application/json"
    }
    body = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}}
            ]
        }],
        "max_tokens": max_tokens,
        "temperature": 0.15,
        "top_p": 0.95
    }
    try:
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(
            None,
            lambda: requests.post(MISTRAL_URL, json=body, headers=headers, timeout=90)
        )
        if r.status_code == 200:
            return {'model': model, 'success': True,
                    'content': r.json()['choices'][0]['message']['content']}
        return {'model': model, 'success': False, 'error': f"HTTP {r.status_code}"}
    except Exception as e:
        return {'model': model, 'success': False, 'error': str(e)}


def _extract_number(text):
    if not text:
        return None
    m = re.search(r'-?\d+[.,]?\d*', str(text).replace(',', '.'))
    if m:
        try:
            return float(m.group(0))
        except ValueError:
            return None
    return None


def _map_decision(raw):
    d = (raw or '').lower()
    if 'شراء' in d or 'buy' in d: return 'BUY'
    if 'بيع' in d or 'sell' in d: return 'SELL'
    if 'كسر' in d or 'breakout' in d: return 'BREAKOUT'
    if 'سحب سيولة' in d or 'sweep' in d: return 'SWEEP'
    if 'انعكاس' in d or 'reversal' in d: return 'REVERSAL'
    if 'فخ' in d or 'trap' in d: return 'TRAP'
    return 'HOLD'


def _parse_response(content):
    if not content:
        return {'valid': False, 'decision': 'HOLD', 'confidence': 0}
    
    text = content.strip()
    p = {
        'valid': True, 'image_valid': True, 'platform_time': None,
        'structure': 'غير محدد', 'timeframe_agreement': False,
        'liquidity_map': '', 'execution_window': 'خارج',
        'current_price': None, 'entry': None, 'sl': None,
        'tp1': None, 'tp2': None, 'tp3': None,
        'decision': 'HOLD', 'decision_raw': '', 'signal_strength': 'متوسطة',
        'entry_type': '', 'entry_timing': '', 'candle_state': '',
        'confidence': 50, 'success_rate': 50,
        'liquidity_trap': 'غير نشط', 'reasoning': '', 'raw': content
    }
    
    if re.search(r'الصورة غير صالحة|صورة أوضح', text):
        p['valid'] = False
        p['image_valid'] = False
        return p

    def grab(pat, default=None):
        m = re.search(pat, text, re.IGNORECASE)
        return m.group(1).strip() if m else default

    p['platform_time'] = grab(r'الوقت على المنصة[^:]*:\s*([^\n]+)')
    p['structure'] = grab(r'حالة الهيكل[^:]*:\s*([^\n+]+)', 'غير محدد')
    agree = grab(r'توافق 4/4 إطارات[^:]*:\s*([^\n)]+)', '')
    p['timeframe_agreement'] = 'نعم' in (agree or '')
    p['liquidity_map'] = grab(r'خريطة السيولة[^:]*:\s*([^\n]+)', '')
    p['execution_window'] = grab(r'نافذة التنفيذ[^:]*:\s*\[?([^\])]+)', 'خارج')
    p['current_price'] = _extract_number(grab(r'السعر الحالي[^:]*:\s*([^\n]+)'))
    p['entry'] = _extract_number(grab(r'نقطة الدخول[^:]*:\s*([^\n]+)'))
    p['candle_state'] = grab(r'حالة الشمعة[^:]*:\s*([^\n]+)', '')
    p['decision_raw'] = grab(r'القرار الفني[^:]*:\s*([^\n]+)', 'احتفاظ')
    p['decision'] = _map_decision(p['decision_raw'])
    p['signal_strength'] = grab(r'قوة الإشارة[^:]*:\s*([^\n💥🔥⚡❄️]+)', 'متوسطة').strip()
    p['entry_type'] = grab(r'نوع الدخول[^:]*:\s*([^\n]+)', '')
    p['entry_timing'] = grab(r'وقت الدخول[^:]*:\s*([^\n]+)', '')
    p['tp1'] = _extract_number(grab(r'TP1[^:]*:\s*([^\n-]+)', ''))
    p['tp2'] = _extract_number(grab(r'TP2[^:]*:\s*([^\n-]+)', ''))
    p['tp3'] = _extract_number(grab(r'TP3[^:]*:\s*([^\n-]+)', ''))
    p['sl'] = _extract_number(grab(r'وقف الخسارة[^:]*:\s*([^\n-]+)', ''))
    
    c = grab(r'مستوى الثقة[^:]*:\s*(\d+)', '')
    if c:
        try: p['confidence'] = int(c)
        except Exception: pass
    
    sr = grab(r'نسبة نجاح الصفقة[^:]*:\s*(\d+)', '')
    if sr:
        try: p['success_rate'] = int(sr)
        except Exception: pass
    
    p['liquidity_trap'] = grab(r'تنبيه فخ السيولة[^:]*:\s*([^\n-]+)', 'غير نشط')
    p['reasoning'] = p['liquidity_map']
    return p


def _consensus(results):
    valid = [r for r in results if r.get('success') and r.get('parsed', {}).get('valid')]
    
    if not valid:
        return {'decision': 'HOLD', 'confidence': 0,
                'reasoning': 'فشل النماذج', 'votes': {},
                'models_used': [], 'agreeing_count': 0, 'total_models': 0}

    votes = {}
    for r in valid:
        d = r['parsed']['decision']
        votes[d] = votes.get(d, 0) + 1

    final = max(votes, key=votes.get)
    vc = votes[final]
    total = len(valid)

    if final == 'TRAP' and vc == total:
        structures = [r['parsed'].get('structure', '') for r in valid]
        if any('صاعد' in s or 'هابط' in s for s in structures):
            final = 'REVERSAL'

    agreeing = [r for r in valid if r['parsed']['decision'] == final] or valid
    avg_conf = sum(r['parsed'].get('confidence', 50) for r in agreeing) // len(agreeing)
    if vc == total:
        avg_conf = min(100, avg_conf + 10)
    elif vc == 2:
        avg_conf = min(100, avg_conf + 5)

    def avg_level(key):
        vals = [r['parsed'].get(key) for r in agreeing if r['parsed'].get(key)]
        return sum(vals) / len(vals) if vals else None

    return {
        'decision': final, 'confidence': avg_conf, 'votes': votes,
        'entry': avg_level('entry'), 'sl': avg_level('sl'),
        'tp1': avg_level('tp1'), 'tp2': avg_level('tp2'), 'tp3': avg_level('tp3'),
        'reasoning': " | ".join([f"{r['model'].split('-')[-1]}:{r['parsed']['decision']}({r['parsed']['confidence']}%)" for r in valid]),
        'models_used': [r['model'] for r in valid],
        'agreeing_count': len(agreeing), 'total_models': total,
    }


def _fmt_price(p):
    if p is None:
        return "—"
    if p >= 1000:
        return f"{p:,.2f}"
    if p >= 1:
        return f"{p:.4f}"
    return f"{p:.5f}"


def _duration_text(t):
    return {"قصير (1m-15m)": "5-15 دقيقة",
            "متوسط (4h-Daily)": "4 ساعات - يومي",
            "طويل (Weekly-Monthly)": "أسبوعي - شهري"}.get(t, "—")


def _format_final(symbol, candle, trade_time, candles_count, session, cons, results):
    d = cons['decision']
    dec_ar = {'BUY': 'شراء 🟢', 'SELL': 'بيع 🔴', 'HOLD': 'احتفاظ 🟡',
              'BREAKOUT': 'كسر هيكلي 💥', 'SWEEP': 'سحب سيولة 🔄',
              'REVERSAL': 'انعكاس فوري 🔄', 'TRAP': 'فخ سيولة 🚨'}.get(d, 'احتفاظ 🟡')

    conf = cons['confidence']
    if conf >= 90:
        strength, se = 'عالية جدا', '💥'
    elif conf >= 75:
        strength, se = 'عالية', '🔥'
    elif conf >= 60:
        strength, se = 'متوسطة', '⚡'
    else:
        strength, se = 'ضعيفة', '❄️'

    ok = sum(1 for r in results if r.get('success'))
    votes = cons.get('votes', {})
    vote_str = " | ".join([f"{k}:{v}" for k, v in votes.items() if v > 0])

    structures = [r['parsed'].get('structure', '') for r in results if r.get('success')]
    structure = structures[0] if structures else 'غير محدد'
    agree = 'نعم' if any(r['parsed'].get('timeframe_agreement') for r in results if r.get('success')) else 'لا'

    lines = [
        "📊 التحليل الفني المتقدم:",
        "• بروتوكول الفشل الذاتي: الصورة صالحة",
        f"• الوقت على المنصة (المرجع): {session['utc_time']}",
        f"• حالة الهيكل: {structure} + (توافق 4/4 إطارات: {agree})",
        f"• خريطة السيولة: {cons.get('reasoning', '')[:120]}",
        "• الثواني المنقضية: -- ثانية (نافذة التنفيذ: داخل النافذة الذهبية)",
        "",
        "🎯 الإشارة التنفيذية:",
        f"• السعر الحالي: {_fmt_price(cons.get('entry'))}",
        f"• نقطة الدخول المعدلة: {_fmt_price(cons.get('entry'))}",
        "• حالة الشمعة: مفتوحة - الوقت المتبقي: --",
        f"• القرار الفني: {dec_ar}",
        f"• قوة الإشارة: {strength} {se}",
        f"• نقطة الدخول: {_fmt_price(cons.get('entry'))}",
        f"• نوع الدخول 🚨: {'دخول مباشر' if conf >= 85 else 'إعادة اختبار'}",
        f"• وقت الدخول: {'فوري (Flash)' if conf >= 90 else 'بعد إغلاق الشمعة'}",
        "• الأهداف الربحية:",
        f"  🎯 TP1: {_fmt_price(cons.get('tp1'))} - [سحب أول سيولة داخلية] - [احتمالية الوصول: عالية]",
        f"  🎯 TP2: {_fmt_price(cons.get('tp2'))} - [الهدف الرئيسي - منطقة عرض/طلب قوية] - [احتمالية الوصول: متوسطة]",
        f"  🎯 TP3: {_fmt_price(cons.get('tp3'))} - [سيولة خارجية أو سد فجوة] - [احتمالية الوصول: متوسطة]",
        f"• وقف الخسارة: {_fmt_price(cons.get('sl'))} - [مع 3 طبقات حماية]",
        f"• المدة المتوقعة: {_duration_text(trade_time)}",
        "• وقت الذروة المتوقع: خلال الـ 5 شموع القادمة",
        "",
        "⚠️ إدارة المخاطر:",
        f"• مستوى الثقة: {conf}٪ = {se}",
        f"• نسبة نجاح الصفقة المتوقعة (V8.0): {cons.get('confidence', 50)}% - {'ممتاز' if conf >= 85 else 'جيد' if conf >= 70 else 'متوسط'}",
        f"• 🚨 تنبيه فخ السيولة: {'نشط' if d == 'TRAP' else 'غير نشط'}",
        "",
        "━━━━━━━━━━━━━━━━━━",
        f"🤖 **التصويت:** {ok}/3 نماذج | {vote_str}",
        f"📊 **الجلسة:** {session['session']} ({session['volatility']})",
        f"⚙️ **الفريم:** {candle} | **الشموع:** {candles_count}",
    ]
    return "\n".join(lines)


async def analyze_chart_image(update, context, image_path, candle, trade_time, symbol,
                               candles_count=100, send_wait=True):
    user_id = update.effective_user.id
    wait_msg = None
    try:
        if send_wait:
            wait_msg = await update.message.reply_text(
                "🧠 **التحليل الثلاثي الاحترافي...**\n"
                "🟢 بصري | 🔴 هيكلي | ⚡ زخمي\n"
                "⏳ 20-35 ثانية"
            )

        # فحص الصلاحية
        if user_id != ADMIN_ID:
            sub_ok, _, _ = SubscriptionSystem.check_subscription(user_id)
            if not sub_ok:
                if SystemSettings.get('analysis_requires_subscription', 1) == 1:
                    if wait_msg:
                        await wait_msg.edit_text(
                            "⚠️ التحليل للمشتركين فقط.\n\n"
                            f"🔑 فعّل اشتراكك: /activate"
                        )
                    return None

        # Cache check
        cache_key = f"analysis_{user_id}_{int(time.time() // 300)}"
        cached = cache_get(cache_key)
        if cached:
            if wait_msg:
                await wait_msg.edit_text(cached, parse_mode="Markdown")
            return cached

        compressed = compress_image(image_path)
        b64 = encode_image(compressed)
        if not b64:
            if wait_msg:
                await wait_msg.edit_text("❌ فشل قراءة الصورة.")
            return None

        session = get_market_session(user_id)

        tasks = []
        for m in MODELS_FOR_ANALYSIS:
            builder = PROMPT_BUILDERS.get(m)
            if builder:
                prompt = builder(symbol, candle, trade_time, candles_count, session)
                tasks.append(_call_model(m, prompt, b64))

        raw = await asyncio.gather(*tasks, return_exceptions=True)
        processed = []
        for r in raw:
            if isinstance(r, Exception):
                processed.append({'success': False, 'error': str(r), 'model': 'unknown'})
            elif r.get('success'):
                r['parsed'] = _parse_response(r['content'])
                processed.append(r)
            else:
                processed.append(r)

        cons = _consensus(processed)
        SubscriptionSystem.increment_usage(user_id, 'chart_analysis_3models')
        ReferralSystem.add_points(user_id, SystemSettings.get('analysis_points', 1), 'analysis')
        save_analysis_context(user_id, cons.get('reasoning', ''))

        final = _format_final(symbol, candle, trade_time, candles_count,
                              session, cons, processed)

        cache_set(cache_key, final)

        if wait_msg:
            try:
                await wait_msg.edit_text(final, parse_mode="Markdown")
            except Exception:
                await update.message.reply_text(final)
        else:
            await update.message.reply_text(final, parse_mode="Markdown")

        # نشر تلقائي
        if SystemSettings.get('channel_auto_post', 1) == 1:
            min_c = SystemSettings.get('channel_min_confidence', 85)
            if cons['confidence'] >= min_c and cons['decision'] not in ('HOLD', 'INVALID'):
                await _post_to_channel(context, symbol, candle, trade_time, cons, session)

        try:
            if compressed != image_path:
                os.remove(compressed)
        except Exception:
            pass

        return final
    except Exception as e:
        print(f"❌ {e}")
        traceback.print_exc()
        if wait_msg:
            try:
                await wait_msg.edit_text(f"❌ خطأ: {str(e)[:100]}")
            except Exception:
                pass
        return None


async def _post_to_channel(context, symbol, candle, trade_time, cons, session):
    try:
        channel = ChannelSettings.get('main')
        if not channel:
            return
        d = cons['decision']
        emoji = {'BUY': '🟢', 'SELL': '🔴', 'BREAKOUT': '💥',
                 'SWEEP': '🔄', 'REVERSAL': '🔄'}.get(d, '🟡')
        d_ar = {'BUY': 'شراء', 'SELL': 'بيع', 'BREAKOUT': 'كسر هيكلي',
                'SWEEP': 'سحب سيولة', 'REVERSAL': 'انعكاس'}.get(d, d)
        text = (
            f"{emoji} **توصية جديدة - {d_ar}** {emoji}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💎 **الأصل:** `{symbol}`\n"
            f"⏱️ **الفريم:** {candle}\n"
            f"🎯 **المدة:** {_duration_text(trade_time)}\n"
            f"🌍 **الجلسة:** {session['session']}\n"
            f"💪 **الثقة:** {cons['confidence']}%\n"
            f"🤖 **النماذج:** {cons.get('agreeing_count', 0)}/{cons.get('total_models', 3)}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📍 **الدخول:** `{_fmt_price(cons.get('entry'))}`\n"
            f"🛑 **وقف الخسارة:** `{_fmt_price(cons.get('sl'))}`\n"
            f"🎯 **الهدف 1:** `{_fmt_price(cons.get('tp1'))}`\n"
            f"🎯 **الهدف 2:** `{_fmt_price(cons.get('tp2'))}`\n"
            f"🎯 **الهدف 3:** `{_fmt_price(cons.get('tp3'))}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🕐 **الوقت:** {session['utc_time']}\n"
            f"📢 {channel}\n"
            f"⚠️ إدارة رأس المال واجبة"
        )
        await context.bot.send_message(chat_id=channel, text=text, parse_mode="Markdown")
        print(f"✅ نشرت: {symbol} {d}")
    except Exception as e:
        print(f"⚠️ نشر: {e}")


# ============================================
# الأزرار أونلاين (TradingView)
# ============================================
online_symbols_cache = {'data': None, 'timestamp': 0}


def get_online_symbols():
    """جلب العملات أونلاين من TradingView مع fallback محلي"""
    global online_symbols_cache
    # Cache 24 ساعة
    if online_symbols_cache['data'] and time.time() - online_symbols_cache['timestamp'] < 86400:
        return online_symbols_cache['data']
    
    try:
        # محاولة جلب من TradingView Scanner (مجاني - لا يحتاج مفتاح)
        url = "https://scanner.tradingview.com/forex/scan"
        payload = {
            "filter": [{"left": "type", "operation": "match", "right": "forex"}],
            "options": {"lang": "en"},
            "markets": ["forex"],
            "symbols": {"query": {"types": []}, "tickers": []},
            "columns": ["name", "close", "change"],
            "sort": {"sortBy": "name", "sortOrder": "asc"},
            "range": [0, 50]
        }
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code == 200:
            data = r.json()
            # بناء القائمة
            online = {}
            forex_list = []
            for item in data.get('data', []):
                name = item['d'][0]
                # فقط الأزواج الرئيسية
                if '/' in name or len(name) == 6:
                    forex_list.append(name)
            if forex_list:
                online['أزواج العملات 🏛️'] = [f"{s} (OTC)" for s in forex_list[:20]]
                # دمج مع الباقي المحلي
                online.update({k: v for k, v in CATEGORIES.items() if 'العملات' not in k})
                online_symbols_cache['data'] = online
                online_symbols_cache['timestamp'] = time.time()
                return online
    except Exception as e:
        print(f"⚠️ أونلاين: {e}")
    
    # Fallback
    return CATEGORIES


# ============================================
# لوحات المفاتيح
# ============================================
def main_keyboard(user_id):
    kb = [
        ["⚙️ إعدادات التحليل", "📊 تحليل صورة"],
        ["💬 دردشة", "📈 توصية"],
        ["👤 حسابي", "🆘 الدعم الفني"],
    ]
    if user_id == ADMIN_ID:
        kb.append(["👑 لوحة الأدمن"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)


def locked_keyboard():
    """لوحة المستخدم غير المشترك - قفل صارم"""
    return ReplyKeyboardMarkup([
        ["🔑 تفعيل اشتراك", "👤 تفاصيل حسابي"],
        ["🆘 الدعم الفني", "📢 القناة"],
    ], resize_keyboard=True)


def admin_main_keyboard():
    return ReplyKeyboardMarkup([
        ["📊 الإحصائيات", "👥 المستخدمين"],
        ["🎫 أكواد التفعيل", "⚙️ الإعدادات"],
        ["📢 القنوات", "📨 إذاعة"],
        ["🆘 التذاكر", "🏠 القائمة الرئيسية"],
    ], resize_keyboard=True)


def back_keyboard():
    return ReplyKeyboardMarkup([["🏠 القائمة الرئيسية"]], resize_keyboard=True)


# ============================================
# Helper: فحص صلاحية الوصول
# ============================================
def is_subscribed(user_id):
    if user_id == ADMIN_ID:
        return True
    ok, _, _ = SubscriptionSystem.check_subscription(user_id)
    return ok


# ============================================
# Handlers: Start
# ============================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    
    SubscriptionSystem.register_user(
        user_id=uid, username=user.username, first_name=user.first_name,
        last_name=user.last_name, language_code=user.language_code, is_bot=user.is_bot
    )
    ReferralSystem.get_or_create_user(uid)
    
    # معالجة الإحالة
    if context.args and context.args[0].startswith('ref_'):
        try:
            referrer_id = int(context.args[0][4:])
            if referrer_id != uid:
                if ReferralSystem.add_referral(referrer_id, uid):
                    try:
                        await context.bot.send_message(
                            chat_id=referrer_id,
                            text=f"🎉 **إحالة ناجحة!**\n\n"
                                 f"تمت إضافة {SystemSettings.get('referral_points', 10)} نقاط لحسابك.",
                            parse_mode="Markdown"
                        )
                    except Exception:
                        pass
        except (ValueError, IndexError):
            pass
    
    session = get_market_session(uid)
    subscribed = is_subscribed(uid)
    
    if uid == ADMIN_ID:
        welcome = (
            f"👑 **مرحباً أيها الأدمن**\n\n"
            f"🕐 الجلسة: {session['session']}\n"
            f"📊 التقلب: {session['volatility']}\n"
            f"⏰ التوقيت: {session['utc_time']}\n\n"
            f"اختر من القائمة:"
        )
        await update.message.reply_text(
            welcome, reply_markup=admin_main_keyboard(), parse_mode="Markdown"
        )
        return ADMIN_MAIN
    
    elif subscribed:
        ok, name, details = SubscriptionSystem.check_subscription(uid)
        welcome = (
            f"🚀 **Obeida Trading V8.0**\n\n"
            f"✅ اشتراكك: {name}\n"
            f"🕐 الجلسة: {session['session']}\n"
            f"📊 التقلب: {session['volatility']}\n\n"
            f"اختر من القائمة:"
        )
        await update.message.reply_text(
            welcome, reply_markup=main_keyboard(uid), parse_mode="Markdown"
        )
        return MAIN_MENU
    else:
        # غير مشترك - قفل صارم
        welcome = (
            f"🚀 **Obeida Trading V8.0**\n\n"
            f"⚠️ **ليس لديك اشتراك نشط**\n\n"
            f"🔑 لتفعيل حسابك:\n"
            f"• اضغط **تفعيل اشتراك** وأدخل الكود\n"
            f"• أو تواصل مع الإدارة\n\n"
            f"🕐 الجلسة: {session['session']}\n\n"
            f"اختر من القائمة:"
        )
        await update.message.reply_text(
            welcome, reply_markup=locked_keyboard(), parse_mode="Markdown"
        )
        return MAIN_MENU


# ============================================
# Handler: القائمة الرئيسية
# ============================================
async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id
    
    # Rate limit
    if not rate_limiter.is_allowed(uid):
        await update.message.reply_text("⚠️ طلبات كثيرة. انتظر دقيقة.")
        return MAIN_MENU
    
    # أزرار المستخدم غير المشترك
    if text == "🔑 تفعيل اشتراك":
        await update.message.reply_text(
            "🔑 **تفعيل الاشتراك**\n\n"
            "أرسل كود التفعيل الآن:\n"
            "مثال: `OBEIDA-XXXX-XXXX`\n\n"
            "أو /cancel للإلغاء",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([["❌ إلغاء"]], resize_keyboard=True)
        )
        return ACTIVATE_CODE_MODE
    
    if text == "👤 تفاصيل حسابي" or text == "👤 حسابي":
        await show_my_account(update, context)
        return MAIN_MENU
    
    if text == "🆘 الدعم الفني":
        if not SystemSettings.get('support_enabled', 1):
            await update.message.reply_text("⚠️ الدعم معطل حالياً.")
            return MAIN_MENU
        await update.message.reply_text(
            "🆘 **الدعم الفني**\n\nأرسل رسالتك (أو /cancel للإلغاء):",
            reply_markup=ReplyKeyboardMarkup([["❌ إلغاء"]], resize_keyboard=True)
        )
        return SUPPORT_MODE
    
    if text == "📢 القناة":
        ch = ChannelSettings.get('main')
        await update.message.reply_text(
            f"📢 **قناتنا الرسمية:**\n\n{ch}\n\n"
            f"🔗 https://t.me/{ch.replace('@', '') if ch.startswith('@') else ch}",
            parse_mode="Markdown"
        )
        return MAIN_MENU
    
    # فحص الصلاحية للباقي
    if not is_subscribed(uid):
        await update.message.reply_text(
            "⚠️ **هذه الميزة للمشتركين فقط**\n\n"
            "🔑 فعّل اشتراكك أولاً.",
            reply_markup=locked_keyboard()
        )
        return MAIN_MENU
    
    # أزرار المشترك
    if text == "⚙️ إعدادات التحليل":
        kb = [CANDLE_SPEEDS[i:i+3] for i in range(0, len(CANDLE_SPEEDS), 3)]
        kb.append(["🏠 القائمة الرئيسية"])
        await update.message.reply_text(
            "⚙️ اختر سرعة الشموع:",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
        )
        return SETTINGS_CANDLE
    
    if text == "📊 تحليل صورة":
        candle, trade_time, _, _ = get_user_setting(uid)
        await update.message.reply_text(
            f"📊 **جاهز للتحليل**\n"
            f"⚙️ {candle} | 🎯 {trade_time}\n\n"
            f"📤 أرسل صورة الشارت:",
            reply_markup=ReplyKeyboardMarkup([["🏠 القائمة الرئيسية"]], resize_keyboard=True),
            parse_mode="Markdown"
        )
        return ANALYZE_MODE
    
    if text == "💬 دردشة":
        await update.message.reply_text(
            "💬 **وضع الدردشة**\n\nأرسل سؤالك أو /stop للإيقاف:",
            reply_markup=ReplyKeyboardMarkup([["🛑 إيقاف الدردشة"]], resize_keyboard=True)
        )
        return CHAT_MODE
    
    if text == "📈 توصية":
        symbols = get_online_symbols()
        kb = [[k] for k in symbols.keys()]
        kb.append(["🏠 القائمة الرئيسية"])
        await update.message.reply_text(
            "📈 **نظام التوصيات**\n\nاختر القسم:",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
            parse_mode="Markdown"
        )
        return RECOMMENDATION_MODE
    
    if text == "🏠 القائمة الرئيسية" or text == "❌ إلغاء":
        return await return_to_main(update, context)
    
    return MAIN_MENU


async def return_to_main(update, context):
    uid = update.effective_user.id
    if uid == ADMIN_ID:
        await update.message.reply_text("🏠 لوحة الأدمن:", reply_markup=admin_main_keyboard())
        return ADMIN_MAIN
    if is_subscribed(uid):
        await update.message.reply_text("🏠 القائمة الرئيسية:", reply_markup=main_keyboard(uid))
    else:
        await update.message.reply_text("🏠 القائمة الرئيسية:", reply_markup=locked_keyboard())
    return MAIN_MENU


# ============================================
# Handler: تفاصيل الحساب (مع زر نسخ)
# ============================================
async def show_my_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    
    ok, name, details = SubscriptionSystem.check_subscription(uid)
    stats = SubscriptionSystem.get_user_stats(uid)
    points_row = ReferralSystem.get_or_create_user(uid)
    points = points_row[0] if points_row else 0
    referrals = ReferralSystem.get_referral_count(uid)
    
    if ok and details:
        sub_status = f"✅ نشط - {name}"
        end_info = ""
        if details.get('end'):
            try:
                end = datetime.fromisoformat(details['end'])
                rem = end - datetime.now()
                if rem.days > 0:
                    end_info = f"\n• ⏳ متبقي: {rem.days} يوم {rem.seconds // 3600} ساعة"
                else:
                    end_info = f"\n• ⏳ متبقي: {rem.seconds // 3600} ساعة"
                end_info += f"\n• 📅 ينتهي: {end.strftime('%Y-%m-%d %H:%M')}"
            except Exception:
                pass
    else:
        sub_status = "❌ لا يوجد اشتراك"
        end_info = ""
    
    # بناء النص للنسخ
    copy_text = (
        f"👤 تفاصيل حسابي - Obeida Trading\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🆔 ID: {uid}\n"
        f"📛 الاسم: {user.first_name or '—'}\n"
        f"🔗 Username: @{user.username or '—'}\n"
        f"🌍 اللغة: {user.language_code or 'ar'}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💎 الاشتراك: {sub_status}\n"
        f"{end_info}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 إحصائيات الاستخدام:\n"
        f"• تحليلات: {stats.get('chart_analysis_3models', 0)}\n"
        f"• دردشات: {stats.get('chat', 0)}\n"
        f"• توصيات: {stats.get('recommendation', 0)}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⭐ نقاطك: {points}\n"
        f"👥 إحالات ناجحة: {referrals}\n"
    )
    
    # عرض مع Markdown
    display_text = (
        f"👤 **تفاصيل حسابك**\n\n"
        f"🆔 ID: `{uid}`\n"
        f"📛 الاسم: {user.first_name or '—'}\n"
        f"🔗 Username: @{user.username or '—'}\n"
        f"🌍 اللغة: {user.language_code or 'ar'}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💎 الاشتراك: {sub_status}{end_info}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 **إحصائياتك:**\n"
        f"• تحليلات: {stats.get('chart_analysis_3models', 0)}\n"
        f"• دردشات: {stats.get('chat', 0)}\n"
        f"• توصيات: {stats.get('recommendation', 0)}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⭐ نقاطك: **{points}**\n"
        f"👥 إحالات: **{referrals}**\n"
    )
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 نسخ التفاصيل", callback_data=f"copy_{uid}")]
    ])
    
    await update.message.reply_text(
        display_text, parse_mode="Markdown", reply_markup=kb
    )
    # نحفظ النص للنسخ
    context.user_data[f'copy_text_{uid}'] = copy_text


# ============================================
# Handler: تفعيل الاشتراك بكود
# ============================================
async def handle_activate_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.effective_user.id
    
    if text in ("❌ إلغاء", "🏠 القائمة الرئيسية"):
        return await return_to_main(update, context)
    
    # رفع الكود وتوحيده
    code = text.upper().strip()
    
    if not code.startswith("OBEIDA-"):
        await update.message.reply_text(
            "❌ صيغة الكود غير صحيحة.\n"
            "يجب أن يبدأ بـ `OBEIDA-`\n\n"
            "أعد المحاولة أو /cancel",
            parse_mode="Markdown"
        )
        return ACTIVATE_CODE_MODE
    
    ok, msg, data = ActivationCodes.validate_and_use(code, uid)
    
    if not ok:
        await update.message.reply_text(f"{msg}\n\nأعد المحاولة أو /cancel")
        return ACTIVATE_CODE_MODE
    
    # نجح - أضف الاشتراك
    sub_ok, sub_data = SubscriptionSystem.add_subscription(
        uid, data['sub_type'], added_by=ADMIN_ID,
        duration_seconds=data['duration']
    )
    
    if sub_ok:
        await update.message.reply_text(
            f"🎉 **تم تفعيل اشتراكك بنجاح!**\n\n"
            f"💎 النوع: {sub_data['name']}\n"
            f"✅ الكود: `{code}`\n\n"
            f"🚀 يمكنك الآن استخدام كل الميزات.",
            parse_mode="Markdown",
            reply_markup=main_keyboard(uid)
        )
        # إشعار الأدمن
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🎫 **كود مُستخدم**\n\n"
                     f"👤 @{update.effective_user.username or uid} (`{uid}`)\n"
                     f"🔑 كود: `{code}`\n"
                     f"💎 النوع: {sub_data['name']}",
                parse_mode="Markdown"
            )
        except Exception:
            pass
        return MAIN_MENU
    
    await update.message.reply_text("❌ خطأ في التفعيل. تواصل مع الأدمن.")
    return ACTIVATE_CODE_MODE


# ============================================
# Handler: إعدادات الشموع
# ============================================
async def handle_settings_candle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id
    
    if text in ("🏠 القائمة الرئيسية", "❌ إلغاء"):
        return await return_to_main(update, context)
    
    if text in CANDLE_SPEEDS:
        save_user_setting(uid, "candle", text)
        kb = [TRADE_TIMES[i:i+2] for i in range(0, len(TRADE_TIMES), 2)]
        kb.append(["🏠 القائمة الرئيسية"])
        await update.message.reply_text(
            f"✅ {text}\n\nاختر مدة الصفقة:",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
        )
        return SETTINGS_TIME
    
    await update.message.reply_text("❌ اختر سرعة صحيحة")
    return SETTINGS_CANDLE


async def handle_settings_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id
    
    if text in ("🏠 القائمة الرئيسية", "❌ إلغاء"):
        return await return_to_main(update, context)
    
    if text in TRADE_TIMES:
        save_user_setting(uid, "trade_time", text)
        await update.message.reply_text(
            "✅ تم حفظ الإعدادات.\n\n📤 ارفع صورة الشارت للتحليل:",
            reply_markup=main_keyboard(uid)
        )
        return MAIN_MENU
    
    await update.message.reply_text("❌ اختر مدة صحيحة")
    return SETTINGS_TIME


# ============================================
# Handler: تحليل الصورة
# ============================================
async def handle_analyze_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id
    
    if text in ("🏠 القائمة الرئيسية", "❌ إلغاء"):
        return await return_to_main(update, context)
    
    await update.message.reply_text("📤 أرسل صورة الشارت.")
    return ANALYZE_MODE


async def handle_image_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    
    if not is_subscribed(uid):
        await update.message.reply_text(
            "⚠️ التحليل للمشتركين فقط.",
            reply_markup=locked_keyboard()
        )
        return MAIN_MENU
    
    if not rate_limiter.is_allowed(uid):
        await update.message.reply_text("⚠️ طلبات كثيرة. انتظر دقيقة.")
        return ANALYZE_MODE
    
    candle, trade_time, _, _ = get_user_setting(uid)
    
    photo = await update.message.photo[-1].get_file()
    ts = int(time.time())
    path = os.path.join(IMAGE_CACHE_DIR, f"img_{uid}_{ts}.jpg")
    await photo.download_to_drive(path)
    
    await analyze_chart_image(
        update, context, path,
        candle=candle, trade_time=trade_time,
        symbol="CHART", candles_count=100
    )
    
    try:
        os.remove(path)
    except Exception:
        pass
    
    await update.message.reply_text(
        "🔽 أرسل صورة أخرى أو /stop للخروج",
        reply_markup=ReplyKeyboardMarkup([["🏠 القائمة الرئيسية"]], resize_keyboard=True)
    )
    return ANALYZE_MODE


# ============================================
# Handler: الدردشة
# ============================================
async def handle_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id
    
    if text in ("🛑 إيقاف الدردشة", "🏠 القائمة الرئيسية"):
        return await return_to_main(update, context)
    
    if not is_subscribed(uid):
        await update.message.reply_text("⚠️ الدردشة للمشتركين فقط.")
        return MAIN_MENU
    
    if not rate_limiter.is_allowed(uid):
        await update.message.reply_text("⚠️ طلبات كثيرة. انتظر دقيقة.")
        return CHAT_MODE
    
    wait = await update.message.reply_text("🤔 أفكر...")
    
    try:
        headers = {"Authorization": f"Bearer {MISTRAL_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": MODEL_CHAT,
            "messages": [
                {"role": "system", "content": "أنت Obeida Trading مساعد ذكي شامل. أجب بالعربية بوضوح وتنظيم."},
                {"role": "user", "content": text}
            ],
            "max_tokens": 2000, "temperature": 0.15
        }
        r = requests.post(MISTRAL_URL, headers=headers, json=payload, timeout=60)
        if r.status_code == 200:
            result = r.json()['choices'][0]['message']['content']
            for i in range(0, len(result), 4000):
                chunk = result[i:i+4000]
                if i == 0:
                    await wait.edit_text(chunk)
                else:
                    await update.message.reply_text(chunk)
            SubscriptionSystem.increment_usage(uid, 'chat')
            ReferralSystem.add_points(uid, SystemSettings.get('chat_points', 1), 'chat')
        else:
            await wait.edit_text(f"❌ خطأ: {r.status_code}")
    except Exception as e:
        await wait.edit_text(f"❌ {e}")
    
    return CHAT_MODE


# ============================================
# Handler: التوصية
# ============================================
async def handle_recommendation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.effective_user.id
    
    if text in ("🏠 القائمة الرئيسية", "❌ إلغاء"):
        return await return_to_main(update, context)
    
    if text == "🔙 العودة للقائمة":
        symbols = get_online_symbols()
        kb = [[k] for k in symbols.keys()]
        kb.append(["🏠 القائمة الرئيسية"])
        await update.message.reply_text(
            "📈 اختر القسم:",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
        )
        return RECOMMENDATION_MODE
    
    if not is_subscribed(uid):
        await update.message.reply_text("⚠️ التوصيات للمشتركين فقط.")
        return MAIN_MENU
    
    symbols = get_online_symbols()
    
    if text in symbols:
        kb = [[a] for a in symbols[text]]
        kb.append(["🔙 العودة للقائمة", "🏠 القائمة الرئيسية"])
        await update.message.reply_text(
            f"📍 {text}\nاختر الأصل:",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
        )
        return CATEGORY_SELECTION
    
    # بحث عن الرمز
    symbol = None
    for lst in symbols.values():
        if text in lst:
            symbol = text
            break
    
    if symbol:
        if not rate_limiter.is_allowed(uid):
            await update.message.reply_text("⚠️ طلبات كثيرة. انتظر دقيقة.")
            return RECOMMENDATION_MODE
        
        wait = await update.message.reply_text(f"📸 سحب شارت {symbol}...")
        candle, trade_time, _, _ = get_user_setting(uid)
        chart = download_chart(symbol, candle)
        
        if chart and os.path.exists(chart):
            with open(chart, 'rb') as f:
                await update.message.reply_photo(photo=f, caption=f"📈 {symbol} ({candle})")
            await wait.edit_text("🧠 التحليل الثلاثي...")
            await analyze_chart_image(
                update, context, chart, candle, trade_time, symbol,
                candles_count=100, send_wait=False
            )
            try:
                os.remove(chart)
            except Exception:
                pass
        else:
            await wait.edit_text("❌ فشل سحب الشارت. حاول مرة أخرى.")
        
        SubscriptionSystem.increment_usage(uid, 'recommendation')
        
        kb = [[k] for k in symbols.keys()]
        kb.append(["🏠 القائمة الرئيسية"])
        await update.message.reply_text(
            "🔽 اختر قسم آخر:",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
        )
        return RECOMMENDATION_MODE
    
    await update.message.reply_text("❌ خيار غير معروف.")
    return RECOMMENDATION_MODE


# ============================================
# Handler: الدعم
# ============================================
async def handle_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id
    user = update.effective_user
    
    if text in ("❌ إلغاء", "🏠 القائمة الرئيسية"):
        return await return_to_main(update, context)
    
    tid = SupportSystem.create_ticket(
        uid, user.username or str(uid), "دعم", text
    )
    
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(f"🆘 **دعم #{tid}**\n\n"
                  f"👤 @{user.username or uid} | ID: `{uid}`\n"
                  f"💬 {text}\n\n"
                  f"للرد: `/reply {tid} ردك`"),
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"⚠️ إشعار: {e}")
    
    await update.message.reply_text(f"✅ تم إرسال رسالتك (#{tid}).")
    await return_to_main(update, context)
    return MAIN_MENU


# ============================================
# Callback: نسخ التفاصيل
# ============================================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = update.effective_user.id
    
    if data.startswith("copy_"):
        target = data[5:]
        copy_text = context.user_data.get(f'copy_text_{target}', '')
        if copy_text:
            await query.message.reply_text(
                f"📋 **انسخ النص التالي:**\n\n`{copy_text}`",
                parse_mode="Markdown"
            )
        else:
            await query.message.reply_text("⚠️ النص غير متوفر.")
    
    elif data.startswith("admin_"):
        # سيتم معالجتها في الجزء 3
        pass


# ============================================
# أوامر مساعدة
# ============================================
async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await return_to_main(update, context)


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await return_to_main(update, context)


async def activate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔑 **تفعيل الاشتراك**\n\n"
        "أرسل كود التفعيل الآن:\n"
        "مثال: `OBEIDA-XXXX-XXXX`\n\n"
        "أو /cancel للإلغاء",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup([["❌ إلغاء"]], resize_keyboard=True)
    )
    return ACTIVATE_CODE_MODE


async def my_account_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_my_account(update, context)
    return MAIN_MENU


async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    bot_username = context.bot.username
    link = ReferralSystem.get_referral_link(bot_username, uid)
    count = ReferralSystem.get_referral_count(uid)
    points_row = ReferralSystem.get_or_create_user(uid)
    points = points_row[0] if points_row else 0
    rp = SystemSettings.get('referral_points', 10)
    
    await update.message.reply_text(
        f"👥 **نظام الإحالة**\n\n"
        f"⭐ نقاطك: {points}\n"
        f"👥 إحالاتك: {count}\n"
        f"🎁 مكافأة كل إحالة: {rp} نقطة\n\n"
        f"🔗 رابطك:\n`{link}`\n\n"
        f"شارك الرابط واربح نقاطاً!",
        parse_mode="Markdown"
    )
    
# ============================================
# لوحة الأدمن من تيليجرام
# ============================================

async def start_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دخول لوحة الأدمن"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⚠️ ليس لديك صلاحية.")
        return MAIN_MENU
    
    await update.message.reply_text(
        "👑 **لوحة الأدمن**\n\nاختر القسم:",
        reply_markup=admin_main_keyboard(),
        parse_mode="Markdown"
    )
    return ADMIN_MAIN


async def handle_admin_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة قائمة الأدمن الرئيسية"""
    if update.effective_user.id != ADMIN_ID:
        return MAIN_MENU
    
    text = update.message.text
    
    if text == "📊 الإحصائيات":
        return await admin_stats(update, context)
    
    if text == "👥 المستخدمين":
        return await admin_users(update, context)
    
    if text == "🎫 أكواد التفعيل":
        return await admin_codes_menu(update, context)
    
    if text == "⚙️ الإعدادات":
        return await admin_settings(update, context)
    
    if text == "📢 القنوات":
        return await admin_channels(update, context)
    
    if text == "📨 إذاعة":
        await update.message.reply_text(
            "📨 **إذاعة رسالة**\n\n"
            "أرسل الرسالة التي تريد إرسالها لكل المشتركين:\n\n"
            "أو /cancel للإلغاء",
            reply_markup=ReplyKeyboardMarkup([["❌ إلغاء"]], resize_keyboard=True)
        )
        return ADMIN_BROADCAST
    
    if text == "🆘 التذاكر":
        return await admin_tickets(update, context)
    
    if text == "🏠 القائمة الرئيسية":
        return await return_to_main(update, context)
    
    return ADMIN_MAIN


# ============================================
# الإحصائيات
# ============================================
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = SubscriptionSystem.get_stats()
    code_stats = ActivationCodes.get_stats()
    
    # إحصائيات إضافية
    total_referrals = 0
    total_points = 0
    try:
        with db_conn() as c:
            cur = c.cursor()
            cur.execute("SELECT COUNT(*) FROM referrals")
            total_referrals = cur.fetchone()[0]
            cur.execute("SELECT SUM(points) FROM user_points")
            row = cur.fetchone()
            total_points = row[0] if row and row[0] else 0
    except Exception:
        pass
    
    text = (
        f"📊 **إحصائيات النظام**\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 **المستخدمون:**\n"
        f"• الإجمالي: {stats['total_users']}\n"
        f"• النشطون: {stats['active_users']}\n"
        f"• المحظورون: {stats['blocked_users']}\n\n"
        f"🎫 **أكواد التفعيل:**\n"
        f"• الإجمالي: {code_stats['total']}\n"
        f"• المستخدمة: {code_stats['used']}\n"
        f"• المتاحة: {code_stats['available']}\n\n"
        f"👥 **الإحالات:**\n"
        f"• الإجمالي: {total_referrals}\n"
        f"• إجمالي النقاط: {total_points}\n\n"
        f"⚙️ **الإعدادات الحالية:**\n"
        f"• تحليلات مجانية: {SystemSettings.get('free_analyses_limit')}\n"
        f"• النشر التلقائي: {'✅' if SystemSettings.get('channel_auto_post') else '❌'}\n"
        f"• الدعم: {'✅' if SystemSettings.get('support_enabled') else '❌'}\n"
    )
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 تحديث", callback_data="admin_refresh_stats")]
    ])
    
    await update.message.reply_text(
        text, parse_mode="Markdown", reply_markup=kb
    )
    return ADMIN_MAIN


# ============================================
# المستخدمين
# ============================================
async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = SubscriptionSystem.get_all_users(limit=20)
    
    if not users:
        await update.message.reply_text("لا يوجد مستخدمون.")
        return ADMIN_MAIN
    
    text = "👥 **آخر 20 مستخدم:**\n━━━━━━━━━━━━━━━━━━\n"
    kb_buttons = []
    
    for u in users:
        uid, uname, fname, created, last_active, blocked, sub_name, sub_end = u
        status = "🚫" if blocked else "✅"
        sub = sub_name or "بدون"
        text += f"{status} `{uid}` @{uname or '—'} | {sub}\n"
        kb_buttons.append([
            InlineKeyboardButton(
                f"{status} {uname or uid}",
                callback_data=f"admin_user_{uid}"
            )
        ])
    
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb_buttons[:15])
    )
    return ADMIN_MAIN


async def admin_user_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض تفاصيل مستخدم مع أزرار تحكم"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        return
    
    uid = int(query.data.split('_')[-1])
    
    # جلب بيانات المستخدم
    user_info = None
    try:
        with db_conn(SUBSCRIPTION_DB_NAME) as c:
            cur = c.cursor()
            cur.execute('''
                SELECT user_id, username, first_name, created_at, last_active, is_blocked
                FROM users WHERE user_id = ?
            ''', (uid,))
            user_info = cur.fetchone()
    except Exception:
        pass
    
    if not user_info:
        await query.message.reply_text("❌ المستخدم غير موجود.")
        return
    
    ok, name, details = SubscriptionSystem.check_subscription(uid)
    stats = SubscriptionSystem.get_user_stats(uid)
    points_row = ReferralSystem.get_or_create_user(uid)
    points = points_row[0] if points_row else 0
    referrals = ReferralSystem.get_referral_count(uid)
    
    text = (
        f"👤 **تفاصيل المستخدم**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🆔 ID: `{uid}`\n"
        f"📛 الاسم: {user_info[2] or '—'}\n"
        f"🔗 Username: @{user_info[1] or '—'}\n"
        f"📅 انضم: {user_info[3]}\n"
        f"⏰ آخر نشاط: {user_info[4]}\n"
        f"🚫 محظور: {'نعم' if user_info[5] else 'لا'}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💎 الاشتراك: {name if ok else '❌ لا يوجد'}\n"
    )
    if ok and details and details.get('end'):
        text += f"📅 ينتهي: {details['end'][:16]}\n"
    
    text += (
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 استخدامات: {len(stats)} ميزة\n"
        f"⭐ النقاط: {points} | 👥 الإحالات: {referrals}\n"
    )
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة اشتراك", callback_data=f"admin_addsub_{uid}")],
        [InlineKeyboardButton("❌ إلغاء الاشتراك", callback_data=f"admin_revokesub_{uid}")],
        [InlineKeyboardButton(
            "🔓 فك الحظر" if user_info[5] else "🚫 حظر",
            callback_data=f"admin_block_{uid}"
        )],
        [InlineKeyboardButton("💬 إرسال رسالة", callback_data=f"admin_msg_{uid}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_back_users")],
    ])
    
    await query.message.reply_text(
        text, parse_mode="Markdown", reply_markup=kb
    )


async def admin_add_sub_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة اشتراك لمستخدم - عرض الأنواع"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        return
    
    uid = int(query.data.split('_')[-1])
    
    types = [
        ('hourly', '⏰ ساعة'),
        ('daily', '📅 يوم'),
        ('weekly', '📆 أسبوع'),
        ('monthly', '🗓️ شهر'),
        ('yearly', '📅 سنة'),
        ('lifetime', '♾️ مدى الحياة'),
    ]
    
    kb_buttons = [
        [InlineKeyboardButton(label, callback_data=f"admin_apply_{uid}_{sub}")]
        for sub, label in types
    ]
    kb_buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"admin_user_{uid}")])
    
    await query.message.reply_text(
        f"➕ **إضافة اشتراك للمستخدم** `{uid}`\n\n"
        f"اختر النوع:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb_buttons)
    )


async def admin_apply_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تطبيق الاشتراك"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        return
    
    parts = query.data.split('_')
    uid = int(parts[2])
    sub_type = parts[3]
    
    ok, data = SubscriptionSystem.add_subscription(uid, sub_type, added_by=ADMIN_ID)
    
    if ok:
        await query.message.reply_text(
            f"✅ **تم إضافة الاشتراك**\n\n"
            f"👤 المستخدم: `{uid}`\n"
            f"💎 النوع: {data['name']}\n"
            f"📅 ينتهي: {data.get('end', 'مدى الحياة')}",
            parse_mode="Markdown"
        )
        # إشعار المستخدم
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=f"🎉 **تم تفعيل اشتراكك!**\n\n"
                     f"💎 النوع: {data['name']}\n"
                     f"📅 ينتهي: {data.get('end', 'مدى الحياة')[:16] if data.get('end') else 'مدى الحياة'}\n\n"
                     f"🚀 استمتع بكل الميزات!",
                parse_mode="Markdown",
                reply_markup=main_keyboard(uid)
            )
        except Exception:
            pass
    else:
        await query.message.reply_text(f"❌ {data}")


async def admin_revoke_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء اشتراك"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        return
    
    uid = int(query.data.split('_')[-1])
    SubscriptionSystem.revoke_subscription(uid)
    
    await query.message.reply_text(
        f"✅ تم إلغاء اشتراك `{uid}`.",
        parse_mode="Markdown"
    )
    try:
        await context.bot.send_message(
            chat_id=uid,
            text="⚠️ تم إلغاء اشتراكك. للاستفسار تواصل مع الإدارة."
        )
    except Exception:
        pass


async def admin_toggle_block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حظر/فك حظر مستخدم"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        return
    
    uid = int(query.data.split('_')[-1])
    
    # تحقق من الحالة
    is_blocked = False
    try:
        with db_conn(SUBSCRIPTION_DB_NAME) as c:
            cur = c.cursor()
            cur.execute("SELECT is_blocked FROM users WHERE user_id = ?", (uid,))
            row = cur.fetchone()
            is_blocked = row[0] if row else 0
    except Exception:
        pass
    
    if is_blocked:
        SubscriptionSystem.unblock_user(uid)
        await query.message.reply_text(f"✅ تم فك حظر `{uid}`.", parse_mode="Markdown")
    else:
        SubscriptionSystem.block_user(uid, "حظر من الأدمن")
        await query.message.reply_text(f"✅ تم حظر `{uid}`.", parse_mode="Markdown")
        try:
            await context.bot.send_message(
                chat_id=uid,
                text="🚫 تم حظر حسابك. تواصل مع الإدارة."
            )
        except Exception:
            pass


# ============================================
# أكواد التفعيل
# ============================================
async def admin_codes_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = ActivationCodes.get_stats()
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ كود واحد", callback_data="admin_gen_single")],
        [InlineKeyboardButton("📦 10 أكواد", callback_data="admin_gen_batch")],
        [InlineKeyboardButton("📋 عرض الأكواد المتاحة", callback_data="admin_list_codes")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_back_main")],
    ])
    
    await update.message.reply_text(
        f"🎫 **أكواد التفعيل**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"• الإجمالي: {stats['total']}\n"
        f"• المستخدمة: {stats['used']}\n"
        f"• المتاحة: {stats['available']}\n\n"
        f"اختر الإجراء:",
        parse_mode="Markdown",
        reply_markup=kb
    )
    return ADMIN_MAIN


async def admin_gen_single(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إنشاء كود واحد - عرض الأنواع"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        return
    
    types = [
        ('hourly', '⏰ ساعة'),
        ('daily', '📅 يوم'),
        ('weekly', '📆 أسبوع'),
        ('monthly', '🗓️ شهر'),
        ('yearly', '📅 سنة'),
        ('lifetime', '♾️ مدى الحياة'),
    ]
    
    kb_buttons = [
        [InlineKeyboardButton(label, callback_data=f"admin_gen_sub_{sub}_1")]
        for sub, label in types
    ]
    kb_buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_back_codes")])
    
    await query.message.reply_text(
        "🎫 **إنشاء كود واحد**\n\nاختر نوع الاشتراك:",
        reply_markup=InlineKeyboardMarkup(kb_buttons)
    )


async def admin_gen_batch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إنشاء 10 أكواد - عرض الأنواع"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        return
    
    types = [
        ('hourly', '⏰ ساعة'),
        ('daily', '📅 يوم'),
        ('weekly', '📆 أسبوع'),
        ('monthly', '🗓️ شهر'),
        ('yearly', '📅 سنة'),
        ('lifetime', '♾️ مدى الحياة'),
    ]
    
    kb_buttons = [
        [InlineKeyboardButton(label, callback_data=f"admin_gen_sub_{sub}_10")]
        for sub, label in types
    ]
    kb_buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_back_codes")])
    
    await query.message.reply_text(
        "📦 **إنشاء 10 أكواد**\n\nاختر نوع الاشتراك:",
        reply_markup=InlineKeyboardMarkup(kb_buttons)
    )


async def admin_generate_codes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """توليد الأكواد فعلياً"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        return
    
    # admin_gen_sub_{type}_{count}
    parts = query.data.split('_')
    sub_type = parts[3]
    count = int(parts[4])
    
    codes = []
    for _ in range(count):
        result = ActivationCodes.generate_code(sub_type, ADMIN_ID)
        if result:
            codes.append(result)
    
    if not codes:
        await query.message.reply_text("❌ فشل التوليد.")
        return
    
    text = f"🎫 **تم توليد {len(codes)} كود**\n"
    text += f"💎 النوع: {ActivationCodes.SUBSCRIPTION_TYPES[sub_type]['name']}\n"
    text += "━━━━━━━━━━━━━━━━━━\n\n"
    for c in codes:
        text += f"`{c['code']}`\n"
    
    text += "\n⚠️ **احفظ هذه الأكواد الآن**"
    
    await query.message.reply_text(text, parse_mode="Markdown")


async def admin_list_codes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض الأكواد المتاحة"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        return
    
    codes = ActivationCodes.list_codes(limit=20, only_unused=True)
    
    if not codes:
        await query.message.reply_text("لا توجد أكواد متاحة.")
        return
    
    text = "🎫 **الأكواد المتاحة (آخر 20):**\n━━━━━━━━━━━━━━━━━━\n"
    for c in codes:
        code, sub_type, used_by, created, expires = c
        text += f"`{code}` — {ActivationCodes.SUBSCRIPTION_TYPES.get(sub_type, {}).get('name', sub_type)}\n"
    
    await query.message.reply_text(text, parse_mode="Markdown")


# ============================================
# الإعدادات
# ============================================
async def admin_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    free_limit = SystemSettings.get('free_analyses_limit')
    auto_post = SystemSettings.get('channel_auto_post')
    min_conf = SystemSettings.get('channel_min_confidence')
    support = SystemSettings.get('support_enabled')
    rate = SystemSettings.get('rate_limit_per_minute')
    ref_pts = SystemSettings.get('referral_points')
    
    text = (
        f"⚙️ **الإعدادات الحالية**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"• تحليلات مجانية: {free_limit} ({'غير محدود' if free_limit == -1 else 'قفل' if free_limit == 0 else 'محدود'})\n"
        f"• النشر التلقائي: {'✅ مفعل' if auto_post else '❌ معطل'}\n"
        f"• حد الثقة للنشر: {min_conf}%\n"
        f"• الدعم الفني: {'✅ مفعل' if support else '❌ معطل'}\n"
        f"• Rate Limit: {rate} طلب/دقيقة\n"
        f"• نقاط الإحالة: {ref_pts}\n"
    )
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎁 التحليلات المجانية", callback_data="admin_set_free")],
        [InlineKeyboardButton(
            f"{'❌ إيقاف' if auto_post else '✅ تفعيل'} النشر التلقائي",
            callback_data="admin_toggle_autopost"
        )],
        [InlineKeyboardButton("📊 حد الثقة", callback_data="admin_set_conf")],
        [InlineKeyboardButton(
            f"{'❌ إيقاف' if support else '✅ تفعيل'} الدعم",
            callback_data="admin_toggle_support"
        )],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_back_main")],
    ])
    
    await update.message.reply_text(
        text, parse_mode="Markdown", reply_markup=kb
    )
    return ADMIN_MAIN


async def admin_set_free(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعديل التحليلات المجانية"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        return
    
    options = [
        (0, "🔒 قفل صارم (0)"),
        (1, "1️⃣ تحليل واحد"),
        (2, "2️⃣ تحليلان"),
        (3, "3️⃣ ثلاثة"),
        (-1, "♾️ غير محدود"),
    ]
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data=f"admin_free_set_{val}")]
        for val, label in options
    ] + [[InlineKeyboardButton("🔙 رجوع", callback_data="admin_back_settings")]])
    
    await query.message.reply_text(
        "🎁 **التحليلات المجانية**\n\nاختر:",
        reply_markup=kb
    )


async def admin_free_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        return
    
    val = int(query.data.split('_')[-1])
    SystemSettings.set('free_analyses_limit', val, updated_by=ADMIN_ID)
    
    await query.message.reply_text(f"✅ تم التعيين: {val}")


async def admin_toggle_autopost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        return
    
    current = SystemSettings.get('channel_auto_post', 1)
    SystemSettings.set('channel_auto_post', 0 if current else 1, updated_by=ADMIN_ID)
    
    await query.message.reply_text(f"✅ النشر التلقائي: {'مفعل' if not current else 'معطل'}")


async def admin_toggle_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        return
    
    current = SystemSettings.get('support_enabled', 1)
    SystemSettings.set('support_enabled', 0 if current else 1, updated_by=ADMIN_ID)
    
    await query.message.reply_text(f"✅ الدعم: {'مفعل' if not current else 'معطل'}")


# ============================================
# القنوات
# ============================================
async def admin_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    main_ch = ChannelSettings.get('main')
    support_ch = ChannelSettings.get('support')
    group_ch = ChannelSettings.get('group')
    
    text = (
        f"📢 **إدارة القنوات**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"• القناة الرئيسية: `{main_ch}`\n"
        f"• الدعم: `{support_ch}`\n"
        f"• المجموعة: `{group_ch or 'لم تحدد'}`\n"
    )
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 تعديل القناة الرئيسية", callback_data="admin_ch_set_main")],
        [InlineKeyboardButton("🆘 تعديل الدعم", callback_data="admin_ch_set_support")],
        [InlineKeyboardButton("👥 تعديل المجموعة", callback_data="admin_ch_set_group")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_back_main")],
    ])
    
    await update.message.reply_text(
        text, parse_mode="Markdown", reply_markup=kb
    )
    return ADMIN_MAIN


async def admin_ch_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء تعديل قناة معينة"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        return
    
    ch_type = query.data.replace("admin_ch_set_", "")
    context.user_data['editing_channel'] = ch_type
    
    await query.message.reply_text(
        f"📢 **تعديل القناة: {ch_type}**\n\n"
        f"أرسل الرابط أو المعرف الجديد:\n"
        f"مثال: `@NewChannel` أو `-100123456789`\n\n"
        f"أو /cancel للإلغاء",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup([["❌ إلغاء"]], resize_keyboard=True)
    )
    return ADMIN_CHANNELS


async def admin_ch_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استقبال القناة الجديدة والتحقق منها"""
    if update.effective_user.id != ADMIN_ID:
        return ADMIN_MAIN
    
    text = update.message.text.strip()
    
    if text in ("❌ إلغاء", "/cancel"):
        await update.message.reply_text("تم الإلغاء.", reply_markup=admin_main_keyboard())
        return ADMIN_MAIN
    
    ch_type = context.user_data.get('editing_channel', 'main')
    
    # تحقق من الصلاحية
    try:
        chat = await context.bot.get_chat(text)
        # حاول إرسال رسالة اختبار
        test = await context.bot.send_message(
            chat_id=chat.id,
            text="✅ تم ربط القناة بنجاح!"
        )
        await test.delete()
        
        ChannelSettings.set(ch_type, text)
        await update.message.reply_text(
            f"✅ **تم التحديث والتحقق**\n\n"
            f"📢 القناة: {chat.title}\n"
            f"🆔 ID: `{chat.id}`\n"
            f"🔗 النوع: {ch_type}",
            parse_mode="Markdown",
            reply_markup=admin_main_keyboard()
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ **فشل التحديث**\n\n"
            f"السبب: {str(e)[:200]}\n\n"
            f"تأكد من:\n"
            f"• البوت Admin في القناة\n"
            f"• الرابط صحيح",
            reply_markup=admin_main_keyboard()
        )
    
    return ADMIN_MAIN


# ============================================
# الإذاعة
# ============================================
async def admin_broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إرسال رسالة لكل المشتركين"""
    if update.effective_user.id != ADMIN_ID:
        return ADMIN_MAIN
    
    text = update.message.text
    
    if text in ("❌ إلغاء", "/cancel"):
        await update.message.reply_text("تم الإلغاء.", reply_markup=admin_main_keyboard())
        return ADMIN_MAIN
    
    status = await update.message.reply_text("📤 جاري الإرسال...")
    
    # جلب كل المستخدمين
    with db_conn(SUBSCRIPTION_DB_NAME) as c:
        cur = c.cursor()
        cur.execute("SELECT user_id FROM users WHERE is_blocked = 0")
        users = [r[0] for r in cur.fetchall()]
    
    sent = 0
    failed = 0
    for uid in users:
        try:
            await context.bot.send_message(chat_id=uid, text=text)
            sent += 1
            await asyncio.sleep(0.05)  # تجنب rate limit تيليجرام
        except Exception:
            failed += 1
    
    await status.edit_text(
        f"✅ **اكتملت الإذاعة**\n\n"
        f"📤 نجح: {sent}\n"
        f"❌ فشل: {failed}",
        parse_mode="Markdown"
    )
    await update.message.reply_text("🏠", reply_markup=admin_main_keyboard())
    return ADMIN_MAIN


# ============================================
# التذاكر
# ============================================
async def admin_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tickets = SupportSystem.get_open()
    
    if not tickets:
        await update.message.reply_text("لا توجد تذاكر مفتوحة.", reply_markup=admin_main_keyboard())
        return ADMIN_MAIN
    
    text = "🆘 **التذاكر المفتوحة:**\n━━━━━━━━━━━━━━━━━━\n"
    kb_buttons = []
    for t in tickets[:10]:
        tid, uid, uname, subj, created, status = t
        text += f"#{tid} — @{uname or uid} — {status}\n"
        kb_buttons.append([
            InlineKeyboardButton(f"#{tid} @{uname or uid}", callback_data=f"admin_ticket_{tid}")
        ])
    
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb_buttons)
    )
    return ADMIN_MAIN


async def admin_ticket_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        return
    
    tid = int(query.data.split('_')[-1])
    
    with db_conn() as c:
        cur = c.cursor()
        cur.execute('''
            SELECT user_id, username, subject, created_at, status, admin_reply
            FROM support_tickets WHERE id = ?
        ''', (tid,))
        t = cur.fetchone()
    
    if not t:
        await query.message.reply_text("❌ التذكرة غير موجودة.")
        return
    
    uid, uname, subj, created, status, reply = t
    
    text = (
        f"🆘 **تذكرة #{tid}**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 @{uname or uid} (`{uid}`)\n"
        f"📅 {created}\n"
        f"📌 {status}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💬 {subj}\n"
    )
    if reply:
        text += f"━━━━━━━━━━━━━━━━━━\n✅ ردك: {reply}\n"
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 رد", callback_data=f"admin_reply_{tid}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_back_tickets")],
    ])
    
    await query.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def admin_reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """`/reply <tid> <message>`"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("الاستخدام: `/reply <tid> <الرد>`", parse_mode="Markdown")
        return
    
    try:
        tid = int(args[0])
        reply = " ".join(args[1:])
    except ValueError:
        await update.message.reply_text("❌ tid غير صالح")
        return
    
    uid = SupportSystem.add_reply(tid, reply)
    if uid:
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=f"📬 **رد الإدارة (#{tid})**\n\n{reply}",
                parse_mode="Markdown"
            )
            await update.message.reply_text("✅ تم الإرسال")
        except Exception as e:
            await update.message.reply_text(f"⚠️ {e}")
    else:
        await update.message.reply_text("❌ التذكرة غير موجودة")


# ============================================
# Callback موحد لكل الأزرار
# ============================================
async def main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = update.effective_user.id
    
    # نسخ التفاصيل
    if data.startswith("copy_"):
        target = data[5:]
        copy_text = context.user_data.get(f'copy_text_{target}', '')
        if copy_text:
            await query.message.reply_text(
                f"📋 **النص للنسخ:**\n\n`{copy_text}`",
                parse_mode="Markdown"
            )
        return
    
    # كل ما يلي للأدمن فقط
    if uid != ADMIN_ID:
        return
    
    if data == "admin_refresh_stats":
        await admin_stats(update, context)
    elif data == "admin_back_main":
        await query.message.reply_text("🏠", reply_markup=admin_main_keyboard())
    elif data == "admin_back_users":
        users = SubscriptionSystem.get_all_users(limit=20)
        text = "👥 **آخر 20 مستخدم:**\n"
        kb_buttons = []
        for u in users:
            uid_, uname, _, _, _, blocked, sub_name, _ = u
            status = "🚫" if blocked else "✅"
            text += f"{status} `{uid_}` @{uname or '—'} | {sub_name or 'بدون'}\n"
            kb_buttons.append([
                InlineKeyboardButton(f"{status} {uname or uid_}",
                                      callback_data=f"admin_user_{uid_}")
            ])
        await query.message.reply_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb_buttons[:15])
        )
    elif data == "admin_back_codes":
        await admin_codes_menu(update, context)
    elif data == "admin_back_settings":
        await admin_settings(update, context)
    elif data == "admin_back_tickets":
        await admin_tickets(update, context)
    elif data.startswith("admin_user_"):
        await admin_user_details(update, context)
    elif data.startswith("admin_addsub_"):
        await admin_add_sub_to_user(update, context)
    elif data.startswith("admin_apply_"):
        await admin_apply_sub(update, context)
    elif data.startswith("admin_revokesub_"):
        await admin_revoke_sub(update, context)
    elif data.startswith("admin_block_"):
        await admin_toggle_block(update, context)
    elif data.startswith("admin_gen_sub_"):
        await admin_generate_codes(update, context)
    elif data == "admin_gen_single":
        await admin_gen_single(update, context)
    elif data == "admin_gen_batch":
        await admin_gen_batch(update, context)
    elif data == "admin_list_codes":
        await admin_list_codes(update, context)
    elif data == "admin_set_free":
        await admin_set_free(update, context)
    elif data.startswith("admin_free_set_"):
        await admin_free_set(update, context)
    elif data == "admin_toggle_autopost":
        await admin_toggle_autopost(update, context)
    elif data == "admin_toggle_support":
        await admin_toggle_support(update, context)
    elif data == "admin_set_conf":
        await query.message.reply_text("📊 استخدم /set_conf <رقم> لتعديل حد الثقة (0-100).")
    elif data.startswith("admin_ch_set_"):
        await admin_ch_set(update, context)
    elif data.startswith("admin_ticket_"):
        await admin_ticket_view(update, context)
    elif data.startswith("admin_reply_"):
        tid = int(data.split('_')[-1])
        context.user_data['reply_ticket'] = tid
        await query.message.reply_text(
            f"💬 أرسل الرد على التذكرة #{tid}:",
            reply_markup=ReplyKeyboardMarkup([["❌ إلغاء"]], resize_keyboard=True)
        )
    elif data == "admin_back_settings":
        await admin_settings(update, context)


# ============================================
# أوامر إضافية للأدمن
# ============================================
async def set_conf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("الاستخدام: `/set_conf 85`", parse_mode="Markdown")
        return
    try:
        val = int(context.args[0])
        if 0 <= val <= 100:
            SystemSettings.set('channel_min_confidence', val, updated_by=ADMIN_ID)
            await update.message.reply_text(f"✅ حد الثقة: {val}%")
        else:
            await update.message.reply_text("❌ يجب بين 0-100")
    except ValueError:
        await update.message.reply_text("❌ رقم غير صالح")


async def add_sub_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """`/add_sub <uid> <type>`"""
    if update.effective_user.id != ADMIN_ID:
        return
    if len(context.args) < 2:
        await update.message.reply_text("الاستخدام: `/add_sub <uid> <type>`", parse_mode="Markdown")
        return
    try:
        target = int(context.args[0])
        sub_type = context.args[1]
        ok, data = SubscriptionSystem.add_subscription(target, sub_type, added_by=ADMIN_ID)
        if ok:
            await update.message.reply_text(f"✅ تمت الإضافة: {data['name']}")
        else:
            await update.message.reply_text(f"❌ {data}")
    except ValueError:
        await update.message.reply_text("❌ uid غير صالح")


async def gen_code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """`/gen_code <type> [count]`"""
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text(
            "الاستخدام: `/gen_code <type> [count]`\n"
            "الأنواع: hourly, daily, weekly, monthly, yearly, lifetime",
            parse_mode="Markdown"
        )
        return
    sub_type = context.args[0]
    count = int(context.args[1]) if len(context.args) > 1 else 1
    
    if sub_type not in ActivationCodes.SUBSCRIPTION_TYPES:
        await update.message.reply_text("❌ نوع غير صالح")
        return
    
    codes = []
    for _ in range(count):
        r = ActivationCodes.generate_code(sub_type, ADMIN_ID)
        if r:
            codes.append(r['code'])
    
    text = f"🎫 **{len(codes)} كود ({sub_type}):**\n\n"
    for c in codes:
        text += f"`{c}`\n"
    await update.message.reply_text(text, parse_mode="Markdown")


# ============================================
# المهام الدورية (Background Jobs)
# ============================================
async def daily_backup(context: ContextTypes.DEFAULT_TYPE):
    """نسخ احتياطي يومي"""
    backup_databases()
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"💾 **نسخ احتياطي يومي**\n\nتم حفظ النسخ في `{BACKUP_DIR}`",
            parse_mode="Markdown"
        )
    except Exception:
        pass


async def check_expiring_subscriptions(context: ContextTypes.DEFAULT_TYPE):
    """إشعار المستخدمين قبل انتهاء الاشتراك"""
    now = datetime.now()
    tomorrow = now + timedelta(days=1)
    
    with db_conn(SUBSCRIPTION_DB_NAME) as c:
        cur = c.cursor()
        cur.execute('''
            SELECT user_id, subscription_name, end_date
            FROM active_subscriptions
            WHERE is_active = 1 AND end_date IS NOT NULL
            AND end_date BETWEEN ? AND ?
        ''', (now.isoformat(), tomorrow.isoformat()))
        expiring = cur.fetchall()
    
    for uid, name, end in expiring:
        try:
            end_dt = datetime.fromisoformat(end)
            hours = int((end_dt - now).total_seconds() / 3600)
            await context.bot.send_message(
                chat_id=uid,
                text=(
                    f"⚠️ **تنبيه: اشتراكك ينتهي قريباً**\n\n"
                    f"💎 الاشتراك: {name}\n"
                    f"⏰ متبقي: {hours} ساعة\n"
                    f"📅 ينتهي: {end_dt.strftime('%Y-%m-%d %H:%M')}\n\n"
                    f"🔑 لتفعيل كود جديد: /activate\n"
                    f"📞 للتواصل: {ChannelSettings.get('support')}"
                ),
                parse_mode="Markdown"
            )
        except Exception:
            pass


# ============================================
# Flask + Admin Panel
# ============================================
app = Flask(__name__)
app.secret_key = SECRET_KEY


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper


ADMIN_LOGIN_HTML = """
<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><title>Login</title>
<style>body{font-family:sans-serif;background:#1a1a2e;color:#eee;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;}
form{background:rgba(255,255,255,0.05);padding:40px;border-radius:15px;min-width:320px;}
h2{color:#e94560;margin-bottom:20px;text-align:center;}
input{width:100%;padding:12px;margin:10px 0;border-radius:8px;border:1px solid #444;background:#000;color:#fff;box-sizing:border-box;}
button{width:100%;padding:12px;background:#e94560;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:1em;font-weight:bold;}
button:hover{background:#ff5c77;}.error{color:#e94560;text-align:center;margin-bottom:10px;}</style></head>
<body><form method="POST"><h2>👑 Admin Login</h2>
{% if error %}<div class="error">{{ error }}</div>{% endif %}
<input type="text" name="username" placeholder="Username" required>
<input type="password" name="password" placeholder="Password" required>
<button type="submit">دخول</button></form></body></html>
"""

ADMIN_PANEL_HTML = """
<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Obeida Admin</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;}
body{font-family:'Segoe UI',Tahoma,sans-serif;background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);color:#eee;min-height:100vh;padding:20px;}
.container{max-width:1200px;margin:0 auto;}
.header{text-align:center;padding:30px;margin-bottom:30px;background:linear-gradient(135deg,#0f3460,#e94560);border-radius:15px;}
.header h1{font-size:2.5em;margin-bottom:10px;}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px;margin-bottom:30px;}
.card{background:rgba(255,255,255,0.05);border-radius:15px;padding:25px;border:1px solid rgba(255,255,255,0.1);}
.card h3{color:#e94560;margin-bottom:15px;}
.stat{display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.05);}
.stat-label{color:#aaa;}.stat-value{font-weight:bold;color:#4ecca3;}
.alert{padding:15px;border-radius:8px;margin-bottom:20px;background:rgba(78,204,163,0.15);border:1px solid #4ecca3;color:#4ecca3;}
.alert-error{background:rgba(233,69,96,0.15);border-color:#e94560;color:#e94560;}
table{width:100%;border-collapse:collapse;margin-top:15px;}
th,td{padding:12px;text-align:right;border-bottom:1px solid rgba(255,255,255,0.1);}
th{background:rgba(233,69,96,0.2);color:#e94560;}
</style></head><body><div class="container">
<div class="header"><h1>👑 Obeida Trading - لوحة التحكم</h1><p>إدارة كاملة V8.0</p></div>
{% if message %}<div class="alert">{{ message }}</div>{% endif %}
{% if error %}<div class="alert alert-error">{{ error }}</div>{% endif %}
<div class="grid">
<div class="card"><h3>📊 المستخدمون</h3>
<div class="stat"><span class="stat-label">إجمالي</span><span class="stat-value">{{ stats.total_users }}</span></div>
<div class="stat"><span class="stat-label">نشطون</span><span class="stat-value">{{ stats.active_users }}</span></div>
<div class="stat"><span class="stat-label">محظورون</span><span class="stat-value">{{ stats.blocked_users }}</span></div>
</div>
<div class="card"><h3>🎫 الأكواد</h3>
<div class="stat"><span class="stat-label">إجمالي</span><span class="stat-value">{{ codes.total }}</span></div>
<div class="stat"><span class="stat-label">مستخدمة</span><span class="stat-value">{{ codes.used }}</span></div>
<div class="stat"><span class="stat-label">متاحة</span><span class="stat-value">{{ codes.available }}</span></div>
</div>
<div class="card"><h3>⚙️ الإعدادات</h3>
<div class="stat"><span class="stat-label">تحليلات مجانية</span><span class="stat-value">{{ settings.free_analyses_limit }}</span></div>
<div class="stat"><span class="stat-label">نشر تلقائي</span><span class="stat-value">{{ '✅' if settings.channel_auto_post else '❌' }}</span></div>
<div class="stat"><span class="stat-label">دعم فني</span><span class="stat-value">{{ '✅' if settings.support_enabled else '❌' }}</span></div>
</div>
</div>
<div class="card"><h3>👥 آخر المستخدمين</h3>
<table><thead><tr><th>ID</th><th>Username</th><th>الاشتراك</th><th>محظور</th></tr></thead><tbody>
{% for u in users %}
<tr><td>{{ u[0] }}</td><td>{{ u[1] or '—' }}</td><td>{{ u[6] or '—' }}</td><td>{{ '🚫' if u[5] else '✅' }}</td></tr>
{% endfor %}
</tbody></table></div>
</div></body></html>
"""


@app.route('/')
def home():
    return redirect(url_for('admin_panel') if session.get('logged_in') else url_for('login'))


@app.route('/healthz')
def healthz():
    return "OK", 200


@app.route('/admin/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form.get('username', '')
        p = request.form.get('password', '')
        if u == ADMIN_USERNAME and hashlib.sha256(p.encode()).hexdigest() == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('admin_panel'))
        return render_template_string(ADMIN_LOGIN_HTML, error="بيانات خاطئة")
    return render_template_string(ADMIN_LOGIN_HTML)


@app.route('/admin')
@login_required
def admin_panel():
    return render_template_string(
        ADMIN_PANEL_HTML,
        stats=SubscriptionSystem.get_stats(),
        codes=ActivationCodes.get_stats(),
        users=SubscriptionSystem.get_all_users(limit=20),
        settings={k: SystemSettings.get(k) for k in DEFAULT_SETTINGS},
        message=request.args.get('message'),
        error=request.args.get('error')
    )


# ============================================
# Job Queue
# ============================================
async def post_init(application: Application):
    if application.job_queue:
        # نسخ احتياطي يومي 3 صباحاً
        application.job_queue.run_daily(daily_backup, time=datetime.strptime("03:00", "%H:%M").time())
        # فحص الاشتراكات المنتهية كل 6 ساعات
        application.job_queue.run_repeating(check_expiring_subscriptions, interval=21600, first=60)
        print("✅ Job Queue initialized")


# ============================================
# main()
# ============================================
def main():
    init_all_dbs()
    
    application = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )
    
    # ConversationHandler
    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("activate", activate_command),
        ],
        states={
            MAIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu)],
            SETTINGS_CANDLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_settings_candle)],
            SETTINGS_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_settings_time)],
            ANALYZE_MODE: [
                MessageHandler(filters.PHOTO, handle_image_analysis),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_analyze_mode),
            ],
            CHAT_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat_message)],
            RECOMMENDATION_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_recommendation)],
            CATEGORY_SELECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_recommendation)],
            SUPPORT_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_support)],
            ACTIVATE_CODE_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_activate_code)],
            
            # Admin states
            ADMIN_MAIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_main)],
            ADMIN_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_send)],
            ADMIN_CHANNELS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_ch_receive)],
        },
        fallbacks=[
            CommandHandler("start", start),
            CommandHandler("cancel", cancel_command),
            CommandHandler("stop", stop_command),
        ],
    )
    
    application.add_handler(conv)
    application.add_handler(CallbackQueryHandler(main_callback))
    
    # أوامر
    application.add_handler(CommandHandler("admin", start_admin))
    application.add_handler(CommandHandler("reply", admin_reply_command))
    application.add_handler(CommandHandler("set_conf", set_conf_command))
    application.add_handler(CommandHandler("add_sub", add_sub_command))
    application.add_handler(CommandHandler("gen_code", gen_code_command))
    application.add_handler(CommandHandler("account", my_account_command))
    application.add_handler(CommandHandler("referral", referral_command))
    
    # Flask في thread
    def run_flask():
        app.telegram_app = application
        app.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(app.loop)
        port = int(os.environ.get('PORT', 5000))
        print(f"🌐 Flask على المنفذ {port}")
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False, threaded=True)
    
    threading.Thread(target=run_flask, daemon=True).start()
    
    # إلغاء webhook
    try:
        asyncio.get_event_loop().run_until_complete(
            application.bot.delete_webhook(drop_pending_updates=True)
        )
    except Exception:
        pass
    
    print("🚀 Bot + Flask started V8.0")
    application.run_polling(drop_pending_updates=True)


if __name__ == '__main__':
    main()
