#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Obeida Trading Bot V7.5 FINAL
نظام تحليل ثلاثي النماذج + لوحة تحكم + نشر تلقائي
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
import io
import pickle
import hashlib
import random
import string
import uuid
import secrets
from datetime import datetime, timedelta
from functools import wraps
from contextlib import contextmanager

from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)
from telegram.error import NetworkError, TimedOut

from flask import (
    Flask, request, jsonify, render_template_string, session,
    redirect, url_for, flash
)
from PIL import Image
import pytz

# ============================================
# الإعدادات الأساسية
# ============================================
TOKEN = os.environ.get('TOKEN')
if not TOKEN:
    raise ValueError("TOKEN environment variable is required")

MISTRAL_KEY = os.environ.get('MISTRAL_KEY')
if not MISTRAL_KEY:
    raise ValueError("MISTRAL_KEY environment variable is required")

MISTRAL_URL = "https://codex-relay.codes/v1/chat/completions"

# النماذج الثلاثة للتحليل
MODELS_FOR_ANALYSIS = ["gpt-6.1-sol", "gpt-6-astra", "gpt-6-luna"]
MODEL_CHAT = "gpt-6-luna"

DB_NAME = "abood-gpt.db"
BACKUP_DIR = "backups"
SUBSCRIPTION_DB_NAME = "subscription_system.db"
IMAGE_CACHE_DIR = "image_cache"
MAX_IMAGE_SIZE = (1024, 1024)
IMAGE_QUALITY = 95

ADMIN_ID = 6207431030
SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(32))
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'Obeida059')
ADMIN_PASSWORD_RAW = os.environ.get('ADMIN_PASSWORD', 'Obeida059')
ADMIN_PASSWORD = hashlib.sha256(ADMIN_PASSWORD_RAW.encode()).hexdigest()

CHANNEL_USERNAME = "@ObeidaTrading"
CHANNEL_ID = os.environ.get('CHANNEL_ID', '@ObeidaTrading')

CANDLE_SPEEDS = ["S5", "S10", "S15", "S30", "M1", "M2", "M3", "M5", "M10", "M15", "M30", "H1", "H4", "D1"]
TRADE_TIMES = ["قصير (1m-15m)", "متوسط (4h-Daily)", "طويل (Weekly-Monthly)"]

# إنشاء المجلدات
for d in [IMAGE_CACHE_DIR, BACKUP_DIR]:
    if not os.path.exists(d):
        os.makedirs(d)

# ============================================
# حالات المحادثة
# ============================================
(
    MAIN_MENU, SETTINGS_CANDLE, SETTINGS_TIME, CHAT_MODE, ANALYZE_MODE,
    RECOMMENDATION_MODE, CATEGORY_SELECTION, ADMIN_MENU, ADD_SUBSCRIPTION,
    SELECT_DURATION, REMOVE_USER, BROADCAST_MESSAGE, SET_USER_DURATION,
    CALCULATOR_MODE, SUPPORT_MODE
) = range(15)

# ============================================
# الإعدادات الافتراضية
# ============================================
DEFAULT_SETTINGS = {
    'free_analyses_limit': 2,
    'analysis_requires_subscription': 0,
    'channel_auto_post': 1,
    'channel_min_confidence': 85,
    'support_enabled': 1,
}

# ============================================
# توزيع العملات
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

# خريطة TradingView
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
    """Context manager آمن لاتصالات SQLite"""
    conn = None
    try:
        conn = sqlite3.connect(db_name, timeout=30)
        yield conn
    finally:
        if conn:
            conn.close()


def log_data_change(action, user_id, details=""):
    try:
        with db_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO data_log (action, user_id, details, timestamp) "
                "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                (action, user_id, details)
            )
            conn.commit()
    except Exception as e:
        print(f"⚠️ log error: {e}")


