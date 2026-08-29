# -*- coding: utf-8 -*-
"""
nova_db.py
====================================================================
لایه‌ی دیتابیس NovaSelf: اتصال Postgres، مدیریت کاربران، اقتصاد الماس،
سفارش‌ها، لاگ‌های ادمین، ذخیره‌سازیِ ریکت/پاسخ‌خودکار/قفلِ قابلیت‌ها/
کانال‌های جوین‌اجباری، سیستم بکاپ کامل، و بررسیِ زنده‌ی عضویت در
کانال‌های جوین اجباری (که به هیچ دیتابیسی متکی نیست، هر بار مستقیم از
تلگرام می‌پرسد).

این فایل عمداً هیچ تابع سازنده‌ی متن/دکمه (UI) ندارد؛ آن‌ها در
nova_menus.py هستند و از اینجا فقط تابع‌های خواندن/نوشتنِ دیتابیس را
Import می‌کنند - نه برعکس (این فایل هرگز از nova_menus وارد نمی‌کند).
====================================================================
"""

import json
import base64
import pickle
import secrets
import string
import logging
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import DictCursor
from telethon.errors import UserNotParticipantError
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.types import ChannelParticipantLeft, ChannelParticipantBanned

from nova_utils import log_internal_error
from nova_state import (
    bot, DATABASE_URL, join_channels_cache, is_admin, tehran_now,
    DIAMOND_RATE_PER_HOUR, MEOW_INTERVAL_SECONDS, FISH_INTERVAL_SECONDS,
    MEOWPOINT_INTERVAL_SECONDS, FRIDGE_INTERVAL_SECONDS,
    reaction_targets, autoreply_cache, feature_locks,
    format_diamonds,
)

# ======================== مدیریت دیتابیس ========================
def get_db_connection():
    """
    اتصال جدید به Postgres. بلافاصله بعد از اتصال، Timezone نشست روی Asia/Tehran
    تنظیم می‌شود تا مقادیر CURRENT_TIMESTAMP/NOW() که در ستون‌های TIMESTAMP (بدون
    Timezone) ذخیره می‌شوند، بر حسب ساعت تهران محاسبه شوند — نه ساعت سرور (که روی
    Railway معمولاً UTC است). این باگِ «تایم/تاریخ اشتباه در بعضی قسمت‌ها» را حل می‌کند.
    """
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    try:
        with conn.cursor() as cursor:
            cursor.execute("SET TIME ZONE 'Asia/Tehran'")
        conn.commit()
    except Exception as e:
        logging.error(f"⚠️ خطا در تنظیم Timezone اتصال دیتابیس: {e}")
    return conn

