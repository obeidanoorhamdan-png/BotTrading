#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Obeida Trading Bot — Pro Edition (ملف واحد)
============================================
بوت تليجرام للتحليل الفني + دردشة + توصيات + نظام اشتراكات
مع لوحة تحكم ويب كاملة للتحكم بكل شيء في البوت.

المتطلبات:
    pip install "python-telegram-bot>=20.7" flask pillow pytz requests werkzeug
    (اختياري للإنتاج) pip install waitress

متغيرات البيئة:
    TOKEN            توكن بوت تليجرام (إلزامي)
    AI_KEY           مفتاح واجهة الذكاء الاصطناعي (إلزامي)
    AI_URL           رابط الواجهة (افتراضي مضبوط)
    ADMIN_ID         معرف المشرف الرئيسي في تليجرام
    ADMIN_USERNAME   اسم مستخدم لوحة الويب (افتراضي: admin)
    ADMIN_PASSWORD   كلمة مرور اللوحة (إن لم تُحدد تُولَّد عشوائياً وتُطبع مرة واحدة)
    SCREENSHOT_KEY   مفتاح screenshotmachine لسحب صور الشارت (اختياري)
    PUBLIC_URL       الرابط العام للوحة (اختياري، يظهر في زر لوحة الويب)
    PORT             منفذ الويب (افتراضي 8080)
    HTTPS            ضع 1 إذا اللوحة خلف HTTPS لتفعيل Secure cookies

التشغيل:
    python obeida_bot.py
"""
from __future__ import annotations

import asyncio
import base64
import csv
import html
import io
import json
import logging
import os
import re
import secrets
import shutil
import sqlite3
import sys
import threading
import time
import traceback
from contextlib import contextmanager
from datetime import datetime, timedelta
from functools import wraps
from logging.handlers import RotatingFileHandler

import pytz
import requests
from flask import Flask, Response, jsonify, redirect, request, send_file, session
from PIL import Image, ImageOps
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.constants import ChatAction
from telegram.error import NetworkError, TimedOut
from telegram.ext import (Application, CommandHandler, ContextTypes,
                          ConversationHandler, MessageHandler, filters)
from werkzeug.security import check_password_hash, generate_password_hash

# ════════════════════════════════════════════════════════════
# 1) الإعدادات الأساسية
# ════════════════════════════════════════════════════════════
APP_VERSION = "3.0.0"
BRAND = "Obeida Trading"
START_TIME = time.time()


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


TOKEN = _env("TOKEN")
AI_KEY = _env("AI_KEY") or _env("MISTRAL_KEY")
AI_URL = _env("AI_URL", "https://codex-relay.codes/v1/chat/completions")
MODEL_VISION = _env("MODEL_VISION", "gpt-6.1-sol")     # الرؤية والاستخراج البصري
MODEL_AUDIT = _env("MODEL_AUDIT", "gpt-6-astra")       # التحليل النصي/التوصية
MODEL_CHAT = _env("MODEL_CHAT", "gpt-6-luna")          # الدردشة
SCREENSHOT_KEY = _env("SCREENSHOT_KEY")
ADMIN_ID = int(_env("ADMIN_ID", "6207431030"))
ADMIN_USERNAME = _env("ADMIN_USERNAME", "admin")
PUBLIC_URL = _env("PUBLIC_URL")
PORT = int(_env("PORT", "8080"))

DB_NAME = _env("DB_NAME", "abood-gpt.db")
SUB_DB = _env("SUBSCRIPTION_DB_NAME", "subscription_system.db")
BACKUP_DIR = "backups"
IMAGE_CACHE_DIR = "image_cache"
DATA_VERSION = "3.0.0"

CANDLE_SPEEDS = ["S5", "S10", "S15", "S30", "M1", "M2", "M3", "M5", "M10", "M15", "M30", "H1", "H4", "D1"]
TRADE_TIMES = ["قصير (1m-15m)", "متوسط (4h-Daily)", "طويل (Weekly-Monthly)"]
BACK = "الرجوع للقائمة الرئيسية"

for _d in (IMAGE_CACHE_DIR, BACKUP_DIR):
    os.makedirs(_d, exist_ok=True)


def setup_logging() -> logging.Logger:
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s")
    logger = logging.getLogger("obeida")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fh = RotatingFileHandler("bot.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(fh)
        logger.addHandler(sh)
    # منع تسريب التوكن في سجلات الطلبات
    for noisy in ("httpx", "httpcore", "werkzeug", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return logger


log = setup_logging()

# ════════════════════════════════════════════════════════════
# 2) الدول والمناطق الزمنية
# ════════════════════════════════════════════════════════════
COUNTRIES = {
    # الدول العربية (أول 22)
    "فلسطين 🇵🇸": "Asia/Gaza", "مصر 🇪🇬": "Africa/Cairo", "السعودية 🇸🇦": "Asia/Riyadh",
    "الإمارات 🇦🇪": "Asia/Dubai", "قطر 🇶🇦": "Asia/Qatar", "الكويت 🇰🇼": "Asia/Kuwait",
    "البحرين 🇧🇭": "Asia/Bahrain", "عمان 🇴🇲": "Asia/Muscat", "اليمن 🇾🇪": "Asia/Aden",
    "العراق 🇮🇶": "Asia/Baghdad", "الأردن 🇯🇴": "Asia/Amman", "لبنان 🇱🇧": "Asia/Beirut",
    "سوريا 🇸🇾": "Asia/Damascus", "ليبيا 🇱🇾": "Africa/Tripoli", "تونس 🇹🇳": "Africa/Tunis",
    "الجزائر 🇩🇿": "Africa/Algiers", "المغرب 🇲🇦": "Africa/Casablanca", "موريتانيا 🇲🇷": "Africa/Nouakchott",
    "السودان 🇸🇩": "Africa/Khartoum", "الصومال 🇸🇴": "Africa/Mogadishu", "جيبوتي 🇩🇯": "Africa/Djibouti",
    "جزر القمر 🇰🇲": "Indian/Comoro",
    # دول رئيسية
    "الولايات المتحدة 🇺🇸 (نيويورك)": "America/New_York", "المملكة المتحدة 🇬🇧": "Europe/London",
    "تركيا 🇹🇷": "Europe/Istanbul", "ألمانيا 🇩🇪": "Europe/Berlin", "فرنسا 🇫🇷": "Europe/Paris",
    "روسيا 🇷🇺": "Europe/Moscow", "الهند 🇮🇳": "Asia/Kolkata", "الصين 🇨🇳": "Asia/Shanghai",
    "اليابان 🇯🇵": "Asia/Tokyo", "كندا 🇨🇦": "America/Toronto", "البرازيل 🇧🇷": "America/Sao_Paulo",
    "أستراليا 🇦🇺": "Australia/Sydney", "جنوب أفريقيا 🇿🇦": "Africa/Johannesburg",
    # بقية الدول
    "إيران 🇮🇷": "Asia/Tehran", "باكستان 🇵🇰": "Asia/Karachi", "أفغانستان 🇦🇫": "Asia/Kabul",
    "بنجلاديش 🇧🇩": "Asia/Dhaka", "إندونيسيا 🇮🇩": "Asia/Jakarta", "ماليزيا 🇲🇾": "Asia/Kuala_Lumpur",
    "تايلاند 🇹🇭": "Asia/Bangkok", "سنغافورة 🇸🇬": "Asia/Singapore", "كوريا الجنوبية 🇰🇷": "Asia/Seoul",
    "نيوزيلندا 🇳🇿": "Pacific/Auckland", "إيطاليا 🇮🇹": "Europe/Rome", "إسبانيا 🇪🇸": "Europe/Madrid",
    "هولندا 🇳🇱": "Europe/Amsterdam", "بلجيكا 🇧🇪": "Europe/Brussels", "النمسا 🇦🇹": "Europe/Vienna",
    "سويسرا 🇨🇭": "Europe/Zurich", "السويد 🇸🇪": "Europe/Stockholm", "النرويج 🇳🇴": "Europe/Oslo",
    "الدنمارك 🇩🇰": "Europe/Copenhagen", "فنلندا 🇫🇮": "Europe/Helsinki", "أوكرانيا 🇺🇦": "Europe/Kiev",
    "بولندا 🇵🇱": "Europe/Warsaw", "اليونان 🇬🇷": "Europe/Athens", "البرتغال 🇵🇹": "Europe/Lisbon",
    "الولايات المتحدة 🇺🇸 (شيكاغو)": "America/Chicago", "الولايات المتحدة 🇺🇸 (دنفر)": "America/Denver",
    "الولايات المتحدة 🇺🇸 (لوس أنجلوس)": "America/Los_Angeles", "المكسيك 🇲🇽": "America/Mexico_City",
    "الأرجنتين 🇦🇷": "America/Argentina/Buenos_Aires", "تشيلي 🇨🇱": "America/Santiago",
    "كولومبيا 🇨🇴": "America/Bogota", "فنزويلا 🇻🇪": "America/Caracas", "بيرو 🇵🇪": "America/Lima",
    "نيجيريا 🇳🇬": "Africa/Lagos", "كينيا 🇰🇪": "Africa/Nairobi", "إثيوبيا 🇪🇹": "Africa/Addis_Ababa",
}
_COUNTRY_KEYS = list(COUNTRIES)
ARAB_KEYS = _COUNTRY_KEYS[:22]
MAJOR_KEYS = _COUNTRY_KEYS[22:35]
DEFAULT_TZ = "Asia/Gaza"

# ════════════════════════════════════════════════════════════
# 3) الأقسام والرموز
# ════════════════════════════════════════════════════════════
CATEGORIES = {
    "أزواج العملات 🏛️": [
        "EUR/USD (OTC)", "GBP/USD (OTC)", "USD/JPY (OTC)", "USD/CHF (OTC)", "AUD/USD (OTC)",
        "USD/CAD (OTC)", "NZD/USD (OTC)", "EUR/GBP (OTC)", "EUR/JPY (OTC)", "GBP/JPY (OTC)",
        "EUR/CHF (OTC)", "AUD/JPY (OTC)", "EUR/AUD (OTC)", "EUR/CAD (OTC)", "GBP/AUD (OTC)",
        "CAD/JPY (OTC)", "CHF/JPY (OTC)", "NZD/JPY (OTC)", "GBP/CHF (OTC)", "AUD/CAD (OTC)"],
    "مؤشرات الأسواق 📊": [
        "S&P 500 (OTC)", "Dow Jones (OTC)", "Nasdaq 100 (OTC)", "DAX 40 (OTC)",
        "CAC 40 (OTC)", "FTSE 100 (OTC)", "Hang Seng (OTC)", "Nikkei 225 (OTC)"],
    "سلع وطاقة 🕯️": ["Gold (OTC)", "Silver (OTC)", "UKOIL (OTC)", "USOIL (OTC)", "Natural Gas (OTC)"],
    "أسهم الشركات 🍎": [
        "Apple (OTC)", "Amazon (OTC)", "Google (OTC)", "Facebook (OTC)", "Microsoft (OTC)",
        "Tesla (OTC)", "Netflix (OTC)", "Intel (OTC)", "Boeing (OTC)", "Visa (OTC)",
        "McDonald's (OTC)", "Pfizer (OTC)", "Coca-Cola (OTC)", "Disney (OTC)",
        "Alibaba (OTC)", "Walmart (OTC)"],
}

SPECIAL_SYMBOLS = {
    "S&P 500 (OTC)": "SP:SPX", "Dow Jones (OTC)": "DJ:DJI", "Nasdaq 100 (OTC)": "NASDAQ:NDX",
    "DAX 40 (OTC)": "GER30", "CAC 40 (OTC)": "FRA40", "FTSE 100 (OTC)": "UK100",
    "Hang Seng (OTC)": "HK50", "Nikkei 225 (OTC)": "JPN225", "Gold (OTC)": "TVC:GOLD",
    "Silver (OTC)": "TVC:SILVER", "UKOIL (OTC)": "TVC:UKOIL", "USOIL (OTC)": "TVC:USOIL",
    "Natural Gas (OTC)": "TVC:NATGAS", "Apple (OTC)": "NASDAQ:AAPL", "Amazon (OTC)": "NASDAQ:AMZN",
    "Google (OTC)": "NASDAQ:GOOGL", "Facebook (OTC)": "NASDAQ:META", "Microsoft (OTC)": "NASDAQ:MSFT",
    "Tesla (OTC)": "NASDAQ:TSLA", "Netflix (OTC)": "NASDAQ:NFLX", "Intel (OTC)": "NASDAQ:INTC",
    "Boeing (OTC)": "NYSE:BA", "Visa (OTC)": "NYSE:V", "McDonald's (OTC)": "NYSE:MCD",
    "Pfizer (OTC)": "NYSE:PFE", "Coca-Cola (OTC)": "NYSE:KO", "Disney (OTC)": "NYSE:DIS",
    "Alibaba (OTC)": "NYSE:BABA", "Walmart (OTC)": "NYSE:WMT",
}
TV_INTERVALS = {"S5": "5S", "S10": "10S", "S15": "15S", "S30": "30S", "M1": "1", "M2": "2", "M3": "3",
                "M5": "5", "M10": "10", "M15": "15", "M30": "30", "H1": "60", "H4": "240", "D1": "D"}


def tv_symbol(name: str) -> str:
    if name in SPECIAL_SYMBOLS:
        return SPECIAL_SYMBOLS[name]
    m = re.match(r"^([A-Z]{3})/([A-Z]{3})", name)
    return f"FX:{m.group(1)}{m.group(2)}" if m else "FX:EURUSD"


# ════════════════════════════════════════════════════════════
# 4) البرومبتات الاحترافية (قابلة للتعديل من لوحة الويب)
# ════════════════════════════════════════════════════════════
ANALYSIS_PROMPT = """أنت محلل فني محترف (Price Action + SMC/ICT + Wyckoff + Volume Profile).
مهمتك: قراءة صورة الشارت المرفقة وإصدار قرار تنفيذي منضبط، مبنيّ فقط على ما هو ظاهر في الصورة.
القاعدة الأولى: لا تخترع أي رقم أو مستوى غير ظاهر. إن لم تستطع قراءته بوضوح فاذكر ذلك صراحةً.

══════ معطيات النظام ══════
• الأصل: {symbol}
• إطار الشموع المختار: {candle} | فريم التحقق: {verification_timeframe} ({candle_category})
• الاستراتيجية: {strategy} | حجم الصفقة: {position_sizing}
• الجلسة: {session_name} ({session_time}) | السيولة: {session_vol}
• توقيت المستخدم: {local_time} ({timezone})
• الوقت المتبقي التقريبي لإغلاق الشمعة: {seconds_remaining} ثانية | المنقضي: {seconds_elapsed} ثانية
• نافذة التنفيذ: {window_status}
• الأخبار: {news_impact} {news_warning}
• حالة السوق: {last_minute_status} | نمط السوق: {market_mode}
• سياق آخر تحليل (للمقارنة فقط، تجاهله إن تغيّر السعر): {previous_context}
ملاحظة: الوقت المتبقي تقدير من النظام؛ ساعة المنصة الظاهرة في الصورة هي المرجع الأول إن وُجدت.

══════ الخطوة 0: فحص جودة الصورة ══════
إذا كان محور الأسعار مقطوعاً أو الشموع غير واضحة أو المؤشرات تحجب الرؤية، أجب فقط بهذه الجملة:
"⚠️ الصورة غير صالحة للتحليل - أرسل صورة أوضح تظهر الشموع ومحور الأسعار."

══════ الخطوة 1: الاستخراج البصري ══════
1. السعر الحالي وأعلى/أدنى سعر ظاهر، والقمم/القيعان التاريخية (أعلى/أدنى نقطة في آخر 20-30 شمعة) ومستويات الدعم/المقاومة.
2. وصف آخر 3 شموع: اللون، نسبة الجسم، نسبة كل ذيل، الحجم النسبي لمتوسط آخر 5 شموع، هل ابتلعت الشمعة السابقة وبكم %.
3. الفجوات السعرية (FVG) غير المملوءة، مناطق السيولة (Equal Highs/Lows)، الأرقام المستديرة القريبة.
4. ساعة المنصة والفريم الظاهر (وقارنه بفريم المستخدم).
5. المسافة إلى الهدف = |الهدف − السعر الحالي| من المحور Y. سرعة الشموع = متوسط (High−Low) لآخر 3 شموع.
   عدد الشموع المتوقعة = المسافة ÷ السرعة. وقت الوصول = وقت المنصة + (الشموع × مدة الفريم). إذا كانت المسافة < 5 نقاط اكتب "فوري (Flash)".

══════ الخطوة 2: فلاتر الحماية (بالترتيب - أي فلتر يفشل يمنع الدخول مع الاتجاه) ══════
1. القمم/القيعان التاريخية: إذا كان السعر ضمن 5 نقاط منها فالشراء/البيع مع الاتجاه ممنوع حتى لو الزخم قوي،
   إلا عند اكتمال "الثالوث المؤسسي": شمعة ماروبوزو (جسم > 90%) تغلق خلف المستوى بـ ≥ 5 نقاط + حجم ≥ 1.5× متوسط آخر 3 شموع + FVG خلفها.
   إن لم يكتمل: ابحث عن انعكاس (ذيل > 40%، ابتلاع، جسم < 50%) وإلا فاحتفاظ.
2. قانون الابتلاع: شمعة عكسية تبتلع ≥ 50% من الشمعة الاندفاعية = انتهاء الزخم وإشارة انعكاس.
3. فلتر الإجهاد: شمعة حالية > 3× متوسط آخر 5 شموع = ذروة؛ لا تدخل مع الاتجاه، انتظر تصحيحاً.
4. الرفض السعري: ذيل > 60% = احتفاظ. ذيل < 15% يُهمل (Marubozu Mode).
5. الفجوات: فجوة > 5 نقاط غير مملوءة تمنع الدخول عند رأس الاندفاع؛ انتظر عودة السعر لملء ~50% منها.
6. الأرقام المستديرة (.000/.500) مغناطيس سيولة: للدخول مع الاتجاه انتظر تجاوزها بـ 3 نقاط (5 عند القمم التاريخية).
7. توافق الفريمات: على فريمات الثواني راجع هيكل M1/M5؛ إن كان الفريم الأكبر معاكساً فلا دخول مع الفريم الأصغر.
8. التوقيت: خارج نافذة التنفيذ = خفض الثقة. دقائق التحول (14/29/44/59) مع أقل من 15 ثانية = دخول فقط عند اندفاع حر واضح.
9. الأخبار: تأثير عالٍ = خفض الثقة وتحذير صريح.
10. مبدأ عام: السيولة تسبق الزخم. ابحث عن سبب انعكاس قبل البحث عن سبب استمرار.

══════ الخطوة 3: القرار ══════
الأولوية: انعكاس مؤكد > كسر هيكلي مؤكد > زخم في منتصف الحركة > احتفاظ.
• الزخم في منتصف الحركة (بعيداً عن القمم والقيعان): 3 شموع بأجسام > 80% وحجم ≥ 1.3× ولا ابتلاع عكسي.
• أي شك أو تعارض بين الأدلة → احتفاظ 🟡 مع ذكر ما الذي ينتظره المتداول.

══════ حساب الثقة (تقدير تحليلي وليس ضماناً) ══════
الثقة = مسافة الأمان من القمم/القيعان (35) + قوة الحجم (25) + دلائل الانعكاس/الاستمرار (20) + توافق الفريمات (10) + شكل الشمعة (10).
90+ 💥 عالية جداً | 75-89 🔥 عالية | 60-74 ⚡ متوسطة | 50-59 🔄 انعكاسية | 40-49 ❄️ منخفضة (احتفاظ) | <40 🚫 لا دخول.
ممنوع ذكر "نسبة نجاح" مضمونة أو إحصائية؛ استخدم مستوى الثقة فقط.