# ============================================
# نظام الإعدادات الديناميكية
# ============================================
class SystemSettings:
    @staticmethod
    def init_db():
        with db_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_by INTEGER
                )
            ''')
            for key, val in DEFAULT_SETTINGS.items():
                cursor.execute(
                    "INSERT OR IGNORE INTO system_settings (key, value) VALUES (?, ?)",
                    (key, str(val))
                )
            conn.commit()

    @staticmethod
    def get(key, default=None):
        try:
            with db_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM system_settings WHERE key = ?", (key,))
                row = cursor.fetchone()
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
        with db_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO system_settings (key, value, updated_by, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (key, str(value), updated_by))
            conn.commit()
        log_data_change("settings_update", updated_by or 0, f"{key}={value}")
        return True


class FreeAnalysesTracker:
    @staticmethod
    def init_db():
        with db_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS free_analyses_usage (
                    user_id INTEGER PRIMARY KEY,
                    used_count INTEGER DEFAULT 0,
                    last_used TIMESTAMP
                )
            ''')
            conn.commit()

    @staticmethod
    def get_remaining(user_id):
        limit = SystemSettings.get('free_analyses_limit', 2)
        if limit == -1:
            return 999999
        if limit == 0:
            return 0
        try:
            with db_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT used_count FROM free_analyses_usage WHERE user_id = ?",
                    (user_id,)
                )
                row = cursor.fetchone()
                used = row[0] if row else 0
                return max(0, limit - used)
        except Exception:
            return limit

    @staticmethod
    def consume(user_id):
        limit = SystemSettings.get('free_analyses_limit', 2)
        if limit == -1:
            return True
        if limit == 0:
            return False
        with db_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO free_analyses_usage (user_id, used_count, last_used)
                VALUES (?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    used_count = used_count + 1,
                    last_used = CURRENT_TIMESTAMP
            ''', (user_id,))
            conn.commit()
        return True

    @staticmethod
    def reset(user_id=None):
        with db_conn() as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute("DELETE FROM free_analyses_usage WHERE user_id = ?", (user_id,))
            else:
                cursor.execute("DELETE FROM free_analyses_usage")
            conn.commit()


class SupportSystem:
    @staticmethod
    def init_db():
        with db_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS support_tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    subject TEXT,
                    status TEXT DEFAULT 'open',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    admin_reply TEXT,
                    replied_at TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS support_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id INTEGER NOT NULL,
                    sender_id INTEGER NOT NULL,
                    is_admin BOOLEAN DEFAULT 0,
                    message TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    @staticmethod
    def create_ticket(user_id, username, subject, message):
        with db_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO support_tickets (user_id, username, subject)
                VALUES (?, ?, ?)
            ''', (user_id, username, subject))
            ticket_id = cursor.lastrowid
            cursor.execute('''
                INSERT INTO support_messages (ticket_id, sender_id, is_admin, message)
                VALUES (?, ?, 0, ?)
            ''', (ticket_id, user_id, message))
            conn.commit()
            return ticket_id

    @staticmethod
    def add_reply(ticket_id, admin_id, reply):
        with db_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO support_messages (ticket_id, sender_id, is_admin, message)
                VALUES (?, ?, 1, ?)
            ''', (ticket_id, admin_id, reply))
            cursor.execute('''
                UPDATE support_tickets 
                SET admin_reply = ?, replied_at = CURRENT_TIMESTAMP,
                    status = 'answered', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (reply, ticket_id))
            conn.commit()
            cursor.execute("SELECT user_id FROM support_tickets WHERE id = ?", (ticket_id,))
            row = cursor.fetchone()
            return row[0] if row else None

    @staticmethod
    def get_open_tickets():
        with db_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, user_id, username, subject, created_at, status
                FROM support_tickets
                WHERE status IN ('open', 'answered')
                ORDER BY created_at DESC LIMIT 50
            ''')
            return cursor.fetchall()


# ============================================
# نظام الاشتراكات
# ============================================
class SubscriptionSystem:
    SUBSCRIPTION_TYPES = {
        'trial': {'name': 'تجريبي', 'duration': 86400, 'features': ['basic_analysis']},
        'hourly': {'name': 'ساعة', 'duration': 3600, 'features': ['basic_analysis']},
        'daily': {'name': 'يوم', 'duration': 86400, 'features': ['basic_analysis', 'chat']},
        'weekly': {'name': 'أسبوع', 'duration': 604800, 'features': ['basic_analysis', 'chat', 'recommendations']},
        'monthly': {'name': 'شهر', 'duration': 2592000, 'features': ['basic_analysis', 'chat', 'recommendations', 'advanced_analysis']},
        'yearly': {'name': 'سنة', 'duration': 31536000, 'features': ['all']},
        'lifetime': {'name': 'مدى الحياة', 'duration': -1, 'features': ['all']}
    }

    @staticmethod
    def init_db():
        with db_conn(SUBSCRIPTION_DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute('''
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
            cursor.execute('''
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
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS permissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    permission TEXT NOT NULL,
                    granted_by INTEGER,
                    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    UNIQUE(user_id, permission)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS usage_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    feature TEXT NOT NULL,
                    count INTEGER DEFAULT 0,
                    last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, feature)
                )
            ''')
            conn.commit()

    @staticmethod
    def register_user(user_id, username=None, first_name=None, last_name=None, language_code=None, is_bot=False):
        with db_conn(SUBSCRIPTION_DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            if cursor.fetchone():
                cursor.execute('''
                    UPDATE users 
                    SET last_active = CURRENT_TIMESTAMP,
                        username = COALESCE(?, username),
                        first_name = COALESCE(?, first_name)
                    WHERE user_id = ?
                ''', (username, first_name, user_id))
            else:
                cursor.execute('''
                    INSERT INTO users (user_id, username, first_name, last_name, language_code, is_bot)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (user_id, username, first_name, last_name, language_code, is_bot))
            conn.commit()

    @staticmethod
    def add_subscription(user_id, subscription_type, added_by=ADMIN_ID):
        if subscription_type not in SubscriptionSystem.SUBSCRIPTION_TYPES:
            return False, "نوع اشتراك غير صالح"
        with db_conn(SUBSCRIPTION_DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
            duration = SubscriptionSystem.SUBSCRIPTION_TYPES[subscription_type]['duration']
            start_date = datetime.now()
            end_date = None if duration < 0 else start_date + timedelta(seconds=duration)
            cursor.execute('''
                UPDATE active_subscriptions SET is_active = 0
                WHERE user_id = ? AND is_active = 1
            ''', (user_id,))
            sub_name = SubscriptionSystem.SUBSCRIPTION_TYPES[subscription_type]['name']
            cursor.execute('''
                INSERT INTO active_subscriptions
                (user_id, subscription_type, subscription_name, start_date, end_date, is_active, added_by)
                VALUES (?, ?, ?, ?, ?, 1, ?)
            ''', (user_id, subscription_type, sub_name,
                  start_date.isoformat(),
                  end_date.isoformat() if end_date else None,
                  added_by))
            features = SubscriptionSystem.SUBSCRIPTION_TYPES[subscription_type]['features']
            all_features = ['basic_analysis', 'chat', 'recommendations', 'advanced_analysis', 'priority']
            for feature in features:
                features_to_add = all_features if feature == 'all' else [feature]
                for f in features_to_add:
                    cursor.execute('''
                        INSERT OR REPLACE INTO permissions (user_id, permission, granted_by, is_active)
                        VALUES (?, ?, ?, 1)
                    ''', (user_id, f, added_by))
            conn.commit()
        # مزامنة
        SubscriptionSystem._sync_main_db(user_id, end_date.isoformat() if end_date else None)
        return True, {'type': subscription_type, 'name': sub_name,
                      'end_date': end_date.isoformat() if end_date else None}

    @staticmethod
    def _sync_main_db(user_id, end_date):
        try:
            with db_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
                if cursor.fetchone():
                    cursor.execute(
                        "UPDATE users SET subscription_end = ? WHERE user_id = ?",
                        (end_date, user_id)
                    )
                else:
                    cursor.execute('''
                        INSERT INTO users (user_id, subscription_end, candle, trade_time, country_timezone)
                        VALUES (?, ?, 'M1', 'قصير (1m-15m)', 'Asia/Gaza')
                    ''', (user_id, end_date))
                conn.commit()
        except Exception as e:
            print(f"⚠️ sync error: {e}")

    @staticmethod
    def check_subscription(user_id):
        try:
            with db_conn(SUBSCRIPTION_DB_NAME) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT is_blocked FROM users WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()
                if row and row[0] == 1:
                    return False, "محظور", None
                cursor.execute('''
                    SELECT subscription_type, subscription_name, start_date, end_date
                    FROM active_subscriptions
                    WHERE user_id = ? AND is_active = 1
                    ORDER BY id DESC LIMIT 1
                ''', (user_id,))
                row = cursor.fetchone()
                if not row:
                    return False, "لا يوجد اشتراك نشط", None
                sub_type, sub_name, start_date, end_date = row
                if end_date:
                    try:
                        end = datetime.fromisoformat(end_date)
                        if end < datetime.now():
                            cursor.execute('''
                                UPDATE active_subscriptions SET is_active = 0
                                WHERE user_id = ? AND is_active = 1
                            ''', (user_id,))
                            conn.commit()
                            return False, "انتهت الصلاحية", None
                    except Exception:
                        pass
                cursor.execute('''
                    SELECT permission FROM permissions
                    WHERE user_id = ? AND is_active = 1
                ''', (user_id,))
                perms = [r[0] for r in cursor.fetchall()]
                return True, sub_name, {'type': sub_type, 'name': sub_name,
                                        'end_date': end_date, 'permissions': perms}
        except Exception as e:
            return False, str(e), None

    @staticmethod
    def increment_usage(user_id, feature):
        try:
            with db_conn(SUBSCRIPTION_DB_NAME) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO usage_stats (user_id, feature, count)
                    VALUES (?, ?, 1)
                    ON CONFLICT(user_id, feature) DO UPDATE SET
                        count = count + 1,
                        last_used = CURRENT_TIMESTAMP
                ''', (user_id, feature))
                conn.commit()
        except Exception:
            pass

    @staticmethod
    def get_all_users():
        with db_conn(SUBSCRIPTION_DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT u.user_id, u.username, u.first_name, u.created_at,
                       u.last_active, u.is_blocked,
                       a.subscription_name, a.end_date
                FROM users u
                LEFT JOIN active_subscriptions a
                ON u.user_id = a.user_id AND a.is_active = 1
                ORDER BY u.created_at DESC LIMIT 100
            ''')
            return cursor.fetchall()

    @staticmethod
    def get_stats():
        stats = {'total_users': 0, 'active_users': 0, 'blocked_users': 0,
                 'subscriptions_by_type': {}, 'feature_usage': {}}
        try:
            with db_conn(SUBSCRIPTION_DB_NAME) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM users")
                stats['total_users'] = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM users WHERE is_blocked = 1")
                stats['blocked_users'] = cursor.fetchone()[0]
                cursor.execute('''
                    SELECT COUNT(DISTINCT user_id) FROM active_subscriptions
                    WHERE is_active = 1 AND (end_date IS NULL OR end_date > datetime('now'))
                ''')
                stats['active_users'] = cursor.fetchone()[0]
                cursor.execute('''
                    SELECT subscription_type, COUNT(*) FROM active_subscriptions
                    WHERE is_active = 1 GROUP BY subscription_type
                ''')
                stats['subscriptions_by_type'] = dict(cursor.fetchall())
                cursor.execute('''
                    SELECT feature, SUM(count) FROM usage_stats
                    GROUP BY feature ORDER BY SUM(count) DESC LIMIT 10
                ''')
                stats['feature_usage'] = dict(cursor.fetchall())
        except Exception:
            pass
        return stats

    @staticmethod
    def revoke_subscription(user_id, performed_by=ADMIN_ID):
        with db_conn(SUBSCRIPTION_DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE active_subscriptions SET is_active = 0
                WHERE user_id = ? AND is_active = 1
            ''', (user_id,))
            cursor.execute('UPDATE permissions SET is_active = 0 WHERE user_id = ?', (user_id,))
            conn.commit()
        SubscriptionSystem._sync_main_db(user_id, None)
        return True, "تم إلغاء الاشتراك"

    @staticmethod
    def block_user(user_id, reason="Blocked by admin"):
        with db_conn(SUBSCRIPTION_DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET is_blocked = 1, blocked_reason = ? WHERE user_id = ?",
                (reason, user_id)
            )
            cursor.execute('''
                UPDATE active_subscriptions SET is_active = 0
                WHERE user_id = ? AND is_active = 1
            ''', (user_id,))
            conn.commit()
        return True, "تم الحظر"

    @staticmethod
    def unblock_user(user_id):
        with db_conn(SUBSCRIPTION_DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET is_blocked = 0, blocked_reason = NULL WHERE user_id = ?",
                (user_id,)
            )
            conn.commit()
        return True, "تم إلغاء الحظر"


# ============================================
# المناطق الزمنية والجلسات التلقائية
# ============================================
def get_user_timezone(user_id):
    try:
        with db_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(users)")
            cols = [c[1] for c in cursor.fetchall()]
            if 'country_timezone' not in cols:
                cursor.execute("ALTER TABLE users ADD COLUMN country_timezone TEXT DEFAULT 'Asia/Gaza'")
                conn.commit()
            cursor.execute("SELECT country_timezone FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return row[0] if row and row[0] else 'Asia/Gaza'
    except Exception:
        return 'Asia/Gaza'


def get_localized_time(user_id=None):
    try:
        tz_str = get_user_timezone(user_id) if user_id else 'Asia/Gaza'
        return datetime.now(pytz.timezone(tz_str))
    except Exception:
        return datetime.now(pytz.timezone('Asia/Gaza'))


def get_market_session_auto(user_id=None):
    """تحديد جلسة السوق تلقائياً بناءً على توقيت UTC"""
    try:
        utc_now = datetime.now(pytz.UTC)
        utc_hour = utc_now.hour
        sessions = []
        if 0 <= utc_hour < 7 or utc_hour >= 22:
            sessions.append("سيدني")
        if 0 <= utc_hour < 9:
            sessions.append("طوكيو")
        if 8 <= utc_hour < 17:
            sessions.append("لندن")
        if 13 <= utc_hour < 22:
            sessions.append("نيويورك")

        if 13 <= utc_hour < 17:
            main = "لندن + نيويورك (تداخل ذهبي)"
            vol = "عالية جداً 🔥"
        elif 8 <= utc_hour < 13:
            main = "لندن"
            vol = "مرتفعة 📈"
        elif 13 <= utc_hour < 22:
            main = "نيويورك"
            vol = "عالية 📊"
        elif 0 <= utc_hour < 9:
            main = "طوكيو/آسيا"
            vol = "منخفضة 📉"
        else:
            main = "سيدني"
            vol = "منخفضة جداً 💤"

        local_tz = pytz.timezone(get_user_timezone(user_id) if user_id else 'Asia/Gaza')
        local_time = datetime.now(local_tz)

        return {
            'session': main, 'volatility': vol,
            'utc_time': utc_now.strftime('%H:%M UTC'),
            'local_time': local_time.strftime('%H:%M'),
            'all_sessions': sessions, 'utc_hour': utc_hour,
        }
    except Exception:
        return {'session': 'عالمية', 'volatility': 'متوسطة',
                'utc_time': '--:--', 'local_time': '--:--',
                'all_sessions': [], 'utc_hour': 12}


# ============================================
# أدوات الصور
# ============================================
def compress_image(image_path, max_size=MAX_IMAGE_SIZE, quality=IMAGE_QUALITY):
    try:
        with Image.open(image_path) as img:
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
            out = image_path.replace('.jpg', '_compressed.jpg').replace('.png', '_compressed.jpg')
            img.save(out, 'JPEG', quality=quality, optimize=True)
            return out
    except Exception as e:
        print(f"⚠️ compress error: {e}")
        return image_path


def encode_image(image_path):
    try:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode('utf-8')
    except Exception as e:
        print(f"encode error: {e}")
        return None


def cleanup_user_data(context, user_id):
    try:
        if os.path.exists(IMAGE_CACHE_DIR):
            for f in os.listdir(IMAGE_CACHE_DIR):
                if f"_{user_id}_" in f or f.startswith(f"img_{user_id}_"):
                    try:
                        os.remove(os.path.join(IMAGE_CACHE_DIR, f))
                    except Exception:
                        pass
        for k in ['temp_image_path', 'compressed_image_path']:
            context.user_data.pop(k, None)
    except Exception:
        pass


# ============================================
# سحب الشارت من TradingView
# ============================================
def download_chart_image_v2(symbol, candle="M1"):
    try:
        tv_symbol = TRADINGVIEW_SYMBOLS.get(symbol, "FX:EURUSD")
        interval_map = {
            "S5": "5S", "S10": "10S", "S15": "15S", "S30": "30S",
            "M1": "1", "M2": "2", "M3": "3", "M5": "5",
            "M10": "10", "M15": "15", "M30": "30",
            "H1": "60", "H4": "240", "D1": "D"
        }
        interval = interval_map.get(candle, "1")
        api_key = os.environ.get('SCREENSHOT_API_KEY', 'c94425')
        chart_url = f"https://www.tradingview.com/chart/?symbol={tv_symbol}&interval={interval}&theme=dark"
        api_url = (
            f"https://api.screenshotmachine.com/?key={api_key}"
            f"&url={chart_url}&dimension=1280x800&device=desktop"
            f"&delay=3000&format=png&cacheLimit=0"
        )
        print(f"📥 سحب شارت {symbol}...")
        resp = requests.get(api_url, timeout=45)
        if resp.status_code == 200 and len(resp.content) > 5000:
            ts = int(time.time())
            safe = re.sub(r'[^\w]', '_', symbol)
            path = os.path.join(IMAGE_CACHE_DIR, f"chart_{safe}_{candle}_{ts}.png")
            with open(path, "wb") as f:
                f.write(resp.content)
            print(f"✅ {path}")
            return path
        return None
    except Exception as e:
        print(f"⚠️ download error: {e}")
        return None


# ============================================
# إعدادات المستخدم
# ============================================
def save_user_setting(user_id, col, val):
    with db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        cursor.execute(f"UPDATE users SET {col} = ? WHERE user_id = ?", (val, user_id))
        conn.commit()
    log_data_change("update_setting", user_id, f"{col}={val}")


def get_user_setting(user_id):
    try:
        with db_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT candle, trade_time, last_analysis_context, last_analysis_time, country_timezone "
                "FROM users WHERE user_id = ?", (user_id,)
            )
            row = cursor.fetchone()
            if row:
                return row
    except Exception:
        pass
    return ("M1", "قصير (1m-15m)", "", None, "Asia/Gaza")


def save_analysis_context(user_id, text):
    try:
        with db_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET last_analysis_context = ?, last_analysis_time = CURRENT_TIMESTAMP "
                "WHERE user_id = ?", (text[:500], user_id)
            )
            conn.commit()
    except Exception:
        pass