def init_db():
    """ایجاد جدول و افزودن ستون‌های جدید در صورت نیاز (idempotent و امن برای ری‌استارت)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS novaself_users (
                user_id BIGINT PRIMARY KEY,
                session TEXT,
                font_id INTEGER DEFAULT 1,
                status INTEGER DEFAULT 0,
                name_time INTEGER DEFAULT 1,
                bio_time INTEGER DEFAULT 0,
                active_action TEXT DEFAULT 'none',
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

        migration_columns = [
            ("date_enabled", "INTEGER DEFAULT 0"),
            ("date_type", "TEXT DEFAULT 'shamsi'"),
            ("date_font", "INTEGER DEFAULT 1"),
            ("text_mode", "INTEGER DEFAULT 0"),
            ("secretary_enabled", "INTEGER DEFAULT 0"),
            ("secretary_text", "TEXT DEFAULT 'مشغولم، بعداً پاسخ می‌دهم ✅'"),
            ("secretary_delay", "INTEGER DEFAULT 60"),
            ("secretary_entities", "BYTEA"),
            ("secretary_media_kind", "TEXT"),
            ("secretary_media_bytes", "BYTEA"),
            ("secretary_media_filename", "TEXT"),
            ("secretary_media_mime", "TEXT"),
            ("diamonds", "DOUBLE PRECISION DEFAULT 0"),
            ("referral_count", "INTEGER DEFAULT 0"),
            ("username", "TEXT"),
            ("last_charge_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("meow_enabled", "INTEGER DEFAULT 0"),
            ("meow_chat_id", "BIGINT"),
            ("meow_last_sent_at", "TIMESTAMP"),
            ("meow_interval_seconds", "INTEGER DEFAULT 320"),
            ("fish_enabled", "INTEGER DEFAULT 0"),
            ("fish_last_run_at", "TIMESTAMP"),
            ("fish_interval_seconds", "INTEGER DEFAULT 3610"),
            ("meowpoint_enabled", "INTEGER DEFAULT 0"),
            ("meowpoint_interval_seconds", "INTEGER DEFAULT 2700"),
            ("meowpoint_last_run_at", "TIMESTAMP"),
            ("streetcat_enabled", "INTEGER DEFAULT 0"),
            ("fridge_enabled", "INTEGER DEFAULT 0"),
            ("fridge_interval_seconds", "INTEGER DEFAULT 1800"),
            ("fridge_last_run_at", "TIMESTAMP"),
            ("fish_operation_common", "TEXT DEFAULT 'feed'"),
            ("fish_operation_rare", "TEXT DEFAULT 'feed'"),
            ("fish_operation_epic", "TEXT DEFAULT 'feed'"),
            ("fish_operation_legendary", "TEXT DEFAULT 'fridge'"),
            ("meow_chat_title", "TEXT"),
            ("reaction_enabled", "BOOLEAN DEFAULT FALSE"),
            ("autoreply_enabled", "BOOLEAN DEFAULT FALSE"),
            ("autoreply_match_type", "TEXT DEFAULT 'exact'"),
            ("autoseen_enabled", "BOOLEAN DEFAULT FALSE"),
        ]
        for col_name, col_def in migration_columns:
            try:
                cursor.execute(f"ALTER TABLE novaself_users ADD COLUMN IF NOT EXISTS {col_name} {col_def}")
                conn.commit()
            except Exception as e:
                conn.rollback()
                logging.error(f"❌ خطا در افزودن ستون {col_name}: {e}")

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS novaself_admin_logs (
                id SERIAL PRIMARY KEY,
                admin_id BIGINT,
                target_id BIGINT,
                action TEXT,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS novaself_gift_codes (
                code TEXT PRIMARY KEY,
                diamonds DOUBLE PRECISION NOT NULL,
                is_active INTEGER DEFAULT 1,
                expires_at TIMESTAMP,
                created_by BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS novaself_gift_code_uses (
                code TEXT REFERENCES novaself_gift_codes(code) ON DELETE CASCADE,
                user_id BIGINT,
                used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (code, user_id)
            )
        ''')
        conn.commit()

        # ---------- سفارش‌های خرید الماس (بخش خرید الماس / کارت‌به‌کارت) ----------
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS novaself_orders (
                order_id TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                username TEXT,
                amount_diamonds DOUBLE PRECISION NOT NULL,
                amount_toman BIGINT NOT NULL,
                payment_method TEXT DEFAULT 'card_to_card',
                status TEXT DEFAULT 'invoice',
                receipt_chat_id BIGINT,
                receipt_message_id BIGINT,
                receipt_file_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                approved_at TIMESTAMP,
                approved_by BIGINT,
                rejected_at TIMESTAMP,
                rejected_by BIGINT,
                rejection_reason TEXT
            )
        ''')
        conn.commit()

        # ---------- لاگ پیام‌های ارسالی ادمین (تکی/همگانی) برای مدیریت/حذف بعدی ----------
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS novaself_broadcasts (
                broadcast_id TEXT PRIMARY KEY,
                admin_id BIGINT,
                kind TEXT,
                target_id BIGINT,
                summary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS novaself_broadcast_deliveries (
                id SERIAL PRIMARY KEY,
                broadcast_id TEXT REFERENCES novaself_broadcasts(broadcast_id) ON DELETE CASCADE,
                user_id BIGINT,
                chat_id BIGINT,
                message_id BIGINT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

        # ---------- قابلیت ریکت (بند ۳-۴) ----------
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS novaself_reactions (
                owner_id BIGINT NOT NULL,
                target_user_id BIGINT NOT NULL,
                target_username TEXT,
                emoji TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (owner_id, target_user_id)
            )
        ''')
        conn.commit()

        # ---------- قابلیت پاسخ خودکار (بند ۵-۱۰) ----------
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS novaself_autoreplies (
                id SERIAL PRIMARY KEY,
                owner_id BIGINT NOT NULL,
                local_id INTEGER NOT NULL,
                trigger_text TEXT NOT NULL,
                response_text TEXT,
                response_entities BYTEA,
                response_media_kind TEXT,
                response_media_bytes BYTEA,
                response_media_filename TEXT,
                response_media_mime TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (owner_id, local_id)
            )
        ''')
        conn.commit()

        # ---------- قفل کردن قابلیت‌ها توسط ادمین ----------
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS novaself_feature_locks (
                user_id BIGINT NOT NULL,
                feature_key TEXT NOT NULL,
                locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, feature_key)
            )
        ''')
        conn.commit()

        # ---------- جوین اجباری ----------
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS novaself_join_channels (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                identifier TEXT NOT NULL,
                invite_link TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

        # توجه: جدول novaself_join_verified قبلاً اینجا ساخته می‌شد تا عضویتِ
        # تأییدشده‌ی هر کاربر برای همیشه ذخیره شود. طبق درخواست صریح، این کش/جدول
        # دیگر استفاده نمی‌شود: عضویت باید هر بار به‌صورت زنده از تلگرام چک شود
        # (نه یک‌بار برای همیشه)، وگرنه کاربری که بعداً کانال را ترک کند همچنان
        # به‌اشتباه «تأییدشده» باقی می‌ماند.

        # ---------- تنظیماتِ سراسری (Key-Value، برای مقادیری مثل جایزه/فعال‌بودنِ Referral) ----------
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS novaself_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        conn.commit()

        # ---------- سیستم Referral ----------
        # referred_id به‌عنوان PRIMARY KEY یعنی هر کاربر فقط دقیقاً یک بار (و فقط
        # با یک دعوت‌کننده) می‌تواند رفرال شود - از ثبت چندباره یا تغییر مصنوعیِ
        # دعوت‌کننده در سطح خودِ دیتابیس جلوگیری می‌کند (نه فقط در سطح کد).
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS novaself_referrals (
                referred_id BIGINT PRIMARY KEY,
                referrer_id BIGINT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reward_credited BOOLEAN DEFAULT FALSE,
                reward_amount DOUBLE PRECISION DEFAULT 0,
                credited_at TIMESTAMP
            )
        ''')
        conn.commit()

        # ---------- سیستم بکاپ ----------
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS novaself_backups (
                id SERIAL PRIMARY KEY,
                created_by BIGINT,
                label TEXT,
                size_bytes INTEGER,
                data BYTEA,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

        logging.info("✅ دیتابیس با موفقیت راه‌اندازی/بروزرسانی شد.")
        cursor.close()
        conn.close()
    except Exception as e:
        logging.error(f"❌ خطا در راه‌اندازی دیتابیس: {e}")

def get_all_users():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)

        cursor.execute("""
            SELECT user_id, session, font_id, status, name_time, bio_time, active_action,
                   joined_at, date_enabled, date_type, date_font, text_mode,
                   secretary_enabled, secretary_text, secretary_delay,
                   secretary_entities, secretary_media_kind, secretary_media_bytes,
                   secretary_media_filename, secretary_media_mime,
                   diamonds, referral_count, username, last_charge_at,
                   meow_enabled, meow_chat_id, meow_last_sent_at, meow_interval_seconds,
                   fish_enabled, fish_last_run_at, fish_interval_seconds,
                   meowpoint_enabled, meowpoint_interval_seconds, meowpoint_last_run_at,
                   streetcat_enabled,
                   fridge_enabled, fridge_interval_seconds, fridge_last_run_at,
                   fish_operation_common, fish_operation_rare, fish_operation_epic, fish_operation_legendary,
                   meow_chat_title, reaction_enabled, autoreply_enabled, autoreply_match_type,
                   autoseen_enabled
            FROM novaself_users
            ORDER BY joined_at DESC
        """)

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        data = {}
        for row in rows:
            user_id = row['user_id']
            secretary_entities = None
            if row['secretary_entities']:
                try:
                    secretary_entities = pickle.loads(bytes(row['secretary_entities']))
                except Exception as e:
                    logging.error(f"❌ خطا در بازخوانیِ Entityهای منشیِ کاربر {user_id}: {e}")
            secretary_media_bytes = bytes(row['secretary_media_bytes']) if row['secretary_media_bytes'] else None

            data[user_id] = {
                "session": row['session'],
                "font_id": row['font_id'] if row['font_id'] is not None else 1,
                "status": bool(row['status']),
                "name_time": bool(row['name_time']),
                "bio_time": bool(row['bio_time']),
                "active_action": row['active_action'] or "none",
                "date_enabled": bool(row['date_enabled']) if row['date_enabled'] is not None else False,
                "date_type": row['date_type'] or "shamsi",
                "date_font": row['date_font'] if row['date_font'] is not None else 1,
                "text_mode": row['text_mode'] if row['text_mode'] is not None else 0,
                "secretary_enabled": bool(row['secretary_enabled']) if row['secretary_enabled'] is not None else False,
                "secretary_text": row['secretary_text'] or "مشغولم، بعداً پاسخ می‌دهم ✅",
                "secretary_delay": row['secretary_delay'] if row['secretary_delay'] is not None else 60,
                "secretary_entities": secretary_entities,
                "secretary_media_kind": row['secretary_media_kind'],
                "secretary_media_bytes": secretary_media_bytes,
                "secretary_media_filename": row['secretary_media_filename'],
                "secretary_media_mime": row['secretary_media_mime'],
                "diamonds": float(row['diamonds']) if row['diamonds'] is not None else 0.0,
                "referral_count": row['referral_count'] if row['referral_count'] is not None else 0,
                "username": row['username'],
                "last_charge_at": row['last_charge_at'] or tehran_now(),
                "joined_at": row['joined_at'] or tehran_now(),
                "meow_enabled": bool(row['meow_enabled']) if row['meow_enabled'] is not None else False,
                "meow_chat_id": row['meow_chat_id'],
                "meow_last_sent_at": row['meow_last_sent_at'],
                "meow_interval_seconds": row['meow_interval_seconds'] if row['meow_interval_seconds'] else MEOW_INTERVAL_SECONDS,
                "fish_enabled": bool(row['fish_enabled']) if row['fish_enabled'] is not None else False,
                "fish_last_run_at": row['fish_last_run_at'],
                "fish_interval_seconds": row['fish_interval_seconds'] if row['fish_interval_seconds'] else FISH_INTERVAL_SECONDS,
                "meowpoint_enabled": bool(row['meowpoint_enabled']) if row['meowpoint_enabled'] is not None else False,
                "meowpoint_interval_seconds": row['meowpoint_interval_seconds'] if row['meowpoint_interval_seconds'] else MEOWPOINT_INTERVAL_SECONDS,
                "meowpoint_last_run_at": row['meowpoint_last_run_at'],
                "streetcat_enabled": bool(row['streetcat_enabled']) if row['streetcat_enabled'] is not None else False,
                "fridge_enabled": bool(row['fridge_enabled']) if row['fridge_enabled'] is not None else False,
                "fridge_interval_seconds": row['fridge_interval_seconds'] if row['fridge_interval_seconds'] else FRIDGE_INTERVAL_SECONDS,
                "fridge_last_run_at": row['fridge_last_run_at'],
                "fish_operation_common": row['fish_operation_common'] or "feed",
                "fish_operation_rare": row['fish_operation_rare'] or "feed",
                "fish_operation_epic": row['fish_operation_epic'] or "feed",
                "fish_operation_legendary": row['fish_operation_legendary'] or "fridge",
                "meow_chat_title": row['meow_chat_title'],
                "reaction_enabled": bool(row['reaction_enabled']),
                "autoreply_enabled": bool(row['autoreply_enabled']),
                "autoreply_match_type": row['autoreply_match_type'] or "exact",
                "autoseen_enabled": bool(row['autoseen_enabled']) if row['autoseen_enabled'] is not None else False,
                "step": "managed",
                "task": None,
                "action_task": None,
                "billing_task": None,
                "meow_task": None,
                "fish_task": None,
                "meowpoint_task": None,
                "fridge_task": None
            }
        return data
    except Exception as e:
        logging.error(f"❌ خطا در بارگذاری کاربران: {e}")
        return {}

def save_user(user_id, user):
    """
    ذخیره تنظیمات عمومی کاربر (نه فیلدهای اقتصادی).
    diamonds / referral_count / last_charge_at عمداً اینجا آپدیت نمی‌شوند چون به‌صورت
    اتمیک توسط charge_diamonds_db / transfer_diamonds_db / admin_adjust_diamonds مدیریت
    می‌شوند؛ آپدیت آن‌ها از این تابع می‌تواند مقدار تازه‌ی دیتابیس را با مقدار قدیمیِ
    حافظه بازنویسی کند و باعث ناسازگاری/از دست رفتن موجودی شود.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO novaself_users
                (user_id, session, font_id, status, name_time, bio_time, active_action,
                 date_enabled, date_type, date_font, text_mode,
                 secretary_enabled, secretary_text, secretary_delay,
                 secretary_entities, secretary_media_kind, secretary_media_bytes,
                 secretary_media_filename, secretary_media_mime,
                 diamonds, referral_count, username, last_charge_at,
                 meow_enabled, meow_chat_id, meow_last_sent_at, meow_interval_seconds,
                 fish_enabled, fish_last_run_at, fish_interval_seconds,
                 meowpoint_enabled, meowpoint_interval_seconds, meowpoint_last_run_at,
                 streetcat_enabled,
                 fridge_enabled, fridge_interval_seconds, fridge_last_run_at,
                 fish_operation_common, fish_operation_rare, fish_operation_epic, fish_operation_legendary,
                 meow_chat_title, reaction_enabled, autoreply_enabled, autoreply_match_type,
                 autoseen_enabled)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET
                session = EXCLUDED.session,
                font_id = EXCLUDED.font_id,
                status = EXCLUDED.status,
                name_time = EXCLUDED.name_time,
                bio_time = EXCLUDED.bio_time,
                active_action = EXCLUDED.active_action,
                date_enabled = EXCLUDED.date_enabled,
                date_type = EXCLUDED.date_type,
                date_font = EXCLUDED.date_font,
                text_mode = EXCLUDED.text_mode,
                secretary_enabled = EXCLUDED.secretary_enabled,
                secretary_text = EXCLUDED.secretary_text,
                secretary_delay = EXCLUDED.secretary_delay,
                secretary_entities = EXCLUDED.secretary_entities,
                secretary_media_kind = EXCLUDED.secretary_media_kind,
                secretary_media_bytes = EXCLUDED.secretary_media_bytes,
                secretary_media_filename = EXCLUDED.secretary_media_filename,
                secretary_media_mime = EXCLUDED.secretary_media_mime,
                meow_enabled = EXCLUDED.meow_enabled,
                meow_chat_id = EXCLUDED.meow_chat_id,
                meow_last_sent_at = EXCLUDED.meow_last_sent_at,
                meow_interval_seconds = EXCLUDED.meow_interval_seconds,
                fish_enabled = EXCLUDED.fish_enabled,
                fish_last_run_at = EXCLUDED.fish_last_run_at,
                fish_interval_seconds = EXCLUDED.fish_interval_seconds,
                meowpoint_enabled = EXCLUDED.meowpoint_enabled,
                meowpoint_interval_seconds = EXCLUDED.meowpoint_interval_seconds,
                meowpoint_last_run_at = EXCLUDED.meowpoint_last_run_at,
                streetcat_enabled = EXCLUDED.streetcat_enabled,
                fridge_enabled = EXCLUDED.fridge_enabled,
                fridge_interval_seconds = EXCLUDED.fridge_interval_seconds,
                fridge_last_run_at = EXCLUDED.fridge_last_run_at,
                fish_operation_common = EXCLUDED.fish_operation_common,
                fish_operation_rare = EXCLUDED.fish_operation_rare,
                fish_operation_epic = EXCLUDED.fish_operation_epic,
                fish_operation_legendary = EXCLUDED.fish_operation_legendary,
                meow_chat_title = EXCLUDED.meow_chat_title,
                reaction_enabled = EXCLUDED.reaction_enabled,
                autoreply_enabled = EXCLUDED.autoreply_enabled,
                autoreply_match_type = EXCLUDED.autoreply_match_type,
                autoseen_enabled = EXCLUDED.autoseen_enabled
        ''', (
            user_id, user.get("session"), user.get("font_id", 1), int(user.get("status", False)),
            int(user.get("name_time", True)), int(user.get("bio_time", False)),
            user.get("active_action", "none"),
            int(user.get("date_enabled", False)), user.get("date_type", "shamsi"),
            user.get("date_font", 1), user.get("text_mode", 0),
            int(user.get("secretary_enabled", False)), user.get("secretary_text", "مشغولم، بعداً پاسخ می‌دهم ✅"),
            user.get("secretary_delay", 60),
            psycopg2.Binary(pickle.dumps(user["secretary_entities"])) if user.get("secretary_entities") else None,
            user.get("secretary_media_kind"),
            psycopg2.Binary(user["secretary_media_bytes"]) if user.get("secretary_media_bytes") else None,
            user.get("secretary_media_filename"), user.get("secretary_media_mime"),
            user.get("diamonds", 0), user.get("referral_count", 0), user.get("username"),
            user.get("last_charge_at", tehran_now()),
            int(user.get("meow_enabled", False)), user.get("meow_chat_id"), user.get("meow_last_sent_at"),
            user.get("meow_interval_seconds", MEOW_INTERVAL_SECONDS),
            int(user.get("fish_enabled", False)), user.get("fish_last_run_at"),
            user.get("fish_interval_seconds", FISH_INTERVAL_SECONDS),
            int(user.get("meowpoint_enabled", False)), user.get("meowpoint_interval_seconds", MEOWPOINT_INTERVAL_SECONDS),
            user.get("meowpoint_last_run_at"),
            int(user.get("streetcat_enabled", False)),
            int(user.get("fridge_enabled", False)), user.get("fridge_interval_seconds", FRIDGE_INTERVAL_SECONDS),
            user.get("fridge_last_run_at"),
            user.get("fish_operation_common", "feed"), user.get("fish_operation_rare", "feed"),
            user.get("fish_operation_epic", "feed"), user.get("fish_operation_legendary", "fridge"),
            user.get("meow_chat_title"),
            user.get("reaction_enabled", False), user.get("autoreply_enabled", False),
            user.get("autoreply_match_type", "exact"), user.get("autoseen_enabled", False)
        ))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logging.error(f"❌ خطا در ذخیره کاربر {user_id}: {e}")

def update_username_db(user_id, username):
    """بروزرسانی مستقل نام‌کاربری (بدون تداخل با فیلدهای اقتصادی)."""
    if not username:
        return
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE novaself_users SET username = %s WHERE user_id = %s", (username, user_id))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logging.error(f"❌ خطا در بروزرسانی نام‌کاربری {user_id}: {e}")

def delete_user_db(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM novaself_users WHERE user_id = %s", (user_id,))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logging.error(f"❌ خطا در حذف کاربر {user_id}: {e}")

def get_user_stats():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM novaself_users")
        total_users = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM novaself_users WHERE status = 1")
        active_users = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        return total_users, active_users
    except Exception as e:
        logging.error(f"❌ خطا در دریافت آمار: {e}")
        return 0, 0

def log_admin_action(admin_id, target_id, action, details=""):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO novaself_admin_logs (admin_id, target_id, action, details) VALUES (%s, %s, %s, %s)",
            (admin_id, target_id, action, details)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logging.error(f"❌ خطا در ثبت لاگ مدیریتی: {e}")

def get_recent_admin_logs(limit=15):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT admin_id, target_id, action, details, created_at "
            "FROM novaself_admin_logs ORDER BY created_at DESC LIMIT %s",
            (limit,)
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows
    except Exception as e:
        logging.error(f"❌ خطا در دریافت لاگ‌های مدیریتی: {e}")
        return []

# ======================== سیستم اقتصادی الماس (اتمیک و امن در برابر Race Condition) ========================
def charge_diamonds_db(user_id, cost):
    """
    کسر اتمیک الماس (برای بیلینگِ روشن‌بودن سلف).
    خروجی: (success: bool, new_balance: float یا None در صورت خطا)
    success=False یعنی موجودی برای این هزینه کافی نبود (و موجودی صفر شده است).
    """
    if cost <= 0:
        return True, None
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT diamonds FROM novaself_users WHERE user_id = %s FOR UPDATE", (user_id,))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return False, None

        current = float(row[0] or 0)
        if current <= 0:
            conn.rollback()
            return False, 0.0

        new_balance = current - cost
        insufficient = new_balance < 0
        if insufficient:
            new_balance = 0.0

        cursor.execute(
            "UPDATE novaself_users SET diamonds = %s, last_charge_at = %s WHERE user_id = %s",
            (new_balance, tehran_now(), user_id)
        )
        conn.commit()
        return (not insufficient), new_balance
    except Exception as e:
        logging.error(f"❌ خطا در کسر الماس کاربر {user_id}: {e}")
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return False, None
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass

def transfer_diamonds_db(sender_id, receiver_id, amount):
    """
    انتقال اتمیک الماس بین دو کاربر (با قفل ردیف به ترتیب ثابت برای جلوگیری از Deadlock).
    خروجی: (success: bool, message: str, sender_balance, receiver_balance)
    """
    if sender_id == receiver_id:
        return False, "❌ انتقال به خودتان امکان‌پذیر نیست.", None, None
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return False, "❌ مقدار وارد شده معتبر نیست.", None, None
    if amount <= 0:
        return False, "❌ مقدار انتقال باید بیشتر از صفر باشد.", None, None

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        ids_sorted = sorted([sender_id, receiver_id])
        cursor.execute(
            "SELECT user_id, diamonds FROM novaself_users WHERE user_id IN (%s, %s) ORDER BY user_id FOR UPDATE",
            (ids_sorted[0], ids_sorted[1])
        )
        rows = {r[0]: float(r[1] or 0) for r in cursor.fetchall()}

        if sender_id not in rows:
            conn.rollback()
            return False, "❌ حساب فرستنده پیدا نشد.", None, None
        if receiver_id not in rows:
            conn.rollback()
            return False, "❌ کاربر گیرنده در سیستم ثبت‌نام نکرده است.", None, None

        sender_balance = rows[sender_id]
        if sender_balance < amount:
            conn.rollback()
            return False, "❌ موجودی شما کافی نیست.", None, None

        new_sender = sender_balance - amount
        new_receiver = rows[receiver_id] + amount

        cursor.execute("UPDATE novaself_users SET diamonds = %s WHERE user_id = %s", (new_sender, sender_id))
        cursor.execute("UPDATE novaself_users SET diamonds = %s WHERE user_id = %s", (new_receiver, receiver_id))
        conn.commit()
        return True, "✅ انتقال با موفقیت انجام شد.", new_sender, new_receiver
    except Exception as e:
        logging.error(f"❌ خطا در انتقال الماس بین {sender_id} و {receiver_id}: {e}")
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return False, "❌ خطای دیتابیس در حین انتقال رخ داد.", None, None
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass

def create_gift_code_db(code, diamonds, expires_at, created_by):
    """ساخت یک کد هدیه‌ی جدید توسط ادمین. خروجی: (success, error_message یا None)."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO novaself_gift_codes (code, diamonds, is_active, expires_at, created_by) "
            "VALUES (%s, %s, 1, %s, %s)",
            (code, diamonds, expires_at, created_by)
        )
        conn.commit()
        return True, None
    except psycopg2.errors.UniqueViolation:
        if conn:
            conn.rollback()
        return False, "این کد از قبل وجود دارد."
    except Exception as e:
        logging.error(f"❌ خطا در ساخت کد هدیه {code}: {e}")
        if conn:
            conn.rollback()
        return False, "خطای دیتابیس رخ داد."
    finally:
        if conn:
            conn.close()

def set_gift_code_active_db(code, is_active):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE novaself_gift_codes SET is_active = %s WHERE code = %s", (int(is_active), code))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"❌ خطا در تغییر وضعیت کد هدیه {code}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def list_gift_codes_db(limit=20):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute(
            "SELECT code, diamonds, is_active, expires_at, created_at FROM novaself_gift_codes "
            "ORDER BY created_at DESC LIMIT %s", (limit,)
        )
        return cursor.fetchall()
    except Exception as e:
        logging.error(f"❌ خطا در دریافت لیست کدهای هدیه: {e}")
        return []
    finally:
        if conn:
            conn.close()

def redeem_gift_code_db(code, user_id):
    """
    اعتبارسنجی و مصرف اتمیک کد هدیه برای یک کاربر.
    خروجی: (success: bool, message: str, new_balance یا None)
    شرط‌ها: وجود کد، فعال بودن، منقضی نشدن، و عدم استفاده‌ی قبلی همین کاربر
    (با قفل ردیف کد + کلید یکتای (code, user_id) در جدول مصرف، برای جلوگیری از Race Condition).
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)

        cursor.execute("SELECT * FROM novaself_gift_codes WHERE code = %s FOR UPDATE", (code,))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return False, "❌ چنین کدی وجود ندارد.", None
        if not row["is_active"]:
            conn.rollback()
            return False, "❌ این کد غیرفعال شده است.", None
        if row["expires_at"] and row["expires_at"] < tehran_now():
            conn.rollback()
            return False, "❌ این کد منقضی شده است.", None

        try:
            cursor.execute(
                "INSERT INTO novaself_gift_code_uses (code, user_id) VALUES (%s, %s)",
                (code, user_id)
            )
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            return False, "❌ شما قبلاً از این کد استفاده کرده‌اید.", None

        cursor.execute("SELECT diamonds FROM novaself_users WHERE user_id = %s FOR UPDATE", (user_id,))
        user_row = cursor.fetchone()
        if not user_row:
            conn.rollback()
            return False, "❌ حساب کاربری شما پیدا نشد.", None

        new_balance = float(user_row["diamonds"] or 0) + float(row["diamonds"])
        cursor.execute("UPDATE novaself_users SET diamonds = %s WHERE user_id = %s", (new_balance, user_id))
        conn.commit()
        return True, f"✅ کد هدیه با موفقیت اعمال شد! {format_diamonds(row['diamonds'])} الماس به حساب شما اضافه شد.", new_balance
    except Exception as e:
        logging.error(f"❌ خطا در مصرف کد هدیه {code} برای کاربر {user_id}: {e}")
        if conn:
            conn.rollback()
        return False, "❌ خطای دیتابیس رخ داد.", None
    finally:
        if conn:
            conn.close()

def get_gift_code_detail_db(code):
    """جزئیات کامل یک کد هدیه به‌همراه تعداد دفعات استفاده (برای صفحه مدیریت کد)."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute("SELECT * FROM novaself_gift_codes WHERE code = %s", (code,))
        row = cursor.fetchone()
        if not row:
            return None
        cursor.execute("SELECT COUNT(*) FROM novaself_gift_code_uses WHERE code = %s", (code,))
        uses = cursor.fetchone()[0]
        result = dict(row)
        result["uses_count"] = uses
        return result
    except Exception as e:
        logging.error(f"❌ خطا در دریافت جزئیات کد هدیه {code}: {e}")
        return None
    finally:
        if conn:
            conn.close()

def update_gift_code_amount_db(code, new_diamonds):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE novaself_gift_codes SET diamonds = %s WHERE code = %s", (new_diamonds, code))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"❌ خطا در تغییر مقدار الماس کد هدیه {code}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def update_gift_code_expiry_db(code, new_expires_at):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE novaself_gift_codes SET expires_at = %s WHERE code = %s", (new_expires_at, code))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"❌ خطا در تغییر انقضای کد هدیه {code}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def delete_gift_code_db(code):
    """حذف کامل کد هدیه (و رکوردهای استفاده‌ی مرتبط با آن، به‌واسطه‌ی CASCADE)."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM novaself_gift_codes WHERE code = %s", (code,))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"❌ خطا در حذف کد هدیه {code}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def admin_adjust_diamonds_db(target_id, amount):
    """
    افزایش/کاهش دستی موجودی الماس توسط ادمین (amount می‌تواند منفی باشد).
    خروجی: (success: bool, new_balance: float یا None)
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT diamonds FROM novaself_users WHERE user_id = %s FOR UPDATE", (target_id,))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return False, None

        current = float(row[0] or 0)
        new_balance = max(current + float(amount), 0.0)

        cursor.execute("UPDATE novaself_users SET diamonds = %s WHERE user_id = %s", (new_balance, target_id))
        conn.commit()
        return True, new_balance
    except Exception as e:
        logging.error(f"❌ خطا در تغییر موجودی الماس کاربر {target_id}: {e}")
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return False, None
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass

def admin_set_referral_db(target_id, new_count):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE novaself_users SET referral_count = %s WHERE user_id = %s RETURNING referral_count",
            (max(int(new_count), 0), target_id)
        )
        row = cursor.fetchone()
        conn.commit()
        return (row is not None), (row[0] if row else None)
    except Exception as e:
        logging.error(f"❌ خطا در تغییر تعداد رفرال کاربر {target_id}: {e}")
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return False, None
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass

# ======================== سیستم Referral ========================
REFERRAL_REWARD_DEFAULT = 30  # مقدار پیش‌فرض جایزه (فقط وقتی هنوز تنظیمی در دیتابیس ثبت نشده)

def get_setting_db(key, default=None):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM novaself_settings WHERE key = %s", (key,))
        row = cursor.fetchone()
        return row[0] if row else default
    except Exception as e:
        logging.error(f"❌ خطا در خواندن تنظیمِ {key}: {e}")
        return default
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass

def set_setting_db(key, value):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO novaself_settings (key, value) VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        ''', (key, str(value)))
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"❌ خطا در ذخیره‌ی تنظیمِ {key}: {e}")
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return False
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass

def get_referral_reward_db():
    """مقدار جایزه‌ی هر رفرال (الماس). پیش‌فرض ۳۰، مگر ادمین تغییرش داده باشد."""
    raw = get_setting_db("referral_reward")
    if raw is None:
        return REFERRAL_REWARD_DEFAULT
    try:
        return float(raw)
    except (TypeError, ValueError):
        return REFERRAL_REWARD_DEFAULT

def set_referral_reward_db(amount):
    return set_setting_db("referral_reward", max(float(amount), 0))

def is_referral_enabled_db():
    """وضعیتِ سراسریِ روشن/خاموشِ Referral. پیش‌فرض روشن، مگر ادمین خاموش کرده باشد."""
    raw = get_setting_db("referral_enabled")
    if raw is None:
        return True
    return raw == "1"

def set_referral_enabled_db(enabled):
    return set_setting_db("referral_enabled", "1" if enabled else "0")

def create_pending_referral_db(referred_id, referrer_id):
    """
    ثبت یک رفرالِ «در انتظار» (هنوز جایزه داده نشده). به‌خاطر PRIMARY KEY روی
    referred_id، اگر این کاربر قبلاً (با هر دعوت‌کننده‌ای) ثبت شده باشد، درخواست
    دوم بی‌صدا نادیده گرفته می‌شود (ON CONFLICT DO NOTHING) - این دقیقاً همان
    محافظتِ درخواست‌شده در برابر «ثبت چندباره» و «تغییر مصنوعیِ دعوت‌کننده» است.
    خروجی: True فقط اگر این بار واقعاً ثبتِ تازه انجام شده باشد.
    """
    if referred_id == referrer_id:
        return False  # جلوگیری از Self Referral
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO novaself_referrals (referred_id, referrer_id)
            VALUES (%s, %s)
            ON CONFLICT (referred_id) DO NOTHING
        ''', (referred_id, referrer_id))
        inserted = cursor.rowcount > 0
        conn.commit()
        return inserted
    except Exception as e:
        logging.error(f"❌ خطا در ثبت رفرالِ در انتظار ({referrer_id}->{referred_id}): {e}")
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return False
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass

def get_pending_referral_db(referred_id):
    """اگر این کاربر یک رفرالِ هنوز-جایزه‌نگرفته دارد، آیدیِ دعوت‌کننده را برمی‌گرداند، وگرنه None."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT referrer_id FROM novaself_referrals WHERE referred_id = %s AND reward_credited = FALSE",
            (referred_id,)
        )
        row = cursor.fetchone()
        return row[0] if row else None
    except Exception as e:
        logging.error(f"❌ خطا در خواندن رفرالِ در انتظارِ {referred_id}: {e}")
        return None
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass

def credit_referral_db(referred_id, reward_amount):
    """
    اعتبارِ رفرال را - فقط اگر هنوز اعتبار داده نشده - به‌صورت اتمیک ثبت می‌کند
    (شرطِ `reward_credited = FALSE` در خودِ UPDATE، نه یک چکِ جداگانه، تا حتی اگر
    این تابع هم‌زمان چند بار صدا زده شود، جایزه فقط یک بار داده شود - محافظت در
    برابر «استفاده چندباره از لینک برای گرفتن جایزه»).
    خروجی: referrer_id در صورت موفقیت (اولین‌بار)، وگرنه None.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE novaself_referrals
            SET reward_credited = TRUE, reward_amount = %s, credited_at = CURRENT_TIMESTAMP
            WHERE referred_id = %s AND reward_credited = FALSE
            RETURNING referrer_id
        ''', (reward_amount, referred_id))
        row = cursor.fetchone()
        conn.commit()
        return row[0] if row else None
    except Exception as e:
        logging.error(f"❌ خطا در اعتباردهیِ رفرالِ {referred_id}: {e}")
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return None
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass

def get_referral_stats_db():
    """آمار کلی رفرال برای پنل ادمین: تعداد کل ثبت‌شده‌ها و تعداد جایزه‌دادهشده‌ها."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE reward_credited) FROM novaself_referrals")
        row = cursor.fetchone()
        return {"total": row[0] or 0, "credited": row[1] or 0}
    except Exception as e:
        logging.error(f"❌ خطا در خواندن آمار رفرال: {e}")
        return {"total": 0, "credited": 0}
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass

def increment_referral_count_db(user_id):
    """افزایشِ اتمیکِ شمارنده‌ی رفرالِ کاربر (بعد از اعتباردهیِ موفقِ یک رفرال)."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE novaself_users SET referral_count = COALESCE(referral_count, 0) + 1 WHERE user_id = %s "
            "RETURNING referral_count",
            (user_id,)
        )
        row = cursor.fetchone()
        conn.commit()
        return row[0] if row else None
    except Exception as e:
        logging.error(f"❌ خطا در افزایش شمارنده‌ی رفرالِ {user_id}: {e}")
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return None
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass

def get_live_balance_db(user_id):
    """خواندن لحظه‌ای موجودی از دیتابیس (برای صفحه حساب کاربری)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT diamonds, referral_count, username FROM novaself_users WHERE user_id = %s",
            (user_id,)
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if not row:
            return None
        return {
            "diamonds": float(row[0] or 0),
            "referral_count": row[1] or 0,
            "username": row[2]
        }
    except Exception as e:
        logging.error(f"❌ خطا در خواندن موجودی لحظه‌ای کاربر {user_id}: {e}")
        return None

def _generate_unique_code(length=8, alphabet=string.ascii_uppercase + string.digits):
    return "".join(secrets.choice(alphabet) for _ in range(length))

# ======================== سفارش‌های خرید الماس ========================
def create_order_db(user_id, username, amount_diamonds, amount_toman, payment_method="card_to_card"):
    """
    ساخت یک سفارش جدید با Order ID یکتا. تلاش می‌شود تا در صورت برخورد نادر با
    یک کد تکراری، دوباره یک کد جدید تولید و امتحان شود.
    خروجی: order_id در صورت موفقیت، یا None در صورت خطا.
    """
    conn = None
    for _ in range(5):
        order_id = _generate_unique_code(8)
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO novaself_orders "
                "(order_id, user_id, username, amount_diamonds, amount_toman, payment_method, status) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'invoice')",
                (order_id, user_id, username, amount_diamonds, amount_toman, payment_method)
            )
            conn.commit()
            return order_id
        except psycopg2.errors.UniqueViolation:
            if conn:
                conn.rollback()
            continue
        except Exception as e:
            logging.error(f"❌ خطا در ساخت سفارش برای کاربر {user_id}: {e}")
            if conn:
                conn.rollback()
            return None
        finally:
            if conn:
                conn.close()
                conn = None
    return None

def get_order_db(order_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute("SELECT * FROM novaself_orders WHERE order_id = %s", (order_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    except Exception as e:
        logging.error(f"❌ خطا در خواندن سفارش {order_id}: {e}")
        return None
    finally:
        if conn:
            conn.close()

def set_order_receipt_db(order_id, chat_id, message_id, file_id):
    """
    ثبت رسید و انتقال اتمیک سفارش از وضعیت 'invoice' به 'pending_review'.
    اگر سفارش از قبل در همین وضعیت نباشد (مثلاً قبلاً رسید ارسال شده)، عملیات رد می‌شود
    تا از ارسال چند رسید برای یک سفارش جلوگیری شود.
    خروجی: (success, order_dict یا None)
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute("SELECT * FROM novaself_orders WHERE order_id = %s FOR UPDATE", (order_id,))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return False, None
        if row["status"] != "invoice":
            conn.rollback()
            return False, dict(row)

        cursor.execute(
            "UPDATE novaself_orders SET status = 'pending_review', receipt_chat_id = %s, "
            "receipt_message_id = %s, receipt_file_id = %s, updated_at = %s WHERE order_id = %s",
            (chat_id, message_id, file_id, tehran_now(), order_id)
        )
        conn.commit()
        row = dict(row)
        row["status"] = "pending_review"
        return True, row
    except Exception as e:
        logging.error(f"❌ خطا در ثبت رسید سفارش {order_id}: {e}")
        if conn:
            conn.rollback()
        return False, None
    finally:
        if conn:
            conn.close()