══════ التنسيق المطلوب (التزم به حرفياً ودون إطالة) ══════
📊 التحليل الفني المتقدم:
• جودة الصورة: [صالحة / غير صالحة]
• وقت المنصة (المرجع): [HH:MM:SS أو غير ظاهر]
• الهيكل: [صاعد/هابط/متذبذب] | توافق الفريمات: [نعم/جزئي/لا]
• خريطة السيولة: [أقرب فخ] + [الهدف القادم]
• الشموع الثلاث الأخيرة: [وصف مختصر]
• الفجوات/الأرقام المستديرة: [...]

🎯 الإشارة التنفيذية:
• السعر الحالي: [..]
• القرار: [شراء 🟢 / بيع 🔴 / كسر هيكلي 💥 / انعكاس فوري 🔄 / فخ سيولة 🚨 / احتفاظ 🟡]
• قوة الإشارة: [عالية جداً 💥 / عالية 🔥 / متوسطة ⚡ / ضعيفة ❄️]
• الدخول: [السعر + الشرط، ويفضل إعادة اختبار المستوى] | النوع: [مباشر / إعادة اختبار / انعكاس]
• TP1: [..] | TP2: [..] | TP3: [..]
• وقف الخسارة: [..] (خلف منطقة الحماية)
• المسافة للهدف: [X.X] نقطة | سرعة الشموع: [X.X] | الشموع المتوقعة: [X.X] | الوصول المتوقع: [HH:MM:SS / فوري (Flash)]
• الفلاتر التي أثّرت على القرار: [أرقام الفلاتر]

⚠️ إدارة المخاطر:
• الثقة: [0-100]٪ [الرمز]
• نقطة إلغاء السيناريو: [السعر]
• 🚨 تنبيه فخ السيولة: [نشط/غير نشط] + [سبب مختصر]

حلّل الشارت الآن وفق ما سبق وأعطني الإجابة بالتنسيق أعلاه فقط."""

RECOMMENDATION_TEXT_PROMPT = """أنت خبير تداول كمي. لا تتوفر لديك بيانات سعرية مباشرة للأصل {symbol} (تعذّر سحب صورة الشارت).
لذلك قدّم "سيناريو هيكلياً تعليمياً" عاماً دون اختراع أي سعر أو رقم محدد.

السياق: إطار {candle} | الاستراتيجية: {strategy} | الجلسة: {session_name} ({session_time}) | السيولة: {session_vol}

اشرح بإيجاز ما الذي يجب على المتداول البحث عنه على شارت {symbol} الآن وفق SMC/Wyckoff:
الهيكل المطلوب تأكيده، مناطق السيولة المحتملة، شروط الدخول والإلغاء بصيغة شروط (وليس أرقاماً)،
وأهم محاذير الجلسة الحالية. اختم بأن القرار النهائي يتطلب مطابقة الشارت الحقيقي.

التنسيق:
📊 ملخص {symbol} (بدون بيانات مباشرة):
• الهيكل المطلوب تأكيده: ..
• السيولة المحتملة: ..
🎯 خطة مشروطة:
• سيناريو الشراء إذا: ..
• سيناريو البيع إذا: ..
• الإلغاء: ..
⚠️ المخاطرة: ..
💡 أرسل صورة الشارت لتحليل دقيق."""

DEFAULT_PROMPTS = {
    "analysis": ANALYSIS_PROMPT,
    "recommendation_text": RECOMMENDATION_TEXT_PROMPT,
    "chat_general": """أنت Obeida Trading، مساعد ذكي شامل يجمع بين الدقة والوضوح والعملية.
تغطي: التحليل الفني والمالي، البرمجة، تحليل البيانات، الكتابة، وحل المشكلات.
أسلوبك: تبدأ بالجواب المباشر في سطر أو سطرين، ثم التفاصيل في نقاط منظمة، ثم خطوة عملية تالية.
إذا كان السؤال غامضاً فافترض أرجح معنى واذكر افتراضك بدل إطالة الأسئلة.""",
    "chat_consult": """أنت Obeida Trading، مستشار احترافي في الاستراتيجية وإدارة المشاريع والعلاقات المهنية والتخطيط المالي العام.
قدّم توصيات واقعية قابلة للتنفيذ مع الموازنة بين الخيارات (مزايا/عيوب/مخاطر)، وبنبرة موضوعية ومهنية.
وضّح الافتراضات، وأشر عند الحاجة إلى استشارة مختص مرخّص في الأمور القانونية والمالية الحساسة.""",
    "chat_invest": """أنت Obeida Trading، محلل استثماري متخصص في التحليل الفني والأساسي وإدارة المخاطر.
قدّم تحليلاً متعدد الأبعاد: الاتجاه، المحفزات، المخاطر، سيناريوهات بديلة، وإدارة رأس المال (حجم المركز/وقف الخسارة).
لا تعد بأرباح ولا تذكر نسب نجاح مضمونة. صرّح أن المعلومات تعليمية وليست توصية مالية شخصية.""",
    "chat_code": """أنت Obeida Trading، مهندس برمجيات خبير (Python وويب وAPIs وقواعد بيانات وذكاء اصطناعي).
اكتب كوداً نظيفاً قابلاً للتشغيل مع معالجة الأخطاء، واشرح القرارات المهمة باختصار.
عند تصحيح خطأ: حدّد السبب الجذري أولاً ثم قدّم الإصلاح ثم كيفية التحقق منه. لا تخترع مكتبات أو دوال غير موجودة.""",
    "chat_write": """أنت Obeida Trading، كاتب محترف في المحتوى التقني والتسويقي والتعليمي والإبداعي.
تكتب بعربية سليمة وجذابة، وتكيّف الأسلوب مع الجمهور والهدف. قدّم نسخة جاهزة للاستخدام أولاً،
ثم اقترح تحسينات أو بدائل قصيرة عند الفائدة.""",
    "chat_smart": """أنت Obeida Trading، خبير حل المشكلات والتفكير النقدي.