# ============================================
# تهيئة قاعدة البيانات الرئيسية
# ============================================
def init_db():
    with db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute('''
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
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                role TEXT,
                content TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS data_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT,
                user_id INTEGER,
                details TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (ADMIN_ID,))
        if cursor.fetchone():
            cursor.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (ADMIN_ID,))
        else:
            cursor.execute('''
                INSERT INTO users (user_id, username, is_admin, country_timezone)
                VALUES (?, 'Sz2zv', 1, 'Asia/Gaza')
            ''', (ADMIN_ID,))
        conn.commit()
    print("✅ Main DB initialized")
    SubscriptionSystem.init_db()
    SystemSettings.init_db()
    FreeAnalysesTracker.init_db()
    SupportSystem.init_db()


# ============================================
# البرومبتات الثلاثة المتخصصة
# ============================================
def _build_prompt_sol(symbol, candle, trade_time, candles_count, session_info):
    """برومبت النموذج البصري الهجومي"""
    duration = {
        "قصير (1m-15m)": "سكالبينج سريع (1-15 دقيقة)",
        "متوسط (4h-Daily)": "سوينج متوسط (4 ساعات - يومي)",
        "طويل (Weekly-Monthly)": "استثماري طويل (أسبوعي - شهري)"
    }.get(trade_time, trade_time)

    return f"""أنت **المحلل البصري الهجومي V7.5 FINAL** — خبير استخراج البيانات من صور الشارت بدقة بكسل.

📋 **بيانات الجلسة:**
- الأصل: {symbol} | الفريم: {candle} | الشموع: {candles_count}
- المدة: {duration} | الجلسة: {session_info['session']} ({session_info['utc_time']}) - {session_info['volatility']}

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
• نسبة نجاح الصفقة المتوقعة (V7.5 FINAL): [XX]% - [التقييم: ممتاز/جيد/متوسط/ضعيف]
• 🚨 تنبيه فخ السيولة: [نشط / غير نشط] - [إذا نشط: تفاصيل التنبيه]

الآن حلل الشارت المرفق بتركيز كامل على استخراج البيانات، وأعطني الإجابة بالتنسيق أعلاه فقط.
"""


def _build_prompt_astra(symbol, candle, trade_time, candles_count, session_info):
    """برومبت النموذج الهيكلي المنطقي"""
    duration = {
        "قصير (1m-15m)": "سكالبينج (1-15 د)",
        "متوسط (4h-Daily)": "سوينج (4h - D)",
        "طويل (Weekly-Monthly)": "استثماري (W - M)"
    }.get(trade_time, trade_time)

    return f"""أنت **المحلل الهيكلي المنطقي V7.5 FINAL** — خبير SMC/Wyckoff/Volume Profile.

📋 **بيانات الجلسة:**
- الأصل: {symbol} | الفريم: {candle} | الشموع: {candles_count}
- المدة: {duration} | الجلسة: {session_info['session']} ({session_info['utc_time']})

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
• نسبة نجاح الصفقة المتوقعة (V7.5 FINAL): [XX]% - [التقييم: ممتاز/جيد/متوسط/ضعيف]
• 🚨 تنبيه فخ السيولة: [نشط / غير نشط] - [إذا نشط: تفاصيل التنبيه]

الآن حلل الشارت المرفق وأعطني الإجابة بالتنسيق أعلاه فقط.
"""


def _build_prompt_luna(symbol, candle, trade_time, candles_count, session_info):
    """برومبت النموذج الزخمي السريع"""
    duration = {
        "قصير (1m-15m)": "سكالبينج خاطف (1-15 د)",
        "متوسط (4h-Daily)": "سوينج (4h - D)",
        "طويل (Weekly-Monthly)": "استثماري (W - M)"
    }.get(trade_time, trade_time)

    return f"""أنت **صائد الزخم السريع V7.5 FINAL** — قناص فرص فوري.

📋 **بيانات الجلسة:**
- الأصل: {symbol} | الفريم: {candle} | الشموع: {candles_count}
- المدة: {duration} | الجلسة: {session_info['session']} ({session_info['utc_time']})

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
• نسبة نجاح الصفقة المتوقعة (V7.5 FINAL): [XX]% - [التقييم: ممتاز/جيد/متوسط/ضعيف]
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
async def _call_model(model_name, prompt, image_b64, max_tokens=1800):
    """استدعاء نموذج واحد"""
    headers = {
        "Authorization": f"Bearer {MISTRAL_KEY}",
        "Content-Type": "application/json"
    }
    body = {
        "model": model_name,
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
        resp = await loop.run_in_executor(
            None,
            lambda: requests.post(MISTRAL_URL, json=body, headers=headers, timeout=90)
        )
        if resp.status_code == 200:
            return {
                'model': model_name,
                'success': True,
                'content': resp.json()['choices'][0]['message']['content']
            }
        return {'model': model_name, 'success': False, 'error': f"HTTP {resp.status_code}"}
    except Exception as e:
        return {'model': model_name, 'success': False, 'error': str(e)}


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
    """استخراج كل الحقول من التنسيق الحرفي"""
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
        'expected_duration': '', 'peak_time': '',
        'confidence': 50, 'success_rate': 50,
        'liquidity_trap': 'غير نشط', 'trap_details': '',
        'reasoning': '', 'raw': content
    }
    
    if re.search(r'الصورة غير صالحة|صورة أوضح', text):
        p['valid'] = False
        p['image_valid'] = False
        return p

    def grab(pattern, default=None):
        m = re.search(pattern, text, re.IGNORECASE)
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
    p['expected_duration'] = grab(r'المدة المتوقعة[^:]*:\s*([^\n]+)', '')
    p['peak_time'] = grab(r'وقت الذروة[^:]*:\s*([^\n]+)', '')
    
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
    """دمج ذكي لنتائج 3 نماذج"""
    valid = [r for r in results if r.get('success') and r.get('parsed', {}).get('valid')]
    
    if not valid:
        return {'decision': 'HOLD', 'confidence': 0,
                'reasoning': 'فشل جميع النماذج', 'votes': {},
                'models_used': [], 'agreeing_count': 0, 'total_models': 0}

    votes = {}
    for r in valid:
        d = r['parsed']['decision']
        votes[d] = votes.get(d, 0) + 1

    final = max(votes, key=votes.get)
    vc = votes[final]
    total = len(valid)

    # إذا كلهم TRAP → تحويل لانعكاس حسب الهيكل
    if final == 'TRAP' and vc == total:
        structures = [r['parsed'].get('structure', '') for r in valid]
        if any('صاعد' in s for s in structures) or any('هابط' in s for s in structures):
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
    if p is None: return "—"
    if p >= 1000: return f"{p:,.2f}"
    if p >= 1: return f"{p:.4f}"
    return f"{p:.5f}"


def _duration_text(t):
    return {"قصير (1m-15m)": "5-15 دقيقة",
            "متوسط (4h-Daily)": "4 ساعات - يومي",
            "طويل (Weekly-Monthly)": "أسبوعي - شهري"}.get(t, "—")


def _format_final(symbol, candle, trade_time, candles_count, session, cons, results):
    """التنسيق النهائي الحرفي"""
    d = cons['decision']
    emoji = {'BUY':'🟢','SELL':'🔴','HOLD':'🟡','BREAKOUT':'💥',
             'SWEEP':'🔄','REVERSAL':'🔄','TRAP':'🚨'}.get(d,'🟡')
    dec_ar = {'BUY':'شراء 🟢','SELL':'بيع 🔴','HOLD':'احتفاظ 🟡',
              'BREAKOUT':'كسر هيكلي 💥','SWEEP':'سحب سيولة 🔄',
              'REVERSAL':'انعكاس فوري 🔄','TRAP':'فخ سيولة 🚨'}.get(d,'احتفاظ 🟡')

    conf = cons['confidence']
    if conf >= 90: strength, se = 'عالية جدا', '💥'
    elif conf >= 75: strength, se = 'عالية', '🔥'
    elif conf >= 60: strength, se = 'متوسطة', '⚡'
    else: strength, se = 'ضعيفة', '❄️'

    ok = sum(1 for r in results if r.get('success'))
    votes = cons.get('votes', {})
    vote_str = " | ".join([f"{k}:{v}" for k,v in votes.items() if v>0])

    structures = [r['parsed'].get('structure','') for r in results if r.get('success')]
    structure = structures[0] if structures else 'غير محدد'
    agree = 'نعم' if any(r['parsed'].get('timeframe_agreement') for r in results if r.get('success')) else 'لا'

    lines = [
        "📊 التحليل الفني المتقدم:",
        "• بروتوكول الفشل الذاتي: الصورة صالحة",
        f"• الوقت على المنصة (المرجع): {session['utc_time']}",
        f"• حالة الهيكل: {structure} + (توافق 4/4 إطارات: {agree})",
        f"• خريطة السيولة: {cons.get('reasoning','')[:120]}",
        "• الثواني المنقضية: -- ثانية (نافذة التنفيذ: داخل النافذة الذهبية)",
        "",
        "🎯 الإشارة التنفيذية:",
        f"• السعر الحالي: {_fmt_price(cons.get('entry'))}",
        f"• نقطة الدخول المعدلة: {_fmt_price(cons.get('entry'))}",
        f"• حالة الشمعة: مفتوحة - الوقت المتبقي: --",
        f"• القرار الفني: {dec_ar}",
        f"• قوة الإشارة: {strength} {se}",
        f"• نقطة الدخول: {_fmt_price(cons.get('entry'))}",
        f"• نوع الدخول 🚨: {'دخول مباشر' if conf>=85 else 'إعادة اختبار'}",
        f"• وقت الدخول: {'فوري (Flash)' if conf>=90 else 'بعد إغلاق الشمعة'}",
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
        f"• نسبة نجاح الصفقة المتوقعة (V7.5 FINAL): {cons.get('confidence',50)}% - {'ممتاز' if conf>=85 else 'جيد' if conf>=70 else 'متوسط'}",
        f"• 🚨 تنبيه فخ السيولة: {'نشط' if d=='TRAP' else 'غير نشط'}",
        "",
        "━━━━━━━━━━━━━━━━━━",
        f"🤖 **التصويت:** {ok}/3 نماذج | {vote_str}",
        f"📊 **الجلسة:** {session['session']} ({session['volatility']})",
        f"⚙️ **الفريم:** {candle} | **الشموع:** {candles_count}",
        f"📢 {CHANNEL_USERNAME}",
    ]
    return "\n".join(lines)


async def analyze_chart_image(update, context, image_path, candle, trade_time, symbol,
                               candles_count=100, send_wait=True):
    """محرك التحليل الثلاثي الاحترافي"""
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
                if SystemSettings.get('analysis_requires_subscription', 0) == 1:
                    if wait_msg:
                        await wait_msg.edit_text("⚠️ التحليل للمشتركين فقط.\n📞 @Sz2zv")
                    return None
                rem = FreeAnalysesTracker.get_remaining(user_id)
                if rem <= 0:
                    if wait_msg:
                        await wait_msg.edit_text("⚠️ استنفدت تحليلاتك المجانية.\n📞 @Sz2zv")
                    return None

        compressed = compress_image(image_path)
        b64 = encode_image(compressed)
        if not b64:
            if wait_msg:
                await wait_msg.edit_text("❌ فشل قراءة الصورة.")
            return None

        session = get_market_session_auto(user_id)

        tasks = []
        for m in MODELS_FOR_ANALYSIS:
            builder = PROMPT_BUILDERS.get(m)
            if not builder:
                continue
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

        if user_id != ADMIN_ID:
            FreeAnalysesTracker.consume(user_id)
        SubscriptionSystem.increment_usage(user_id, 'chart_analysis_3models')
        save_analysis_context(user_id, cons.get('reasoning', ''))

        final = _format_final(symbol, candle, trade_time, candles_count,
                              session, cons, processed)

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
                await _post_channel(context, symbol, candle, trade_time, cons, session)

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


async def _post_channel(context, symbol, candle, trade_time, cons, session):
    try:
        d = cons['decision']
        emoji = {'BUY':'🟢','SELL':'🔴','BREAKOUT':'💥','SWEEP':'🔄','REVERSAL':'🔄'}.get(d,'🟡')
        d_ar = {'BUY':'شراء','SELL':'بيع','BREAKOUT':'كسر هيكلي','SWEEP':'سحب سيولة','REVERSAL':'انعكاس'}.get(d,d)
        text = (
            f"{emoji} **توصية جديدة - {d_ar}** {emoji}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💎 **الأصل:** `{symbol}`\n"
            f"⏱️ **الفريم:** {candle}\n"
            f"🎯 **المدة:** {_duration_text(trade_time)}\n"
            f"🌍 **الجلسة:** {session['session']}\n"
            f"💪 **الثقة:** {cons['confidence']}%\n"
            f"🤖 **النماذج:** {cons.get('agreeing_count',0)}/{cons.get('total_models',3)}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📍 **الدخول:** `{_fmt_price(cons.get('entry'))}`\n"
            f"🛑 **وقف الخسارة:** `{_fmt_price(cons.get('sl'))}`\n"
            f"🎯 **الهدف 1:** `{_fmt_price(cons.get('tp1'))}`\n"
            f"🎯 **الهدف 2:** `{_fmt_price(cons.get('tp2'))}`\n"
            f"🎯 **الهدف 3:** `{_fmt_price(cons.get('tp3'))}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🕐 **الوقت:** {session['utc_time']}\n"
            f"📢 {CHANNEL_USERNAME}\n"
            f"⚠️ إدارة رأس المال واجبة"
        )
        await context.bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="Markdown")
        print(f"✅ نشرت: {symbol} {d}")
    except Exception as e:
        print(f"⚠️ نشر فشل: {e}")

# ============================================
# Flask Admin
# ============================================
app = Flask(__name__)
app.secret_key = SECRET_KEY

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
.header{text-align:center;padding:30px;margin-bottom:30px;background:linear-gradient(135deg,#0f3460,#e94560);border-radius:15px;box-shadow:0 10px 30px rgba(233,69,96,0.3);}
.header h1{font-size:2.5em;margin-bottom:10px;}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px;margin-bottom:30px;}
.card{background:rgba(255,255,255,0.05);border-radius:15px;padding:25px;border:1px solid rgba(255,255,255,0.1);}
.card:hover{border-color:#e94560;}
.card h3{color:#e94560;margin-bottom:15px;}
.stat{display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.05);}
.stat:last-child{border-bottom:none;}
.stat-label{color:#aaa;}.stat-value{font-weight:bold;color:#4ecca3;}
.form-group{margin-bottom:15px;}
.form-group label{display:block;margin-bottom:8px;color:#ccc;font-size:0.9em;}
.form-group input,.form-group select{width:100%;padding:12px;border-radius:8px;border:1px solid rgba(255,255,255,0.2);background:rgba(0,0,0,0.3);color:#fff;font-size:1em;}
.btn{padding:12px 25px;border:none;border-radius:8px;cursor:pointer;font-size:1em;font-weight:bold;margin-top:10px;}
.btn-primary{background:#e94560;color:white;}.btn-primary:hover{background:#ff5c77;}
.btn-success{background:#4ecca3;color:#1a1a2e;}
.btn-danger{background:#d32f2f;color:white;}
.alert{padding:15px;border-radius:8px;margin-bottom:20px;background:rgba(78,204,163,0.15);border:1px solid #4ecca3;color:#4ecca3;}
.alert-error{background:rgba(233,69,96,0.15);border-color:#e94560;color:#e94560;}
table{width:100%;border-collapse:collapse;margin-top:15px;}
th,td{padding:12px;text-align:right;border-bottom:1px solid rgba(255,255,255,0.1);}
th{background:rgba(233,69,96,0.2);color:#e94560;}
.tabs{display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap;}
.tab{padding:10px 20px;background:rgba(255,255,255,0.05);border-radius:8px;cursor:pointer;color:#ccc;border:1px solid transparent;}
.tab.active{background:#e94560;color:white;border-color:#e94560;}
.tab-content{display:none;}.tab-content.active{display:block;}
</style></head><body><div class="container">
<div class="header"><h1>👑 Obeida Trading - لوحة التحكم</h1><p>إدارة كاملة للنظام</p></div>
{% if message %}<div class="alert">{{ message }}</div>{% endif %}
{% if error %}<div class="alert alert-error">{{ error }}</div>{% endif %}

<div class="tabs">
<div class="tab active" onclick="showTab('dashboard', this)">📊 الرئيسية</div>
<div class="tab" onclick="showTab('settings', this)">⚙️ الإعدادات</div>
<div class="tab" onclick="showTab('users', this)">👥 المستخدمين</div>
<div class="tab" onclick="showTab('support', this)">🆘 الدعم</div>
<div class="tab" onclick="showTab('channel', this)">📢 القناة</div>
</div>

<div id="dashboard" class="tab-content active"><div class="grid">
<div class="card"><h3>📊 إحصائيات</h3>
<div class="stat"><span class="stat-label">إجمالي المستخدمين</span><span class="stat-value">{{ stats.total_users }}</span></div>
<div class="stat"><span class="stat-label">المشتركين النشطين</span><span class="stat-value">{{ stats.active_users }}</span></div>
<div class="stat"><span class="stat-label">المحظورين</span><span class="stat-value">{{ stats.blocked_users }}</span></div>
</div>
<div class="card"><h3>📈 استخدام الميزات</h3>
{% for f, c in stats.feature_usage.items() %}
<div class="stat"><span class="stat-label">{{ f }}</span><span class="stat-value">{{ c }}</span></div>
{% endfor %}</div>
<div class="card"><h3>🔑 الاشتراكات</h3>
{% for t, c in stats.subscriptions_by_type.items() %}
<div class="stat"><span class="stat-label">{{ t }}</span><span class="stat-value">{{ c }}</span></div>
{% endfor %}</div>
</div></div>

<div id="settings" class="tab-content">
<div class="card"><h3>⚙️ إعدادات التحليل</h3>
<form method="POST" action="/admin/settings">
<div class="form-group"><label>عدد التحليلات المجانية (0=إيقاف, -1=غير محدود)</label>
<input type="number" name="free_analyses_limit" value="{{ settings.free_analyses_limit }}"></div>
<div class="form-group"><label>التحليل للمشتركين فقط؟</label>
<select name="analysis_requires_subscription">
<option value="0" {% if settings.analysis_requires_subscription == 0 %}selected{% endif %}>لا</option>
<option value="1" {% if settings.analysis_requires_subscription == 1 %}selected{% endif %}>نعم</option>
</select></div>
<div class="form-group"><label>النشر التلقائي في القناة</label>
<select name="channel_auto_post">
<option value="0" {% if settings.channel_auto_post == 0 %}selected{% endif %}>معطل</option>
<option value="1" {% if settings.channel_auto_post == 1 %}selected{% endif %}>مفعل</option>
</select></div>
<div class="form-group"><label>حد الثقة الأدنى للنشر (%)</label>
<input type="number" name="channel_min_confidence" value="{{ settings.channel_min_confidence }}"></div>
<div class="form-group"><label>الدعم الفني</label>
<select name="support_enabled">
<option value="0" {% if settings.support_enabled == 0 %}selected{% endif %}>معطل</option>
<option value="1" {% if settings.support_enabled == 1 %}selected{% endif %}>مفعل</option>
</select></div>
<button type="submit" class="btn btn-primary">💾 حفظ</button>
</form></div>

<div class="card" style="margin-top:20px;"><h3>🔄 إعادة تعيين التحليلات المجانية</h3>
<form method="POST" action="/admin/reset_free">
<div class="form-group"><label>User ID (فارغ = الجميع)</label>
<input type="text" name="user_id" placeholder="123456789"></div>
<button type="submit" class="btn btn-danger">🔄 إعادة تعيين</button>
</form></div>
</div>

<div id="users" class="tab-content"><div class="card"><h3>👥 المستخدمين</h3>
<table><thead><tr><th>ID</th><th>Username</th><th>الاشتراك</th><th>الحالة</th><th>آخر نشاط</th></tr></thead><tbody>
{% for u in users %}
<tr><td>{{ u[0] }}</td><td>{{ u[1] or '—' }}</td><td>{{ u[6] or 'لا يوجد' }}</td>
<td>{% if u[5] %}🚫{% else %}✅{% endif %}</td><td>{{ u[4] or '—' }}</td></tr>
{% endfor %}
</tbody></table></div></div>

<div id="support" class="tab-content"><div class="card"><h3>🆘 التذاكر</h3>
<table><thead><tr><th>#</th><th>User</th><th>الموضوع</th><th>الحالة</th><th>رد</th></tr></thead><tbody>
{% for t in tickets %}
<tr><td>{{ t[0] }}</td><td>{{ t[2] or t[1] }}</td><td>{{ t[3] }}</td><td>{{ t[5] }}</td>
<td><form method="POST" action="/admin/reply" style="display:flex;gap:5px;">
<input type="hidden" name="ticket_id" value="{{ t[0] }}">
<input type="text" name="reply" placeholder="ردك" style="padding:5px;border-radius:5px;border:1px solid #444;background:#000;color:#fff;">
<button type="submit" class="btn btn-success" style="padding:5px 10px;">إرسال</button>
</form></td></tr>
{% endfor %}
</tbody></table></div></div>

<div id="channel" class="tab-content"><div class="card"><h3>📢 القناة</h3>
<p>القناة: <a href="https://t.me/ObeidaTrading" target="_blank" style="color:#4ecca3;">{{ channel }}</a></p>
<form method="POST" action="/admin/broadcast_channel">
<div class="form-group"><label>رسالة للنشر</label>
<textarea name="message" rows="5" style="width:100%;padding:10px;border-radius:8px;background:#000;color:#fff;border:1px solid #444;"></textarea></div>
<button type="submit" class="btn btn-success">📤 نشر</button>
</form></div></div>
</div>
<script>
function showTab(id, el) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.getElementById(id).classList.add('active');
    el.classList.add('active');
}
</script></body></html>
"""


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper


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
        users=SubscriptionSystem.get_all_users(),
        tickets=SupportSystem.get_open_tickets(),
        settings={k: SystemSettings.get(k) for k in DEFAULT_SETTINGS},
        channel=CHANNEL_USERNAME,
        message=request.args.get('message'),
        error=request.args.get('error')
    )


@app.route('/admin/settings', methods=['POST'])
@login_required
def admin_settings():
    try:
        for key in DEFAULT_SETTINGS:
            v = request.form.get(key)
            if v is not None:
                SystemSettings.set(key, v, updated_by=ADMIN_ID)
        return redirect(url_for('admin_panel', message="✅ تم الحفظ"))
    except Exception as e:
        return redirect(url_for('admin_panel', error=str(e)))


@app.route('/admin/reset_free', methods=['POST'])
@login_required
def admin_reset_free():
    uid = request.form.get('user_id', '').strip()
    try:
        FreeAnalysesTracker.reset(int(uid) if uid else None)
        return redirect(url_for('admin_panel', message="✅ تم"))
    except Exception as e:
        return redirect(url_for('admin_panel', error=str(e)))


@app.route('/admin/reply', methods=['POST'])
@login_required
def admin_reply_web():
    tid = request.form.get('ticket_id')
    reply = request.form.get('reply', '').strip()
    if not reply:
        return redirect(url_for('admin_panel', error="الرد فارغ"))
    try:
        uid = SupportSystem.add_reply(int(tid), ADMIN_ID, reply)
        if uid and hasattr(app, 'telegram_app'):
            asyncio.run_coroutine_threadsafe(
                app.telegram_app.bot.send_message(
                    chat_id=uid,
                    text=f"📬 **رد الإدارة #{tid}**\n\n{reply}",
                    parse_mode="Markdown"
                ),
                app.loop
            )
        return redirect(url_for('admin_panel', message="✅ تم الرد"))
    except Exception as e:
        return redirect(url_for('admin_panel', error=str(e)))


@app.route('/admin/broadcast_channel', methods=['POST'])
@login_required
def admin_broadcast():
    msg = request.form.get('message', '').strip()
    if not msg:
        return redirect(url_for('admin_panel', error="الرسالة فارغة"))
    try:
        if hasattr(app, 'telegram_app'):
            asyncio.run_coroutine_threadsafe(
                app.telegram_app.bot.send_message(
                    chat_id=CHANNEL_ID, text=msg, parse_mode="Markdown"
                ),
                app.loop
            )
        return redirect(url_for('admin_panel', message="✅ تم النشر"))
    except Exception as e:
        return redirect(url_for('admin_panel', error=str(e)))
        
# ============================================
# Handlers
# ============================================
async def subscription_required(update, context):
    uid = update.effective_user.id
    if uid == ADMIN_ID:
        return True
    user = update.effective_user
    SubscriptionSystem.register_user(
        user_id=uid, username=user.username, first_name=user.first_name,
        last_name=user.last_name, language_code=user.language_code, is_bot=user.is_bot
    )
    ok, msg, _ = SubscriptionSystem.check_subscription(uid)
    if not ok:
        await update.message.reply_text(
            f"⚠️ **ليس لديك صلاحية**\n\n❌ {msg}\n\n"
            f"📞 للاشتراك: @Sz2zv",
            parse_mode="Markdown"
        )
        return False
    return True


def main_keyboard(user_id):
    kb = [
        ["⚙️ إعدادات التحليل", "📊 تحليل صورة"],
        ["💬 دردشة", "📈 توصية"],
        ["🧮 حاسبة", "🆘 الدعم الفني"],
    ]
    if user_id == ADMIN_ID:
        kb.append(["👑 لوحة التحكم"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)


async def start(update, context):
    user = update.effective_user
    uid = user.id
    SubscriptionSystem.register_user(
        user_id=uid, username=user.username, first_name=user.first_name,
        last_name=user.last_name, language_code=user.language_code, is_bot=user.is_bot
    )
    cleanup_user_data(context, uid)
    
    is_admin = (uid == ADMIN_ID)
    ok, msg, details = SubscriptionSystem.check_subscription(uid)
    session = get_market_session_auto(uid)
    
    if is_admin:
        welcome = (f"👑 **مرحباً أيها الأدمن**\n\n"
                   f"🕐 الجلسة: {session['session']}\n"
                   f"📊 التقلب: {session['volatility']}\n"
                   f"⏰ التوقيت: {session['utc_time']}\n\n"
                   f"اختر من القائمة:")
    elif ok:
        sub = details['name'] if details else 'مشترك'
        welcome = (f"🚀 **Obeida Trading**\n\n"
                   f"✅ اشتراكك: {sub}\n"
                   f"🕐 الجلسة: {session['session']}\n"
                   f"📊 التقلب: {session['volatility']}\n\n"
                   f"اختر من القائمة:")
    else:
        rem = FreeAnalysesTracker.get_remaining(uid)
        txt = f"🎁 تحليلات مجانية: **{rem}**" if rem > 0 else "⚠️ استنفدت التحليلات المجانية"
        welcome = (f"🚀 **Obeida Trading**\n\n{txt}\n"
                   f"🕐 الجلسة: {session['session']}\n\n"
                   f"💡 للاشتراك: @Sz2zv\n\nاختر من القائمة:")
    
    await update.message.reply_text(
        welcome, reply_markup=main_keyboard(uid), parse_mode="Markdown"
    )
    return MAIN_MENU


async def handle_main_menu(update, context):
    text = update.message.text
    uid = update.effective_user.id
    
    if text == "🧮 حاسبة":
        return await start_calculator(update, context)
    if text == "🆘 الدعم الفني":
        return await start_support(update, context)
    if text == "👑 لوحة التحكم" and uid == ADMIN_ID:
        await update.message.reply_text(
            f"🔗 **لوحة التحكم:**\nhttp://your-server:5000/admin/login"
        )
        return MAIN_MENU
    
    if text == "⚙️ إعدادات التحليل":
        kb = [CANDLE_SPEEDS[i:i+3] for i in range(0, len(CANDLE_SPEEDS), 3)]
        kb.append(["الرجوع للقائمة الرئيسية"])
        await update.message.reply_text(
            "⚙️ اختر سرعة الشموع:",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
        )
        return SETTINGS_CANDLE
    
    if text == "📊 تحليل صورة":
        candle, trade_time, _, _, _ = get_user_setting(uid)
        await update.message.reply_text(
            f"📊 **جاهز للتحليل**\n⚙️ {candle} | 🎯 {trade_time}\n\n📤 أرسل صورة الشارت:",
            reply_markup=ReplyKeyboardMarkup([["الرجوع للقائمة الرئيسية"]],
                                              resize_keyboard=True),
            parse_mode="Markdown"
        )
        return ANALYZE_MODE
    
    if text == "💬 دردشة":
        return await start_chat(update, context)
    if text == "📈 توصية":
        return await start_recommendation(update, context)
    if text == "الرجوع للقائمة الرئيسية":
        await update.message.reply_text("🏠", reply_markup=main_keyboard(uid))
        return MAIN_MENU
    
    return MAIN_MENU


async def handle_settings_candle(update, context):
    text = update.message.text
    uid = update.effective_user.id
    if text == "الرجوع للقائمة الرئيسية":
        await update.message.reply_text("🏠", reply_markup=main_keyboard(uid))
        return MAIN_MENU
    if text in CANDLE_SPEEDS:
        save_user_setting(uid, "candle", text)
        kb = [TRADE_TIMES[i:i+2] for i in range(0, len(TRADE_TIMES), 2)]
        kb.append(["الرجوع للقائمة الرئيسية"])
        await update.message.reply_text(
            f"✅ {text}\n\nاختر مدة الصفقة:",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
        )
        return SETTINGS_TIME
    await update.message.reply_text("❌ اختر سرعة صحيحة")
    return SETTINGS_CANDLE


async def handle_settings_time(update, context):
    text = update.message.text
    uid = update.effective_user.id
    if text == "الرجوع للقائمة الرئيسية":
        await update.message.reply_text("🏠", reply_markup=main_keyboard(uid))
        return MAIN_MENU
    if text in TRADE_TIMES:
        save_user_setting(uid, "trade_time", text)
        await update.message.reply_text(
            f"✅ تم حفظ الإعدادات.\n📤 ارفع صورة الشارت:",
            reply_markup=main_keyboard(uid)
        )
        return MAIN_MENU
    await update.message.reply_text("❌ اختر مدة صحيحة")
    return SETTINGS_TIME


async def handle_analyze_mode(update, context):
    text = update.message.text
    uid = update.effective_user.id
    if text == "الرجوع للقائمة الرئيسية":
        await update.message.reply_text("🏠", reply_markup=main_keyboard(uid))
        return MAIN_MENU
    await update.message.reply_text("📤 أرسل صورة الشارت.")
    return ANALYZE_MODE


async def handle_image_analysis(update, context):
    uid = update.effective_user.id
    candle, trade_time, _, _, _ = get_user_setting(uid)
    
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
    return ANALYZE_MODE


async def start_chat(update, context):
    if not await subscription_required(update, context):
        return CHAT_MODE
    kb = [["ايقاف الدردشة", "الرجوع للقائمة الرئيسية"]]
    await update.message.reply_text(
        "💬 **وضع الدردشة**\n\nأرسل سؤالك.",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return CHAT_MODE


async def handle_chat_message(update, context):
    if not await subscription_required(update, context):
        return CHAT_MODE
    text = update.message.text
    uid = update.effective_user.id
    
    if text == "ايقاف الدردشة" or text == "الرجوع للقائمة الرئيسية":
        await update.message.reply_text("🏠", reply_markup=main_keyboard(uid))
        return MAIN_MENU
    
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
        resp = requests.post(MISTRAL_URL, headers=headers, json=payload, timeout=60)
        if resp.status_code == 200:
            result = resp.json()['choices'][0]['message']['content']
            for i in range(0, len(result), 4000):
                chunk = result[i:i+4000]
                if i == 0:
                    await wait.edit_text(chunk)
                else:
                    await update.message.reply_text(chunk)
        else:
            await wait.edit_text(f"❌ خطأ: {resp.status_code}")
    except Exception as e:
        await wait.edit_text(f"❌ {e}")
    
    return CHAT_MODE


async def start_recommendation(update, context):
    if not await subscription_required(update, context):
        return RECOMMENDATION_MODE
    kb = [[k] for k in CATEGORIES.keys()]
    kb.append(["الرجوع للقائمة الرئيسية"])
    await update.message.reply_text(
        "📈 **نظام التوصيات**\n\nاختر القسم:",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return RECOMMENDATION_MODE


async def handle_recommendation(update, context):
    if not await subscription_required(update, context):
        return RECOMMENDATION_MODE
    text = update.message.text.strip()
    uid = update.effective_user.id
    
    if text == "الرجوع للقائمة الرئيسية":
        await update.message.reply_text("🏠", reply_markup=main_keyboard(uid))
        return MAIN_MENU
    if text == "🔙 العودة للقائمة":
        return await start_recommendation(update, context)
    
    if text in CATEGORIES:
        kb = [[a] for a in CATEGORIES[text]]
        kb.append(["🔙 العودة للقائمة", "الرجوع للقائمة الرئيسية"])
        await update.message.reply_text(
            f"📍 {text}\nاختر:",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
        )
        return CATEGORY_SELECTION
    
    # البحث عن الأصل
    symbol = None
    for lst in CATEGORIES.values():
        if text in lst:
            symbol = text
            break
    
    if symbol:
        wait = await update.message.reply_text(f"📸 سحب شارت {symbol}...")
        chart = download_chart_image_v2(symbol, "M1")
        if chart and os.path.exists(chart):
            with open(chart, 'rb') as f:
                await update.message.reply_photo(photo=f, caption=f"📈 {symbol}")
            await wait.edit_text("🧠 التحليل الثلاثي...")
            await analyze_chart_image(
                update, context, chart, "M1", "قصير (1m-15m)", symbol,
                candles_count=100, send_wait=False
            )
            try:
                os.remove(chart)
            except Exception:
                pass
        else:
            await wait.edit_text("❌ فشل سحب الشارت. حاول مرة أخرى.")
        
        kb = [[k] for k in CATEGORIES.keys()]
        kb.append(["الرجوع للقائمة الرئيسية"])
        await update.message.reply_text(
            "🔽 اختر قسم آخر:",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
        )
        return RECOMMENDATION_MODE
    
    await update.message.reply_text(
        "❌ خيار غير معروف.",
        reply_markup=ReplyKeyboardMarkup([["الرجوع للقائمة الرئيسية"]], resize_keyboard=True)
    )
    return RECOMMENDATION_MODE


async def start_calculator(update, context):
    if not await subscription_required(update, context):
        return CALCULATOR_MODE
    kb = [
        ["💰 حساب حجم الصفقة", "📊 حساب الأرباح"],
        ["📉 حساب المخاطر", "🎯 حساب نقاط الدخول"],
        ["الرجوع للقائمة الرئيسية"]
    ]
    await update.message.reply_text(
        "🧮 **الحاسبة**\n\nاختر النوع:",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return CALCULATOR_MODE


async def handle_calculator(update, context):
    text = update.message.text
    uid = update.effective_user.id
    
    if text == "الرجوع للقائمة الرئيسية":
        await update.message.reply_text("🏠", reply_markup=main_keyboard(uid))
        return MAIN_MENU
    
    if text == "💰 حساب حجم الصفقة":
        context.user_data['calc'] = 'size'
        await update.message.reply_text(
            "أرسل: `رأس المال | نسبة المخاطرة% | مسافة الوقف`\nمثال: `1000 | 2 | 50`",
            parse_mode="Markdown"
        )
        return CALCULATOR_MODE
    if text == "📊 حساب الأرباح":
        context.user_data['calc'] = 'profit'
        await update.message.reply_text("أرسل: `لوت | نقاط`\nمثال: `1 | 30`", parse_mode="Markdown")
        return CALCULATOR_MODE
    if text == "📉 حساب المخاطر":
        context.user_data['calc'] = 'risk'
        await update.message.reply_text("أرسل: `رأس المال | نسبة%`\nمثال: `5000 | 1.5`", parse_mode="Markdown")
        return CALCULATOR_MODE
    if text == "🎯 حساب نقاط الدخول":
        context.user_data['calc'] = 'entry'
        await update.message.reply_text("أرسل: `دخول | وقف | R:R`\nمثال: `1.0850 | 1.0820 | 2`", parse_mode="Markdown")
        return CALCULATOR_MODE
    
    mode = context.user_data.get('calc')
    if mode:
        try:
            parts = [float(x.strip()) for x in text.split('|')]
            if mode == 'size' and len(parts) == 3:
                cap, risk, dist = parts
                amt = cap * risk / 100
                size = amt / dist if dist > 0 else 0
                res = f"💰 **حجم الصفقة:**\n• المخاطرة: ${amt:,.2f}\n• الحجم: {size:.4f} لوت"
            elif mode == 'profit' and len(parts) == 2:
                lot, pts = parts
                res = f"📊 **الربح:** ${lot * pts * 10:,.2f}"
            elif mode == 'risk' and len(parts) == 2:
                cap, pct = parts
                res = f"📉 **المخاطرة:** ${cap * pct / 100:,.2f}"
            elif mode == 'entry' and len(parts) == 3:
                e, sl, rr = parts
                r = abs(e - sl)
                res = (f"🎯 **النقاط:**\n• دخول: {e}\n• وقف: {sl}\n"
                       f"• TP1 (1:{rr}): {e + r*rr:.5f}\n• TP2 (1:{rr*2}): {e + r*rr*2:.5f}")
            else:
                res = "❌ صيغة خاطئة"
            await update.message.reply_text(res, parse_mode="Markdown")
            context.user_data.pop('calc', None)
        except Exception:
            await update.message.reply_text("❌ أرقام غير صالحة")
    return CALCULATOR_MODE


async def start_support(update, context):
    if not SystemSettings.get('support_enabled', 1):
        await update.message.reply_text("⚠️ الدعم معطل.")
        return MAIN_MENU
    if not await subscription_required(update, context):
        return SUPPORT_MODE
    await update.message.reply_text(
        "🆘 **الدعم الفني**\n\nأرسل رسالتك (أو /cancel):",
        reply_markup=ReplyKeyboardRemove()
    )
    return SUPPORT_MODE


async def handle_support(update, context):
    text = update.message.text
    uid = update.effective_user.id
    user = update.effective_user
    
    if text == "/cancel":
        await update.message.reply_text("🏠", reply_markup=main_keyboard(uid))
        return MAIN_MENU
    
    tid = SupportSystem.create_ticket(uid, user.username or str(uid), "دعم", text)
    
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
    await update.message.reply_text("🏠", reply_markup=main_keyboard(uid))
    return MAIN_MENU


async def admin_reply(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("الاستخدام: `/reply <id> <الرد>`", parse_mode="Markdown")
        return
    try:
        tid = int(args[0])
        reply = " ".join(args[1:])
    except ValueError:
        await update.message.reply_text("❌ id غير صالح")
        return
    uid = SupportSystem.add_reply(tid, ADMIN_ID, reply)
    if uid:
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=f"📬 **رد الإدارة #{tid}**\n\n{reply}",
                parse_mode="Markdown"
            )
            await update.message.reply_text("✅ تم الإرسال")
        except Exception as e:
            await update.message.reply_text(f"⚠️ {e}")
    else:
        await update.message.reply_text("❌ التذكرة غير موجودة")


# ============================================
# main
# ============================================
def main():
    init_db()
    
    application = Application.builder().token(TOKEN).build()
    
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
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
            CALCULATOR_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_calculator)],
            SUPPORT_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_support)],
        },
        fallbacks=[CommandHandler("start", start)],
    )
    
    application.add_handler(conv)
    application.add_handler(CommandHandler("reply", admin_reply))
    
    def run_flask():
        app.telegram_app = application
        app.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(app.loop)
        app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
    
    threading.Thread(target=run_flask, daemon=True).start()
    
    print("🚀 Bot + Flask started")
    application.run_polling(drop_pending_updates=True)


if __name__ == '__main__':
    main()
    