def approve_order_db(order_id, admin_id):
    """
    تأیید اتمیک سفارش: فقط اگر سفارش دقیقاً در وضعیت 'pending_review' باشد پردازش می‌شود
    (با قفل ردیف سفارش)، سپس موجودی کاربر با قفل جداگانه افزایش می‌یابد. اگر دو ادمین
    همزمان تأیید کنند، دومی روی همین SELECT...FOR UPDATE بلاک شده و بعد از Commit اولی،
    وضعیت را 'approved' می‌بیند و خروجی already_processed برمی‌گرداند.
    خروجی: (success, status_code, order_dict)
    status_code یکی از: 'ok', 'not_found', 'already_processed'
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute("SELECT * FROM novaself_orders WHERE order_id = %s FOR UPDATE", (order_id,))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return False, "not_found", None
        if row["status"] != "pending_review":
            conn.rollback()
            return False, "already_processed", dict(row)

        user_id = row["user_id"]
        cursor.execute("SELECT diamonds FROM novaself_users WHERE user_id = %s FOR UPDATE", (user_id,))
        user_row = cursor.fetchone()
        if not user_row:
            conn.rollback()
            return False, "user_not_found", dict(row)

        new_balance = float(user_row["diamonds"] or 0) + float(row["amount_diamonds"])
        now = tehran_now()
        cursor.execute("UPDATE novaself_users SET diamonds = %s WHERE user_id = %s", (new_balance, user_id))
        cursor.execute(
            "UPDATE novaself_orders SET status = 'approved', approved_at = %s, approved_by = %s, "
            "updated_at = %s WHERE order_id = %s",
            (now, admin_id, now, order_id)
        )
        conn.commit()

        result = dict(row)
        result["status"] = "approved"
        result["approved_at"] = now
        result["approved_by"] = admin_id
        result["_new_balance"] = new_balance
        return True, "ok", result
    except Exception as e:
        logging.error(f"❌ خطا در تأیید سفارش {order_id}: {e}")
        if conn:
            conn.rollback()
        return False, "error", None
    finally:
        if conn:
            conn.close()

def reject_order_db(order_id, admin_id, reason):
    """رد اتمیک سفارش؛ فقط اگر هنوز در وضعیت 'pending_review' باشد (مشابه approve_order_db)."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute("SELECT * FROM novaself_orders WHERE order_id = %s FOR UPDATE", (order_id,))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return False, "not_found", None
        if row["status"] != "pending_review":
            conn.rollback()
            return False, "already_processed", dict(row)

        now = tehran_now()
        cursor.execute(
            "UPDATE novaself_orders SET status = 'rejected', rejected_at = %s, rejected_by = %s, "
            "rejection_reason = %s, updated_at = %s WHERE order_id = %s",
            (now, admin_id, reason, now, order_id)
        )
        conn.commit()
        result = dict(row)
        result["status"] = "rejected"
        result["rejection_reason"] = reason
        return True, "ok", result
    except Exception as e:
        logging.error(f"❌ خطا در رد سفارش {order_id}: {e}")
        if conn:
            conn.rollback()
        return False, "error", None
    finally:
        if conn:
            conn.close()