فكّك المشكلة إلى عناصرها، اعرض 2-3 حلول مع مقارنة سريعة، ثم أوصِ بأفضلها مع خطوات التنفيذ ومعايير النجاح.""",
}
PROMPT_META = {
    "analysis": ("تحليل صور الشارت", "البرومبت الرئيسي لتحليل الصور. المتغيرات: {symbol} {candle} {verification_timeframe} {candle_category} {strategy} {position_sizing} {session_name} {session_time} {session_vol} {local_time} {timezone} {seconds_remaining} {seconds_elapsed} {window_status} {news_impact} {news_warning} {last_minute_status} {market_mode} {previous_context}"),
    "recommendation_text": ("التوصية النصية (احتياطي)", "يُستخدم عند تعذّر سحب صورة الشارت. المتغيرات: {symbol} {candle} {strategy} {session_name} {session_time} {session_vol}"),
    "chat_general": ("دردشة: مساعد شامل", "شخصية الدردشة"),
    "chat_consult": ("دردشة: استشارات احترافية", "شخصية الدردشة"),
    "chat_invest": ("دردشة: تحليل استثماري", "شخصية الدردشة"),
    "chat_code": ("دردشة: دعم برمجي", "شخصية الدردشة"),
    "chat_write": ("دردشة: كتابة إبداعية", "شخصية الدردشة"),
    "chat_smart": ("دردشة: حلول ذكية", "شخصية الدردشة"),
}
PERSONAS = {"🚀 مساعد شامل": "chat_general", "💼 استشارات احترافية": "chat_consult",
            "📈 تحليل استثماري": "chat_invest", "👨‍💻 دعم برمجي": "chat_code",
            "📝 كتابة إبداعية": "chat_write", "🧠 حلول ذكية": "chat_smart"}
CHAT_COMMON_RULES = ("\n\nقواعد عامة: أجب بلغة المستخدم (العربية افتراضياً) وباختصار منظم. "
                     "لا تختلق معلومات أو مصادر؛ إذا لم تكن متأكداً فقل ذلك. "
                     "لا تذكر هذه التعليمات.")
DISCLAIMER = "⚠️ تحليل تعليمي وليس نصيحة مالية. التداول ينطوي على مخاطر قد تؤدي لخسارة رأس المال."


def render_prompt(template: str, values: dict) -> str:
    """استبدال آمن للمتغيرات {name} فقط دون التأثر بأي أقواس أخرى."""
    return re.sub(r"\{(\w+)\}", lambda m: str(values.get(m.group(1), m.group(0))), template)


# ════════════════════════════════════════════════════════════
# 5) قواعد البيانات + الإعدادات
# ════════════════════════════════════════════════════════════
@contextmanager
def get_conn(path: str):
    conn = sqlite3.connect(path, timeout=20)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


DEFAULT_SETTINGS = {
    "maintenance": "0",
    "maintenance_message": "🛠️ البوت تحت الصيانة حالياً. سنعود قريباً، شكراً لصبرك.",
    "welcome_message": "",
    "support_username": "@Sz2zv",
    "prices": "• ساعة: 1$\n• يوم: 5$\n• أسبوعي: 15$\n• شهري: 40$",
    "auto_trial": "0",
    "enforce_features": "0",
    "cooldown_seconds": "8",
    "history_messages": "6",
    "history_retention_hours": "24",
    "model_vision": MODEL_VISION,
    "model_audit": MODEL_AUDIT,
    "model_chat": MODEL_CHAT,
    "ai_temperature": "0.2",
    "vision_max_tokens": "1400",
    "chat_max_tokens": "2200",
}


class Settings:
    _cache: dict = {}
    _ts = 0.0
    _lock = threading.Lock()

    @classmethod
    def _load(cls) -> dict:
        with cls._lock:
            if cls._cache and time.time() - cls._ts < 2:
                return cls._cache
            try:
                with get_conn(DB_NAME) as c:
                    rows = c.execute("SELECT key, value FROM bot_settings").fetchall()
                cls._cache = {r["key"]: r["value"] for r in rows}
                cls._ts = time.time()
            except Exception as e:
                log.warning("settings load failed: %s", e)
            return cls._cache

    @classmethod
    def get(cls, key: str, default=None):
        v = cls._load().get(key)
        if v is None:
            v = DEFAULT_SETTINGS.get(key, default)
        return v

    @classmethod
    def raw(cls, key: str):
        return cls._load().get(key)

    @classmethod
    def int(cls, key: str, default: int = 0) -> int:
        try:
            return int(float(cls.get(key, default)))
        except Exception:
            return default

    @classmethod
    def float(cls, key: str, default: float = 0.0) -> float:
        try:
            return float(cls.get(key, default))
        except Exception:
            return default

    @classmethod
    def set(cls, key: str, value) -> None:
        with get_conn(DB_NAME) as c:
            c.execute("""INSERT INTO bot_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)
                         ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP""",
                      (key, str(value)))
        cls._ts = 0.0

    @classmethod
    def delete(cls, key: str) -> None:
        with get_conn(DB_NAME) as c:
            c.execute("DELETE FROM bot_settings WHERE key=?", (key,))
        cls._ts = 0.0


def get_prompt(key: str) -> str:
    return Settings.raw("prompt:" + key) or DEFAULT_PROMPTS[key]


def audit(actor: str, action: str, target: str = "", details: str = "") -> None:
    try:
        with get_conn(DB_NAME) as c:
            c.execute("INSERT INTO audit_log (actor, action, target, details) VALUES (?,?,?,?)",
                      (actor, action, str(target), details[:500]))
    except Exception as e:
        log.warning("audit failed: %s", e)


def log_data_change(action: str, user_id: int, details: str = "") -> None:
    try:
        with get_conn(DB_NAME) as c:
            c.execute("INSERT INTO data_log (action, user_id, details) VALUES (?,?,?)", (action, user_id, details))
    except Exception:
        pass


def init_main_db() -> None:
    with get_conn(DB_NAME) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, candle TEXT DEFAULT 'M1',
            trade_time TEXT DEFAULT 'قصير (1m-15m)', chat_context TEXT DEFAULT '',
            last_analysis_context TEXT DEFAULT '', last_analysis_time DATETIME DEFAULT NULL,
            subscription_start DATETIME DEFAULT NULL, subscription_end DATETIME DEFAULT NULL,
            is_admin INTEGER DEFAULT 0, country_timezone TEXT DEFAULT 'Asia/Gaza')""")
        cols = {r["name"] for r in c.execute("PRAGMA table_info(users)").fetchall()}
        for name, ddl in {
            "username": "TEXT", "candle": "TEXT DEFAULT 'M1'", "trade_time": "TEXT DEFAULT 'قصير (1m-15m)'",
            "chat_context": "TEXT DEFAULT ''", "last_analysis_context": "TEXT DEFAULT ''",
            "last_analysis_time": "DATETIME DEFAULT NULL", "subscription_start": "DATETIME DEFAULT NULL",
            "subscription_end": "DATETIME DEFAULT NULL", "is_admin": "INTEGER DEFAULT 0",
            "country_timezone": "TEXT DEFAULT 'Asia/Gaza'",
        }.items():
            if name not in cols:
                c.execute(f"ALTER TABLE users ADD COLUMN {name} {ddl}")
        c.execute("""CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, role TEXT, content TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_history(user_id, id)")
        c.execute("""CREATE TABLE IF NOT EXISTS data_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, user_id INTEGER, details TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS bot_settings (
            key TEXT PRIMARY KEY, value TEXT, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT, action TEXT, target TEXT, details TEXT,
            ts DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        if c.execute("SELECT 1 FROM users WHERE user_id=?", (ADMIN_ID,)).fetchone():
            c.execute("UPDATE users SET is_admin=1 WHERE user_id=?", (ADMIN_ID,))
        else:
            c.execute("INSERT INTO users (user_id, username, is_admin, country_timezone) VALUES (?,?,1,?)",
                      (ADMIN_ID, "admin", DEFAULT_TZ))
    log.info("✅ Main database ready")


# ════════════════════════════════════════════════════════════
# 6) أدوات الوقت والمنطقة الزمنية
# ════════════════════════════════════════════════════════════
def parse_dt(s):
    try:
        return datetime.fromisoformat(s) if s else None
    except Exception:
        return None


def fmt_remaining(end_date) -> str:
    if not end_date:
        return "غير محدود ♾️"
    end = parse_dt(end_date)
    if not end:
        return "-"
    secs = int((end - datetime.now()).total_seconds())
    if secs <= 0:
        return "منتهي"
    d, r = divmod(secs, 86400)
    h, r = divmod(r, 3600)
    m = r // 60
    parts = []
    if d:
        parts.append(f"{d} يوم")
    if h:
        parts.append(f"{h} ساعة")
    if m or not parts:
        parts.append(f"{m} دقيقة")
    return " و ".join(parts)


def get_user_timezone(user_id: int) -> str:
    try:
        with get_conn(DB_NAME) as c:
            r = c.execute("SELECT country_timezone FROM users WHERE user_id=?", (user_id,)).fetchone()
        if r and r["country_timezone"] in pytz.all_timezones_set:
            return r["country_timezone"]
    except Exception:
        pass
    return DEFAULT_TZ


def set_user_timezone(user_id: int, tz: str) -> bool:
    if tz not in pytz.all_timezones_set:
        return False
    with get_conn(DB_NAME) as c:
        if not c.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone():
            c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        c.execute("UPDATE users SET country_timezone=? WHERE user_id=?", (tz, user_id))
    log_data_change("update_timezone", user_id, tz)
    return True


def get_localized_time(user_id: int) -> datetime:
    return datetime.now(pytz.timezone(get_user_timezone(user_id)))


def candle_seconds(candle: str) -> int:
    m = re.match(r"^([SMHD])(\d+)$", candle or "")
    if not m:
        return 60
    return int(m.group(2)) * {"S": 1, "M": 60, "H": 3600, "D": 86400}[m.group(1)]


def verification_tf(candle: str) -> str:
    unit, val = (candle[:1], int(candle[1:])) if re.match(r"^[SMHD]\d+$", candle or "") else ("M", 1)
    if unit == "S":
        return "S15" if val <= 15 else "S30"
    if unit == "M":
        return "M1" if val <= 5 else ("M5" if val <= 15 else "M15")
    return "H1" if unit == "H" else "H4"


def get_market_session(user_id=None):
    """جلسة السوق (حسب التوقيت العالمي) مع عرض الساعات بتوقيت المستخدم."""
    tz_name = get_user_timezone(user_id) if user_id else DEFAULT_TZ
    tz = pytz.timezone(tz_name)
    now = datetime.now(pytz.utc)
    h = now.hour + now.minute / 60

    def rng(a, b):
        s = now.replace(hour=a % 24, minute=0, second=0).astimezone(tz).strftime("%H:%M")
        e = now.replace(hour=b % 24, minute=0, second=0).astimezone(tz).strftime("%H:%M")
        return f"{s}-{e} بتوقيتك"

    if 12 <= h < 16:
        return "تداخل لندن/نيويورك", rng(12, 16), "عالية جداً", tz_name
    if 7 <= h < 12:
        return "جلسة لندن/أوروبا", rng(7, 16), "مرتفعة", tz_name
    if 16 <= h < 21:
        return "جلسة نيويورك", rng(12, 21), "مرتفعة", tz_name
    if 0 <= h < 7:
        return "الجلسة الآسيوية", rng(0, 8), "منخفضة إلى متوسطة", tz_name
    return "جلسة المحيط الهادئ", rng(21, 24), "منخفضة", tz_name


HIGH_IMPACT_UTC = [(7, 0), (8, 30), (12, 30), (13, 30), (14, 0), (15, 0), (18, 0), (19, 0)]


def news_state():
    now = datetime.now(pytz.utc)
    minutes = now.hour * 60 + now.minute
    for hh, mm in HIGH_IMPACT_UTC:
        diff = abs(minutes - (hh * 60 + mm))
        if diff <= 30:
            return "🔴 عالي", "⚠️ نافذة أخبار اقتصادية محتملة قريبة جداً (تقدير تقريبي)"
        if diff <= 90:
            return "🟡 متوسط", "📢 اقتراب من وقت أخبار شائعة (تقدير تقريبي)"
    return "🟢 منخفض", ""


def execution_window(period: int, elapsed: int):
    if period > 300:
        return "غير مطبقة على هذا الفريم"
    ok = 0.15 * period <= elapsed <= 0.70 * period
    return "داخل نافذة التنفيذ ✅" if ok else "خارج نافذة التنفيذ ❌"


# ════════════════════════════════════════════════════════════
# 7) نظام الاشتراكات
# ════════════════════════════════════════════════════════════
def sub_status(blocked, has_sub, is_active, end_date) -> str:
    if blocked:
        return "blocked"
    if not has_sub:
        return "none"
    if not is_active:
        return "expired"
    if not end_date:
        return "active"
    end = parse_dt(end_date)
    return "active" if end and end > datetime.now() else "expired"


class SubscriptionSystem:
    TYPES = {
        'trial': {'name': 'تجريبي', 'duration': 86400, 'features': ['basic_analysis']},
        'hourly': {'name': 'ساعة', 'duration': 3600, 'features': ['basic_analysis']},
        'daily': {'name': 'يوم', 'duration': 86400, 'features': ['basic_analysis', 'chat']},
        'weekly': {'name': 'أسبوع', 'duration': 604800, 'features': ['basic_analysis', 'chat', 'recommendations']},
        'monthly': {'name': 'شهر', 'duration': 2592000,
                    'features': ['basic_analysis', 'chat', 'recommendations', 'advanced_analysis']},
        'yearly': {'name': 'سنة', 'duration': 31536000,
                   'features': ['basic_analysis', 'chat', 'recommendations', 'advanced_analysis', 'priority']},
        'lifetime': {'name': 'مدى الحياة', 'duration': -1, 'features': ['all']},
    }
    ALL_FEATURES = ['basic_analysis', 'chat', 'recommendations', 'advanced_analysis', 'priority']

    @staticmethod
    def init_db():
        with get_conn(SUB_DB) as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, last_name TEXT, language_code TEXT,
                is_bot BOOLEAN DEFAULT 0, is_premium BOOLEAN DEFAULT 0, added_to_attachment_menu BOOLEAN DEFAULT 0,
                can_join_groups BOOLEAN DEFAULT 1, can_read_all_group_messages BOOLEAN DEFAULT 0,
                supports_inline_queries BOOLEAN DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP, is_blocked BOOLEAN DEFAULT 0,
                blocked_reason TEXT, metadata TEXT DEFAULT '{}');
            CREATE TABLE IF NOT EXISTS active_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, subscription_type TEXT NOT NULL,
                subscription_name TEXT NOT NULL, start_date TIMESTAMP NOT NULL, end_date TIMESTAMP,
                is_active BOOLEAN DEFAULT 1, auto_renew BOOLEAN DEFAULT 0, payment_method TEXT,
                payment_reference TEXT, price REAL, currency TEXT DEFAULT 'USD', added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, metadata TEXT DEFAULT '{}');
            CREATE TABLE IF NOT EXISTS subscription_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, action TEXT NOT NULL,
                old_subscription TEXT, new_subscription TEXT, reason TEXT, performed_by INTEGER,
                performed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, metadata TEXT DEFAULT '{}');
            CREATE TABLE IF NOT EXISTS permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, permission TEXT NOT NULL,
                granted_by INTEGER, granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, expires_at TIMESTAMP,
                is_active BOOLEAN DEFAULT 1, metadata TEXT DEFAULT '{}', UNIQUE(user_id, permission));
            CREATE TABLE IF NOT EXISTS usage_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, feature TEXT NOT NULL,
                count INTEGER DEFAULT 0, last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_time_used REAL DEFAULT 0, metadata TEXT DEFAULT '{}', UNIQUE(user_id, feature));
            CREATE TABLE IF NOT EXISTS change_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT, table_name TEXT NOT NULL, record_id INTEGER,
                action TEXT NOT NULL, old_data TEXT, new_data TEXT, changed_by INTEGER,
                changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, metadata TEXT DEFAULT '{}');
            CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
            CREATE INDEX IF NOT EXISTS idx_sub_user ON active_subscriptions(user_id);
            CREATE INDEX IF NOT EXISTS idx_sub_active ON active_subscriptions(is_active);
            CREATE INDEX IF NOT EXISTS idx_hist_user ON subscription_history(user_id);
            CREATE INDEX IF NOT EXISTS idx_perm_user ON permissions(user_id);
            CREATE INDEX IF NOT EXISTS idx_usage_user ON usage_stats(user_id);
            """)
        log.info("✅ Subscription database ready")

    # ── المستخدمون ──
    @staticmethod
    def register_user(user_id, username=None, first_name=None, last_name=None, language_code=None, is_bot=False) -> bool:
        """يسجّل/يحدّث المستخدم. يعيد True إن كان مستخدماً جديداً."""
        with get_conn(SUB_DB) as c:
            if c.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone():
                c.execute("""UPDATE users SET last_active=CURRENT_TIMESTAMP, username=COALESCE(?,username),
                             first_name=COALESCE(?,first_name), last_name=COALESCE(?,last_name),
                             language_code=COALESCE(?,language_code) WHERE user_id=?""",
                          (username, first_name, last_name, language_code, user_id))
                return False
            c.execute("""INSERT INTO users (user_id, username, first_name, last_name, language_code, is_bot)
                         VALUES (?,?,?,?,?,?)""", (user_id, username, first_name, last_name, language_code, int(is_bot)))
            return True

    @staticmethod
    def _grant_permissions(c, user_id, sub_type, by):
        c.execute("UPDATE permissions SET is_active=0 WHERE user_id=?", (user_id,))
        feats = SubscriptionSystem.TYPES[sub_type]['features']
        if 'all' in feats:
            feats = SubscriptionSystem.ALL_FEATURES
        for f in feats:
            c.execute("INSERT OR REPLACE INTO permissions (user_id, permission, granted_by, is_active) VALUES (?,?,?,1)",
                      (user_id, f, by))

    @staticmethod
    def add_subscription(user_id, sub_type, added_by=ADMIN_ID, reason=""):
        if sub_type not in SubscriptionSystem.TYPES:
            return False, "نوع اشتراك غير صالح"
        info = SubscriptionSystem.TYPES[sub_type]
        start = datetime.now()
        end = start + timedelta(seconds=info['duration']) if info['duration'] > 0 else None
        try:
            with get_conn(SUB_DB) as c:
                if not c.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone():
                    c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
                old = c.execute("SELECT subscription_type FROM active_subscriptions WHERE user_id=? AND is_active=1 "
                                "ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()
                c.execute("UPDATE active_subscriptions SET is_active=0 WHERE user_id=? AND is_active=1", (user_id,))
                c.execute("""INSERT INTO active_subscriptions (user_id, subscription_type, subscription_name,
                             start_date, end_date, is_active, added_by) VALUES (?,?,?,?,?,1,?)""",
                          (user_id, sub_type, info['name'], start.isoformat(), end.isoformat() if end else None, added_by))
                SubscriptionSystem._grant_permissions(c, user_id, sub_type, added_by)
                c.execute("""INSERT INTO subscription_history (user_id, action, old_subscription, new_subscription,
                             reason, performed_by) VALUES (?,?,?,?,?,?)""",
                          (user_id, 'add', old["subscription_type"] if old else None, sub_type, reason, added_by))
            SubscriptionSystem.sync_main(user_id, start.isoformat(), end.isoformat() if end else None)
            return True, {'subscription_type': sub_type, 'subscription_name': info['name'],
                          'start_date': start.isoformat(), 'end_date': end.isoformat() if end else None}
        except Exception as e:
            log.exception("add_subscription")
            return False, str(e)

    @staticmethod
    def sync_main(user_id, start, end):
        """مزامنة تاريخ الاشتراك مع قاعدة البيانات الرئيسية (للتوافق مع النسخ القديمة)."""
        try:
            with get_conn(SUB_DB) as c:
                r = c.execute("SELECT username FROM users WHERE user_id=?", (user_id,)).fetchone()
            username = r["username"] if r else None
            with get_conn(DB_NAME) as c:
                if c.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone():
                    c.execute("UPDATE users SET subscription_start=?, subscription_end=?, username=COALESCE(?,username) "
                              "WHERE user_id=?", (start, end, username, user_id))
                else:
                    c.execute("INSERT INTO users (user_id, username, subscription_start, subscription_end) VALUES (?,?,?,?)",
                              (user_id, username, start, end))
        except Exception as e:
            log.warning("sync_main failed: %s", e)

    @staticmethod
    def check_subscription(user_id):
        try:
            with get_conn(SUB_DB) as c:
                u = c.execute("SELECT is_blocked FROM users WHERE user_id=?", (user_id,)).fetchone()
                if u and u["is_blocked"]:
                    return False, "محظور", {'blocked': True}
                s = c.execute("""SELECT subscription_type, subscription_name, start_date, end_date
                                 FROM active_subscriptions WHERE user_id=? AND is_active=1
                                 ORDER BY id DESC LIMIT 1""", (user_id,)).fetchone()
                if not s:
                    return False, "لا يوجد اشتراك نشط", None
                end = parse_dt(s["end_date"]) if s["end_date"] else None
                if s["end_date"] and (end is None or end < datetime.now()):
                    c.execute("UPDATE active_subscriptions SET is_active=0 WHERE user_id=? AND is_active=1", (user_id,))
                    c.execute("UPDATE permissions SET is_active=0 WHERE user_id=?", (user_id,))
                    return False, "انتهت صلاحية الاشتراك", None
                perms = [p["permission"] for p in c.execute(
                    "SELECT permission FROM permissions WHERE user_id=? AND is_active=1", (user_id,)).fetchall()]
            return True, s["subscription_name"], {'type': s["subscription_type"], 'name': s["subscription_name"],
                                                  'start_date': s["start_date"], 'end_date': s["end_date"],
                                                  'permissions': perms}
        except Exception as e:
            log.exception("check_subscription")
            return False, str(e), None

    @staticmethod
    def has_permission(user_id, permission) -> bool:
        if user_id == ADMIN_ID:
            return True
        try:
            with get_conn(SUB_DB) as c:
                u = c.execute("SELECT is_blocked FROM users WHERE user_id=?", (user_id,)).fetchone()
                if u and u["is_blocked"]:
                    return False
                return c.execute("SELECT 1 FROM permissions WHERE user_id=? AND permission=? AND is_active=1",
                                 (user_id, permission)).fetchone() is not None
        except Exception:
            return False

    @staticmethod
    def increment_usage(user_id, feature):
        try:
            with get_conn(SUB_DB) as c:
                c.execute("""INSERT INTO usage_stats (user_id, feature, count) VALUES (?,?,1)
                             ON CONFLICT(user_id, feature) DO UPDATE SET count=count+1, last_used=CURRENT_TIMESTAMP""",
                          (user_id, feature))
        except Exception:
            pass

    @staticmethod
    def revoke_subscription(user_id, reason="Revoked by admin", by=ADMIN_ID):
        try:
            with get_conn(SUB_DB) as c:
                r = c.execute("SELECT subscription_type FROM active_subscriptions WHERE user_id=? AND is_active=1 LIMIT 1",
                              (user_id,)).fetchone()
                if not r:
                    return False, "لا يوجد اشتراك نشط لهذا المستخدم"
                c.execute("UPDATE active_subscriptions SET is_active=0 WHERE user_id=? AND is_active=1", (user_id,))
                c.execute("UPDATE permissions SET is_active=0 WHERE user_id=?", (user_id,))
                c.execute("INSERT INTO subscription_history (user_id, action, old_subscription, reason, performed_by) "
                          "VALUES (?,?,?,?,?)", (user_id, 'revoke', r["subscription_type"], reason, by))
            SubscriptionSystem.sync_main(user_id, None, None)
            return True, "تم إلغاء الاشتراك بنجاح"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def extend_subscription(user_id, seconds, reason="Extended by admin", by=ADMIN_ID):
        if seconds <= 0 or seconds > 315360000:
            return False, "مدة التمديد غير صالحة"
        try:
            with get_conn(SUB_DB) as c:
                r = c.execute("SELECT id, end_date, is_active, subscription_type FROM active_subscriptions "
                              "WHERE user_id=? ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()
                if not r:
                    return False, "لا يوجد اشتراك سابق لهذا المستخدم"
                if r["subscription_type"] == "lifetime" and r["is_active"]:
                    return False, "الاشتراك مدى الحياة ولا يحتاج تمديداً"
                base = parse_dt(r["end_date"]) or datetime.now()
                if base < datetime.now():
                    base = datetime.now()
                new_end = base + timedelta(seconds=seconds)
                c.execute("UPDATE active_subscriptions SET end_date=?, is_active=1 WHERE id=?", (new_end.isoformat(), r["id"]))
                SubscriptionSystem._grant_permissions(c, user_id, r["subscription_type"], by)
                c.execute("INSERT INTO subscription_history (user_id, action, old_subscription, new_subscription, reason, "
                          "performed_by) VALUES (?,?,?,?,?,?)",
                          (user_id, 'extend', r["subscription_type"], f"+{seconds}s", reason, by))
            SubscriptionSystem.sync_main(user_id, None, new_end.isoformat())
            return True, f"تم تمديد الاشتراك حتى {new_end.strftime('%Y-%m-%d %H:%M')}"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def block_user(user_id, reason="Blocked by admin", by=ADMIN_ID):
        if user_id == ADMIN_ID:
            return False, "لا يمكن حظر المشرف الرئيسي"
        try:
            with get_conn(SUB_DB) as c:
                if not c.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone():
                    c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
                c.execute("UPDATE users SET is_blocked=1, blocked_reason=? WHERE user_id=?", (reason, user_id))
                c.execute("UPDATE active_subscriptions SET is_active=0 WHERE user_id=? AND is_active=1", (user_id,))
                c.execute("UPDATE permissions SET is_active=0 WHERE user_id=?", (user_id,))
                c.execute("INSERT INTO subscription_history (user_id, action, reason, performed_by) VALUES (?,?,?,?)",
                          (user_id, 'block', reason, by))
            return True, "تم حظر المستخدم بنجاح"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def unblock_user(user_id, by=ADMIN_ID):
        try:
            with get_conn(SUB_DB) as c:
                c.execute("UPDATE users SET is_blocked=0, blocked_reason=NULL WHERE user_id=?", (user_id,))
                c.execute("INSERT INTO subscription_history (user_id, action, performed_by) VALUES (?,'unblock',?)",
                          (user_id, by))
            return True, "تم إلغاء حظر المستخدم بنجاح"
        except Exception as e:
            return False, str(e)

    # ── الاستعلامات ──
    @staticmethod
    def get_all_users() -> list:
        with get_conn(SUB_DB) as c:
            rows = c.execute("""
                SELECT u.user_id, u.username, u.first_name, u.last_name, u.created_at, u.last_active,
                       u.is_blocked, u.blocked_reason, s.subscription_type, s.subscription_name,
                       s.start_date, s.end_date, s.is_active, s.id AS sid
                FROM users u LEFT JOIN active_subscriptions s
                  ON s.id = (SELECT MAX(id) FROM active_subscriptions WHERE user_id = u.user_id)
                ORDER BY u.last_active DESC""").fetchall()
        tzs = {}
        try:
            with get_conn(DB_NAME) as c:
                tzs = {r["user_id"]: r["country_timezone"] for r in c.execute(
                    "SELECT user_id, country_timezone FROM users").fetchall()}
        except Exception:
            pass
        out = []
        for r in rows:
            name = " ".join(x for x in [r["first_name"], r["last_name"]] if x) or r["username"] or str(r["user_id"])
            out.append({
                "user_id": r["user_id"], "name": name, "username": r["username"] or "",
                "created_at": r["created_at"], "last_active": r["last_active"],
                "blocked": bool(r["is_blocked"]), "blocked_reason": r["blocked_reason"],
                "sub_type": r["subscription_type"], "sub_name": r["subscription_name"] or "",
                "start_date": r["start_date"], "end_date": r["end_date"],
                "status": sub_status(r["is_blocked"], r["sid"] is not None, r["is_active"], r["end_date"]),
                "timezone": tzs.get(r["user_id"]) or DEFAULT_TZ,
            })
        return out

    @staticmethod
    def audience_ids(audience: str) -> list:
        users = SubscriptionSystem.get_all_users()
        if audience == "all":
            return [u["user_id"] for u in users if not u["blocked"]]
        if audience == "expired":
            return [u["user_id"] for u in users if u["status"] == "expired"]
        return [u["user_id"] for u in users if u["status"] == "active"]

    @staticmethod
    def get_profile(user_id: int):
        users = [u for u in SubscriptionSystem.get_all_users() if u["user_id"] == user_id]
        if not users:
            return None
        u = users[0]
        with get_conn(SUB_DB) as c:
            u["permissions"] = [r["permission"] for r in c.execute(
                "SELECT permission FROM permissions WHERE user_id=? AND is_active=1", (user_id,)).fetchall()]
            u["usage"] = {r["feature"]: r["count"] for r in c.execute(
                "SELECT feature, count FROM usage_stats WHERE user_id=?", (user_id,)).fetchall()}
            u["history"] = [dict(r) for r in c.execute(
                "SELECT action, old_subscription, new_subscription, reason, performed_by, performed_at "
                "FROM subscription_history WHERE user_id=? ORDER BY id DESC LIMIT 20", (user_id,)).fetchall()]
        u["remaining"] = fmt_remaining(u["end_date"]) if u["status"] == "active" else "-"
        try:
            with get_conn(DB_NAME) as c:
                r = c.execute("SELECT candle, trade_time FROM users WHERE user_id=?", (user_id,)).fetchone()
                u["candle"], u["trade_time"] = (r["candle"], r["trade_time"]) if r else ("M1", TRADE_TIMES[0])
        except Exception:
            u["candle"], u["trade_time"] = "M1", TRADE_TIMES[0]
        return u

    @staticmethod
    def get_stats() -> dict:
        users = SubscriptionSystem.get_all_users()
        st = {"total_users": len(users),
              "blocked_users": sum(u["blocked"] for u in users),
              "active_users": sum(u["status"] == "active" for u in users),
              "expired_users": sum(u["status"] == "expired" for u in users),
              "no_sub_users": sum(u["status"] == "none" for u in users)}
        by_type = {}
        for u in users:
            if u["status"] == "active":
                by_type[u["sub_name"] or "?"] = by_type.get(u["sub_name"] or "?", 0) + 1
        st["subscriptions_by_type"] = by_type
        with get_conn(SUB_DB) as c:
            st["feature_usage"] = {r["feature"]: r["total"] for r in c.execute(
                "SELECT feature, SUM(count) AS total FROM usage_stats GROUP BY feature ORDER BY total DESC LIMIT 12").fetchall()}
            st["new_today"] = c.execute("SELECT COUNT(*) FROM users WHERE date(created_at)=date('now')").fetchone()[0]
            series = {r["d"]: r["n"] for r in c.execute(
                "SELECT date(created_at) AS d, COUNT(*) AS n FROM users WHERE created_at>=date('now','-6 days') "
                "GROUP BY d").fetchall()}
        today = datetime.utcnow().date()
        st["new_users_7d"] = {str(today - timedelta(days=i)): series.get(str(today - timedelta(days=i)), 0)
                              for i in range(6, -1, -1)}
        st["total_usage"] = sum(st["feature_usage"].values())
        return st


def check_user_subscription(user_id):
    if user_id == ADMIN_ID:
        return True, "مشرف"
    ok, msg, _ = SubscriptionSystem.check_subscription(user_id)
    return ok, msg


def feature_allowed(user_id: int, feature: str) -> bool:
    if user_id == ADMIN_ID or Settings.get("enforce_features") != "1":
        return True
    return SubscriptionSystem.has_permission(user_id, feature)


# ════════════════════════════════════════════════════════════
# 8) إعدادات المستخدم والسياق والمحادثات
# ════════════════════════════════════════════════════════════
def save_user_setting(user_id: int, col: str, val) -> None:
    if col not in ("candle", "trade_time"):
        raise ValueError("invalid column")
    with get_conn(DB_NAME) as c:
        if not c.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone():
            c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        c.execute(f"UPDATE users SET {col}=? WHERE user_id=?", (val, user_id))
    log_data_change("update_setting", user_id, f"{col}={val}")


def get_user_setting(user_id: int):
    with get_conn(DB_NAME) as c:
        r = c.execute("SELECT candle, trade_time, last_analysis_context, last_analysis_time, country_timezone "
                      "FROM users WHERE user_id=?", (user_id,)).fetchone()
    if r:
        return (r["candle"] or "M1", r["trade_time"] or TRADE_TIMES[0], r["last_analysis_context"],
                r["last_analysis_time"], r["country_timezone"] or DEFAULT_TZ)
    return "M1", TRADE_TIMES[0], "", None, DEFAULT_TZ


def save_analysis_context(user_id: int, text: str) -> None:
    with get_conn(DB_NAME) as c:
        c.execute("UPDATE users SET last_analysis_context=?, last_analysis_time=CURRENT_TIMESTAMP WHERE user_id=?",
                  (text[:700], user_id))


def get_analysis_context(user_id: int) -> str:
    try:
        with get_conn(DB_NAME) as c:
            r = c.execute("SELECT last_analysis_context, last_analysis_time FROM users WHERE user_id=?",
                          (user_id,)).fetchone()
        if not r or not r["last_analysis_context"] or not r["last_analysis_time"]:
            return ""
        t = datetime.strptime(r["last_analysis_time"], "%Y-%m-%d %H:%M:%S")  # UTC
        if (datetime.utcnow() - t).total_seconds() > 600:
            return ""
        return r["last_analysis_context"]
    except Exception:
        return ""


def load_history(user_id: int, limit: int) -> list:
    if limit <= 0:
        return []
    with get_conn(DB_NAME) as c:
        rows = c.execute("SELECT role, content FROM chat_history WHERE user_id=? ORDER BY id DESC LIMIT ?",
                         (user_id, limit)).fetchall()
    return [{"role": r["role"], "content": r["content"][:1500]} for r in reversed(rows)]


def save_history(user_id: int, role: str, content: str) -> None:
    with get_conn(DB_NAME) as c:
        c.execute("INSERT INTO chat_history (user_id, role, content) VALUES (?,?,?)", (user_id, role, content[:4000]))


def cleanup_old_records() -> None:
    try:
        hours = max(1, Settings.int("history_retention_hours", 24))
        with get_conn(DB_NAME) as c:
            c.execute("DELETE FROM chat_history WHERE timestamp < datetime('now', ?)", (f"-{hours} hours",))
            c.execute("DELETE FROM data_log WHERE timestamp < datetime('now','-7 days')")
            c.execute("DELETE FROM audit_log WHERE ts < datetime('now','-90 days')")
    except Exception as e:
        log.warning("cleanup records: %s", e)


def cleanup_old_images(max_age: int = 600) -> None:
    now = time.time()
    try:
        for fn in os.listdir(IMAGE_CACHE_DIR):
            p = os.path.join(IMAGE_CACHE_DIR, fn)
            if os.path.isfile(p) and now - os.path.getmtime(p) > max_age:
                try:
                    os.remove(p)
                except OSError:
                    pass
    except Exception as e:
        log.warning("cleanup images: %s", e)


# ════════════════════════════════════════════════════════════
# 9) واجهة الذكاء الاصطناعي + الصور
# ════════════════════════════════════════════════════════════
class AIError(Exception):
    pass


def ai_chat(messages: list, model: str, max_tokens: int, temperature: float = 0.0, timeout: int = 75, retries: int = 2) -> str:
    if not AI_KEY:
        raise AIError("لم يتم ضبط AI_KEY")
    headers = {"Authorization": f"Bearer {AI_KEY}", "Content-Type": "application/json"}
    body = {"model": model, "messages": messages, "max_tokens": max_tokens,
            "temperature": temperature, "top_p": 1.0, "random_seed": 42}
    last = "unknown"
    for attempt in range(retries + 1):
        try:
            r = requests.post(AI_URL, json=body, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"].strip()
            last = f"HTTP {r.status_code}"
            log.warning("AI error %s: %s", r.status_code, r.text[:200])
            if r.status_code not in (429, 500, 502, 503, 504):
                break
        except requests.exceptions.Timeout:
            last = "timeout"
        except (requests.exceptions.RequestException, KeyError, ValueError) as e:
            last = type(e).__name__
        time.sleep(1.5 * (attempt + 1))
    raise AIError(last)


def compress_image(path: str, max_px: int = 1280, quality: int = 90) -> str:
    try:
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGBA")
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[-1])
                img = bg
            else:
                img = img.convert("RGB")
            img.thumbnail((max_px, max_px), Image.Resampling.LANCZOS)
            out = os.path.splitext(path)[0] + "_c.jpg"
            img.save(out, "JPEG", quality=quality, optimize=True)
            return out
    except Exception as e:
        log.warning("compress failed: %s", e)
        return path


def encode_image(path: str):
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception as e:
        log.warning("encode failed: %s", e)
        return None


def download_chart_image(symbol: str, candle: str = "M5"):
    """سحب صورة شارت (يتطلب SCREENSHOT_KEY)."""
    if not SCREENSHOT_KEY:
        return None
    try:
        chart_url = f"https://www.tradingview.com/chart/?symbol={tv_symbol(symbol)}&interval={TV_INTERVALS.get(candle, '5')}"
        r = requests.get("https://api.screenshotmachine.com/",
                         params={"key": SCREENSHOT_KEY, "url": chart_url, "dimension": "1024x768",
                                 "device": "desktop", "delay": 3000, "format": "png"}, timeout=40)
        if r.status_code == 200 and r.content[:4] == b"\x89PNG":
            safe = re.sub(r"[^\w]+", "_", symbol)
            p = os.path.join(IMAGE_CACHE_DIR, f"chart_{safe}_{int(time.time())}.png")
            with open(p, "wb") as f:
                f.write(r.content)
            return p
        log.warning("chart download failed: %s", r.status_code)
    except Exception as e:
        log.warning("chart download error: %s", e)
    return None


def clean_text(t: str) -> str:
    if not t:
        return ""
    out, prev = [], None
    for line in t.replace("\r", "").split("\n"):
        s = line.rstrip()
        if s and s == prev:
            continue
        out.append(s)
        prev = s
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def build_analysis_context(user_id: int, candle: str, trade_time: str, symbol: str) -> dict:
    session_name, session_time, session_vol, tz_name = get_market_session(user_id)
    local = get_localized_time(user_id)
    period = candle_seconds(candle)
    remaining = period - (int(time.time()) % period)
    elapsed = period - remaining
    utc_min = datetime.now(pytz.utc).minute
    trap = utc_min in (14, 29, 44, 59) and remaining < 15
    news_impact, news_warning = news_state()
    category = {"S": "فريمات ثواني - حركات سريعة وانعكاسات مفاجئة", "M": "فريمات دقائق - سرعة متوسطة",
                "H": "فريمات ساعات - حركة بطيئة وثابتة", "D": "فريم يومي - اتجاهات طويلة"}.get(candle[:1], "")
    strategies = {TRADE_TIMES[0]: ("سكالبينج (Scalping) - دخول وخروج سريع", "حجم كبير نسبياً مع وقف خسارة ضيق"),
                  TRADE_TIMES[1]: ("سوينج (Swing) - متوسط الأجل", "حجم معتدل مع وقف خسارة متوسط"),
                  TRADE_TIMES[2]: ("تداول موقف (Position) - طويل الأجل", "حجم صغير مع وقف خسارة واسع")}
    strategy, sizing = strategies.get(trade_time, (trade_time, "-"))
    return {
        "symbol": symbol, "candle": candle, "verification_timeframe": verification_tf(candle),
        "candle_category": category, "strategy": strategy, "position_sizing": sizing,
        "session_name": session_name, "session_time": session_time, "session_vol": session_vol,
        "local_time": local.strftime("%Y-%m-%d %H:%M:%S"), "timezone": tz_name,
        "seconds_remaining": remaining, "seconds_elapsed": elapsed,
        "window_status": execution_window(period, elapsed),
        "news_impact": news_impact, "news_warning": news_warning,
        "last_minute_status": "VOLATILITY_EXPANSION (دقيقة تحول)" if trap else "STABLE_FLOW",
        "market_mode": "AGGRESSIVE" if candle.startswith("S") else "CONSERVATIVE",
        "previous_context": get_analysis_context(user_id) or "غير متوفر",
    }


# ════════════════════════════════════════════════════════════
# 10) أدوات تليجرام المشتركة
# ════════════════════════════════════════════════════════════
def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    kb = [["⚙️ إعدادات التحليل", "📊 تحليل صورة"], ["💬 دردشة", "📈 توصية"],
          ["👤 حسابي", "🌍 دولتك"], ["ℹ️ المساعدة"]]
    if user_id == ADMIN_ID:
        kb.append(["👑 لوحة التحكم"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)


def chat_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([
        ["🚀 مساعد شامل", "💼 استشارات احترافية"], ["📈 تحليل استثماري", "👨‍💻 دعم برمجي"],
        ["📝 كتابة إبداعية", "🧠 حلول ذكية"], ["ايقاف الدردشة", BACK]], resize_keyboard=True)


def reco_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[k] for k in CATEGORIES] + [[BACK]], resize_keyboard=True)


def chunk_text(text: str, limit: int = 3800) -> list:
    if len(text) <= limit:
        return [text]
    parts, cur = [], ""
    for line in text.split("\n"):
        while len(line) > limit:
            if cur:
                parts.append(cur)
                cur = ""
            parts.append(line[:limit])
            line = line[limit:]
        if len(cur) + len(line) + 1 > limit:
            parts.append(cur)
            cur = ""
        cur += line + "\n"
    if cur.strip():
        parts.append(cur)
    return parts


async def send_long(message, text: str, code: bool = False, reply_markup=None) -> None:
    """إرسال نص طويل مقسّماً. code=True يعرضه كـ Code Block قابل للنسخ."""
    parts = chunk_text(text)
    for i, part in enumerate(parts):
        markup = reply_markup if i == len(parts) - 1 else None
        if code:
            body = "```\n" + part.replace("`", "'").strip() + "\n```"
            try:
                await message.reply_text(body, parse_mode="Markdown", reply_markup=markup)
                continue
            except Exception:
                pass
        await message.reply_text(part.strip(), reply_markup=markup)


async def safe_edit(msg, text: str) -> None:
    try:
        await msg.edit_text(text)
    except Exception:
        pass


async def safe_delete(msg) -> None:
    try:
        await msg.delete()
    except Exception:
        pass


def subscription_required_text(user_id: int, reason: str) -> str:
    return (f"⚠️ <b>عذراً، لا تملك صلاحية استخدام البوت حالياً</b>\n\n"
            f"❌ الحالة: {esc(reason)}\n\n"
            f"🆔 <b>معرّفك:</b> <code>{user_id}</code>\n"
            f"<i>(اضغط على الرقم لنسخه وأرسله للمشرف لتفعيل اشتراكك)</i>\n\n"
            f"🔑 <b>أسعار الاشتراكات:</b>\n{esc(Settings.get('prices'))}\n\n"
            f"📞 للاشتراك والتواصل: {esc(Settings.get('support_username'))}\n\n"
            f"بعد التفعيل أرسل /start")


async def ensure_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """تسجيل المستخدم + فحص الصيانة والاشتراك. يرسل الرسالة المناسبة عند الرفض."""
    user, msg = update.effective_user, update.effective_message
    if not user or not msg:
        return False
    is_new = await asyncio.to_thread(SubscriptionSystem.register_user, user.id, user.username, user.first_name,
                                     user.last_name, user.language_code, user.is_bot)
    if user.id == ADMIN_ID:
        return True
    if is_new and Settings.get("auto_trial") == "1":
        await asyncio.to_thread(SubscriptionSystem.add_subscription, user.id, "trial", ADMIN_ID, "auto trial")
    if Settings.get("maintenance") == "1":
        await msg.reply_text(Settings.get("maintenance_message"))
        return False
    ok, reason, _ = await asyncio.to_thread(SubscriptionSystem.check_subscription, user.id)
    if ok:
        return True
    await msg.reply_text(subscription_required_text(user.id, reason), parse_mode="HTML",
                         reply_markup=ReplyKeyboardMarkup([["👤 حسابي"]], resize_keyboard=True))
    return False


def cooldown_left(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> int:
    if user_id == ADMIN_ID:
        return 0
    wait = Settings.int("cooldown_seconds", 8)
    last = context.user_data.get("last_ai", 0)
    left = int(wait - (time.time() - last))
    if left <= 0:
        context.user_data["last_ai"] = time.time()
        return 0
    return left


def cleanup_user_data(context: ContextTypes.DEFAULT_TYPE, user_id: int | None = None) -> None:
    if user_id:
        try:
            for fn in os.listdir(IMAGE_CACHE_DIR):
                if f"_{user_id}_" in fn:
                    try:
                        os.remove(os.path.join(IMAGE_CACHE_DIR, fn))
                    except OSError:
                        pass
        except Exception:
            pass
    for k in ("admin_action", "target_user_id", "last_recommendation_symbol", "persona"):
        context.user_data.pop(k, None)


# ════════════════════════════════════════════════════════════
# 11) حالات المحادثة
# ════════════════════════════════════════════════════════════
(MAIN_MENU, SETTINGS_CANDLE, SETTINGS_TIME, CHAT_MODE, ANALYZE_MODE, RECOMMENDATION_MODE,
 CATEGORY_SELECTION, ADMIN_MENU, ADMIN_INPUT, COUNTRY_SELECTION) = range(10)


# ════════════════════════════════════════════════════════════
# 12) معالجات البوت: البداية والحساب والمساعدة
# ════════════════════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    cleanup_user_data(context, user.id)
    if not await ensure_access(update, context):
        return MAIN_MENU
    ok, reason, details = await asyncio.to_thread(SubscriptionSystem.check_subscription, user.id)
    tz = get_user_timezone(user.id)
    local = get_localized_time(user.id).strftime("%Y-%m-%d %H:%M")
    if user.id == ADMIN_ID:
        sub_line = "👑 أنت مسؤول النظام - صلاحيات كاملة"
    else:
        sub_line = f"✅ اشتراكك: <b>{esc(details['name'])}</b>\n⏳ المتبقي: {esc(fmt_remaining(details['end_date']))}"
    extra = Settings.get("welcome_message")
    text = (f"🚀 <b>أهلاً بك {esc(user.first_name or '')} في {BRAND}</b>\n\n{sub_line}\n"
            f"🆔 معرّفك: <code>{user.id}</code>\n🕒 توقيتك: {local} ({esc(tz)})\n\n"
            f"🤖 <b>الخدمات:</b>\n• 📊 تحليل الشارتات بالصور\n• 📈 توصيات فورية\n• 💬 دردشة ذكية\n"
            f"• 👤 حسابي ومعلومات اشتراكك\n• 🌍 ضبط توقيت دولتك\n"
            + (f"\n{esc(extra)}\n" if extra else "") + "\nاختر أحد الخيارات 👇")
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=main_keyboard(user.id))
    return MAIN_MENU


async def show_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بطاقة معلومات الحساب (متاحة لجميع المستخدمين حتى غير المشتركين)."""
    user = update.effective_user
    await asyncio.to_thread(SubscriptionSystem.register_user, user.id, user.username, user.first_name,
                            user.last_name, user.language_code, user.is_bot)
    p = await asyncio.to_thread(SubscriptionSystem.get_profile, user.id)
    candle, trade_time, _, _, tz = get_user_setting(user.id)
    local = get_localized_time(user.id).strftime("%Y-%m-%d %H:%M")
    if user.id == ADMIN_ID:
        sub_block = "💎 <b>الاشتراك:</b> 👑 مشرف (غير محدود)"
    elif p and p["status"] == "active":
        end = p["end_date"][:16].replace("T", " ") if p["end_date"] else "غير محدود ♾️"
        sub_block = (f"💎 <b>الاشتراك:</b> {esc(p['sub_name'])} ✅ نشط\n📅 بدأ: {esc((p['start_date'] or '')[:16].replace('T', ' '))}\n"
                     f"📆 ينتهي: {esc(end)}\n⏳ المتبقي: {esc(p['remaining'])}\n"
                     f"🔐 الصلاحيات: {esc(', '.join(p['permissions']) or '-')}")
    elif p and p["status"] == "blocked":
        sub_block = f"💎 <b>الاشتراك:</b> 🚫 محظور\n📝 السبب: {esc(p['blocked_reason'] or '-')}"
    elif p and p["status"] == "expired":
        sub_block = f"💎 <b>الاشتراك:</b> ❌ منتهي ({esc(p['sub_name'])})\n📞 للتجديد: {esc(Settings.get('support_username'))}"
    else:
        sub_block = f"💎 <b>الاشتراك:</b> ❌ لا يوجد\n📞 للاشتراك: {esc(Settings.get('support_username'))}"
    usage = p["usage"] if p else {}
    created = (p["created_at"] or "")[:10] if p else "-"
    text = (f"👤 <b>معلومات حسابك</b>\n━━━━━━━━━━━━━━\n"
            f"🆔 <b>المعرّف:</b> <code>{user.id}</code>\n"
            f"📛 <b>الاسم:</b> {esc(user.full_name)}\n"
            f"🔗 <b>اليوزر:</b> {('@' + esc(user.username)) if user.username else '—'}\n"
            f"📅 <b>تاريخ الانضمام:</b> {esc(created)}\n━━━━━━━━━━━━━━\n{sub_block}\n━━━━━━━━━━━━━━\n"
            f"⚙️ <b>الإعدادات:</b> شموع {esc(candle)} | {esc(trade_time)}\n"
            f"🌍 <b>المنطقة:</b> {esc(tz)} — 🕒 {local}\n━━━━━━━━━━━━━━\n"
            f"📈 <b>استخدامك:</b>\n• تحليل صور: {usage.get('photo_analysis', 0)}\n"
            f"• توصيات: {usage.get('recommendation', 0)}\n• رسائل دردشة: {usage.get('chat_message', 0)}")
    kb = main_keyboard(user.id) if (user.id == ADMIN_ID or (p and p["status"] == "active")) \
        else ReplyKeyboardMarkup([["👤 حسابي"]], resize_keyboard=True)
    await update.effective_message.reply_text(text, parse_mode="HTML", reply_markup=kb)


async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    await update.message.reply_text(f"🆔 معرّفك: <code>{u.id}</code>\n(اضغط عليه لنسخه)", parse_mode="HTML")


async def cmd_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_account(update, context)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (f"🤖 <b>دليل {BRAND}</b>\n\n<b>الأوامر:</b>\n/start - القائمة الرئيسية\n/me - معلومات حسابك\n"
            f"/id - عرض معرّفك\n/help - المساعدة\n/cancel - إلغاء وتنظيف\n\n"
            f"<b>طريقة الاستخدام:</b>\n1️⃣ من «⚙️ إعدادات التحليل» اختر سرعة الشموع ومدة الصفقة\n"
            f"2️⃣ أرسل صورة الشارت في «📊 تحليل صورة» (يجب أن تظهر الشموع ومحور الأسعار بوضوح)\n"
            f"3️⃣ أو اختر «📈 توصية» لسحب الشارت وتحليله تلقائياً\n"
            f"4️⃣ «💬 دردشة» لمساعد ذكي بعدة تخصصات\n5️⃣ «🌍 دولتك» لضبط التوقيت المحلي\n\n"
            f"<b>أنواع القرار:</b>\n🟢 شراء | 🔴 بيع | 💥 كسر هيكلي | 🔄 انعكاس/سحب سيولة | 🚨 فخ سيولة | 🟡 احتفاظ\n\n"
            f"<b>مدة الصفقة:</b>\n• قصير (1m-15m): تنفيذ سريع\n• متوسط (4h-Daily): انتظار أيام\n• طويل (Weekly-Monthly): استثمار طويل\n\n"
            f"🔑 <b>الأسعار:</b>\n{esc(Settings.get('prices'))}\n📞 {esc(Settings.get('support_username'))}\n\n"
            f"<i>{esc(DISCLAIMER)}</i>")
    await update.message.reply_text(text, parse_mode="HTML")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user:
        cleanup_user_data(context, update.effective_user.id)
    await update.message.reply_text("تم الإلغاء وتنظيف الذاكرة. اكتب /start للبدء من جديد.",
                                    reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ════════════════════════════════════════════════════════════
# 13) القائمة الرئيسية والإعدادات
# ════════════════════════════════════════════════════════════
async def go_main(update: Update, text: str = "🏠 العودة للقائمة الرئيسية"):
    await update.message.reply_text(text, reply_markup=main_keyboard(update.effective_user.id))
    return MAIN_MENU


async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    uid = update.effective_user.id
    if text == "👤 حسابي":
        await show_account(update, context)
        return MAIN_MENU
    if not await ensure_access(update, context):
        return MAIN_MENU
    if text == "🌍 دولتك":
        return await country_selection(update, context)
    if text == "ℹ️ المساعدة":
        await help_command(update, context)
        return MAIN_MENU
    if text == "👑 لوحة التحكم" and uid == ADMIN_ID:
        return await start_admin_panel(update, context)
    if text == "⚙️ إعدادات التحليل":
        kb = [CANDLE_SPEEDS[i:i + 3] for i in range(0, len(CANDLE_SPEEDS), 3)] + [[BACK]]
        await update.message.reply_text("⚙️ *إعدادات التحليل الفني*\n\nحدد سرعة الشموع للبدء:",
                                        parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return SETTINGS_CANDLE
    if text == "📊 تحليل صورة":
        candle, trade_time, _, _, _ = get_user_setting(uid)
        await update.message.reply_text(
            f"📊 <b>نظام التحليل جاهز</b>\n\n⚙️ إعداداتك الحالية:\n• 🏃 سرعة الشموع: <b>{esc(candle)}</b>\n"
            f"• 🕧 الاستراتيجية: <b>{esc(trade_time)}</b>\n\n📤 أرسل صورة الشارت الآن\n"
            f"<i>نصيحة: تأكد أن الشموع ومحور الأسعار وساعة المنصة ظاهرة بوضوح.</i>",
            parse_mode="HTML", reply_markup=ReplyKeyboardMarkup([[BACK]], resize_keyboard=True))
        return ANALYZE_MODE
    if text == "💬 دردشة":
        return await start_chat_mode(update, context)
    if text == "📈 توصية":
        return await start_recommendation_mode(update, context)
    await update.message.reply_text("اختر أحد الخيارات من القائمة 👇", reply_markup=main_keyboard(uid))
    return MAIN_MENU


async def handle_settings_candle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, uid = (update.message.text or "").strip(), update.effective_user.id
    if not await ensure_access(update, context):
        return MAIN_MENU
    if text == BACK:
        return await go_main(update)
    if text in CANDLE_SPEEDS:
        save_user_setting(uid, "candle", text)
        kb = [TRADE_TIMES[i:i + 2] for i in range(0, len(TRADE_TIMES), 2)] + [[BACK]]
        await update.message.reply_text(
            f"✅ تم تعيين سرعة الشموع: *{text}*\n\n⬇️ الآن حدد *مدة الصفقة*:\n"
            f"1- *قصير (1m-15m)*: تنفيذ سريع، مخاطر منخفضة\n2- *متوسط (4h-Daily)*: انتظار أيام، مخاطر متوسطة\n"
            f"3- *طويل (Weekly-Monthly)*: استثمار طويل، مخاطر مرتفعة",
            parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return SETTINGS_TIME
    await update.message.reply_text("❌ الرجاء اختيار سرعة شموع من الأزرار.")
    return SETTINGS_CANDLE


async def handle_settings_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, uid = (update.message.text or "").strip(), update.effective_user.id
    if not await ensure_access(update, context):
        return MAIN_MENU
    if text == BACK:
        return await go_main(update)
    if text in TRADE_TIMES:
        save_user_setting(uid, "trade_time", text)
        candle = get_user_setting(uid)[0]
        await update.message.reply_text(
            f"🚀 <b>تم حفظ الإعدادات</b>\n\n✅ سرعة الشموع: {esc(candle)}\n✅ مدة الصفقة: {esc(text)}\n\n"
            f"📤 أرسل صورة الشارت الآن من «📊 تحليل صورة».", parse_mode="HTML", reply_markup=main_keyboard(uid))
        return MAIN_MENU
    await update.message.reply_text("❌ الرجاء اختيار مدة صفقة من الأزرار.")
    return SETTINGS_TIME


# ════════════════════════════════════════════════════════════
# 14) اختيار الدولة
# ════════════════════════════════════════════════════════════
def _pair_rows(items: list) -> list:
    return [items[i:i + 2] for i in range(0, len(items), 2)]


async def country_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    kb = _pair_rows(ARAB_KEYS + MAJOR_KEYS) + [["🌍 جميع الدول", "🔍 بحث عن دولة"], [BACK]]
    await update.message.reply_text(
        f"🌍 <b>اختر دولتك</b>\n\n🕒 وقتك الحالي: {get_localized_time(uid).strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"📍 منطقتك: {esc(get_user_timezone(uid))}\n\nاختر من الأزرار أو اكتب اسم الدولة للبحث:",
        parse_mode="HTML", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    return COUNTRY_SELECTION


async def handle_country_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, uid = (update.message.text or "").strip(), update.effective_user.id
    if not await ensure_access(update, context):
        return MAIN_MENU
    if text == BACK:
        return await go_main(update)
    if text == "🌍 جميع الدول":
        await update.message.reply_text("🌍 جميع الدول المتاحة:", reply_markup=ReplyKeyboardMarkup(
            _pair_rows(_COUNTRY_KEYS) + [[BACK]], resize_keyboard=True))
        return COUNTRY_SELECTION
    if text == "🔍 بحث عن دولة":
        await update.message.reply_text("🔍 اكتب اسم الدولة (مثال: مصر، السعودية، تركيا):")
        return COUNTRY_SELECTION
    if text in COUNTRIES:
        set_user_timezone(uid, COUNTRIES[text])
        await update.message.reply_text(
            f"✅ <b>تم تعيين دولتك</b>\n\n📍 {esc(text)}\n🕒 توقيتك المحلي: "
            f"{get_localized_time(uid).strftime('%Y-%m-%d %H:%M:%S')}\n\nسيُستخدم في جميع التحليلات.",
            parse_mode="HTML", reply_markup=main_keyboard(uid))
        return MAIN_MENU
    if len(text) > 1:
        found = [c for c in _COUNTRY_KEYS if text in c][:10]
        if found:
            await update.message.reply_text(f"🔍 نتائج البحث عن «{text}»:", reply_markup=ReplyKeyboardMarkup(
                [[c] for c in found] + [[BACK]], resize_keyboard=True))
            return COUNTRY_SELECTION
    await update.message.reply_text("❌ الدولة غير موجودة. اختر من القائمة أو اكتب اسماً صحيحاً.")
    return COUNTRY_SELECTION


# ════════════════════════════════════════════════════════════
# 15) الدردشة
# ════════════════════════════════════════════════════════════
async def start_chat_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not feature_allowed(uid, "chat"):
        await update.message.reply_text("🔒 الدردشة غير متاحة في باقتك الحالية. للترقية: " + Settings.get("support_username"))
        return MAIN_MENU
    SubscriptionSystem.increment_usage(uid, "chat_mode")
    context.user_data["persona"] = "🚀 مساعد شامل"
    await update.message.reply_text(
        f"🚀 <b>وضع الدردشة مع {BRAND}</b>\n\nاختر التخصص أو أرسل سؤالك مباشرة:\n"
        f"<i>التخصص الحالي: 🚀 مساعد شامل</i>", parse_mode="HTML", reply_markup=chat_keyboard())
    return CHAT_MODE


async def handle_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, uid = (update.message.text or "").strip(), update.effective_user.id
    if not await ensure_access(update, context):
        return MAIN_MENU
    if text in ("ايقاف الدردشة", BACK):
        return await go_main(update, "✅ تم إنهاء وضع الدردشة." if text == "ايقاف الدردشة" else "🏠 العودة للقائمة الرئيسية")
    if text in PERSONAS:
        context.user_data["persona"] = text
        await update.message.reply_text(f"✅ تم اختيار: <b>{esc(text)}</b>\n💬 أرسل سؤالك الآن:", parse_mode="HTML")
        return CHAT_MODE
    if not feature_allowed(uid, "chat"):
        await update.message.reply_text("🔒 الدردشة غير متاحة في باقتك الحالية.")
        return MAIN_MENU
    left = cooldown_left(context, uid)
    if left:
        await update.message.reply_text(f"⏳ انتظر {left} ثانية قبل الرسالة التالية.")
        return CHAT_MODE
    SubscriptionSystem.increment_usage(uid, "chat_message")
    persona = context.user_data.get("persona", "🚀 مساعد شامل")
    system = get_prompt(PERSONAS.get(persona, "chat_general")) + CHAT_COMMON_RULES
    history = await asyncio.to_thread(load_history, uid, Settings.int("history_messages", 6))
    messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": text[:4000]}]
    wait = await update.message.reply_text("💭 جارٍ التفكير...")
    await update.effective_chat.send_action(ChatAction.TYPING)
    try:
        result = await asyncio.to_thread(ai_chat, messages, Settings.get("model_chat"),
                                         Settings.int("chat_max_tokens", 2200), Settings.float("ai_temperature", 0.2))
        result = clean_text(result)
        await asyncio.to_thread(save_history, uid, "user", text)
        await asyncio.to_thread(save_history, uid, "assistant", result)
        await safe_delete(wait)
        await send_long(update.message, f"{result}\n\n━━━━━━━━━━━━\n🤖 {BRAND}", reply_markup=chat_keyboard())
    except AIError as e:
        await safe_edit(wait, f"❌ تعذّر الحصول على رد ({e}). حاول مرة أخرى بعد قليل.")
    except Exception:
        log.exception("chat error")
        await safe_edit(wait, "❌ حدث خطأ غير متوقع. حاول مجدداً.")
    return CHAT_MODE


# ════════════════════════════════════════════════════════════
# 16) تحليل الصور والتوصيات
# ════════════════════════════════════════════════════════════
async def run_chart_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE, image_path: str,
                             symbol: str, status_msg, keyboard=None) -> bool:
    uid = update.effective_user.id
    files = [image_path]
    try:
        candle, trade_time, _, _, _ = get_user_setting(uid)
        await safe_edit(status_msg, "🔍 جارٍ استخراج البيانات وتحليل الشارت...")
        await update.effective_chat.send_action(ChatAction.TYPING)
        compressed = await asyncio.to_thread(compress_image, image_path)
        files.append(compressed)
        b64 = await asyncio.to_thread(encode_image, compressed)
        if not b64:
            await safe_edit(status_msg, "❌ تعذّرت قراءة الصورة. أرسل صورة أوضح.")
            return False
        ctx = build_analysis_context(uid, candle, trade_time, symbol)
        prompt = render_prompt(get_prompt("analysis"), ctx)
        messages = [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}}]}]
        raw = await asyncio.to_thread(ai_chat, messages, Settings.get("model_vision"),
                                      Settings.int("vision_max_tokens", 1400), 0.0, 90)
        analysis = clean_text(raw)
        await asyncio.to_thread(save_analysis_context, uid, analysis)
        report = (f"✅ تم التحليل - {symbol}\n━━━━━━━━━━━━━━━━━━━━\n{analysis}\n\n━━━━━━━━━━━━━━━━━━━━\n"
                  f"🔧 الإعدادات المستخدمة:\n• الفريم: {candle} (تحقق: {ctx['verification_timeframe']})\n"
                  f"• الجلسة: {ctx['session_name']} ({ctx['session_time']})\n• نمط السوق: {ctx['market_mode']}\n"
                  f"• المنقضي من الشمعة: {ctx['seconds_elapsed']}ث — {ctx['window_status']}\n"
                  f"• التوقيت: {ctx['local_time']} ({ctx['timezone']})\n━━━━━━━━━━━━━━━━━━━━\n"
                  f"{DISCLAIMER}\n🤖 {BRAND}")
        await safe_delete(status_msg)
        await send_long(update.effective_message, report, code=True, reply_markup=keyboard)
        return True
    except AIError as e:
        await safe_edit(status_msg, f"❌ تعذّر الاتصال بمحرك التحليل ({e}). حاول مرة أخرى.")
    except Exception:
        log.error("analysis error: %s", traceback.format_exc())
        await safe_edit(status_msg, "❌ حدث خطأ أثناء التحليل. حاول مرة أخرى.")
    finally:
        for p in files:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass
    return False