# ======================== لاگ پیام‌های ادمین (تکی/همگانی) ========================
def create_broadcast_record_db(admin_id, kind, target_id, summary):
    conn = None
    for _ in range(5):
        broadcast_id = _generate_unique_code(10)
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO novaself_broadcasts (broadcast_id, admin_id, kind, target_id, summary) "
                "VALUES (%s, %s, %s, %s, %s)",
                (broadcast_id, admin_id, kind, target_id, (summary or "")[:200])
            )
            conn.commit()
            return broadcast_id
        except psycopg2.errors.UniqueViolation:
            if conn:
                conn.rollback()
            continue
        except Exception as e:
            logging.error(f"❌ خطا در ثبت رکورد پیام ادمین: {e}")
            if conn:
                conn.rollback()
            return None
        finally:
            if conn:
                conn.close()
                conn = None
    return None

def add_broadcast_delivery_db(broadcast_id, user_id, chat_id, message_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO novaself_broadcast_deliveries (broadcast_id, user_id, chat_id, message_id) "
            "VALUES (%s, %s, %s, %s)",
            (broadcast_id, user_id, chat_id, message_id)
        )
        conn.commit()
    except Exception as e:
        logging.error(f"❌ خطا در ثبت رسید ارسال پیام ({broadcast_id}): {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

def list_broadcasts_db(limit=15):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute(
            "SELECT broadcast_id, admin_id, kind, target_id, summary, created_at "
            "FROM novaself_broadcasts ORDER BY created_at DESC LIMIT %s", (limit,)
        )
        return cursor.fetchall()
    except Exception as e:
        logging.error(f"❌ خطا در دریافت لیست پیام‌های ارسالی: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_broadcast_deliveries_db(broadcast_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute(
            "SELECT user_id, chat_id, message_id FROM novaself_broadcast_deliveries WHERE broadcast_id = %s",
            (broadcast_id,)
        )
        return cursor.fetchall()
    except Exception as e:
        logging.error(f"❌ خطا در دریافت رسیدهای پیام {broadcast_id}: {e}")
        return []
    finally:
        if conn:
            conn.close()

def delete_broadcast_record_db(broadcast_id):
    """حذف رکورد پیام و همه‌ی رسیدهای مرتبط (CASCADE) بعد از حذف پیام‌ها از چت کاربران."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM novaself_broadcasts WHERE broadcast_id = %s", (broadcast_id,))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"❌ خطا در حذف رکورد پیام {broadcast_id}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

# ======================== قابلیت ریکت (ذخیره‌سازی) ========================
def get_user_reactions_db(owner_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute(
            "SELECT target_user_id, target_username, emoji FROM novaself_reactions WHERE owner_id = %s ORDER BY created_at",
            (owner_id,)
        )
        return cursor.fetchall()
    except Exception as e:
        logging.error(f"❌ خطا در خواندن لیست ریکت کاربر {owner_id}: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_all_reactions_db():
    """برای بارگذاری کش تمام کاربران در استارتاپ."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute("SELECT owner_id, target_user_id, target_username, emoji FROM novaself_reactions")
        return cursor.fetchall()
    except Exception as e:
        logging.error(f"❌ خطا در بارگذاری اولیه‌ی ریکت‌ها: {e}")
        return []
    finally:
        if conn:
            conn.close()

def set_user_reaction_db(owner_id, target_user_id, target_username, emoji):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO novaself_reactions (owner_id, target_user_id, target_username, emoji)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (owner_id, target_user_id) DO UPDATE SET
                target_username = EXCLUDED.target_username,
                emoji = EXCLUDED.emoji
        ''', (owner_id, target_user_id, target_username, emoji))
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"❌ خطا در ذخیره ریکت (owner={owner_id} target={target_user_id}): {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def remove_user_reaction_db(owner_id, target_user_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM novaself_reactions WHERE owner_id = %s AND target_user_id = %s",
            (owner_id, target_user_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"❌ خطا در حذف ریکت (owner={owner_id} target={target_user_id}): {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def load_reactions_cache():
    """بارگذاری کش ریکت‌ها در استارتاپ (بند «Restart نباید تنظیمات را از بین ببرد»)."""
    # نکته: عمداً reaction_targets.clear()+update() به‌جای بازتخصیصِ کامل (=)
    # استفاده می‌شود؛ چون این دیکشنری از nova_state وارد شده و ماژول‌های دیگر
    # (مثل main.py و nova_self_features.py) با from-import همین شیء را در
    # حافظه گرفته‌اند - بازتخصیصِ کامل، ارتباط آن‌ها با نسخه‌ی تازه را قطع می‌کرد.
    fresh = {}
    for row in get_all_reactions_db():
        fresh.setdefault(row["owner_id"], {})[row["target_user_id"]] = {
            "emoji": row["emoji"], "username": row["target_username"]
        }
    reaction_targets.clear()
    reaction_targets.update(fresh)
    logging.info(f"👍 کش ریکت بارگذاری شد: {sum(len(v) for v in fresh.values())} کاربر هدف در {len(fresh)} حساب.")

# ======================== قابلیت پاسخ خودکار (ذخیره‌سازی) ========================
def add_autoreply_db(owner_id, trigger_text, response_text, entities, media_kind, media_bytes, media_filename, media_mime):
    """
    یک پاسخ خودکار جدید ذخیره می‌کند و شماره‌ی نمایشیِ بعدیِ (local_id) مخصوصِ همان
    کاربر را برمی‌گرداند (۱، ۲، ۳ ...). Entityهای Formatting با pickle سریالایز
    می‌شوند چون این‌ها اشیاء TL تلگرام هستند نه دیتای ساده — pickle این‌جا امن است
    چون فقط توسط خودِ سرور نوشته و خوانده می‌شود (نه ورودی خارجی/غیرقابل‌اعتماد).
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COALESCE(MAX(local_id), 0) + 1 FROM novaself_autoreplies WHERE owner_id = %s", (owner_id,))
        local_id = cursor.fetchone()[0]

        entities_blob = psycopg2.Binary(pickle.dumps(entities)) if entities else None
        media_blob = psycopg2.Binary(media_bytes) if media_bytes else None

        cursor.execute('''
            INSERT INTO novaself_autoreplies
                (owner_id, local_id, trigger_text, response_text, response_entities,
                 response_media_kind, response_media_bytes, response_media_filename, response_media_mime)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (owner_id, local_id, trigger_text, response_text, entities_blob,
              media_kind, media_blob, media_filename, media_mime))
        conn.commit()
        return local_id
    except Exception as e:
        logging.error(f"❌ خطا در ذخیره پاسخ خودکار برای کاربر {owner_id}: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            conn.close()

def delete_autoreply_db(owner_id, local_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM novaself_autoreplies WHERE owner_id = %s AND local_id = %s",
            (owner_id, local_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"❌ خطا در حذف پاسخ خودکار (owner={owner_id} local_id={local_id}): {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def get_all_autoreplies_db():
    """برای بارگذاری کش تمام کاربران در استارتاپ."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute("SELECT * FROM novaself_autoreplies ORDER BY owner_id, local_id")
        return cursor.fetchall()
    except Exception as e:
        logging.error(f"❌ خطا در بارگذاری اولیه‌ی پاسخ‌های خودکار: {e}")
        return []
    finally:
        if conn:
            conn.close()

def load_autoreplies_cache():
    """بارگذاری کش پاسخ‌های خودکار در استارتاپ، شامل Unpickle کردن Entityها."""
    fresh = {}
    for row in get_all_autoreplies_db():
        entities = None
        if row["response_entities"]:
            try:
                entities = pickle.loads(bytes(row["response_entities"]))
            except Exception as e:
                log_internal_error("unpickle_autoreply_entities", f"owner={row['owner_id']} local_id={row['local_id']} err={e}")
        media_bytes = bytes(row["response_media_bytes"]) if row["response_media_bytes"] else None
        fresh.setdefault(row["owner_id"], []).append({
            "local_id": row["local_id"],
            "trigger_text": row["trigger_text"],
            "response_text": row["response_text"],
            "entities": entities,
            "media_kind": row["response_media_kind"],
            "media_bytes": media_bytes,
            "media_filename": row["response_media_filename"],
            "media_mime": row["response_media_mime"],
        })
    autoreply_cache.clear()
    autoreply_cache.update(fresh)
    logging.info(f"🤖 کش پاسخ خودکار بارگذاری شد: {sum(len(v) for v in fresh.values())} پاسخ در {len(fresh)} حساب.")

# ======================== قفل کردن قابلیت‌ها توسط ادمین ========================
def get_all_feature_locks_db():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, feature_key FROM novaself_feature_locks")
        return cursor.fetchall()
    except Exception as e:
        logging.error(f"❌ خطا در بارگذاری اولیه‌ی قفل قابلیت‌ها: {e}")
        return []
    finally:
        if conn:
            conn.close()

def load_feature_locks_cache():
    """بارگذاری کش قفل‌ها در استارتاپ (تا Restart تنظیمات قفل را از بین نبرد)."""
    fresh = {}
    for owner_id, feature_key in get_all_feature_locks_db():
        fresh.setdefault(owner_id, set()).add(feature_key)
    feature_locks.clear()
    feature_locks.update(fresh)
    logging.info(f"🔒 کش قفل قابلیت‌ها بارگذاری شد: {sum(len(v) for v in fresh.values())} قفل روی {len(fresh)} کاربر.")

def lock_feature_db(user_id, feature_key):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO novaself_feature_locks (user_id, feature_key)
            VALUES (%s, %s)
            ON CONFLICT (user_id, feature_key) DO NOTHING
        ''', (user_id, feature_key))
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"❌ خطا در قفل کردن قابلیت {feature_key} برای {user_id}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def unlock_feature_db(user_id, feature_key):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM novaself_feature_locks WHERE user_id = %s AND feature_key = %s",
            (user_id, feature_key)
        )
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"❌ خطا در باز کردن قفل {feature_key} برای {user_id}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def is_feature_locked(user_id, feature_key):
    return feature_key in feature_locks.get(user_id, set())

# ======================== جوین اجباری ========================
def create_join_channel_db(title, identifier, invite_link):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO novaself_join_channels (title, identifier, invite_link) VALUES (%s, %s, %s) RETURNING id",
            (title, identifier, invite_link)
        )
        new_id = cursor.fetchone()[0]
        conn.commit()
        return new_id
    except Exception as e:
        logging.error(f"❌ خطا در افزودن کانال جوین اجباری: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            conn.close()

def list_join_channels_db(active_only=False):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        if active_only:
            cursor.execute("SELECT * FROM novaself_join_channels WHERE is_active = TRUE ORDER BY id")
        else:
            cursor.execute("SELECT * FROM novaself_join_channels ORDER BY id")
        return cursor.fetchall()
    except Exception as e:
        logging.error(f"❌ خطا در خواندن لیست کانال‌های جوین اجباری: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_join_channel_db(channel_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute("SELECT * FROM novaself_join_channels WHERE id = %s", (channel_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    except Exception as e:
        logging.error(f"❌ خطا در خواندن کانال جوین اجباری {channel_id}: {e}")
        return None
    finally:
        if conn:
            conn.close()

def update_join_channel_link_db(channel_id, new_link):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE novaself_join_channels SET invite_link = %s WHERE id = %s", (new_link, channel_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"❌ خطا در تغییر لینک کانال {channel_id}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def set_join_channel_active_db(channel_id, active):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE novaself_join_channels SET is_active = %s WHERE id = %s", (active, channel_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"❌ خطا در تغییر وضعیت کانال {channel_id}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def delete_join_channel_db(channel_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM novaself_join_channels WHERE id = %s", (channel_id,))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"❌ خطا در حذف کانال {channel_id}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

# توجه: توابع mark_user_verified_db / get_all_verified_users_db / get_verified_count_db
# قبلاً اینجا بودند و عضویتِ تأییدشده را برای همیشه در دیتابیس ذخیره می‌کردند.
# طبق درخواست صریح حذف شدند: دیگر هیچ وضعیت عضویتی در دیتابیس ثبت نمی‌شود؛
# هر بار که لازم باشد، عضویت مستقیماً و زنده از تلگرام (check_user_joined_all)
# پرسیده می‌شود.

# ======================== سیستم بکاپ ========================
# لیست تمام جداول قابل بکاپ به‌همراه (کلید اصلی، ستون‌های محافظت‌شده که هنگام
# بازیابی هرگز رونویسی نمی‌شوند). محافظت از session کاربران طبق تأکید صریح
# درخواست («بازیابی بکاپ نباید باعث حذف Session کاربران شود») است.
BACKUP_TABLE_PKS = {
    "novaself_users": (["user_id"], ["session"]),
    "novaself_gift_codes": (["code"], []),
    "novaself_gift_code_uses": (["code", "user_id"], []),
    "novaself_orders": (["order_id"], []),
    "novaself_broadcasts": (["broadcast_id"], []),
    "novaself_broadcast_deliveries": (["id"], []),
    "novaself_reactions": (["owner_id", "target_user_id"], []),
    "novaself_autoreplies": (["id"], []),
    "novaself_feature_locks": (["user_id", "feature_key"], []),
    "novaself_join_channels": (["id"], []),
    "novaself_admin_logs": (["id"], []),
}

def _backup_row_to_jsonable(row_dict):
    """تبدیل یک ردیف دیتابیس (شامل bytes/datetime) به دیکشنری قابل JSON."""
    out = {}
    for k, v in row_dict.items():
        if isinstance(v, (bytes, memoryview)):
            out[k] = {"__bytes__": base64.b64encode(bytes(v)).decode("ascii")}
        elif isinstance(v, datetime):
            out[k] = {"__datetime__": v.isoformat()}
        else:
            out[k] = v
    return out

def _backup_jsonable_to_row(row_dict):
    """معکوس _backup_row_to_jsonable برای بازیابی."""
    out = {}
    for k, v in row_dict.items():
        if isinstance(v, dict) and "__bytes__" in v:
            out[k] = base64.b64decode(v["__bytes__"])
        elif isinstance(v, dict) and "__datetime__" in v:
            out[k] = datetime.fromisoformat(v["__datetime__"])
        else:
            out[k] = v
    return out

def build_backup_payload():
    """
    دامپ کامل تمام جداول پروژه به یک دیکشنری JSON-پذیر.
    خروجی: (payload_dict, error یا None)
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        dump = {
            "meta": {
                "created_at": tehran_now().isoformat(),
                "version": 1,
                "tables": list(BACKUP_TABLE_PKS.keys()),
            }
        }
        for table in BACKUP_TABLE_PKS:
            try:
                cursor.execute(f"SELECT * FROM {table}")
                rows = cursor.fetchall()
                dump[table] = [_backup_row_to_jsonable(dict(r)) for r in rows]
            except Exception as e:
                logging.error(f"⚠️ خطا در دامپ جدول {table}: {e}")
                dump[table] = []
        return dump, None
    except Exception as e:
        logging.error(f"❌ خطا در ساخت بکاپ: {e}")
        return None, str(e)
    finally:
        if conn:
            conn.close()

def create_backup_db(admin_id, label=None):
    """
    یک بکاپ کامل می‌سازد و مستقیماً داخل خودِ دیتابیس (جدول novaself_backups)
    ذخیره می‌کند — این‌طوری بکاپ‌ها مستقل از فایل‌سیستم موقتِ Railway باقی می‌مانند.
    خروجی: (backup_id, size_bytes) یا (None, 0) در صورت خطا.
    """
    dump, error = build_backup_payload()
    if dump is None:
        return None, 0

    payload_bytes = json.dumps(dump, ensure_ascii=False).encode("utf-8")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO novaself_backups (created_by, label, size_bytes, data) VALUES (%s, %s, %s, %s) RETURNING id",
            (admin_id, label, len(payload_bytes), psycopg2.Binary(payload_bytes))
        )
        new_id = cursor.fetchone()[0]
        conn.commit()
        return new_id, len(payload_bytes)
    except Exception as e:
        logging.error(f"❌ خطا در ذخیره بکاپ: {e}")
        if conn:
            conn.rollback()
        return None, 0
    finally:
        if conn:
            conn.close()

def list_backups_db():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute(
            "SELECT id, created_by, label, size_bytes, created_at FROM novaself_backups ORDER BY created_at DESC"
        )
        return cursor.fetchall()
    except Exception as e:
        logging.error(f"❌ خطا در دریافت لیست بکاپ‌ها: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_backup_data_db(backup_id):
    """محتوای کامل یک بکاپ (بایت خام JSON) را برمی‌گرداند، یا None."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT data FROM novaself_backups WHERE id = %s", (backup_id,))
        row = cursor.fetchone()
        return bytes(row[0]) if row else None
    except Exception as e:
        logging.error(f"❌ خطا در خواندن بکاپ {backup_id}: {e}")
        return None
    finally:
        if conn:
            conn.close()

def delete_backup_db(backup_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM novaself_backups WHERE id = %s", (backup_id,))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"❌ خطا در حذف بکاپ {backup_id}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def restore_backup_payload(dump):
    """
    بازیابیِ یک دامپِ JSON روی دیتابیس فعلی. برای هر جدول از INSERT ... ON CONFLICT
    DO UPDATE استفاده می‌شود (نه TRUNCATE/DELETE) — یعنی هیچ رکورد کاربر یا دیتای
    دیگری هرگز حذف نمی‌شود، فقط رونویسی/افزوده می‌شود. ستون‌های محافظت‌شده (مثل
    session کاربران) هرگز در SET قرار نمی‌گیرند، پس مقدار زنده‌ی فعلی‌شان دست‌نخورده
    باقی می‌ماند؛ برای کاربرِ کاملاً جدید (که در DB فعلی وجود ندارد) session از
    خودِ بکاپ درج می‌شود چون در آن حالت چیزی برای «شکستن» وجود ندارد.
    خروجی: (success: bool, summary: dict جدول->تعداد ردیف بازیابی‌شده, error یا None)
    """
    conn = None
    summary = {}
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        for table, (pk_cols, protect_cols) in BACKUP_TABLE_PKS.items():
            rows = dump.get(table) or []
            restored = 0
            for raw_row in rows:
                row = _backup_jsonable_to_row(raw_row)
                cols = list(row.keys())
                if not cols or not all(pk in cols for pk in pk_cols):
                    continue

                placeholders = ", ".join(["%s"] * len(cols))
                col_list = ", ".join(cols)
                update_cols = [c for c in cols if c not in pk_cols and c not in protect_cols]

                if update_cols:
                    set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
                    conflict_clause = f"ON CONFLICT ({', '.join(pk_cols)}) DO UPDATE SET {set_clause}"
                else:
                    conflict_clause = f"ON CONFLICT ({', '.join(pk_cols)}) DO NOTHING"

                sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) {conflict_clause}"
                try:
                    cursor.execute(sql, [row[c] for c in cols])
                    restored += 1
                except Exception as e:
                    logging.error(f"⚠️ خطا در بازیابی یک ردیف از {table}: {e}")

            summary[table] = restored

        conn.commit()
        return True, summary, None
    except Exception as e:
        logging.error(f"❌ خطا در بازیابی بکاپ: {e}")
        if conn:
            conn.rollback()
        return False, summary, str(e)
    finally:
        if conn:
            conn.close()

def reload_join_channels_cache():
    """کش کانال‌های فعال را از دیتابیس تازه می‌کند (بعد از هر افزودن/حذف/ویرایش ادمین)."""
    # نکته: slice-assignment (`[:] =`) به‌جای بازتخصیصِ کامل، تا همان شیء لیستِ
    # اصلی (که ماژول‌های دیگر با from-import گرفته‌اند) در جا به‌روزرسانی شود.
    join_channels_cache[:] = list(list_join_channels_db(active_only=True))

def load_join_gate_cache():
    """بارگذاری اولیه‌ی کش کانال‌های جوین اجباری در استارتاپ."""
    reload_join_channels_cache()
    logging.info(
        f"🔐 جوین اجباری: {len(join_channels_cache)} کانال فعال "
        f"(عضویت هر بار زنده چک می‌شود، بدون ذخیره‌سازی وضعیت تأیید)."
    )

async def check_user_joined_all(user_id):
    """
    بررسی عضویت کاربر در تمام کانال‌های فعالِ جوین اجباری با کلاینت بات.

    این نسخه Fail-closed است (دقیقاً مثل join.py): تا وقتی مطمئن نشویم کاربر
    واقعاً عضو یک کانال است، آن کانال را «باقیمانده» (missing) در نظر می‌گیریم -
    چه علتش این باشد که کاربر عضو نیست/ترک کرده/بن شده، چه اینکه خودِ بات به هر
    دلیلی (کانال خصوصی است، بات هنوز داخلِ کانال نیست، شناسه‌ی کانال اشتباه
    ذخیره شده و ...) نتواند وضعیت را بررسی کند. یعنی سلف تا وقتی عضویت با
    قطعیت تأیید نشود، برای آن کاربر کار نمی‌کند.

    نکته‌ی مهم و پیش‌نیاز عملیاتی: خودِ اکانتِ بات (@همون که BOT_TOKEN مال
    اوست) باید در همه‌ی کانال‌های جوین اجباری عضو باشد (ترجیحاً ادمین)،
    وگرنه GetParticipantRequest/get_entity برای بات هم شکست می‌خورد و طبق
    منطق Fail-closed، هیچ‌کس هرگز نمی‌تواند این گیت را رد کند. اگر بات هنوز
    عضو کانال نشده، همین‌جا لاگ هشدار (هم در لاگ اصلی که در Railway دیده
    می‌شود، هم در nova_internal.log) ثبت می‌شود.

    خروجی: (all_joined: bool, missing_channels: list[dict])
    """
    missing = []
    for ch in join_channels_cache:
        identifier = ch["identifier"]
        try:
            identifier = int(identifier)
        except (ValueError, TypeError):
            pass

        try:
            channel_entity = await bot.get_entity(identifier)
            participant = await bot(GetParticipantRequest(channel_entity, user_id))
            if isinstance(participant.participant, (ChannelParticipantLeft, ChannelParticipantBanned)):
                missing.append(ch)
        except UserNotParticipantError:
            # کاربر اصلاً عضو کانال نیست -> قطعاً باقیمانده است
            missing.append(ch)
        except Exception as e:
            # هر خطای دیگری (کانال خصوصی، بات عضو کانال نیست، شناسه‌ی اشتباه و...)
            # هم به‌معنیِ «عضویت تأیید نشد» است، پس این کانال هم باقیمانده حساب
            # می‌شود (Fail-closed). این خطا را در لاگ اصلی (قابل مشاهده در Railway)
            # هم ثبت می‌کنیم تا مشخص شود مشکل از کدام کانال/تنظیمات است.
            logging.warning(
                f"⚠️ جوین اجباری: بررسی عضویت کاربر {user_id} در کانال "
                f"«{ch.get('title')}» (id={ch.get('id')}) ناموفق بود: {e}. "
                f"بررسی کنید که بات حتماً عضو/ادمین این کانال باشد و شناسه‌ی "
                f"کانال درست ذخیره شده باشد."
            )
            log_internal_error("check_joined", f"channel_id={ch.get('id')} err={e}")
            missing.append(ch)

    return (len(missing) == 0), missing

async def enforce_join_gate(user_id):
    """
    نگهبانِ عمومیِ جوین اجباری - باید قبل از نمایش هر پنل/قابلیتی از سلف صدا زده
    شود (نه فقط /start). هر بار زنده و مستقیم از تلگرام چک می‌کند (بدون تکیه به
    هیچ کش/دیتابیسی)، تا کاربری که قبلاً عضو بوده ولی الان یکی از کانال‌ها را
    ترک کرده، دوباره و بلافاصله مسدود شود.

    خروجی: (blocked: bool, missing: list) - وقتی blocked=True است، فراخواننده
    باید پیام جوین اجباری را نشان دهد و از ادامه‌ی پردازش (باز کردن هر منو/قابلیت
    دیگری) صرف‌نظر کند.
    """
    if not join_channels_cache or is_admin(user_id):
        return False, []
    all_joined, missing = await check_user_joined_all(user_id)
    return (not all_joined), missing