async def _download_incoming_image(update: Update, uid: int):
    msg = update.message
    ts = int(time.time() * 1000)
    path = os.path.join(IMAGE_CACHE_DIR, f"img_{uid}_{ts}.jpg")
    if msg.photo:
        f = await msg.photo[-1].get_file()
    elif msg.document and (msg.document.mime_type or "").startswith("image/"):
        f = await msg.document.get_file()
    else:
        return None
    await f.download_to_drive(path)
    return path


async def handle_photo_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await ensure_access(update, context):
        return MAIN_MENU
    if not feature_allowed(uid, "basic_analysis"):
        await update.message.reply_text("🔒 تحليل الصور غير متاح في باقتك.")
        return MAIN_MENU
    left = cooldown_left(context, uid)
    if left:
        await update.message.reply_text(f"⏳ انتظر {left} ثانية قبل الطلب التالي.")
        return ANALYZE_MODE
    wait = await update.message.reply_text("📸 تم استلام الصورة بنجاح...")
    try:
        path = await _download_incoming_image(update, uid)
        if not path:
            await safe_edit(wait, "❌ أرسل صورة الشارت كصورة.")
            return ANALYZE_MODE
        SubscriptionSystem.increment_usage(uid, "photo_analysis")
        await run_chart_analysis(update, context, path, "الشارت المرفق", wait,
                                 ReplyKeyboardMarkup([["📊 تحليل صورة"], [BACK]], resize_keyboard=True))
    except Exception:
        log.exception("photo analysis")
        await safe_edit(wait, "❌ تعذّر استلام الصورة. حاول مجدداً.")
    return ANALYZE_MODE


async def handle_analyze_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not await ensure_access(update, context):
        return MAIN_MENU
    if text == BACK:
        return await go_main(update)
    if text == "📊 تحليل صورة":
        await update.message.reply_text("📤 أرسل صورة الشارت الآن.")
        return ANALYZE_MODE
    await update.message.reply_text("📤 الرجاء إرسال صورة الشارت فقط، أو اضغط «" + BACK + "».",
                                    reply_markup=ReplyKeyboardMarkup([[BACK]], resize_keyboard=True))
    return ANALYZE_MODE


async def start_recommendation_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not feature_allowed(uid, "recommendations"):
        await update.message.reply_text("🔒 التوصيات غير متاحة في باقتك الحالية. للترقية: " + Settings.get("support_username"))
        return MAIN_MENU
    await update.message.reply_text("🚀 *نظام التوصيات*\n\nاختر القسم المطلوب:", parse_mode="Markdown",
                                    reply_markup=reco_keyboard())
    return RECOMMENDATION_MODE


async def text_recommendation(uid: int, symbol: str) -> str:
    candle, trade_time, _, _, _ = get_user_setting(uid)
    ctx = build_analysis_context(uid, candle, trade_time, symbol)
    prompt = render_prompt(get_prompt("recommendation_text"), ctx)
    raw = await asyncio.to_thread(ai_chat, [{"role": "user", "content": prompt}], Settings.get("model_audit"),
                                  900, 0.0)
    return clean_text(raw)


async def handle_recommendation_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, uid = (update.message.text or "").strip(), update.effective_user.id
    if not await ensure_access(update, context):
        return MAIN_MENU
    if text == BACK:
        return await go_main(update)
    if text in ("🔙 العودة للقائمة",):
        await update.message.reply_text("🔙 اختر القسم المطلوب:", reply_markup=reco_keyboard())
        return RECOMMENDATION_MODE
    if text in CATEGORIES:
        kb = _pair_rows(CATEGORIES[text]) + [["🔙 العودة للقائمة", BACK]]
        await update.message.reply_text(f"📍 قسم: {text}\nاختر الأصل:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return CATEGORY_SELECTION
    symbol = next((s for lst in CATEGORIES.values() for s in lst if s == text), None)
    if not symbol:
        await update.message.reply_text("❌ خيار غير موجود. اختر من الأزرار.")
        return RECOMMENDATION_MODE
    left = cooldown_left(context, uid)
    if left:
        await update.message.reply_text(f"⏳ انتظر {left} ثانية قبل الطلب التالي.")
        return CATEGORY_SELECTION
    context.user_data["last_recommendation_symbol"] = symbol
    SubscriptionSystem.increment_usage(uid, "recommendation")
    wait = await update.message.reply_text(f"📸 جارٍ سحب شارت {symbol}...")
    candle = get_user_setting(uid)[0]
    chart = await asyncio.to_thread(download_chart_image, symbol, candle)
    back_kb = reco_keyboard()
    if chart and os.path.exists(chart):
        try:
            with open(chart, "rb") as ph:
                await update.message.reply_photo(photo=ph, caption=f"📈 شارت {symbol}")
        except Exception as e:
            log.warning("send chart photo: %s", e)
        await run_chart_analysis(update, context, chart, symbol, wait, back_kb)
    else:
        try:
            analysis = await text_recommendation(uid, symbol)
            await safe_delete(wait)
            await send_long(update.message, f"📈 توصية {symbol} (بدون بيانات مباشرة)\n━━━━━━━━━━━━━━━━━━\n{analysis}\n"
                            f"━━━━━━━━━━━━━━━━━━\n{DISCLAIMER}\n🤖 {BRAND}", code=True, reply_markup=back_kb)
        except AIError as e:
            await safe_edit(wait, f"❌ تعذّر إنشاء التوصية ({e}).")
    return RECOMMENDATION_MODE


async def handle_recommendation_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await ensure_access(update, context):
        return MAIN_MENU
    left = cooldown_left(context, uid)
    if left:
        await update.message.reply_text(f"⏳ انتظر {left} ثانية.")
        return RECOMMENDATION_MODE
    symbol = context.user_data.get("last_recommendation_symbol", "الشارت المرفق")
    wait = await update.message.reply_text(f"📊 جارٍ تحليل {symbol}...")
    path = await _download_incoming_image(update, uid)
    if not path:
        await safe_edit(wait, "❌ أرسل صورة الشارت كصورة.")
        return RECOMMENDATION_MODE
    SubscriptionSystem.increment_usage(uid, "recommendation_photo")
    await run_chart_analysis(update, context, path, symbol, wait, reco_keyboard())
    return RECOMMENDATION_MODE


# ════════════════════════════════════════════════════════════
# 17) البث والرسائل عبر Telegram HTTP API (مشترك بين البوت والويب)
# ════════════════════════════════════════════════════════════
BROADCAST = {"running": False, "total": 0, "sent": 0, "failed": 0, "started": None, "finished": None, "preview": ""}
_broadcast_lock = threading.Lock()


def send_telegram(chat_id: int, text: str, retry: bool = True):
    try:
        r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                          json={"chat_id": chat_id, "text": text[:4096]}, timeout=15)
        if r.status_code == 200:
            return True, ""
        if r.status_code == 429 and retry:
            time.sleep(int(r.json().get("parameters", {}).get("retry_after", 2)) + 1)
            return send_telegram(chat_id, text, retry=False)
        return False, r.json().get("description", str(r.status_code))
    except Exception as e:
        return False, str(e)


def _broadcast_worker(ids: list, text: str) -> None:
    body = f"📢 رسالة إدارية\n\n{text}\n\n━━━━━━━━━━━━\n{BRAND}"
    for uid in ids:
        ok, _ = send_telegram(uid, body)
        BROADCAST["sent" if ok else "failed"] += 1
        time.sleep(0.06)
    BROADCAST["running"] = False
    BROADCAST["finished"] = datetime.now().isoformat(timespec="seconds")
    audit("system", "broadcast_done", "", f"sent={BROADCAST['sent']} failed={BROADCAST['failed']}")


def start_broadcast(text: str, audience: str = "active", actor: str = "web"):
    with _broadcast_lock:
        if BROADCAST["running"]:
            return False, "هناك إذاعة قيد التنفيذ حالياً"
        ids = SubscriptionSystem.audience_ids(audience)
        if not ids:
            return False, "لا يوجد مستلمون ضمن هذه الفئة"
        BROADCAST.update(running=True, total=len(ids), sent=0, failed=0,
                         started=datetime.now().isoformat(timespec="seconds"), finished=None, preview=text[:80])
    audit(actor, "broadcast", audience, f"{len(ids)} recipients")
    threading.Thread(target=_broadcast_worker, args=(ids, text), daemon=True).start()
    return True, f"بدأت الإذاعة لـ {len(ids)} مستخدم"


# ════════════════════════════════════════════════════════════
# 18) لوحة تحكم المشرف داخل تليجرام
# ════════════════════════════════════════════════════════════
ADMIN_KB = ReplyKeyboardMarkup([
    ["👥 عرض المستخدمين", "➕ إضافة اشتراك"], ["🗑️ إلغاء اشتراك", "⏱️ تمديد اشتراك"],
    ["🚫 حظر مستخدم", "✅ إلغاء حظر"], ["📢 إذاعة للمشتركين", "📊 إحصائيات"],
    ["🌐 لوحة الويب", "🔙 العودة للقائمة الرئيسية"]], resize_keyboard=True)
DURATION_MAP = {"🕐 ساعة": "hourly", "📅 يوم": "daily", "📆 أسبوع": "weekly", "📅 شهر": "monthly",
                "📅 سنة": "yearly", "♾️ مدى الحياة": "lifetime", "🧪 تجريبي": "trial"}
STATUS_ICON = {"active": "✅", "expired": "⌛", "blocked": "🚫", "none": "➖"}


async def start_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ ليس لديك صلاحية.")
        return MAIN_MENU
    await update.message.reply_text("👑 <b>لوحة تحكم المشرف</b>\nللتحكم الكامل استخدم لوحة الويب 🌐", parse_mode="HTML",
                                    reply_markup=ADMIN_KB)
    return ADMIN_MENU


async def handle_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, uid = (update.message.text or "").strip(), update.effective_user.id
    if uid != ADMIN_ID:
        return MAIN_MENU
    prompts = {"➕ إضافة اشتراك": ("add_id", "➕ أرسل معرّف المستخدم (User ID):"),
               "🗑️ إلغاء اشتراك": ("revoke", "🗑️ أرسل معرّف المستخدم لإلغاء اشتراكه:"),
               "⏱️ تمديد اشتراك": ("extend", "⏱️ أرسل: المعرّف ثم المدة بالثواني\nمثال: 123456789 86400"),
               "🚫 حظر مستخدم": ("block", "🚫 أرسل المعرّف (واختيارياً السبب)\nمثال: 123456789 مخالفة"),
               "✅ إلغاء حظر": ("unblock", "✅ أرسل معرّف المستخدم لإلغاء حظره:"),
               "📢 إذاعة للمشتركين": ("broadcast", "📢 أرسل نص الرسالة لإذاعتها للمشتركين النشطين:")}
    if text == "🔙 العودة للقائمة الرئيسية":
        context.user_data.pop("admin_action", None)
        return await go_main(update)
    if text in prompts:
        action, msg = prompts[text]
        context.user_data["admin_action"] = action
        await update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup([["إلغاء"]], resize_keyboard=True))
        return ADMIN_INPUT
    if text == "👥 عرض المستخدمين":
        users = await asyncio.to_thread(SubscriptionSystem.get_all_users)
        if not users:
            await update.message.reply_text("📭 لا يوجد مستخدمون بعد.")
        else:
            lines = [f"{STATUS_ICON[u['status']]} {u['name']} | {u['user_id']} | {u['sub_name'] or '-'} | "
                     f"{(u['end_date'] or '∞')[:16]}" for u in users[:60]]
            await send_long(update.message, f"👥 المستخدمون ({len(users)}) - آخر 60:\n\n" + "\n".join(lines))
    elif text == "📊 إحصائيات":
        s = await asyncio.to_thread(SubscriptionSystem.get_stats)
        out = (f"📊 إحصائيات النظام\n\n👥 المستخدمون: {s['total_users']}\n✅ نشطون: {s['active_users']}\n"
               f"⌛ منتهية: {s['expired_users']}\n🚫 محظورون: {s['blocked_users']}\n🆕 جدد اليوم: {s['new_today']}\n\n"
               f"📈 الميزات الأكثر استخداماً:\n" + "\n".join(f"• {k}: {v}" for k, v in list(s['feature_usage'].items())[:6]))
        await update.message.reply_text(out)
    elif text == "🌐 لوحة الويب":
        url = PUBLIC_URL or f"http://localhost:{PORT}"
        await update.message.reply_text(f"🌐 رابط لوحة الويب:\n{url}/admin\n\nالمستخدم: {ADMIN_USERNAME}")
    return ADMIN_MENU


async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, uid = (update.message.text or "").strip(), update.effective_user.id
    if uid != ADMIN_ID:
        return MAIN_MENU
    action = context.user_data.get("admin_action")
    if text == "إلغاء" or not action:
        context.user_data.pop("admin_action", None)
        return await start_admin_panel(update, context)
    parts = text.split(maxsplit=1)
    try:
        if action == "add_id":
            context.user_data["target_user_id"] = int(parts[0])
            context.user_data["admin_action"] = "add_type"
            kb = [["🕐 ساعة", "📅 يوم"], ["📆 أسبوع", "📅 شهر"], ["📅 سنة", "♾️ مدى الحياة"], ["🧪 تجريبي", "إلغاء"]]
            await update.message.reply_text(f"اختر مدة الاشتراك للمستخدم {parts[0]}:",
                                            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
            return ADMIN_INPUT
        if action == "add_type":
            if text not in DURATION_MAP:
                await update.message.reply_text("❌ اختر من الأزرار.")
                return ADMIN_INPUT
            target = context.user_data.pop("target_user_id")
            ok, res = SubscriptionSystem.add_subscription(target, DURATION_MAP[text], uid, "telegram panel")
            if ok:
                end = res["end_date"][:16].replace("T", " ") if res["end_date"] else "غير محدد (مدى الحياة)"
                audit("admin_tg", "grant", target, res["subscription_type"])
                await update.message.reply_text(f"✅ تم تفعيل اشتراك {res['subscription_name']} للمستخدم {target}\nينتهي: {end}")
                send_telegram(target, f"✅ تم تفعيل اشتراكك ({res['subscription_name']})\nينتهي: {end}\nأرسل /start للبدء.")
            else:
                await update.message.reply_text(f"❌ {res}")
        elif action == "revoke":
            ok, msg = SubscriptionSystem.revoke_subscription(int(parts[0]), by=uid)
            audit("admin_tg", "revoke", parts[0])
            await update.message.reply_text(("✅ " if ok else "❌ ") + msg)
        elif action == "extend":
            ok, msg = SubscriptionSystem.extend_subscription(int(parts[0]), int(parts[1]), by=uid)
            audit("admin_tg", "extend", parts[0], parts[1])
            await update.message.reply_text(("✅ " if ok else "❌ ") + msg)
        elif action == "block":
            ok, msg = SubscriptionSystem.block_user(int(parts[0]), parts[1] if len(parts) > 1 else "Blocked by admin", uid)
            audit("admin_tg", "block", parts[0])
            await update.message.reply_text(("✅ " if ok else "❌ ") + msg)
        elif action == "unblock":
            ok, msg = SubscriptionSystem.unblock_user(int(parts[0]), uid)
            audit("admin_tg", "unblock", parts[0])
            await update.message.reply_text(("✅ " if ok else "❌ ") + msg)
        elif action == "broadcast":
            ok, msg = start_broadcast(text, "active", "admin_tg")
            await update.message.reply_text(("📢 " if ok else "❌ ") + msg)
    except (ValueError, IndexError):
        await update.message.reply_text("❌ صيغة غير صحيحة. تأكد من الأرقام وأعد المحاولة.")
        return ADMIN_INPUT
    context.user_data.pop("admin_action", None)
    await update.message.reply_text("👑 لوحة التحكم:", reply_markup=ADMIN_KB)
    return ADMIN_MENU


# ════════════════════════════════════════════════════════════
# 19) النسخ الاحتياطي والمهام الدورية
# ════════════════════════════════════════════════════════════
def _sqlite_backup(src: str, dst: str) -> None:
    s, d = sqlite3.connect(src), sqlite3.connect(dst)
    try:
        s.backup(d)
    finally:
        d.close()
        s.close()


class DataProtection:
    @staticmethod
    def backup_all() -> list:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        made = []
        for prefix, path in (("main_backup", DB_NAME), ("subscription_backup", SUB_DB)):
            if os.path.exists(path):
                dst = os.path.join(BACKUP_DIR, f"{prefix}_{ts}.db")
                _sqlite_backup(path, dst)
                made.append(os.path.basename(dst))
        DataProtection.prune()
        return made

    @staticmethod
    def prune(keep: int = 30) -> None:
        for prefix in ("main_backup", "subscription_backup"):
            files = sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith(prefix) and f.endswith(".db"))
            for old in files[:-keep]:
                try:
                    os.remove(os.path.join(BACKUP_DIR, old))
                except OSError:
                    pass

    @staticmethod
    def list_backups() -> list:
        out = []
        for f in sorted(os.listdir(BACKUP_DIR), reverse=True):
            if f.endswith(".db"):
                p = os.path.join(BACKUP_DIR, f)
                out.append({"name": f, "size": round(os.path.getsize(p) / 1024, 1),
                            "date": datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M")})
        return out

    @staticmethod
    def restore(name: str) -> None:
        if not re.fullmatch(r"(main|subscription)_backup_\d{8}_\d{6}\.db", name):
            raise ValueError("اسم ملف غير صالح")
        src = os.path.join(BACKUP_DIR, name)
        if not os.path.exists(src):
            raise FileNotFoundError("الملف غير موجود")
        DataProtection.backup_all()  # نسخة أمان قبل الاستعادة
        _sqlite_backup(src, DB_NAME if name.startswith("main") else SUB_DB)


async def periodic_cleanup():
    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(cleanup_old_images)
            await asyncio.to_thread(cleanup_old_records)
        except Exception as e:
            log.warning("periodic cleanup: %s", e)


async def backup_scheduler():
    while True:
        await asyncio.sleep(3600)
        try:
            await asyncio.to_thread(DataProtection.backup_all)
            log.info("⏰ scheduled backup done")
        except Exception as e:
            log.warning("scheduled backup: %s", e)


BOT_STATE = {"username": "", "name": "", "started": None, "ok": False}


async def post_init(application: Application) -> None:
    me = await application.bot.get_me()
    BOT_STATE.update(username=me.username, name=me.full_name, started=datetime.now().isoformat(timespec="seconds"), ok=True)
    try:
        from telegram import BotCommand
        await application.bot.set_my_commands([
            BotCommand("start", "القائمة الرئيسية"), BotCommand("me", "معلومات حسابي"),
            BotCommand("id", "عرض معرّفي"), BotCommand("help", "المساعدة"), BotCommand("cancel", "إلغاء")])
    except Exception as e:
        log.warning("set commands: %s", e)
    application.bot_data["tasks"] = [asyncio.create_task(periodic_cleanup()), asyncio.create_task(backup_scheduler())]
    log.info("🤖 Bot @%s is running", me.username)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    tb = "".join(traceback.format_exception(None, err, err.__traceback__))
    log.error("Unhandled error: %s\n%s", err, tb)
    if isinstance(err, (NetworkError, TimedOut)):
        return
    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(update.effective_chat.id, "⚠️ حدث خطأ تقني. حاول مرة أخرى بعد قليل.")
        except Exception:
            pass


# ════════════════════════════════════════════════════════════
# 20) لوحة تحكم الويب (Flask API + واجهة SPA)
# ════════════════════════════════════════════════════════════
app = Flask(__name__)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=_env("HTTPS") == "1",
                  PERMANENT_SESSION_LIFETIME=timedelta(hours=12))
_LOGIN_FAILS: dict = {}


@app.after_request
def _security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Cache-Control"] = "no-store"
    return resp


def init_web_security() -> None:
    secret = Settings.raw("flask_secret")
    if not secret:
        secret = secrets.token_hex(32)
        Settings.set("flask_secret", secret)
    app.secret_key = secret
    env_pw = _env("ADMIN_PASSWORD")
    if env_pw:
        Settings.set("admin_password_hash", generate_password_hash(env_pw))
    elif not Settings.raw("admin_password_hash"):
        pw = secrets.token_urlsafe(10)
        Settings.set("admin_password_hash", generate_password_hash(pw))
        banner = f"\n{'=' * 56}\n🔐 كلمة مرور لوحة الويب (تظهر مرة واحدة فقط):\n   المستخدم: {ADMIN_USERNAME}\n   كلمة المرور: {pw}\n{'=' * 56}\n"
        print(banner)
        log.warning("Generated admin panel password (shown once on console)")


def api(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return jsonify(ok=False, error="unauthorized"), 401
        if request.method != "GET":
            tok = request.headers.get("X-CSRF-Token", "")
            if not tok or not secrets.compare_digest(tok, session.get("csrf", "")):
                return jsonify(ok=False, error="رمز الحماية غير صالح، أعد تحميل الصفحة"), 403
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            log.exception("api error")
            return jsonify(ok=False, error=str(e)), 500
    return wrapper


def _body() -> dict:
    return request.get_json(silent=True) or {}


@app.get("/")
def home():
    return redirect("/admin")


@app.get("/login")
def login_page():
    return Response(LOGIN_HTML, mimetype="text/html")


@app.post("/api/login")
def api_login():
    ip = (request.headers.get("X-Forwarded-For", request.remote_addr or "")).split(",")[0].strip()
    now = time.time()
    fails = [t for t in _LOGIN_FAILS.get(ip, []) if now - t < 600]
    if len(fails) >= 5:
        return jsonify(ok=False, error="محاولات كثيرة. انتظر 10 دقائق."), 429
    d = _body()
    user_ok = secrets.compare_digest(str(d.get("username", "123")), ADMIN_USERNAME)
    pass_ok = check_password_hash(Settings.raw("admin_password_hash") or "", str(d.get("password", "123")))
    if user_ok and pass_ok:
        _LOGIN_FAILS.pop(ip, None)
        session.clear()
        session.update(logged_in=True, csrf=secrets.token_urlsafe(24))
        session.permanent = True
        audit("web", "login", ip)
        return jsonify(ok=True)
    fails.append(now)
    _LOGIN_FAILS[ip] = fails
    audit("web", "login_failed", ip)
    time.sleep(0.6)
    return jsonify(ok=False, error="اسم المستخدم أو كلمة المرور غير صحيحة"), 401


@app.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/admin")
def admin_page():
    if not session.get("logged_in"):
        return redirect("/login")
    return Response(ADMIN_HTML, mimetype="text/html")


@app.get("/api/session")
@api
def api_session():
    return jsonify(ok=True, csrf=session["csrf"], username=ADMIN_USERNAME, bot=BOT_STATE, version=APP_VERSION)


@app.get("/api/dashboard")
@api
def api_dashboard():
    stats = SubscriptionSystem.get_stats()
    sizes = {os.path.basename(p): round(os.path.getsize(p) / 1024, 1) for p in (DB_NAME, SUB_DB) if os.path.exists(p)}
    system = {"uptime": fmt_remaining((datetime.now() + timedelta(seconds=time.time() - START_TIME)).isoformat()).replace("منتهي", "0"),
              "bot": BOT_STATE, "maintenance": Settings.get("maintenance") == "1", "version": APP_VERSION,
              "ai_configured": bool(AI_KEY), "screenshot_configured": bool(SCREENSHOT_KEY),
              "db_sizes_kb": sizes, "python": sys.version.split()[0], "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
              "models": {"vision": Settings.get("model_vision"), "chat": Settings.get("model_chat"),
                         "audit": Settings.get("model_audit")}}
    return jsonify(ok=True, stats=stats, system=system, broadcast=BROADCAST)


@app.get("/api/timezones")
@api
def api_timezones():
    return jsonify(ok=True, items=[[k, v] for k, v in COUNTRIES.items()])


@app.get("/api/users")
@api
def api_users():
    q = (request.args.get("q") or "").strip().lower()
    status = request.args.get("status") or ""
    page = max(1, int(request.args.get("page", 1) or 1))
    per = min(100, max(5, int(request.args.get("per", 25) or 25)))
    users = SubscriptionSystem.get_all_users()
    if status:
        users = [u for u in users if u["status"] == status]
    if q:
        users = [u for u in users if q in str(u["user_id"]) or q in u["name"].lower() or q in u["username"].lower()]
    total = len(users)
    return jsonify(ok=True, total=total, page=page, per=per, users=users[(page - 1) * per: page * per])


@app.get("/api/users/<int:uid>")
@api
def api_user_detail(uid):
    p = SubscriptionSystem.get_profile(uid)
    if not p:
        return jsonify(ok=False, error="المستخدم غير موجود"), 404
    return jsonify(ok=True, user=p, types={k: v["name"] for k, v in SubscriptionSystem.TYPES.items()})


def _notify(uid: int, text: str, enabled: bool) -> None:
    if enabled:
        threading.Thread(target=send_telegram, args=(uid, text), daemon=True).start()


@app.post("/api/users/add")
@api
def api_user_add():
    d = _body()
    uid, t = int(d.get("user_id", 0)), d.get("type", "monthly")
    if uid <= 0:
        return jsonify(ok=False, error="معرّف غير صالح")
    ok, res = SubscriptionSystem.add_subscription(uid, t, ADMIN_ID, "web panel")
    if not ok:
        return jsonify(ok=False, error=res)
    audit("web", "grant", uid, t)
    end = res["end_date"][:16].replace("T", " ") if res["end_date"] else "مدى الحياة"
    _notify(uid, f"✅ تم تفعيل اشتراكك ({res['subscription_name']})\nينتهي: {end}\nأرسل /start للبدء.", d.get("notify", True))
    return jsonify(ok=True, message=f"تم تفعيل اشتراك {res['subscription_name']}")


@app.post("/api/users/<int:uid>/<action>")
@api
def api_user_action(uid, action):
    d = _body()
    notify = bool(d.get("notify", True))
    if action == "grant":
        ok, res = SubscriptionSystem.add_subscription(uid, d.get("type", "monthly"), ADMIN_ID, "web panel")
        if not ok:
            return jsonify(ok=False, error=res)
        end = res["end_date"][:16].replace("T", " ") if res["end_date"] else "مدى الحياة"
        _notify(uid, f"✅ تم تفعيل اشتراكك ({res['subscription_name']})\nينتهي: {end}", notify)
        audit("web", "grant", uid, d.get("type", ""))
        return jsonify(ok=True, message=f"تم منح اشتراك {res['subscription_name']}")
    if action == "extend":
        ok, msg = SubscriptionSystem.extend_subscription(uid, int(d.get("seconds", 0)), "web panel", ADMIN_ID)
        if ok:
            _notify(uid, f"✅ تم تمديد اشتراكك. {msg}", notify)
            audit("web", "extend", uid, str(d.get("seconds")))
        return jsonify(ok=ok, message=msg, error=None if ok else msg)
    if action == "revoke":
        ok, msg = SubscriptionSystem.revoke_subscription(uid, "web panel", ADMIN_ID)
        if ok:
            _notify(uid, f"⚠️ تم إلغاء اشتراكك. للتواصل: {Settings.get('support_username')}", notify)
            audit("web", "revoke", uid)
        return jsonify(ok=ok, message=msg, error=None if ok else msg)
    if action == "block":
        ok, msg = SubscriptionSystem.block_user(uid, str(d.get("reason") or "Blocked by admin")[:200], ADMIN_ID)
        if ok:
            audit("web", "block", uid, str(d.get("reason", "")))
        return jsonify(ok=ok, message=msg, error=None if ok else msg)
    if action == "unblock":
        ok, msg = SubscriptionSystem.unblock_user(uid, ADMIN_ID)
        audit("web", "unblock", uid)
        return jsonify(ok=ok, message=msg, error=None if ok else msg)
    if action == "message":
        text = str(d.get("text", "")).strip()
        if not text:
            return jsonify(ok=False, error="الرسالة فارغة")
        ok, err = send_telegram(uid, f"📩 رسالة من الإدارة:\n\n{text}")
        audit("web", "message", uid, text[:80])
        return jsonify(ok=ok, message="تم إرسال الرسالة" if ok else "", error=None if ok else f"فشل الإرسال: {err}")
    if action == "timezone":
        ok = set_user_timezone(uid, str(d.get("timezone", "")))
        audit("web", "timezone", uid, str(d.get("timezone", "")))
        return jsonify(ok=ok, message="تم تحديث المنطقة الزمنية", error=None if ok else "منطقة زمنية غير صالحة")
    return jsonify(ok=False, error="إجراء غير معروف"), 404


@app.post("/api/broadcast")
@api
def api_broadcast():
    d = _body()
    text = str(d.get("text", "")).strip()
    if not text:
        return jsonify(ok=False, error="نص الرسالة مطلوب")
    ok, msg = start_broadcast(text[:3500], d.get("audience", "active"), "web")
    return jsonify(ok=ok, message=msg, error=None if ok else msg)


@app.get("/api/broadcast/status")
@api
def api_broadcast_status():
    return jsonify(ok=True, broadcast=BROADCAST)


NUMERIC_SETTINGS = {"cooldown_seconds": (0, 600), "history_messages": (0, 20), "history_retention_hours": (1, 720),
                    "ai_temperature": (0, 1.5), "vision_max_tokens": (200, 4000), "chat_max_tokens": (200, 6000)}
BOOL_SETTINGS = {"maintenance", "auto_trial", "enforce_features"}


@app.get("/api/settings")
@api
def api_settings_get():
    return jsonify(ok=True, settings={k: Settings.get(k) for k in DEFAULT_SETTINGS})


@app.post("/api/settings")
@api
def api_settings_set():
    d = _body()
    changed = []
    for k, v in d.items():
        if k not in DEFAULT_SETTINGS:
            continue
        v = str(v).strip()
        if k in BOOL_SETTINGS:
            v = "1" if v in ("1", "true", "True") else "0"
        elif k in NUMERIC_SETTINGS:
            lo, hi = NUMERIC_SETTINGS[k]
            try:
                n = float(v)
            except ValueError:
                return jsonify(ok=False, error=f"قيمة غير صالحة: {k}")
            if not lo <= n <= hi:
                return jsonify(ok=False, error=f"{k} يجب أن تكون بين {lo} و {hi}")
        elif k.startswith("model_") and not re.fullmatch(r"[\w.\-:/]{1,80}", v):
            return jsonify(ok=False, error=f"اسم نموذج غير صالح: {k}")
        elif not v and k in ("support_username", "maintenance_message"):
            return jsonify(ok=False, error=f"الحقل مطلوب: {k}")
        Settings.set(k, v[:4000])
        changed.append(k)
    audit("web", "settings", "", ",".join(changed))
    return jsonify(ok=True, message=f"تم حفظ {len(changed)} إعداد")


@app.get("/api/prompts")
@api
def api_prompts():
    items = [{"key": k, "title": PROMPT_META[k][0], "desc": PROMPT_META[k][1], "value": get_prompt(k),
              "default": DEFAULT_PROMPTS[k], "custom": Settings.raw("prompt:" + k) is not None} for k in DEFAULT_PROMPTS]
    return jsonify(ok=True, items=items)


@app.post("/api/prompts")
@api
def api_prompts_save():
    d = _body()
    key, value = d.get("key"), str(d.get("value", "")).strip()
    if key not in DEFAULT_PROMPTS:
        return jsonify(ok=False, error="مفتاح غير معروف")
    if len(value) < 20 or len(value) > 30000:
        return jsonify(ok=False, error="طول البرومبت يجب أن يكون بين 20 و 30000 حرف")
    Settings.set("prompt:" + key, value)
    audit("web", "prompt_save", key, f"{len(value)} chars")
    return jsonify(ok=True, message="تم حفظ البرومبت وسيُطبق فوراً")


@app.post("/api/prompts/reset")
@api
def api_prompts_reset():
    key = _body().get("key")
    if key not in DEFAULT_PROMPTS:
        return jsonify(ok=False, error="مفتاح غير معروف")
    Settings.delete("prompt:" + key)
    audit("web", "prompt_reset", key)
    return jsonify(ok=True, message="تمت استعادة البرومبت الافتراضي", value=DEFAULT_PROMPTS[key])


@app.get("/api/logs")
@api
def api_logs():
    kind = request.args.get("type", "audit")
    if kind == "audit":
        with get_conn(DB_NAME) as c:
            rows = [dict(r) for r in c.execute("SELECT actor, action, target, details, ts FROM audit_log "
                                               "ORDER BY id DESC LIMIT 200").fetchall()]
        return jsonify(ok=True, rows=rows)
    lines = []
    if os.path.exists("bot.log"):
        with open("bot.log", "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-250:]
    return jsonify(ok=True, text="".join(lines))


@app.get("/api/backups")
@api
def api_backups():
    return jsonify(ok=True, items=DataProtection.list_backups())


@app.post("/api/backups/create")
@api
def api_backup_create():
    made = DataProtection.backup_all()
    audit("web", "backup_create", "", ",".join(made))
    return jsonify(ok=True, message=f"تم إنشاء {len(made)} نسخة")


@app.get("/api/backups/download/<name>")
@api
def api_backup_download(name):
    if not re.fullmatch(r"(main|subscription)_backup_\d{8}_\d{6}\.db", name):
        return jsonify(ok=False, error="اسم غير صالح"), 400
    p = os.path.join(BACKUP_DIR, name)
    if not os.path.exists(p):
        return jsonify(ok=False, error="الملف غير موجود"), 404
    return send_file(os.path.abspath(p), as_attachment=True, download_name=name)


@app.post("/api/backups/restore")
@api
def api_backup_restore():
    name = str(_body().get("name", ""))
    try:
        DataProtection.restore(name)
    except (ValueError, FileNotFoundError) as e:
        return jsonify(ok=False, error=str(e))
    Settings._ts = 0.0
    audit("web", "backup_restore", name)
    return jsonify(ok=True, message="تمت الاستعادة (أُنشئت نسخة أمان قبلها)")


@app.get("/api/export/users.csv")
@api
def api_export_csv():
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["user_id", "name", "username", "status", "subscription", "start", "end", "timezone", "created", "last_active"])
    for u in SubscriptionSystem.get_all_users():
        w.writerow([u["user_id"], u["name"], u["username"], u["status"], u["sub_name"], u["start_date"],
                    u["end_date"], u["timezone"], u["created_at"], u["last_active"]])
    audit("web", "export_csv")
    return Response("\ufeff" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=users.csv"})


@app.get("/api/export/data.json")
@api
def api_export_json():
    data = {"exported_at": datetime.now().isoformat(), "version": DATA_VERSION,
            "stats": SubscriptionSystem.get_stats(), "users": SubscriptionSystem.get_all_users()}
    return Response(json.dumps(data, ensure_ascii=False, indent=2, default=str), mimetype="application/json",
                    headers={"Content-Disposition": "attachment; filename=obeida_export.json"})


@app.post("/api/test_ai")
@api
def api_test_ai():
    t0 = time.time()
    try:
        ai_chat([{"role": "user", "content": "ping"}], Settings.get("model_chat"), 8, 0.0, 30, 0)
        return jsonify(ok=True, message=f"الاتصال ناجح ✅ ({int((time.time() - t0) * 1000)}ms)")
    except AIError as e:
        return jsonify(ok=False, error=f"فشل الاتصال: {e}")


@app.post("/api/password")
@api
def api_password():
    d = _body()
    if not check_password_hash(Settings.raw("admin_password_hash") or "", str(d.get("old", ""))):
        return jsonify(ok=False, error="كلمة المرور الحالية غير صحيحة")
    new = str(d.get("new", ""))
    if len(new) < 8:
        return jsonify(ok=False, error="كلمة المرور الجديدة يجب ألا تقل عن 8 أحرف")
    Settings.set("admin_password_hash", generate_password_hash(new))
    audit("web", "password_change")
    note = " (ملاحظة: ADMIN_PASSWORD في البيئة سيعيد ضبطها عند إعادة التشغيل)" if _env("ADMIN_PASSWORD") else ""
    return jsonify(ok=True, message="تم تغيير كلمة المرور" + note)


@app.get("/health")
@app.get("/ping")
def health():
    return jsonify(status="ok", bot=BOT_STATE["ok"], version=APP_VERSION)


# ── واجهات HTML ──
LOGIN_HTML = r"""<!DOCTYPE html>
<html dir="rtl" lang="ar"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>تسجيل الدخول — Obeida Trading</title>
<style>
*{box-sizing:border-box;margin:0;font-family:'Segoe UI',Tahoma,Arial,sans-serif}
body{min-height:100vh;display:grid;place-items:center;background:linear-gradient(135deg,#0f172a,#1e3a8a 60%,#4c1d95);padding:16px}
.card{background:#fff;border-radius:20px;padding:34px;width:100%;max-width:390px;box-shadow:0 20px 60px rgba(0,0,0,.35)}
.logo{font-size:3.2em;text-align:center}h1{text-align:center;color:#0f172a;margin:6px 0 4px}p.s{text-align:center;color:#64748b;font-size:.9em;margin-bottom:22px}
label{display:block;font-weight:600;color:#334155;margin:14px 0 6px;font-size:.92em}
input{width:100%;padding:12px;border:2px solid #e2e8f0;border-radius:10px;font-size:1em}input:focus{outline:0;border-color:#4f46e5}
button{width:100%;margin-top:22px;padding:13px;border:0;border-radius:10px;background:#4f46e5;color:#fff;font-size:1.05em;font-weight:700;cursor:pointer}
button:hover{background:#4338ca}button:disabled{opacity:.6}.err{background:#fee2e2;color:#991b1b;padding:10px;border-radius:10px;margin-bottom:6px;text-align:center;display:none}
</style></head><body><div class="card"><div class="logo">🤖</div><h1>Obeida Trading</h1><p class="s">لوحة تحكم البوت</p>
<div class="err" id="err"></div>
<label>👤 اسم المستخدم</label><input id="u" autocomplete="username" autofocus>
<label>🔑 كلمة المرور</label><input id="p" type="password" autocomplete="current-password">
<button id="b">تسجيل الدخول</button></div>
<script>
const $=id=>document.getElementById(id);
async function go(){const b=$('b');b.disabled=true;$('err').style.display='none';
try{const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:$('u').value,password:$('p').value})});
const d=await r.json();if(d.ok){location='/admin'}else{$('err').textContent=d.error||'خطأ';$('err').style.display='block'}}
catch(e){$('err').textContent='تعذر الاتصال';$('err').style.display='block'}b.disabled=false}
$('b').onclick=go;document.addEventListener('keydown',e=>{if(e.key==='Enter')go()});
</script></body></html>"""

ADMIN_HTML = r"""<!DOCTYPE html>
<html dir="rtl" lang="ar"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>لوحة التحكم — Obeida Trading</title>
<style>
:root{--bg:#f1f5f9;--card:#fff;--tx:#0f172a;--mu:#64748b;--bd:#e2e8f0;--pr:#4f46e5;--ok:#16a34a;--wa:#d97706;--er:#dc2626;--side:#0f172a}
@media(prefers-color-scheme:dark){:root{--bg:#0b1120;--card:#111a2e;--tx:#e2e8f0;--mu:#94a3b8;--bd:#1e293b;--side:#070b16}}
*{box-sizing:border-box;margin:0;font-family:'Segoe UI',Tahoma,Arial,sans-serif}
body{background:var(--bg);color:var(--tx);display:flex;min-height:100vh}
aside{width:230px;background:var(--side);color:#cbd5e1;padding:18px 12px;position:sticky;top:0;height:100vh;flex-shrink:0;overflow:auto}
aside h2{color:#fff;font-size:1.1em;margin:0 8px 4px}aside small{display:block;margin:0 8px 16px;color:#94a3b8}
aside a{display:block;padding:11px 12px;border-radius:10px;color:#cbd5e1;text-decoration:none;margin-bottom:4px;font-size:.95em}
aside a:hover{background:#1e293b}aside a.on{background:var(--pr);color:#fff}
main{flex:1;padding:22px;min-width:0}
.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px;flex-wrap:wrap;gap:10px}
h1{font-size:1.5em}h3{margin-bottom:12px}h4{margin:16px 0 8px}
.grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));margin-bottom:18px}
.card{background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:18px;margin-bottom:16px}
.grid .card{margin:0}.stat .n{font-size:2em;font-weight:800;color:var(--pr)}.stat .l{color:var(--mu);font-size:.9em}.stat .s{font-size:.8em;color:var(--ok)}
.muted{color:var(--mu)}.code{font-family:monospace;background:var(--bd);padding:2px 7px;border-radius:6px}
table{width:100%;border-collapse:collapse;font-size:.92em}th{background:var(--pr);color:#fff;padding:10px;text-align:center;white-space:nowrap}
td{padding:10px;border-bottom:1px solid var(--bd);text-align:center}tr.cl:hover{background:var(--bd);cursor:pointer}
.tw{overflow-x:auto;border-radius:10px;border:1px solid var(--bd)}
.badge{padding:3px 10px;border-radius:20px;font-size:.82em;font-weight:700;display:inline-block}
.b-active{background:#dcfce7;color:#166534}.b-expired{background:#fef3c7;color:#92400e}.b-blocked{background:#fee2e2;color:#991b1b}.b-none{background:var(--bd);color:var(--mu)}
.btn{padding:9px 16px;border:0;border-radius:9px;font-weight:700;cursor:pointer;background:var(--pr);color:#fff;font-size:.9em}
.btn:hover{opacity:.9}.btn.ok{background:var(--ok)}.btn.wa{background:var(--wa)}.btn.er{background:var(--er)}.btn.ghost{background:transparent;color:var(--tx);border:1px solid var(--bd)}
input,select,textarea{width:100%;padding:10px;border:2px solid var(--bd);border-radius:9px;background:var(--card);color:var(--tx);font-size:.95em}
input:focus,select:focus,textarea:focus{outline:0;border-color:var(--pr)}textarea{min-height:90px;resize:vertical;font-family:inherit}
textarea.big{min-height:340px;font-family:Consolas,monospace;font-size:.85em;direction:rtl}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:8px}.row>*{flex:1;min-width:120px}.row>.btn{flex:0 0 auto}
.f{margin-bottom:14px}.f label{display:block;font-weight:600;margin-bottom:5px;font-size:.92em}
.bar{display:grid;grid-template-columns:130px 1fr 50px;gap:8px;align-items:center;margin:7px 0;font-size:.88em}
.bar div{background:var(--bd);height:10px;border-radius:6px;overflow:hidden}.bar i{display:block;height:100%;background:var(--pr)}
#modal{position:fixed;inset:0;background:rgba(0,0,0,.55);display:none;align-items:center;justify-content:center;z-index:50;padding:14px}
#modal.on{display:flex}#modal .box{background:var(--card);border-radius:16px;padding:22px;width:100%;max-width:680px;max-height:90vh;overflow:auto}
.hd{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}
.g2{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:8px;margin-bottom:6px}.g2 div{background:var(--bg);padding:9px 12px;border-radius:9px;font-size:.9em}
#toast{position:fixed;bottom:20px;left:20px;padding:12px 20px;border-radius:10px;color:#fff;display:none;z-index:99;max-width:80vw}
#toast.ok{background:var(--ok)}#toast.err{background:var(--er)}
pre.log{background:#020617;color:#cbd5e1;padding:14px;border-radius:10px;max-height:520px;overflow:auto;font-size:.78em;direction:ltr;text-align:left;white-space:pre-wrap}
.tabs{display:flex;gap:8px;margin-bottom:12px}.pg{display:flex;gap:8px;justify-content:center;margin-top:12px;align-items:center}
@media(max-width:800px){body{flex-direction:column}aside{width:100%;height:auto;position:static;display:flex;flex-wrap:wrap;gap:4px}aside h2,aside small{width:100%}aside a{margin:0}}
</style></head><body>
<aside><h2>🤖 Obeida Trading</h2><small id="botinfo">…</small>
<a href="#dashboard">📊 لوحة المعلومات</a><a href="#users">👥 المستخدمون</a><a href="#broadcast">📢 الإذاعة</a>
<a href="#prompts">🧠 البرومبتات</a><a href="#settings">⚙️ إعدادات البوت</a><a href="#logs">📜 السجلات</a>
<a href="#backups">💾 النسخ الاحتياطي</a><a href="#security">🔐 الأمان</a></aside>
<main><div class="top"><h1 id="title"></h1><button class="btn er" onclick="logout()">تسجيل الخروج</button></div><div id="main"></div></main>
<div id="modal" onclick="if(event.target===this)closeModal()"></div><div id="toast"></div>
<script>
let CSRF='',TZ=[],TYPES={trial:'تجريبي',hourly:'ساعة',daily:'يوم',weekly:'أسبوع',monthly:'شهر',yearly:'سنة',lifetime:'مدى الحياة'};
const ST={active:'نشط',expired:'منتهي',blocked:'محظور',none:'بدون اشتراك'};
const FT={bot_access:'دخول البوت',chat_message:'رسائل الدردشة',photo_analysis:'تحليل صور',recommendation:'توصيات',chat_mode:'فتح الدردشة',recommendation_photo:'صور التوصيات'};
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,body,method){
 const r=await fetch(path,{method:method||(body!==undefined?'POST':'GET'),credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':CSRF},body:body!==undefined?JSON.stringify(body):undefined});
 if(r.status===401){location='/login';return}
 const d=await r.json().catch(()=>({ok:false,error:'استجابة غير صالحة'}));
 if(!d.ok)throw new Error(d.error||'خطأ');return d}
function toast(m,t){const e=$('#toast');e.textContent=m;e.className=t||'ok';e.style.display='block';clearTimeout(e._t);e._t=setTimeout(()=>e.style.display='none',3500)}
function modal(h){const m=$('#modal');m.innerHTML='<div class="box">'+h+'</div>';m.classList.add('on')}
function closeModal(){$('#modal').classList.remove('on')}
async function logout(){await api('/api/logout',{});location='/login'}
const bars=o=>{const v=Object.values(o);const mx=Math.max(1,...v);return Object.entries(o).map(([k,n])=>`<div class="bar"><span>${esc(FT[k]||k)}</span><div><i style="width:${n/mx*100}%"></i></div><b>${n}</b></div>`).join('')||'<div class="muted">لا توجد بيانات</div>'};
const badge=s=>`<span class="badge b-${s}">${ST[s]||s}</span>`;
const dt=s=>s?String(s).slice(0,16).replace('T',' '):'—';
const typeOpts=()=>Object.entries(TYPES).map(([k,v])=>`<option value="${k}">${v}</option>`).join('');
function setTitle(t){$('#title').textContent=t}

async function dashboard(){setTitle('📊 لوحة المعلومات');const d=await api('/api/dashboard'),s=d.stats,y=d.system;
 const pct=(a,b)=>b?Math.round(a/b*100)+'%':'0%';
 $('#main').innerHTML=`<div class="grid">
 <div class="card stat"><div class="l">👥 إجمالي المستخدمين</div><div class="n">${s.total_users}</div><div class="s">+${s.new_today} اليوم</div></div>
 <div class="card stat"><div class="l">✅ مشتركون نشطون</div><div class="n">${s.active_users}</div><div class="s">${pct(s.active_users,s.total_users)}</div></div>
 <div class="card stat"><div class="l">⌛ اشتراكات منتهية</div><div class="n">${s.expired_users}</div></div>
 <div class="card stat"><div class="l">🚫 محظورون</div><div class="n">${s.blocked_users}</div></div>
 <div class="card stat"><div class="l">⚡ إجمالي الاستخدام</div><div class="n">${s.total_usage}</div></div></div>
 <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(320px,1fr))">
 <div class="card"><h3>📈 أكثر الميزات استخداماً</h3>${bars(s.feature_usage)}</div>
 <div class="card"><h3>💎 الاشتراكات النشطة حسب النوع</h3>${bars(s.subscriptions_by_type)}</div>
 <div class="card"><h3>🆕 مستخدمون جدد (7 أيام)</h3>${bars(s.new_users_7d)}</div>
 <div class="card"><h3>🖥️ حالة النظام</h3><div class="g2">
 <div>🤖 البوت: ${y.bot.ok?'<b style=color:var(--ok)>يعمل</b> @'+esc(y.bot.username):'<b style=color:var(--er)>متوقف</b>'}</div>
 <div>🛠️ الصيانة: ${y.maintenance?'<b style=color:var(--wa)>مفعلة</b>':'متوقفة'}</div>
 <div>🧠 الذكاء الاصطناعي: ${y.ai_configured?'مهيأ ✅':'غير مهيأ ❌'}</div>
 <div>📸 سحب الشارت: ${y.screenshot_configured?'مهيأ ✅':'غير مهيأ (احتياطي نصي)'}</div>
 <div>🕒 وقت الخادم: ${esc(y.server_time)}</div><div>🐍 Python ${esc(y.python)} | v${esc(y.version)}</div>
 <div>🔬 نموذج الصور: <span class=code>${esc(y.models.vision)}</span></div><div>💬 نموذج الدردشة: <span class=code>${esc(y.models.chat)}</span></div></div>
 <div class="row" style="margin-top:10px"><button class="btn" onclick="testAI()">اختبار اتصال الذكاء الاصطناعي</button></div></div></div>`}
async function testAI(){try{const d=await api('/api/test_ai',{});toast(d.message)}catch(e){toast(e.message,'err')}}

let UQ={q:'',status:'',page:1};
async function users(){setTitle('👥 المستخدمون');
 $('#main').innerHTML=`<div class="card"><div class="row"><input id="uq" placeholder="🔍 بحث بالاسم أو المعرف أو اليوزر" value="${esc(UQ.q)}">
 <select id="us" style="max-width:180px"><option value="">كل الحالات</option>${Object.entries(ST).map(([k,v])=>`<option value="${k}" ${UQ.status===k?'selected':''}>${v}</option>`).join('')}</select>
 <button class="btn ok" onclick="addSub()">➕ إضافة اشتراك</button><a class="btn ghost" href="/api/export/users.csv" style="text-decoration:none;text-align:center">⬇️ CSV</a></div>
 <div class="tw"><table><thead><tr><th>المعرف</th><th>الاسم</th><th>اليوزر</th><th>الاشتراك</th><th>ينتهي</th><th>الحالة</th><th>آخر نشاط</th><th>المنطقة</th></tr></thead><tbody id="ub"></tbody></table></div><div class="pg" id="pg"></div></div>`;
 $('#uq').oninput=e=>{UQ.q=e.target.value;UQ.page=1;clearTimeout(window._ut);window._ut=setTimeout(loadUsers,300)};
 $('#us').onchange=e=>{UQ.status=e.target.value;UQ.page=1;loadUsers()};loadUsers()}
async function loadUsers(){const d=await api(`/api/users?q=${encodeURIComponent(UQ.q)}&status=${UQ.status}&page=${UQ.page}`);
 $('#ub').innerHTML=d.users.map(u=>`<tr class="cl" onclick="openUser(${u.user_id})"><td><span class=code>${u.user_id}</span></td><td>${esc(u.name)}</td><td>${u.username?'@'+esc(u.username):'—'}</td><td>${esc(u.sub_name||'—')}</td><td>${u.end_date?dt(u.end_date):(u.sub_name?'∞':'—')}</td><td>${badge(u.status)}</td><td>${dt(u.last_active)}</td><td>${esc(u.timezone)}</td></tr>`).join('')||'<tr><td colspan=8 class=muted>لا توجد نتائج</td></tr>';
 const pages=Math.max(1,Math.ceil(d.total/d.per));$('#pg').innerHTML=`<button class="btn ghost" ${UQ.page<=1?'disabled':''} onclick="UQ.page--;loadUsers()">السابق</button><span>صفحة ${UQ.page} من ${pages} (${d.total})</span><button class="btn ghost" ${UQ.page>=pages?'disabled':''} onclick="UQ.page++;loadUsers()">التالي</button>`}
function addSub(){modal(`<div class="hd"><h3>➕ إضافة اشتراك</h3><button class="btn ghost" onclick="closeModal()">✕</button></div>
 <div class="f"><label>معرّف المستخدم (User ID)</label><input id="a_id" type="number" placeholder="123456789"></div>
 <div class="f"><label>نوع الاشتراك</label><select id="a_t">${typeOpts()}</select></div>
 <div class="f"><label><input type="checkbox" id="a_n" checked style="width:auto"> إشعار المستخدم عبر تليجرام</label></div>
 <button class="btn ok" onclick="doAdd()">تفعيل</button>`)}
async function doAdd(){try{const d=await api('/api/users/add',{user_id:+$('#a_id').value,type:$('#a_t').value,notify:$('#a_n').checked});toast(d.message);closeModal();if(location.hash==='#users')loadUsers()}catch(e){toast(e.message,'err')}}
async function userAct(id,action,body,conf){if(conf&&!confirm(conf))return;try{const d=await api(`/api/users/${id}/${action}`,body||{});toast(d.message||'تم');openUser(id);if(location.hash==='#users')loadUsers()}catch(e){toast(e.message,'err')}}
async function openUser(id){if(!TZ.length)TZ=(await api('/api/timezones')).items;const d=await api('/api/users/'+id),u=d.user;
 modal(`<div class="hd"><h3>👤 ${esc(u.name)} <span class=code>${u.user_id}</span></h3><button class="btn ghost" onclick="closeModal()">✕</button></div>
 <div class="g2"><div>الحالة: ${badge(u.status)}</div><div>الاشتراك: <b>${esc(u.sub_name||'—')}</b></div><div>ينتهي: ${u.end_date?dt(u.end_date):(u.sub_name?'∞':'—')}</div><div>المتبقي: ${esc(u.remaining)}</div>
 <div>اليوزر: ${u.username?'@'+esc(u.username):'—'}</div><div>انضم: ${dt(u.created_at)}</div><div>آخر نشاط: ${dt(u.last_active)}</div><div>المنطقة: ${esc(u.timezone)}</div>
 <div>الشموع: ${esc(u.candle)}</div><div>الاستراتيجية: ${esc(u.trade_time)}</div><div>الصلاحيات: ${esc(u.permissions.join(', ')||'—')}</div>${u.blocked?`<div>سبب الحظر: ${esc(u.blocked_reason||'—')}</div>`:''}</div>
 <div class="g2">${Object.entries(u.usage).map(([k,v])=>`<div>${esc(FT[k]||k)}: <b>${v}</b></div>`).join('')}</div>
 <h4>💎 منح / تغيير اشتراك</h4><div class="row"><select id="g_t">${typeOpts()}</select><button class="btn ok" onclick="userAct(${id},'grant',{type:$('#g_t').value})">منح</button></div>
 <h4>⏱️ تمديد</h4><div class="row"><select id="e_s"><option value="3600">ساعة</option><option value="86400" selected>يوم</option><option value="604800">أسبوع</option><option value="2592000">شهر</option><option value="31536000">سنة</option></select><button class="btn" onclick="userAct(${id},'extend',{seconds:+$('#e_s').value})">تمديد</button>
 <button class="btn wa" onclick="userAct(${id},'revoke',{},'إلغاء الاشتراك؟')">إلغاء الاشتراك</button></div>
 <h4>🚫 الحظر</h4><div class="row"><input id="b_r" placeholder="سبب الحظر (اختياري)">${u.blocked?`<button class="btn ok" onclick="userAct(${id},'unblock')">إلغاء الحظر</button>`:`<button class="btn er" onclick="userAct(${id},'block',{reason:$('#b_r').value},'حظر المستخدم؟')">حظر</button>`}</div>
 <h4>🌍 المنطقة الزمنية</h4><div class="row"><select id="z_t">${TZ.map(([k,v])=>`<option value="${esc(v)}" ${v===u.timezone?'selected':''}>${esc(k)} — ${esc(v)}</option>`).join('')}</select><button class="btn" onclick="userAct(${id},'timezone',{timezone:$('#z_t').value})">حفظ</button></div>
 <h4>📩 رسالة مباشرة</h4><textarea id="m_t" placeholder="اكتب رسالة تصل للمستخدم في تليجرام"></textarea><div class="row"><button class="btn" onclick="userAct(${id},'message',{text:$('#m_t').value})">إرسال</button></div>
 <h4>🧾 سجل الاشتراكات</h4><div class="tw"><table><thead><tr><th>الإجراء</th><th>من</th><th>إلى</th><th>السبب</th><th>التاريخ</th></tr></thead><tbody>${u.history.map(h=>`<tr><td>${esc(h.action)}</td><td>${esc(h.old_subscription||'—')}</td><td>${esc(h.new_subscription||'—')}</td><td>${esc(h.reason||'—')}</td><td>${dt(h.performed_at)}</td></tr>`).join('')||'<tr><td colspan=5 class=muted>لا يوجد</td></tr>'}</tbody></table></div>`)}

let BT=null;
async function broadcast(){setTitle('📢 الإذاعة');
 $('#main').innerHTML=`<div class="card"><div class="f"><label>الفئة المستهدفة</label><select id="bc_a"><option value="active">المشتركون النشطون</option><option value="expired">المنتهية اشتراكاتهم</option><option value="all">جميع المستخدمين (عدا المحظورين)</option></select></div>
 <div class="f"><label>نص الرسالة (نص عادي)</label><textarea id="bc_t" style="min-height:160px" placeholder="اكتب الرسالة..."></textarea></div>
 <button class="btn ok" onclick="doBc()">📤 إرسال الإذاعة</button></div><div class="card" id="bc_s"></div>`;bcStatus()}
async function doBc(){if(!confirm('إرسال الإذاعة الآن؟'))return;try{const d=await api('/api/broadcast',{text:$('#bc_t').value,audience:$('#bc_a').value});toast(d.message);bcStatus()}catch(e){toast(e.message,'err')}}
async function bcStatus(){clearTimeout(BT);if(location.hash!=='#broadcast')return;const b=(await api('/api/broadcast/status')).broadcast;
 const done=b.sent+b.failed;$('#bc_s').innerHTML=b.started?`<h3>حالة آخر إذاعة ${b.running?'⏳ جارية':'✅ منتهية'}</h3><div class="bar" style="grid-template-columns:90px 1fr 70px"><span>التقدم</span><div><i style="width:${b.total?done/b.total*100:0}%"></i></div><b>${done}/${b.total}</b></div><div class="g2"><div>✅ نجحت: ${b.sent}</div><div>❌ فشلت: ${b.failed}</div><div>بدأت: ${esc(b.started)}</div><div>انتهت: ${esc(b.finished||'—')}</div></div>`:'<span class=muted>لا توجد إذاعات بعد.</span>';
 if(b.running)BT=setTimeout(bcStatus,2000)}

async function prompts(){setTitle('🧠 البرومبتات');const d=await api('/api/prompts');
 $('#main').innerHTML='<div class="card muted">عدّل البرومبتات هنا وستُطبَّق فوراً دون إعادة تشغيل. حافظ على المتغيرات بين الأقواس {} كما هي.</div>'+d.items.map(p=>`<div class="card"><div class="hd"><h3>${esc(p.title)} ${p.custom?'<span class="badge b-active">معدّل</span>':'<span class="badge b-none">افتراضي</span>'}</h3></div>
 <div class="muted" style="font-size:.82em;margin-bottom:8px;direction:ltr;text-align:left">${esc(p.desc)}</div><textarea class="big" id="pr_${p.key}">${esc(p.value)}</textarea>
 <div class="row" style="margin-top:8px"><button class="btn ok" onclick="savePrompt('${p.key}')">💾 حفظ</button><button class="btn wa" onclick="resetPrompt('${p.key}')">↩️ استعادة الافتراضي</button></div></div>`).join('')}
async function savePrompt(k){try{const d=await api('/api/prompts',{key:k,value:$('#pr_'+k).value});toast(d.message);prompts()}catch(e){toast(e.message,'err')}}
async function resetPrompt(k){if(!confirm('استعادة النسخة الافتراضية؟'))return;try{const d=await api('/api/prompts/reset',{key:k});toast(d.message);prompts()}catch(e){toast(e.message,'err')}}

const FIELDS=[['maintenance','🛠️ وضع الصيانة (يمنع غير المشرف)','bool'],['maintenance_message','رسالة الصيانة','area'],['welcome_message','رسالة ترحيب إضافية (اختياري)','area'],
['support_username','حساب الدعم (@username)','text'],['prices','نص الأسعار','area'],['auto_trial','🎁 تجربة مجانية (24 ساعة) تلقائية للمستخدم الجديد','bool'],
['enforce_features','🔒 تقييد الميزات حسب نوع الاشتراك (ساعة/تجريبي: تحليل فقط، يوم: + دردشة، أسبوع+: + توصيات)','bool'],
['cooldown_seconds','فاصل (ثوانٍ) بين طلبات الذكاء الاصطناعي لكل مستخدم','num'],['history_messages','عدد رسائل ذاكرة الدردشة','num'],['history_retention_hours','مدة حفظ سجل الدردشة (ساعات)','num'],
['model_vision','نموذج تحليل الصور','text'],['model_audit','نموذج التوصية النصية','text'],['model_chat','نموذج الدردشة','text'],
['ai_temperature','حرارة الدردشة (0 - 1.5)','num'],['vision_max_tokens','أقصى طول للتحليل (tokens)','num'],['chat_max_tokens','أقصى طول لرد الدردشة (tokens)','num']];
async function settings(){setTitle('⚙️ إعدادات البوت');const s=(await api('/api/settings')).settings;
 $('#main').innerHTML='<div class="card">'+FIELDS.map(([k,l,t])=>`<div class="f"><label>${l}</label>`+(t==='bool'?`<select id="s_${k}"><option value="0" ${s[k]!=='1'?'selected':''}>متوقف</option><option value="1" ${s[k]==='1'?'selected':''}>مفعّل</option></select>`:t==='area'?`<textarea id="s_${k}">${esc(s[k])}</textarea>`:`<input id="s_${k}" type="${t==='num'?'number':'text'}" step="any" value="${esc(s[k])}">`)+'</div>').join('')+'<button class="btn ok" onclick="saveSettings()">💾 حفظ الإعدادات</button></div>'}
async function saveSettings(){const b={};FIELDS.forEach(([k])=>b[k]=$('#s_'+k).value);try{const d=await api('/api/settings',b);toast(d.message)}catch(e){toast(e.message,'err')}}

async function logs(){setTitle('📜 السجلات');$('#main').innerHTML='<div class="tabs"><button class="btn" onclick="logTab(\'audit\')">سجل الإجراءات</button><button class="btn ghost" onclick="logTab(\'app\')">سجل التطبيق</button></div><div id="lg"></div>';logTab('audit')}
async function logTab(t){const d=await api('/api/logs?type='+t);$('#lg').innerHTML=t==='audit'?`<div class="tw"><table><thead><tr><th>الوقت (UTC)</th><th>المنفّذ</th><th>الإجراء</th><th>الهدف</th><th>تفاصيل</th></tr></thead><tbody>${d.rows.map(r=>`<tr><td>${esc(r.ts)}</td><td>${esc(r.actor)}</td><td>${esc(r.action)}</td><td>${esc(r.target)}</td><td>${esc(r.details)}</td></tr>`).join('')||'<tr><td colspan=5 class=muted>لا يوجد</td></tr>'}</tbody></table></div>`:`<pre class="log">${esc(d.text||'لا يوجد سجل')}</pre>`}

async function backups(){setTitle('💾 النسخ الاحتياطي');const d=await api('/api/backups');
 $('#main').innerHTML=`<div class="card"><div class="row"><button class="btn ok" onclick="mkBackup()">➕ إنشاء نسخة احتياطية الآن</button><a class="btn ghost" href="/api/export/data.json" style="text-decoration:none">⬇️ تصدير JSON</a></div><p class="muted">تُنشأ نسخة تلقائية كل ساعة (آخر 30 نسخة).</p></div>
 <div class="card"><div class="tw"><table><thead><tr><th>الملف</th><th>التاريخ</th><th>الحجم</th><th>إجراءات</th></tr></thead><tbody>${d.items.map(b=>`<tr><td class=code>${esc(b.name)}</td><td>${esc(b.date)}</td><td>${b.size} KB</td><td><a class="btn" style="text-decoration:none" href="/api/backups/download/${encodeURIComponent(b.name)}">تحميل</a> <button class="btn er" onclick="restore('${esc(b.name)}')">استعادة</button></td></tr>`).join('')||'<tr><td colspan=4 class=muted>لا توجد نسخ</td></tr>'}</tbody></table></div></div>`}
async function mkBackup(){try{const d=await api('/api/backups/create',{});toast(d.message);backups()}catch(e){toast(e.message,'err')}}
async function restore(n){if(!confirm('سيتم استبدال البيانات الحالية بهذه النسخة (مع نسخة أمان قبلها). متابعة؟'))return;try{const d=await api('/api/backups/restore',{name:n});toast(d.message);backups()}catch(e){toast(e.message,'err')}}

async function security(){setTitle('🔐 الأمان');
 $('#main').innerHTML=`<div class="card" style="max-width:480px"><h3>تغيير كلمة المرور</h3><div class="f"><label>الحالية</label><input id="pw0" type="password"></div><div class="f"><label>الجديدة (8 أحرف فأكثر)</label><input id="pw1" type="password"></div><button class="btn ok" onclick="chPw()">تغيير</button></div>
 <div class="card muted">🔒 الجلسة صالحة 12 ساعة، وتُحجب محاولات الدخول بعد 5 محاولات فاشلة لمدة 10 دقائق. كل إجراء إداري يُسجَّل في «السجلات».</div>`}
async function chPw(){try{const d=await api('/api/password',{old:$('#pw0').value,new:$('#pw1').value});toast(d.message);$('#pw0').value='';$('#pw1').value=''}catch(e){toast(e.message,'err')}}

const views={dashboard,users,broadcast,prompts,settings,logs,backups,security};
async function route(){const v=(location.hash||'#dashboard').slice(1);document.querySelectorAll('aside a').forEach(a=>a.classList.toggle('on',a.getAttribute('href')==='#'+v));
 $('#main').innerHTML='<div class="muted">جارٍ التحميل…</div>';try{await(views[v]||dashboard)()}catch(e){toast(e.message,'err')}}
(async()=>{try{const s=await api('/api/session');CSRF=s.csrf;$('#botinfo').textContent=(s.bot.username?'@'+s.bot.username:'البوت')+' • v'+s.version}catch(e){location='/login';return}
 window.addEventListener('hashchange',route);route()})();
</script></body></html>"""


def run_flask_server() -> None:
    try:
        from waitress import serve
        log.info("🌐 Web panel (waitress) on port %s", PORT)
        serve(app, host="0.0.0.0", port=PORT, threads=8)
    except ImportError:
        log.info("🌐 Web panel (flask dev server) on port %s — يُفضّل: pip install waitress", PORT)
        app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False, threaded=True)


# ════════════════════════════════════════════════════════════
# 21) التشغيل
# ════════════════════════════════════════════════════════════
def build_application() -> Application:
    application = Application.builder().token(TOKEN).concurrent_updates(True).post_init(post_init).build()
    text_filter = filters.TEXT & ~filters.COMMAND
    image_filter = filters.PHOTO | filters.Document.IMAGE
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start),
                      MessageHandler(text_filter, handle_main_menu),
                      MessageHandler(image_filter, handle_photo_analysis)],
        states={
            MAIN_MENU: [MessageHandler(text_filter, handle_main_menu), MessageHandler(image_filter, handle_photo_analysis)],
            SETTINGS_CANDLE: [MessageHandler(text_filter, handle_settings_candle)],
            SETTINGS_TIME: [MessageHandler(text_filter, handle_settings_time)],
            CHAT_MODE: [MessageHandler(text_filter, handle_chat_message)],
            ANALYZE_MODE: [MessageHandler(text_filter, handle_analyze_mode),
                           MessageHandler(image_filter, handle_photo_analysis)],
            RECOMMENDATION_MODE: [MessageHandler(text_filter, handle_recommendation_selection),
                                  MessageHandler(image_filter, handle_recommendation_photo)],
            CATEGORY_SELECTION: [MessageHandler(text_filter, handle_recommendation_selection),
                                 MessageHandler(image_filter, handle_recommendation_photo)],
            ADMIN_MENU: [MessageHandler(text_filter, handle_admin_menu)],
            ADMIN_INPUT: [MessageHandler(text_filter, handle_admin_input)],
            COUNTRY_SELECTION: [MessageHandler(text_filter, handle_country_selection)],
        },
        fallbacks=[CommandHandler("start", start), CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    application.add_handler(CommandHandler("id", cmd_id))
    application.add_handler(CommandHandler("me", cmd_me))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(conv)
    application.add_error_handler(error_handler)
    return application


def main() -> None:
    if not TOKEN:
        sys.exit("❌ متغير البيئة TOKEN غير مضبوط. ضع توكن البوت ثم أعد التشغيل.")
    if not AI_KEY:
        log.warning("⚠️ AI_KEY غير مضبوط — ميزات التحليل والدردشة لن تعمل حتى تضبطه.")
    log.info("🤖 Starting %s v%s", BRAND, APP_VERSION)
    init_main_db()
    SubscriptionSystem.init_db()
    init_web_security()
    try:
        DataProtection.backup_all()
    except Exception as e:
        log.warning("initial backup failed: %s", e)
    for fn in os.listdir(IMAGE_CACHE_DIR):
        try:
            os.remove(os.path.join(IMAGE_CACHE_DIR, fn))
        except OSError:
            pass
    threading.Thread(target=run_flask_server, daemon=True).start()
    log.info("🌐 Admin panel: %s/admin", PUBLIC_URL or f"http://localhost:{PORT}")
    build_application().run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
