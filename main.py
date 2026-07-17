import asyncio
import os
import pytz
import psycopg2
import jdatetime
from hijridate import Gregorian
from psycopg2.extras import DictCursor
from datetime import datetime, timedelta
from telethon import TelegramClient, events, Button, helpers
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError, FloodWaitError, MessageNotModifiedError, RPCError
)
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.messages import SetTypingRequest, GetFullChatRequest
from telethon.tl.types import (
    SendMessageTypingAction, SendMessageRecordAudioAction, SendMessageUploadPhotoAction,
    SendMessageRecordRoundAction, SendMessageUploadDocumentAction, SendMessageUploadVideoAction,
    SendMessageGamePlayAction, SendMessageChooseStickerAction,
    MessageEntityBold, MessageEntityItalic, MessageEntityUnderline,
    MessageEntityStrike, MessageEntitySpoiler, MessageEntityCode,
    MessageEntityBlockquote, ChannelParticipantsAdmins, InputMessageEntityMentionName
)
import logging
from webapp_api import create_webapp_app, run_webapp_server
from nova_utils import (
    status_icon, toggle_label, build_clock_preview, build_date_preview,
    build_sender_receipt, build_receiver_receipt, ClickDebouncer, safe_call,
    log_diamond_transfer, log_self_toggle, log_settings_change, log_internal_error,
)

# ======================== تنظیمات اولیه ========================
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_IDS = [int(id.strip()) for id in os.environ.get("ADMIN_IDS", "").split(",") if id.strip()]
MINIAPP_ORIGIN = os.environ.get("MINIAPP_ORIGIN", "*")  # آدرس گیت‌هاب‌پیجز، مثل: https://username.github.io
PORT = int(os.environ.get("PORT", 8080))  # ریلوی این متغیر رو خودش ست می‌کنه

if not all([API_ID, API_HASH, BOT_TOKEN, DATABASE_URL]):
    raise ValueError("تمامی متغیرهای محیطی باید تنظیم شوند!")

if not ADMIN_IDS:
    logging.warning("⚠️ هشدار: هیچ ادمینی تنظیم نشده است!")

bot = TelegramClient('helper_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ======================== تنظیمات سیستم الماس ========================
DIAMOND_RATE_PER_HOUR = 5       # مصرف الماس به ازای هر ساعت روشن بودن سلف
DIAMOND_PRICE_TOMAN = 20        # قیمت هر الماس به تومان
BILLING_INTERVAL_SECONDS = 60   # فاصله زمانی محاسبه و کسر الماس
SUPPORT_USERNAME = "@SayPouYa"

# ======================== دیکشنری‌های عمومی ========================
active_clients = {}
generator_data = {}
active_signins = {}
user_data = {}
broadcast_data = {}
secretary_state = {}   # {user_id: {peer_id: {"replied": bool, "task": Task}}}
_auto_sent_marks = set()  # {(user_id, chat_id, message_id)} پیام‌هایی که خودمان خودکار فرستادیم (نباید توسط حالت متن ادیت شوند)
transfer_data = {}     # {user_id: {"target_id":..., "amount":...}} وضعیت موقت انتقال الماس
admin_action_data = {} # {admin_id: {"type":..., "target_id":..., "step":...}} وضعیت موقت عملیات مدیریتی روی الماس/رفرال
click_debouncer = ClickDebouncer(window_seconds=1.2)  # جلوگیری از پردازش کلیک تکراری روی دکمه‌ها

TAG_ADMIN_TRIGGERS = {".تگ ادمین", ".تگادمین", ".tagadmins"}
TAG_MEMBERS_TRIGGERS = {".تگ اعضا", ".تگاعضا", ".tagall"}

# ======================== فونت‌های کامل ========================
FONTS = {
    0: {'0': '0', '1': '1', '2': '2', '3': '3', '4': '4', '5': '5', '6': '6', '7': '7', '8': '8', '9': '9'},
    1: {'0': '𝟬', '1': '𝟭', '2': '𝟮', '3': '𝟯', '4': '𝟰', '5': '𝟱', '6': '𝟲', '7': '𝟳', '8': '𝟴', '9': '𝟵'},
    2: {'0': '𝟘', '1': '𝟙', '2': '𝟚', '3': '𝟛', '4': '𝟜', '5': '𝟝', '6': '𝟞', '7': '𝟟', '8': '𝟠', '9': '𝟡'},
    3: {'0': '𝟶', '1': '𝟷', '2': '𝟸', '3': '𝟹', '4': '𝟺', '5': '𝟻', '6': '𝟼', '7': '𝟽', '8': '𝟾', '9': '𝟿'},
    4: {'0': '𝟢', '1': '𝟣', '2': '𝟤', '3': '𝟥', '4': '𝟦', '5': '𝟧', '6': '𝟨', '7': '𝟩', '8': '𝟪', '9': '𝟫'},
    5: {'0': '𝟎', '1': '𝟏', '2': '𝟐', '3': '𝟑', '4': '𝟒', '5': '𝟓', '6': '𝟔', '7': '𝟕', '8': '𝟖', '9': '𝟗'},
    6: {'0': '０', '1': '１', '2': '２', '3': '３', '4': '４', '5': '５', '6': '６', '7': '７', '8': '８', '9': '９'},
    7: {'0': '𝟬', '1': '𝟭', '2': '𝟮', '3': '𝟯', '4': '𝟰', '5': '𝟱', '6': '𝟲', '7': '𝟳', '8': '𝟴', '9': '𝟵'},
    8: {'0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹'},
    9: {'0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄', '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉'},
    10: {'0': '⓪', '1': '①', '2': '②', '3': '③', '4': '④', '5': '⑤', '6': '⑥', '7': '⑦', '8': '⑧', '9': '⑨'},
    11: {'0': '⓿', '1': '➊', '2': '➋', '3': '➌', '4': '➍', '5': '➎', '6': '➏', '7': '➐', '8': '➑', '9': '➒'},
    12: {'0': '۰', '1': '۱', '2': '۲', '3': '۳', '4': '۴', '5': '۵', '6': '۶', '7': '۷', '8': '۸', '9': '۹'},
    13: {'0': '٠', '1': '١', '2': '٢', '3': '٣', '4': '٤', '5': '٥', '6': '٦', '7': '٧', '8': '٨', '9': '٩'},
}

FONT_NAMES = {
    0: "معمولی (123)",
    1: "بولد ضخیم (𝟭𝟮𝟯)",
    2: "بولد گرد (𝟙𝟚𝟛)",
    3: "ماشین تحریر (𝟷𝟸𝟹)",
    4: "بولد کلاسیک (𝟣𝟤𝟥)",
    5: "ساده (𝟏𝟐𝟑)",
    6: "فول‌وید (１２３)",
    7: "بولد مدرن (𝟭𝟮𝟯)",
    8: "بالانویس (¹²³)",
    9: "زیرنویس (₁₂₃)",
    10: "دایره‌ای (①②③)",
    11: "دایره‌ای پر (➊➋➌)",
    12: "فارسی (۱۲۳)",
    13: "عربی (١٢٣)"
}

ACTIONS = {
    'typing': ('در حال تایپ', SendMessageTypingAction()),
    'voice': ('در حال ضبط صدا', SendMessageRecordAudioAction()),
    'photo': ('در حال ارسال عکس', SendMessageUploadPhotoAction(0)),
    'round': ('در حال ضبط ویدیو', SendMessageRecordRoundAction()),
    'doc': ('در حال ارسال سند', SendMessageUploadDocumentAction(0)),
    'video': ('در حال ارسال ویدیو', SendMessageUploadVideoAction(0)),
    'game': ('در حال بازی', SendMessageGamePlayAction()),
    'sticker': ('در حال انتخاب استیکر', SendMessageChooseStickerAction())
}

# ======================== انواع تاریخ ========================
DATE_TYPE_NAMES = {
    "gregorian": "میلادی",
    "shamsi": "شمسی",
    "qamari": "قمری",
}

# ======================== حالت‌های متن ========================
TEXTMODE_NAMES = {
    1: "نقل قول",
    2: "بولد",
    3: "زیرخط",
    4: "ایتالیک",
    5: "اسپویلر",
    6: "خط خورده",
    7: "تدریجی",
    8: "تک‌فاصله",
}

# ======================== مدیریت دیتابیس ========================
def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

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
            ("diamonds", "DOUBLE PRECISION DEFAULT 0"),
            ("referral_count", "INTEGER DEFAULT 0"),
            ("username", "TEXT"),
            ("last_charge_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
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
                   diamonds, referral_count, username, last_charge_at
            FROM novaself_users
            ORDER BY joined_at DESC
        """)

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        data = {}
        for row in rows:
            user_id = row['user_id']
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
                "diamonds": float(row['diamonds']) if row['diamonds'] is not None else 0.0,
                "referral_count": row['referral_count'] if row['referral_count'] is not None else 0,
                "username": row['username'],
                "last_charge_at": row['last_charge_at'] or datetime.now(),
                "joined_at": row['joined_at'] or datetime.now(),
                "step": "managed",
                "task": None,
                "action_task": None,
                "billing_task": None
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
                 diamonds, referral_count, username, last_charge_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                secretary_delay = EXCLUDED.secretary_delay
        ''', (
            user_id, user.get("session"), user.get("font_id", 1), int(user.get("status", False)),
            int(user.get("name_time", True)), int(user.get("bio_time", False)),
            user.get("active_action", "none"),
            int(user.get("date_enabled", False)), user.get("date_type", "shamsi"),
            user.get("date_font", 1), user.get("text_mode", 0),
            int(user.get("secretary_enabled", False)), user.get("secretary_text", "مشغولم، بعداً پاسخ می‌دهم ✅"),
            user.get("secretary_delay", 60),
            user.get("diamonds", 0), user.get("referral_count", 0), user.get("username"),
            user.get("last_charge_at", datetime.now())
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
            (new_balance, datetime.now(), user_id)
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

def format_diamonds(value):
    value = float(value or 0)
    if value == int(value):
        return f"{int(value):,}"
    return f"{value:,.2f}"

def format_toman(diamonds):
    toman = float(diamonds or 0) * DIAMOND_PRICE_TOMAN
    return f"{toman:,.0f}"

def format_expiry(diamonds):
    diamonds = float(diamonds or 0)
    if diamonds <= 0 or not DIAMOND_RATE_PER_HOUR:
        return "منقضی شده"
    total_hours = diamonds / DIAMOND_RATE_PER_HOUR
    days = int(total_hours // 24)
    hours = int(total_hours % 24)
    if days > 0:
        return f"{days} روز و {hours} ساعت"
    return f"{hours} ساعت"

# ======================== توابع کمکی ========================
def apply_font(text, font_id):
    font_dict = FONTS.get(font_id, FONTS[0])
    return "".join(font_dict.get(char, char) for char in text)

def is_admin(user_id):
    return user_id in ADMIN_IDS

def make_default_user(session=None, status=False, step="menu"):
    return {
        "session": session,
        "font_id": 1,
        "status": status,
        "name_time": True,
        "bio_time": False,
        "active_action": "none",
        "date_enabled": False,
        "date_type": "shamsi",
        "date_font": 1,
        "text_mode": 0,
        "secretary_enabled": False,
        "secretary_text": "مشغولم، بعداً پاسخ می‌دهم ✅",
        "secretary_delay": 60,
        "diamonds": 0.0,
        "referral_count": 0,
        "username": None,
        "last_charge_at": datetime.now(),
        "task": None,
        "action_task": None,
        "billing_task": None,
        "step": step,
        "joined_at": datetime.now()
    }

def format_date(dt, date_type):
    """تبدیل datetime به رشته تاریخ بر اساس نوع انتخابی (میلادی/شمسی/قمری)."""
    try:
        if date_type == "shamsi":
            jd = jdatetime.datetime.fromgregorian(datetime=dt)
            return jd.strftime("%Y/%m/%d")
        elif date_type == "qamari":
            h = Gregorian(dt.year, dt.month, dt.day).to_hijri()
            return f"{h.year}/{h.month:02d}/{h.day:02d}"
        else:
            return dt.strftime("%Y/%m/%d")
    except Exception as e:
        logging.error(f"⚠️ خطا در محاسبه تاریخ ({date_type}): {e}")
        return dt.strftime("%Y/%m/%d")

def make_blockquote_entity(offset, length, collapsed=False):
    """سازگار با نسخه‌های مختلف Telethon برای نقل‌قول تدریجی (collapsed)."""
    try:
        return MessageEntityBlockquote(offset=offset, length=length, collapsed=collapsed)
    except TypeError:
        return MessageEntityBlockquote(offset=offset, length=length)

def build_format_entities(text, mode):
    """ساخت entity قالب‌بندی مناسب برای متن کامل پیام بر اساس حالت انتخابی."""
    if not text or not mode or mode not in TEXTMODE_NAMES:
        return None

    surrogated = helpers.add_surrogate(text)
    length = len(surrogated)
    if length == 0:
        return None
    offset = 0

    if mode == 1:
        return [make_blockquote_entity(offset, length, collapsed=False)]
    if mode == 2:
        return [MessageEntityBold(offset, length)]
    if mode == 3:
        return [MessageEntityUnderline(offset, length)]
    if mode == 4:
        return [MessageEntityItalic(offset, length)]
    if mode == 5:
        return [MessageEntitySpoiler(offset, length)]
    if mode == 6:
        return [MessageEntityStrike(offset, length)]
    if mode == 7:
        return [make_blockquote_entity(offset, length, collapsed=True)]
    if mode == 8:
        return [MessageEntityCode(offset, length)]
    return None

async def safe_edit(event, text, buttons=None):
    """
    ویرایش امن پیام + پاسخ فوری به Callback (برای جلوگیری از تأخیر/اسپینر روی دکمه‌ها).
    جلوگیری از کرش شدن هندلرها به‌خاطر خطای ویرایش پیام (مثل MessageNotModified).
    """
    try:
        await event.edit(text, buttons=buttons)
    except MessageNotModifiedError:
        pass
    except Exception as e:
        logging.error(f"⚠️ خطا در ویرایش پیام: {e}")
        try:
            await event.answer("❌ خطا در بروزرسانی پیام، دوباره تلاش کنید.", alert=True)
            return
        except Exception:
            pass
    try:
        await event.answer()
    except Exception:
        pass

# ======================== منوهای کاربر ========================
def get_main_menu_keyboard(user):
    status_text = status_icon(user["status"])
    expiry_text = format_expiry(user.get("diamonds", 0))
    return [
        [Button.inline(f"وضعیت سلف ({status_text})  |  ⏳ {expiry_text}", b"toggle_status")],
        [
            Button.inline("📅 تاریخ", b"menu_date"),
            Button.inline("🎭 اکشن", b"menu_actions"),
            Button.inline("⌚ ساعت", b"menu_time"),
        ],
        [
            Button.inline("🖊️ حالت متن", b"menu_textmode"),
            Button.inline("🏷️ تگ", b"menu_tag"),
        ],
        [Button.inline("🧑‍💼 منشی پیوی", b"menu_secretary")],
        [Button.inline("👤 حساب کاربری", b"menu_account")]
    ]

def get_time_menu_keyboard(user):
    name_status = status_icon(user["name_time"])
    bio_status = status_icon(user["bio_time"])
    return [
        [Button.inline(f"ساعت نام ({name_status})", b"toggle_name_time")],
        [Button.inline(f"ساعت بیو ({bio_status})", b"toggle_bio_time")],
        [Button.inline("فونت ساعت", b"menu_fonts")],
        [Button.inline("🔙 بازگشت", b"back_to_main")]
    ]

def get_time_menu_text(user):
    font_name = FONT_NAMES.get(user["font_id"], "بولد")
    preview = build_clock_preview(apply_font, user["font_id"])
    return (
        "⌚ **تنظیمات ساعت**\n\n"
        f"فونت ساعت: {font_name}\n\n"
        f"{preview}"
    )

def get_fonts_menu_text(user):
    font_name = FONT_NAMES.get(user["font_id"], "بولد")
    preview = build_clock_preview(apply_font, user["font_id"])
    return (
        "🔤 **انتخاب فونت ساعت**\n\n"
        f"فونت ساعت: {font_name}\n\n"
        f"{preview}"
    )

def get_fonts_menu_keyboard(current_font_id):
    buttons = []
    row = []

    for font_id, font_name in FONT_NAMES.items():
        mark = status_icon(font_id == current_font_id)
        row.append(Button.inline(f"{mark} {font_name}", f"setfont_{font_id}".encode()))

        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([Button.inline("🔙 بازگشت به ساعت", b"menu_time")])
    return buttons

def get_actions_menu_keyboard(current_action):
    buttons = []
    row = []

    for action_key, (action_name, _) in ACTIONS.items():
        mark = status_icon(action_key == current_action)
        row.append(Button.inline(f"{mark} {action_name}", f"setact_{action_key}".encode()))

        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([Button.inline("🔙 بازگشت", b"back_to_main")])
    return buttons

def get_date_menu_keyboard(user):
    enabled_status = status_icon(user.get("date_enabled"))
    current_type = user.get("date_type", "shamsi")

    type_row = []
    for type_key, type_name in DATE_TYPE_NAMES.items():
        mark = status_icon(type_key == current_type)
        type_row.append(Button.inline(f"{mark} {type_name}", f"setdatetype_{type_key}".encode()))

    return [
        [Button.inline(f"تاریخ بیو ({enabled_status})", b"toggle_date_enabled")],
        type_row,
        [Button.inline("فونت تاریخ", b"menu_date_fonts")],
        [Button.inline("🔙 بازگشت", b"back_to_main")]
    ]

def get_date_menu_text(user):
    preview = build_date_preview(apply_font, format_date, user.get("date_font", 1), user.get("date_type", "shamsi"))
    return (
        "📅 **تنظیمات تاریخ**\n\n"
        f"{preview}"
    )

def get_date_fonts_menu_keyboard(current_font_id):
    buttons = []
    row = []

    for font_id, font_name in FONT_NAMES.items():
        mark = status_icon(font_id == current_font_id)
        row.append(Button.inline(f"{mark} {font_name}", f"setdatefont_{font_id}".encode()))

        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([Button.inline("🔙 بازگشت به تاریخ", b"menu_date")])
    return buttons

def get_date_fonts_menu_text(user):
    font_name = FONT_NAMES.get(user.get("date_font", 1), "بولد")
    preview = build_date_preview(apply_font, format_date, user.get("date_font", 1), user.get("date_type", "shamsi"))
    return (
        "🔤 **انتخاب فونت تاریخ**\n\n"
        f"فونت تاریخ: {font_name}\n\n"
        f"{preview}"
    )

def get_textmode_menu_keyboard(current_mode):
    buttons = []
    row = []

    for mode_id, mode_name in TEXTMODE_NAMES.items():
        mark = status_icon(mode_id == current_mode)
        row.append(Button.inline(f"{mark} {mode_name}", f"settextmode_{mode_id}".encode()))

        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([Button.inline("🔙 بازگشت", b"back_to_main")])
    return buttons

def get_tag_menu_text():
    return (
        "🏷️ **قابلیت تگ**\n\n"
        "این قابلیت با ارسال یکی از دستورات زیر (توسط خودتان) داخل هر گروه فعال می‌شود:\n\n"
        "▫️ `.تگ ادمین` — منشن تمام ادمین‌های همان گروه.\n"
        "▫️ `.تگ اعضا` — منشن تمام اعضای همان گروه.\n\n"
        "نکات:\n"
        "▫️ فقط داخل گروه/سوپرگروه کار می‌کند و در چت خصوصی غیرفعال است.\n"
        "▫️ اگر دستور را روی پیامی ریپلای کنید، خروجی هم روی همان پیام ریپلای می‌شود.\n"
        "▫️ در گروه‌های بزرگ، پیام‌ها به چند بخش تقسیم می‌شوند تا محدودیت تلگرام رعایت شود."
    )

def get_tag_menu_keyboard():
    return [[Button.inline("🔙 بازگشت", b"back_to_main")]]

def get_secretary_menu_text(user):
    status = status_icon(user.get("secretary_enabled"))
    delay = user.get("secretary_delay", 60)
    text_preview = user.get("secretary_text") or "مشغولم، بعداً پاسخ می‌دهم ✅"
    return (
        "🧑‍💼 **منشی پیوی**\n\n"
        f"وضعیت: {status}\n"
        f"⏱️ تأخیر پاسخ: {delay} ثانیه\n"
        f"📝 متن فعلی:\n{text_preview}\n\n"
        "وقتی روشن باشد، به اولین پیام خصوصی هر شخص (که هنوز پاسخ منشی نگرفته) "
        "بعد از تأخیر تعیین‌شده، این متن ارسال می‌شود؛ تا وقتی طرف پیام تازه‌ای ندهد، دوباره ارسال نمی‌شود."
    )

def get_secretary_menu_keyboard(user):
    on = user.get("secretary_enabled", False)
    delay = user.get("secretary_delay", 60)
    return [
        [
            Button.inline(f"روشن ({status_icon(on)})", b"secretary_on"),
            Button.inline(f"خاموش ({status_icon(not on)})", b"secretary_off"),
        ],
        [Button.inline("📝 تنظیم متن", b"secretary_set_text")],
        [Button.inline(f"⏱️ تنظیم تایم ({delay} ثانیه)", b"secretary_set_time")],
        [Button.inline("🔙 بازگشت", b"back_to_main")]
    ]

def get_account_text(user_id, user):
    username = user.get("username")
    username_display = f"@{username}" if username else "ثبت نشده"
    diamonds = format_diamonds(user.get("diamonds", 0))
    toman = format_toman(user.get("diamonds", 0))
    expiry = format_expiry(user.get("diamonds", 0))

    return (
        "👤 **حساب کاربری**\n\n"
        f"💡 نام کاربری: {username_display}\n"
        f"🆔 آیدی عددی: `{user_id}`\n"
        f"👥 تعداد رفرال: {user.get('referral_count', 0)}\n"
        f"💎 موجودی الماس: {diamonds}\n"
        f"💰 معادل تومانی: {toman} تومان\n"
        f"⏳ انقضای تخمینی: {expiry}\n\n"
        "--------------------"
    )

def get_account_keyboard():
    return [
        [Button.inline("💎 خرید الماس", b"account_buy_diamond"), Button.inline("💸 انتقال الماس", b"account_transfer_start")],
        [Button.inline("🗑 حذف حساب کاربری", b"account_delete_confirm")],
        [Button.inline("🔙 بازگشت", b"back_to_main")]
    ]

def get_account_delete_warning_keyboard():
    return [
        [Button.inline("❌ لغو عملیات", b"menu_account")],
        [Button.inline("✅ تایید و حذف حساب کاربری", b"account_delete_final")]
    ]

def get_transfer_cancel_keyboard():
    return [[Button.inline("❌ لغو", b"transfer_cancel")]]

def get_transfer_confirm_keyboard():
    return [
        [Button.inline("✅ تایید انتقال", b"transfer_confirm_execute")],
        [Button.inline("❌ لغو", b"transfer_cancel")]
    ]

def get_code_keyboard(current_code=""):
    display = current_code if current_code else "خالی"
    return [
        [Button.inline(f"🔢 کد وارد شده: {display}", b"void")],
        [Button.inline("1", b"k_1"), Button.inline("2", b"k_2"), Button.inline("3", b"k_3")],
        [Button.inline("4", b"k_4"), Button.inline("5", b"k_5"), Button.inline("6", b"k_6")],
        [Button.inline("7", b"k_7"), Button.inline("8", b"k_8"), Button.inline("9", b"k_9")],
        [Button.inline("❌ پاک کردن", b"k_clear"), Button.inline("0", b"k_0"), Button.inline("✅ تایید", b"k_submit")]
    ]

# ======================== منوهای ادمین ========================
def get_admin_main_menu():
    total, active = get_user_stats()
    return [
        [Button.inline(f"📊 آمار کاربران ({total} نفر)", b"admin_stats")],
        [Button.inline("📋 لیست کاربران", b"admin_users_list")],
        [Button.inline("📨 ارسال پیام همگانی", b"admin_broadcast")],
        [Button.inline("🔍 جستجوی کاربر", b"admin_search_user")],
        [Button.inline("📜 لاگ‌های مدیریتی اخیر", b"admin_logs")],
        [Button.inline("🔄 بروزرسانی همه کاربران", b"admin_refresh_all")]
    ]

def get_users_list_page(page=0, per_page=10):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        offset = page * per_page

        cursor.execute("""
            SELECT user_id, status, joined_at
            FROM novaself_users
            ORDER BY joined_at DESC
            LIMIT %s OFFSET %s
        """, (per_page, offset))

        users = cursor.fetchall()
        cursor.close()
        conn.close()

        buttons = []
        for user in users:
            mark = status_icon(user[1])
            buttons.append([Button.inline(
                f"{mark} کاربر {user[0]}",
                f"admin_view_user_{user[0]}".encode()
            )])

        nav_buttons = []
        if page > 0:
            nav_buttons.append(Button.inline("⬅️ قبلی", f"admin_users_page_{page-1}".encode()))
        nav_buttons.append(Button.inline(f"📄 صفحه {page+1}", b"void"))
        nav_buttons.append(Button.inline("➡️ بعدی", f"admin_users_page_{page+1}".encode()))
        buttons.append(nav_buttons)

        buttons.append([Button.inline("🔙 بازگشت به پنل ادمین", b"admin_panel")])

        return buttons
    except Exception as e:
        logging.error(f"❌ خطا در دریافت لیست کاربران: {e}")
        return [[Button.inline("🔙 بازگشت", b"admin_panel")]]

def get_user_detail_buttons(user_id):
    return [
        [Button.inline("🔄 تغییر وضعیت", f"admin_toggle_user_{user_id}".encode())],
        [
            Button.inline("➕ افزایش الماس", f"admin_add_diamond_{user_id}".encode()),
            Button.inline("➖ کاهش الماس", f"admin_sub_diamond_{user_id}".encode()),
        ],
        [Button.inline("👥 تغییر تعداد رفرال", f"admin_set_referral_{user_id}".encode())],
        [Button.inline("❌ حذف کاربر", f"admin_delete_user_{user_id}".encode())],
        [Button.inline("📨 ارسال پیام به این کاربر", f"admin_send_to_user_{user_id}".encode())],
        [Button.inline("🔙 بازگشت به لیست", b"admin_users_list")]
    ]

# ======================== کمکی: پیام‌های خودکار (نباید توسط حالت متن دوباره ادیت شوند) ========================
def _mark_auto_sent(user_id, chat_id, message_id):
    _auto_sent_marks.add((user_id, chat_id, message_id))

def _pop_auto_sent(user_id, chat_id, message_id):
    key = (user_id, chat_id, message_id)
    if key in _auto_sent_marks:
        _auto_sent_marks.discard(key)
        return True
    return False

# ======================== قابلیت تگ ========================
async def _gather_chat_admins(event):
    """دریافت لیست ادمین‌های چت؛ سازگار با سوپرگروه/کانال و گروه‌های قدیمی."""
    admins = []
    try:
        chat = await event.get_chat()
        async for u in event.client.iter_participants(chat, filter=ChannelParticipantsAdmins()):
            if not u.bot and not u.deleted:
                admins.append(u)
        return admins
    except Exception:
        pass

    try:
        full = await event.client(GetFullChatRequest(event.chat_id))
        admin_ids = {
            p.user_id for p in full.full_chat.participants.participants
            if p.__class__.__name__ in ("ChatParticipantAdmin", "ChatParticipantCreator")
        }
        for u in full.users:
            if u.id in admin_ids and not u.bot and not u.deleted:
                admins.append(u)
    except Exception as e:
        logging.error(f"⚠️ خطا در دریافت ادمین‌های چت: {e}")

    return admins

async def _send_mentions(event, users_list, user_id):
    """ساخت و ارسال پیام‌های منشن‌دار به‌صورت تکه‌تکه (فقط منشن، بدون هیچ متن اضافه) + مدیریت FloodWait."""
    if not users_list:
        return

    chunk_size = 25
    reply_to = event.reply_to_msg_id if event.is_reply else None

    for i in range(0, len(users_list), chunk_size):
        chunk = users_list[i:i + chunk_size]
        body = ""
        entities = []
        cursor = 0

        for u in chunk:
            name = (u.first_name or "کاربر").strip() or "کاربر"
            mention_text = name + " "
            surrogated_piece = helpers.add_surrogate(mention_text)
            try:
                input_user = await event.client.get_input_entity(u)
                entities.append(InputMessageEntityMentionName(
                    offset=cursor, length=len(surrogated_piece.rstrip()), user_id=input_user
                ))
            except Exception:
                pass
            body += mention_text
            cursor += len(surrogated_piece)

        try:
            sent = await safe_call(
                event.client.send_message, event.chat_id, body,
                formatting_entities=entities, reply_to=reply_to if i == 0 else None
            )
            _mark_auto_sent(user_id, sent.chat_id, sent.id)
        except RPCError as e:
            logging.error(f"⚠️ خطا در ارسال پیام تگ: {e}")
        except Exception as e:
            logging.error(f"⚠️ خطای غیرمنتظره در ارسال تگ: {e}")

        await asyncio.sleep(1.5)

async def handle_tag_admins(event, user_id):
    try:
        admins = await _gather_chat_admins(event)
        if not admins:
            await event.reply("❌ ادمینی برای منشن پیدا نشد یا دسترسی کافی برای دریافت لیست ادمین‌ها وجود ندارد.")
            return
        await _send_mentions(event, admins, user_id)
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
    except Exception as e:
        logging.error(f"⚠️ خطا در تگ ادمین (کاربر {user_id}): {e}")

async def handle_tag_members(event, user_id):
    try:
        chat = await event.get_chat()
        members = []
        try:
            async for u in event.client.iter_participants(chat, limit=1000):
                if not u.bot and not u.deleted:
                    members.append(u)
        except (RPCError, Exception) as e:
            logging.error(f"⚠️ خطا در دریافت اعضای گروه: {e}")
            await event.reply("❌ دریافت لیست اعضا با خطا مواجه شد (ممکن است دسترسی کافی نباشد یا گروه محدودیت داشته باشد).")
            return

        if not members:
            await event.reply("❌ عضوی برای منشن پیدا نشد.")
            return

        await _send_mentions(event, members, user_id)
    except Exception as e:
        logging.error(f"⚠️ خطا در تگ اعضا (کاربر {user_id}): {e}")

# ======================== هندلر یکپارچه پیام‌های خروجی (حالت متن + دستورات تگ) ========================
def make_outgoing_handler(user_id):
    async def handler(event):
        try:
            if _pop_auto_sent(user_id, event.chat_id, event.id):
                return

            user = user_data.get(user_id)
            if not user or not user.get("status"):
                return

            raw_text = event.raw_text
            text_stripped = raw_text.strip() if raw_text else ""

            # --- دستورات تگ (فقط داخل گروه/سوپرگروه) ---
            if text_stripped and not event.is_private:
                lowered = text_stripped.lower()
                if lowered in TAG_ADMIN_TRIGGERS:
                    await handle_tag_admins(event, user_id)
                    return
                if lowered in TAG_MEMBERS_TRIGGERS:
                    await handle_tag_members(event, user_id)
                    return

            # --- حالت متن ---
            mode = user.get("text_mode", 0)
            if not mode or not text_stripped:
                return

            entities = build_format_entities(raw_text, mode)
            if not entities:
                return

            await asyncio.sleep(0.2)
            await event.client.edit_message(
                event.chat_id, event.id, raw_text, formatting_entities=entities
            )
        except Exception as e:
            logging.error(f"⚠️ خطا در پردازش پیام خروجی کاربر {user_id}: {e}")

    return handler

# ======================== قابلیت منشی (پاسخ‌گوی خودکار) ========================
def make_secretary_incoming_handler(user_id):
    async def handler(event):
        try:
            if not event.is_private:
                return

            user = user_data.get(user_id)
            if not user or not user.get("status") or not user.get("secretary_enabled"):
                return

            peer_id = event.sender_id
            if not peer_id:
                return

            # رفع باگ: منشی نباید به ربات‌های تلگرامی پاسخ بدهد (فقط پیوی کاربران واقعی)
            try:
                sender = await event.get_sender()
                if sender is None or getattr(sender, "bot", False):
                    return
            except Exception:
                return

            state = secretary_state.setdefault(user_id, {})
            peer_state = state.get(peer_id)

            # اگر تسک تأخیریِ فعالی برای این نفر در جریان است، تسک تازه‌ای نساز (جلوگیری از Task اضافی)
            if peer_state and peer_state.get("task") and not peer_state["task"].done() and not peer_state.get("replied"):
                return

            delay = max(1, int(user.get("secretary_delay", 60)))
            reply_text = user.get("secretary_text") or "مشغولم، بعداً پاسخ می‌دهم ✅"

            async def _delayed_reply():
                try:
                    await asyncio.sleep(delay)
                    cur_user = user_data.get(user_id)
                    if not cur_user or not cur_user.get("status") or not cur_user.get("secretary_enabled"):
                        return
                    client = active_clients.get(user_id)
                    if not client:
                        return
                    sent = await client.send_message(peer_id, cur_user.get("secretary_text") or reply_text)
                    _mark_auto_sent(user_id, sent.chat_id, sent.id)
                    if user_id in secretary_state and peer_id in secretary_state[user_id]:
                        secretary_state[user_id][peer_id]["replied"] = True
                except asyncio.CancelledError:
                    pass
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    logging.error(f"⚠️ خطا در ارسال پیام منشی کاربر {user_id}: {e}")

            task = asyncio.get_event_loop().create_task(_delayed_reply())
            state[peer_id] = {"replied": False, "task": task}
        except Exception as e:
            logging.error(f"⚠️ خطای منشی کاربر {user_id}: {e}")

    return handler

def _cleanup_secretary_state(user_id):
    """لغو تسک‌های در انتظار منشی و آزادسازی حافظه (جلوگیری از Memory Leak)."""
    peer_states = secretary_state.pop(user_id, None)
    if peer_states:
        for st in peer_states.values():
            t = st.get("task")
            if t and not t.done():
                t.cancel()

# ======================== مدیریت چرخه حیات کلاینت سلف ========================
def register_active_client(user_id, client):
    """ثبت کلاینتِ از قبل متصل و احراز‌هویت‌شده (بدون اتصال مجدد)."""
    active_clients[user_id] = client
    client.add_event_handler(make_outgoing_handler(user_id), events.NewMessage(outgoing=True))
    client.add_event_handler(make_secretary_incoming_handler(user_id), events.NewMessage(incoming=True))

    loop = asyncio.get_event_loop()
    if user_id in user_data:
        user_data[user_id]["task"] = loop.create_task(self_bot_worker(user_id, client))
        user_data[user_id]["action_task"] = loop.create_task(self_bot_action_worker(user_id, client))
        user_data[user_id]["billing_task"] = loop.create_task(diamond_billing_worker(user_id, client))

async def start_self_client(user_id, session_string):
    """ساخت یک کلاینت جدید از روی سشن ذخیره‌شده، اتصال و ثبت آن."""
    if not session_string:
        return None
    try:
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            return None
    except Exception as e:
        logging.error(f"❌ خطا در اتصال کلاینت کاربر {user_id}: {e}")
        return None

    register_active_client(user_id, client)
    return client

async def stop_self_client(user_id):
    """
    توقف کامل و امن کلاینت سلف یک کاربر (تسک‌ها + قطع اتصال + پاکسازی وضعیت منشی).
    این تابع ممکن است از داخل خودِ یکی از تسک‌ها (مثلاً diamond_billing_worker هنگام اتمام
    موجودی) صدا زده شود؛ برای جلوگیری از خودکنسل‌کردنِ تسکِ در حال اجرا، تسک جاری را
    از لیست کنسل‌شدنی مستثنی می‌کنیم.
    """
    user = user_data.get(user_id)
    current = asyncio.current_task()

    if user:
        for key in ("task", "action_task", "billing_task"):
            t = user.get(key)
            if t and t is not current:
                t.cancel()
            user[key] = None

    _cleanup_secretary_state(user_id)

    client = active_clients.pop(user_id, None)
    if client:
        try:
            if client.is_connected():
                await client.disconnect()
        except Exception:
            pass

# ======================== توابع اصلی سلف ========================
async def self_bot_worker(user_id, client):
    try:
        me = await client.get_me()
        first_name = me.first_name or "کاربر"
        last_signature = None

        if user_id in user_data and user_data[user_id].get("username") != me.username:
            user_data[user_id]["username"] = me.username
            update_username_db(user_id, me.username)

        while True:
            if user_id not in user_data or not user_data[user_id]["status"]:
                break

            user = user_data[user_id]
            tehran_tz = pytz.timezone('Asia/Tehran')
            now = datetime.now(tehran_tz)
            current_time = now.strftime("%H:%M")
            current_date_raw = format_date(now, user.get("date_type", "shamsi"))

            signature = (
                current_time, current_date_raw,
                user["name_time"], user["bio_time"], user["font_id"],
                user.get("date_enabled", False), user.get("date_type", "shamsi"),
                user.get("date_font", 1)
            )

            if signature != last_signature:
                formatted_time = apply_font(current_time, user["font_id"])
                formatted_date = apply_font(current_date_raw, user.get("date_font", 1))

                try:
                    if user["name_time"]:
                        await client(UpdateProfileRequest(first_name=first_name, last_name=formatted_time))
                    else:
                        await client(UpdateProfileRequest(first_name=first_name, last_name=""))

                    bio_parts = []
                    if user["bio_time"]:
                        bio_parts.append(formatted_time)
                    if user.get("date_enabled"):
                        bio_parts.append(formatted_date)

                    if bio_parts:
                        await client(UpdateProfileRequest(about=" | ".join(bio_parts)))

                    last_signature = signature
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    logging.error(f"⚠️ خطا در بروزرسانی پروفایل کاربر {user_id}: {e}")

            await asyncio.sleep(5)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logging.error(f"❌ خطای اصلی سلف برای کاربر {user_id}: {e}")
    finally:
        try:
            if active_clients.get(user_id) is client:
                active_clients.pop(user_id, None)
            if client and client.is_connected():
                await client.disconnect()
        except Exception:
            pass

async def self_bot_action_worker(user_id, client):
    try:
        while True:
            if user_id not in user_data or not user_data[user_id]["status"]:
                break

            user = user_data[user_id]
            action_key = user["active_action"]

            if action_key == 'none' or action_key not in ACTIONS:
                await asyncio.sleep(4)
                continue

            try:
                async for dialog in client.iter_dialogs(limit=10):
                    if dialog.is_user or dialog.is_group:
                        try:
                            await client(SetTypingRequest(
                                peer=dialog.input_entity,
                                action=ACTIONS[action_key][1]
                            ))
                        except Exception:
                            pass
            except Exception as e:
                logging.error(f"⚠️ خطا در نمایش اکشن کاربر {user_id}: {e}")

            await asyncio.sleep(4)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logging.error(f"❌ خطای اکشن برای کاربر {user_id}: {e}")

async def diamond_billing_worker(user_id, client):
    """
    هر BILLING_INTERVAL_SECONDS ثانیه، به نسبت مدت‌زمان سپری‌شده الماس کسر می‌کند
    (نرخ: DIAMOND_RATE_PER_HOUR الماس به ازای هر ساعت روشن بودن سلف).
    اگر موجودی تمام شود، سلف به‌صورت خودکار خاموش و به کاربر اطلاع داده می‌شود.
    """
    try:
        last_charge = datetime.now(pytz.UTC)

        while True:
            if user_id not in user_data or not user_data[user_id]["status"]:
                break

            await asyncio.sleep(BILLING_INTERVAL_SECONDS)

            if user_id not in user_data or not user_data[user_id]["status"]:
                break

            now = datetime.now(pytz.UTC)
            elapsed_hours = (now - last_charge).total_seconds() / 3600
            last_charge = now

            cost = elapsed_hours * DIAMOND_RATE_PER_HOUR
            if cost <= 0:
                continue

            success, new_balance = charge_diamonds_db(user_id, cost)

            if user_id in user_data and new_balance is not None:
                user_data[user_id]["diamonds"] = new_balance

            if not success:
                if user_id in user_data:
                    user_data[user_id]["status"] = False
                    save_user(user_id, user_data[user_id])

                await stop_self_client(user_id)

                try:
                    await bot.send_message(
                        user_id,
                        "⛔ **موجودی الماس شما به پایان رسید و سلف شما به‌صورت خودکار متوقف شد.**\n\n"
                        "برای فعال‌سازی مجدد، ابتدا از بخش «👤 حساب کاربری» موجودی خود را افزایش دهید."
                    )
                except Exception:
                    pass
                break

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logging.error(f"⚠️ خطای بیلینگ الماس کاربر {user_id}: {e}")

async def autostart_saved_users():
    await asyncio.sleep(5)

    for user_id, user in list(user_data.items()):
        if user["status"] and user["session"]:
            if float(user.get("diamonds", 0)) <= 0:
                user["status"] = False
                save_user(user_id, user)
                logging.warning(f"⚠️ سلف کاربر {user_id} به‌دلیل موجودی صفر الماس غیرفعال ماند.")
                continue

            client = await start_self_client(user_id, user["session"])
            if client:
                logging.info(f"✅ سلف کاربر {user_id} راه‌اندازی شد.")
            else:
                user["status"] = False
                save_user(user_id, user)
                logging.warning(f"⚠️ سلف کاربر {user_id} به‌دلیل نشست نامعتبر غیرفعال شد.")

# ======================== هندلرهای ربات ========================
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    """هندلر دستور /start - کاملاً یکسان برای همه کاربران"""
    user_id = event.sender_id

    if user_id in generator_data:
        return

    if user_id not in user_data:
        user_data[user_id] = make_default_user(step="menu")

    user = user_data[user_id]

    if user["session"] is None:
        buttons = [
            [Button.inline("🚀 نصب Nova Self", b"start_gen_fast")]
        ]
        await event.respond(
            "🌟 **به ربات مدیریت NovaSelf خوش آمدید!**",
            buttons=buttons
        )
    else:
        await event.respond(
            "🔗 **پنل مدیریت NovaSelf**\n"
            "از طریق منوی زیر می‌توانید تنظیمات خود را مدیریت کنید:",
            buttons=get_main_menu_keyboard(user)
        )

@bot.on(events.NewMessage(pattern='/admin'))
async def admin_handler(event):
    """هندلر دستور /admin - فقط برای ادمین‌ها"""
    user_id = event.sender_id

    if not is_admin(user_id):
        await event.respond("❌ شما دسترسی ادمین ندارید!")
        return

    await event.respond(
        "👑 **پنل مدیریت NovaSelf**\n\n"
        "به پنل ادمین خوش آمدید! از طریق منوی زیر می‌توانید کاربران را مدیریت کنید:",
        buttons=get_admin_main_menu()
    )

@bot.on(events.CallbackQuery)
async def callback_handler(event):
    user_id = event.sender_id
    data = event.data

    if data == b"void":
        await event.answer()
        return

    if not click_debouncer.should_process(user_id, data):
        await event.answer()  # کلیک تکراری/سریع؛ بی‌صدا نادیده گرفته می‌شود
        return

    # ====== منوی ادمین ======
    if is_admin(user_id):
        # پنل ادمین
        if data == b"admin_panel":
            await safe_edit(event,
                "👑 **پنل مدیریت NovaSelf**\n\n"
                "از طریق منوی زیر می‌توانید کاربران را مدیریت کنید:",
                buttons=get_admin_main_menu()
            )
            return

        # آمار کاربران
        if data == b"admin_stats":
            total, active = get_user_stats()
            await safe_edit(event,
                f"📊 **آمار کاربران:**\n\n"
                f"👥 تعداد کل کاربران: {total}\n"
                f"🟢 کاربران فعال: {active}\n"
                f"🔴 کاربران غیرفعال: {total - active}\n\n"
                f"🕐 آخرین بروزرسانی: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                buttons=[Button.inline("🔙 بازگشت", b"admin_panel")]
            )
            return

        # لیست کاربران
        if data == b"admin_users_list":
            buttons = get_users_list_page(0)
            await safe_edit(event,
                "📋 **لیست کاربران:**\n\n"
                "برای مشاهده جزئیات هر کاربر روی آن کلیک کنید:",
                buttons=buttons
            )
            return

        # صفحه‌بندی لیست کاربران
        if data.startswith(b"admin_users_page_"):
            page = int(data.decode().split("_")[3])
            buttons = get_users_list_page(page)
            await safe_edit(event,
                "📋 **لیست کاربران:**\n\n"
                "برای مشاهده جزئیات هر کاربر روی آن کلیک کنید:",
                buttons=buttons
            )
            return

        # مشاهده جزئیات کاربر
        if data.startswith(b"admin_view_user_"):
            target_id = int(data.decode().split("_")[3])
            if target_id in user_data:
                user = user_data[target_id]

                status_text = status_icon(user["status"])
                font_name = FONT_NAMES.get(user["font_id"], "نامشخص")
                action_name = ACTIONS.get(user["active_action"], ("هیچ",))[0] if user["active_action"] != "none" else "هیچ"
                date_text = (
                    f"{status_icon(True)} {DATE_TYPE_NAMES.get(user.get('date_type', 'shamsi'), '؟')}"
                    if user.get("date_enabled") else status_icon(False)
                )
                textmode_text = TEXTMODE_NAMES.get(user.get("text_mode", 0), "خاموش") if user.get("text_mode") else "خاموش"
                secretary_text = (
                    f"{status_icon(True)} ({user.get('secretary_delay', 60)} ثانیه)"
                    if user.get("secretary_enabled") else status_icon(False)
                )
                username_display = f"@{user.get('username')}" if user.get("username") else "ثبت نشده"

                await safe_edit(event,
                    f"👤 **جزئیات کاربر:**\n\n"
                    f"🆔 شناسه: `{target_id}`\n"
                    f"💡 یوزرنیم: {username_display}\n"
                    f"📊 وضعیت: {status_text}\n"
                    f"💎 موجودی الماس: {format_diamonds(user.get('diamonds', 0))} ({format_toman(user.get('diamonds', 0))} تومان)\n"
                    f"👥 تعداد رفرال: {user.get('referral_count', 0)}\n"
                    f"🔤 فونت: {font_name}\n"
                    f"⌚ ساعت نام: {status_icon(user['name_time'])}\n"
                    f"⌚ ساعت بیو: {status_icon(user['bio_time'])}\n"
                    f"📅 تاریخ: {date_text}\n"
                    f"🖊️ حالت متن: {textmode_text}\n"
                    f"🧑‍💼 منشی پیوی: {secretary_text}\n"
                    f"🎭 اکشن: {action_name}\n"
                    f"📅 تاریخ ثبت: {user.get('joined_at', 'نامشخص')}\n\n"
                    f"💡 برای مدیریت این کاربر از دکمه‌های زیر استفاده کنید:",
                    buttons=get_user_detail_buttons(target_id)
                )
            else:
                await event.answer("❌ کاربر پیدا نشد!", alert=True)
            return

        # تغییر وضعیت کاربر توسط ادمین
        if data.startswith(b"admin_toggle_user_"):
            target_id = int(data.decode().split("_")[3])
            if target_id in user_data:
                user = user_data[target_id]
                user["status"] = not user["status"]

                if user["status"]:
                    if float(user.get("diamonds", 0)) <= 0:
                        user["status"] = False
                        await event.answer("💎 موجودی الماس این کاربر کافی نیست.", alert=True)
                    else:
                        client = await start_self_client(target_id, user["session"])
                        if not client:
                            user["status"] = False
                            await event.answer("❌ خطا در راه‌اندازی (نشست نامعتبر است)", alert=True)
                        else:
                            await event.answer("✅ وضعیت کاربر تغییر کرد!", alert=True)
                else:
                    await stop_self_client(target_id)
                    await event.answer("✅ وضعیت کاربر تغییر کرد!", alert=True)

                save_user(target_id, user)
                log_admin_action(user_id, target_id, "toggle_status", f"new_status={user['status']}")

                await safe_edit(event,
                    f"👤 **جزئیات کاربر:**\n\n"
                    f"🆔 شناسه: `{target_id}`\n"
                    f"📊 وضعیت جدید: {status_icon(user['status'])}",
                    buttons=get_user_detail_buttons(target_id)
                )
            return

        # حذف کاربر توسط ادمین
        if data.startswith(b"admin_delete_user_"):
            target_id = int(data.decode().split("_")[3])
            if target_id in user_data:
                await stop_self_client(target_id)
                delete_user_db(target_id)
                del user_data[target_id]
                log_admin_action(user_id, target_id, "delete_user", "")

                await event.answer("✅ کاربر حذف شد!", alert=True)
                await safe_edit(event,
                    "🗑️ **کاربر با موفقیت حذف شد.**",
                    buttons=[Button.inline("🔙 بازگشت به لیست", b"admin_users_list")]
                )
            return

        # ارسال پیام به کاربر خاص
        if data.startswith(b"admin_send_to_user_"):
            target_id = int(data.decode().split("_")[4])
            broadcast_data[user_id] = {
                "type": "single",
                "target_id": target_id,
                "step": "get_message"
            }
            await safe_edit(event,
                f"📨 **ارسال پیام به کاربر {target_id}**\n\n"
                "لطفاً پیام خود را به صورت متن ارسال کنید.\n"
                "برای لغو عملیات، /cancel را بفرستید."
            )
            return

        # ارسال پیام همگانی
        if data == b"admin_broadcast":
            broadcast_data[user_id] = {
                "type": "broadcast",
                "step": "get_message"
            }
            await safe_edit(event,
                "📨 **ارسال پیام همگانی**\n\n"
                "⚠️ این پیام برای **همه کاربران** ارسال خواهد شد!\n\n"
                "لطفاً پیام خود را به صورت متن ارسال کنید.\n"
                "برای لغو عملیات، /cancel را بفرستید."
            )
            return

        # جستجوی کاربر
        if data == b"admin_search_user":
            broadcast_data[user_id] = {
                "type": "search",
                "step": "get_user_id"
            }
            await safe_edit(event,
                "🔍 **جستجوی کاربر**\n\n"
                "لطفاً شناسه (ID) کاربر مورد نظر را وارد کنید:"
            )
            return

        # نمایش لاگ‌های مدیریتی اخیر
        if data == b"admin_logs":
            logs = get_recent_admin_logs(15)
            if not logs:
                log_text = "📜 **لاگ مدیریتی**\n\nهنوز هیچ عملیاتی ثبت نشده است."
            else:
                lines = ["📜 **۱۵ عملیات مدیریتی اخیر:**\n"]
                for admin_id_l, target_id_l, action_l, details_l, created_at_l in logs:
                    ts = created_at_l.strftime("%Y-%m-%d %H:%M") if created_at_l else "؟"
                    lines.append(f"▫️ [{ts}] ادمین {admin_id_l} ← کاربر {target_id_l} | {action_l} {details_l}")
                log_text = "\n".join(lines)
            await safe_edit(event, log_text, buttons=[Button.inline("🔙 بازگشت", b"admin_panel")])
            return

        # افزایش الماس
        if data.startswith(b"admin_add_diamond_"):
            target_id = int(data.decode().split("_")[3])
            admin_action_data[user_id] = {"type": "add_diamond", "target_id": target_id, "step": "get_amount"}
            await safe_edit(event,
                f"➕ **افزایش الماس کاربر {target_id}**\n\n"
                "لطفاً مقدار الماس موردنظر برای افزایش را وارد کنید (عدد مثبت):"
            )
            return

        # کاهش الماس
        if data.startswith(b"admin_sub_diamond_"):
            target_id = int(data.decode().split("_")[3])
            admin_action_data[user_id] = {"type": "sub_diamond", "target_id": target_id, "step": "get_amount"}
            await safe_edit(event,
                f"➖ **کاهش الماس کاربر {target_id}**\n\n"
                "لطفاً مقدار الماس موردنظر برای کاهش را وارد کنید (عدد مثبت):"
            )
            return

        # تغییر تعداد رفرال
        if data.startswith(b"admin_set_referral_"):
            target_id = int(data.decode().split("_")[3])
            admin_action_data[user_id] = {"type": "set_referral", "target_id": target_id, "step": "get_amount"}
            await safe_edit(event,
                f"👥 **تغییر تعداد رفرال کاربر {target_id}**\n\n"
                "لطفاً تعداد رفرال جدید را وارد کنید (عدد صفر یا مثبت):"
            )
            return

        # بروزرسانی همه کاربران
        if data == b"admin_refresh_all":
            await safe_edit(event, "⏳ در حال بروزرسانی اطلاعات همه کاربران...")

            for uid, user in list(user_data.items()):
                if user["status"] and user["session"]:
                    await stop_self_client(uid)
                    client = await start_self_client(uid, user["session"])
                    if not client:
                        user["status"] = False
                        save_user(uid, user)
                        logging.error(f"❌ خطا در بروزرسانی کاربر {uid}")

            await safe_edit(event,
                "✅ **همه کاربران با موفقیت بروزرسانی شدند!**",
                buttons=[Button.inline("🔙 بازگشت", b"admin_panel")]
            )
            return

    # ====== منوی کاربر ======

    if data == b"start_gen_fast":
        generator_data[user_id] = {
            "step": "get_phone",
            "phone": None,
            "phone_code_hash": None,
            "code_buffer": ""
        }
        await safe_edit(event,
            "📞 **مرحله اول: وارد کردن شماره**\n\n"
            "لطفاً شماره تلفن خود را به همراه کد کشور وارد کنید.\n"
            "مثال: `+989123456789`"
        )
        return

    if user_id in generator_data and generator_data[user_id]["step"] == "get_code":
        generator = generator_data[user_id]

        if data.startswith(b"k_"):
            action = data.decode().split("_")[1]

            if action.isdigit():
                if len(generator["code_buffer"]) < 5:
                    generator["code_buffer"] += action

                await safe_edit(event,
                    "📩 **مرحله دوم: وارد کردن کد تایید**\n\n"
                    "کد ۵ رقمی ارسال شده به تلگرام خود را وارد کنید:",
                    buttons=get_code_keyboard(generator["code_buffer"])
                )

            elif action == "clear":
                generator["code_buffer"] = ""
                await safe_edit(event,
                    "📩 **مرحله دوم: وارد کردن کد تایید**\n\n"
                    "کد ۵ رقمی ارسال شده به تلگرام خود را وارد کنید:",
                    buttons=get_code_keyboard(generator["code_buffer"])
                )

            elif action == "submit":
                if len(generator["code_buffer"]) < 5:
                    await event.answer("⚠️ لطفاً کد ۵ رقمی را کامل وارد کنید!", alert=True)
                    return

                await safe_edit(event, "⏳ در حال بررسی کد و ورود به حساب...")
                await process_code_signin(event, user_id, generator["code_buffer"])

            return

    if user_id not in user_data:
        return

    user = user_data[user_id]

    if data == b"back_to_main":
        await safe_edit(event,
            "🔗 **پنل مدیریت NovaSelf**\n"
            "از طریق منوی زیر می‌توانید تنظیمات خود را مدیریت کنید:",
            buttons=get_main_menu_keyboard(user)
        )
        return

    if data == b"menu_time":
        await safe_edit(event,
            get_time_menu_text(user),
            buttons=get_time_menu_keyboard(user)
        )
        return

    if data == b"menu_fonts":
        await safe_edit(event,
            get_fonts_menu_text(user),
            buttons=get_fonts_menu_keyboard(user["font_id"])
        )
        return

    if data == b"menu_actions":
        await safe_edit(event,
            "🎭 **مدیریت اکشن‌های فیک**\n\n"
            "با انتخاب هر گزینه، وضعیت شما به‌صورت مداوم برای دیگران نمایش داده می‌شود:",
            buttons=get_actions_menu_keyboard(user["active_action"])
        )
        return

    if data == b"menu_date":
        await safe_edit(event,
            get_date_menu_text(user),
            buttons=get_date_menu_keyboard(user)
        )
        return

    if data == b"toggle_date_enabled":
        user["date_enabled"] = not user.get("date_enabled", False)
        save_user(user_id, user)
        log_settings_change(user_id, "date_enabled", user["date_enabled"])
        await safe_edit(event,
            get_date_menu_text(user),
            buttons=get_date_menu_keyboard(user)
        )
        return

    if data.startswith(b"setdatetype_"):
        date_type = data.decode().split("_", 1)[1]
        if date_type in DATE_TYPE_NAMES:
            user["date_type"] = date_type
            save_user(user_id, user)
            log_settings_change(user_id, "date_type", date_type)
        await safe_edit(event,
            get_date_menu_text(user),
            buttons=get_date_menu_keyboard(user)
        )
        return

    if data == b"menu_date_fonts":
        await safe_edit(event,
            get_date_fonts_menu_text(user),
            buttons=get_date_fonts_menu_keyboard(user.get("date_font", 1))
        )
        return

    if data.startswith(b"setdatefont_"):
        font_id = int(data.decode().split("_")[1])
        user["date_font"] = font_id
        save_user(user_id, user)
        log_settings_change(user_id, "date_font", font_id)
        await safe_edit(event,
            get_date_fonts_menu_text(user),
            buttons=get_date_fonts_menu_keyboard(font_id)
        )
        return

    if data == b"menu_textmode":
        await safe_edit(event,
            "🖊️ **حالت متن**\n\n"
            "با انتخاب یکی از حالت‌های زیر، تمام پیام‌های متنی شما بلافاصله پس از ارسال "
            "با همان قالب ویرایش می‌شوند. برای غیرفعال کردن، دوباره روی گزینه فعال بزنید.",
            buttons=get_textmode_menu_keyboard(user.get("text_mode", 0))
        )
        return

    if data.startswith(b"settextmode_"):
        mode_id = int(data.decode().split("_")[1])
        if user.get("text_mode") == mode_id:
            user["text_mode"] = 0
        else:
            user["text_mode"] = mode_id
        save_user(user_id, user)
        await safe_edit(event,
            "🖊️ **حالت متن**\n\n"
            "✅ حالت متن با موفقیت بروزرسانی شد.",
            buttons=get_textmode_menu_keyboard(user.get("text_mode", 0))
        )
        return

    if data.startswith(b"setfont_"):
        font_id = int(data.decode().split("_")[1])
        user["font_id"] = font_id
        save_user(user_id, user)
        log_settings_change(user_id, "font_id", font_id)

        await safe_edit(event,
            get_fonts_menu_text(user),
            buttons=get_fonts_menu_keyboard(font_id)
        )
        return

    if data.startswith(b"setact_"):
        action_key = data.decode().split("_")[1]

        if user["active_action"] == action_key:
            user["active_action"] = "none"
        else:
            user["active_action"] = action_key

        save_user(user_id, user)

        await safe_edit(event,
            "🎭 **مدیریت اکشن‌های فیک**\n\n"
            f"✅ وضعیت اکشن با موفقیت تغییر یافت.",
            buttons=get_actions_menu_keyboard(user["active_action"])
        )
        return

    if data == b"toggle_status":
        user["status"] = not user["status"]

        if user["status"]:
            if float(user.get("diamonds", 0)) <= 0:
                user["status"] = False
                await event.answer(
                    "💎 موجودی الماس شما کافی نیست.\n\nابتدا از بخش «حساب کاربری» موجودی خود را افزایش دهید.",
                    alert=True
                )
            else:
                client = await start_self_client(user_id, user["session"])
                if not client:
                    user["status"] = False
                    await event.answer("❌ نشست منقضی شده یا خطا در اتصال!", alert=True)
        else:
            await stop_self_client(user_id)

        save_user(user_id, user)
        log_self_toggle(user_id, user["status"])

        await safe_edit(event,
            "🔗 **پنل مدیریت NovaSelf**\n"
            "از طریق منوی زیر می‌توانید تنظیمات خود را مدیریت کنید:",
            buttons=get_main_menu_keyboard(user)
        )
        return

    if data == b"toggle_name_time":
        user["name_time"] = not user["name_time"]
        save_user(user_id, user)
        log_settings_change(user_id, "name_time", user["name_time"])

        await safe_edit(event,
            get_time_menu_text(user),
            buttons=get_time_menu_keyboard(user)
        )
        return

    if data == b"toggle_bio_time":
        user["bio_time"] = not user["bio_time"]
        save_user(user_id, user)
        log_settings_change(user_id, "bio_time", user["bio_time"])

        await safe_edit(event,
            get_time_menu_text(user),
            buttons=get_time_menu_keyboard(user)
        )
        return

    if data == b"menu_account":
        await safe_edit(event, get_account_text(user_id, user), buttons=get_account_keyboard())
        return

    if data == b"account_buy_diamond":
        await safe_edit(event,
            "💎 **خرید الماس**\n\n"
            "در حال حاضر درگاه پرداخت فعال نیست.\n\n"
            f"جهت خرید الماس با {SUPPORT_USERNAME} در تماس باشید.",
            buttons=[[Button.inline("🔙 بازگشت", b"menu_account")]]
        )
        return

    if data == b"account_delete_confirm":
        await safe_edit(event,
            "⚠️ **هشدار**\n\n"
            "با حذف حساب کاربری، تمام اطلاعات شما شامل تنظیمات، سشن، داده‌های ذخیره‌شده و "
            "سایر اطلاعات (از جمله موجودی الماس و رفرال) به‌صورت دائمی از دیتابیس حذف خواهند شد.\n\n"
            "این عملیات غیرقابل بازگشت است.",
            buttons=get_account_delete_warning_keyboard()
        )
        return

    if data == b"account_delete_final":
        await stop_self_client(user_id)
        delete_user_db(user_id)
        del user_data[user_id]
        transfer_data.pop(user_id, None)

        await safe_edit(event,
            "🗑️ **حساب کاربری با موفقیت و به‌صورت کامل حذف شد.**\n\n"
            "برای شروع مجدد، دستور /start را ارسال کنید."
        )
        return

    if data == b"account_transfer_start":
        transfer_data[user_id] = {}
        user["step"] = "transfer_get_target"
        await safe_edit(event,
            "💸 **انتقال الماس**\n\n"
            "لطفاً آیدی عددی کاربر مقصد را ارسال کنید:",
            buttons=get_transfer_cancel_keyboard()
        )
        return

    if data == b"transfer_cancel":
        transfer_data.pop(user_id, None)
        user["step"] = "managed"
        await safe_edit(event, get_account_text(user_id, user), buttons=get_account_keyboard())
        return

    if data == b"transfer_confirm_execute":
        pending = transfer_data.get(user_id)
        if not pending or "target_id" not in pending or "amount" not in pending:
            await event.answer("❌ اطلاعات انتقال یافت نشد، دوباره تلاش کنید.", alert=True)
            return

        target_id = pending["target_id"]
        amount = pending["amount"]

        success, message, sender_balance, receiver_balance = transfer_diamonds_db(user_id, target_id, amount)

        if success:
            if user_id in user_data:
                user_data[user_id]["diamonds"] = sender_balance
            if target_id in user_data:
                user_data[target_id]["diamonds"] = receiver_balance

            transfer_data.pop(user_id, None)
            user["step"] = "managed"
            log_diamond_transfer(user_id, target_id, amount)

            when = datetime.now()
            sender_username = user.get("username")
            sender_label = f"@{sender_username}" if sender_username else f"`{user_id}`"
            receiver_user = user_data.get(target_id, {})
            receiver_username = receiver_user.get("username")
            receiver_label = f"@{receiver_username}" if receiver_username else f"`{target_id}`"
            amount_str = format_diamonds(amount)

            # --- رسید فرستنده (روی همین پیام) ---
            await safe_edit(event,
                build_sender_receipt(receiver_label, amount_str, format_diamonds(sender_balance), when),
                buttons=[[Button.inline("🔙 بازگشت به حساب کاربری", b"menu_account")]]
            )

            # --- رسید گیرنده (پیام جداگانه به خودش، اگر قبلاً با ربات استارت زده باشد) ---
            try:
                await safe_call(
                    bot.send_message, target_id,
                    build_receiver_receipt(sender_label, amount_str, format_diamonds(receiver_balance), when)
                )
            except Exception as e:
                log_internal_error("receiver_receipt_send", e)
        else:
            await safe_edit(event,
                f"{message}",
                buttons=[[Button.inline("🔙 بازگشت به حساب کاربری", b"menu_account")]]
            )
            transfer_data.pop(user_id, None)
            user["step"] = "managed"
        return

    if data == b"menu_tag":
        await safe_edit(event, get_tag_menu_text(), buttons=get_tag_menu_keyboard())
        return

    if data == b"menu_secretary":
        await safe_edit(event, get_secretary_menu_text(user), buttons=get_secretary_menu_keyboard(user))
        return

    if data == b"secretary_on":
        user["secretary_enabled"] = True
        save_user(user_id, user)
        log_settings_change(user_id, "secretary_enabled", True)
        await safe_edit(event, get_secretary_menu_text(user), buttons=get_secretary_menu_keyboard(user))
        return

    if data == b"secretary_off":
        user["secretary_enabled"] = False
        save_user(user_id, user)
        log_settings_change(user_id, "secretary_enabled", False)
        await safe_edit(event, get_secretary_menu_text(user), buttons=get_secretary_menu_keyboard(user))
        return

    if data == b"secretary_set_text":
        user["step"] = "secretary_get_text"
        await safe_edit(event,
            "📝 متن موردنظر خود را ارسال کنید.\n\n"
            "این متن جایگزین پیام پیش‌فرض منشی می‌شود."
        )
        return

    if data == b"secretary_set_time":
        user["step"] = "secretary_get_time"
        await safe_edit(event,
            "⏱️ لطفاً زمان تأخیر پاسخ منشی را بر حسب **ثانیه** ارسال کنید.\n\n"
            "نمونه:\n"
            "▫️ ۱ دقیقه = 60\n"
            "▫️ ۵ دقیقه = 300\n"
            "▫️ ۱۰ دقیقه = 600"
        )
        return

# ======================== پردازش ورود با کد ========================
async def process_code_signin(event, user_id, code):
    generator = generator_data[user_id]
    client = active_signins.get(user_id)

    if not client:
        await event.respond("❌ نشست منقضی شده است. لطفاً مجدداً /start را بزنید.")
        del generator_data[user_id]
        return

    try:
        await client.sign_in(generator["phone"], code, phone_code_hash=generator["phone_code_hash"])
        session_string = client.session.save()

        user_data[user_id] = make_default_user(session=session_string, status=True, step="managed")
        save_user(user_id, user_data[user_id])
        register_active_client(user_id, client)

        await event.respond(
            "✅ **ورود با موفقیت انجام شد!**\n\n"
            "▫️ حساب شما به ربات متصل شد.\n"
            "▫️ اطلاعات در دیتابیس ابری ذخیره شد.\n"
            "▫️ سلف شما هم‌اکنون فعال است."
        )

        del generator_data[user_id]
        if user_id in active_signins:
            del active_signins[user_id]

        await event.respond(
            "🔗 **پنل مدیریت NovaSelf**\n"
            "از طریق منوی زیر می‌توانید تنظیمات خود را مدیریت کنید:",
            buttons=get_main_menu_keyboard(user_data[user_id])
        )

    except SessionPasswordNeededError:
        generator["step"] = "get_password"
        await event.respond(
            "🔐 **تایید دو مرحله‌ای فعال است!**\n\n"
            "لطفاً رمز عبور دو مرحله‌ای حساب خود را وارد کنید:"
        )
    except Exception as e:
        generator["code_buffer"] = ""
        await event.respond(
            f"❌ **خطا در ورود:**\n\n`{str(e)}`\n\n"
            "لطفاً مجدداً تلاش کنید:"
        )
        await event.respond(
            "📩 کد تایید را مجدداً وارد کنید:",
            buttons=get_code_keyboard("")
        )

# ======================== هندلر پیام‌های متنی ========================
@bot.on(events.NewMessage)
async def message_handler(event):
    user_id = event.sender_id
    text = event.text.strip() if event.text else ""

    # لغو عملیات
    _pending_steps = {
        "transfer_get_target", "transfer_get_amount", "transfer_confirm",
        "secretary_get_text", "secretary_get_time"
    }
    _has_pending_step = user_id in user_data and user_data[user_id].get("step") in _pending_steps

    if text == "/cancel" and (user_id in broadcast_data or user_id in admin_action_data or _has_pending_step):
        broadcast_data.pop(user_id, None)
        admin_action_data.pop(user_id, None)
        transfer_data.pop(user_id, None)
        if user_id in user_data:
            user_data[user_id]["step"] = "managed"
        await event.respond("❌ عملیات لغو شد.")
        if is_admin(user_id):
            await event.respond("👑 پنل ادمین:", buttons=get_admin_main_menu())
        return

    # ====== پردازش عملیات مدیریتی الماس/رفرال ======
    if user_id in admin_action_data and is_admin(user_id):
        action = admin_action_data[user_id]
        target_id = action["target_id"]

        try:
            amount = float(text)
        except (TypeError, ValueError):
            await event.respond("❌ لطفاً یک عدد معتبر ارسال کنید.")
            return

        if action["type"] in ("add_diamond", "sub_diamond"):
            if amount <= 0:
                await event.respond("❌ مقدار باید بیشتر از صفر باشد.")
                return

            signed_amount = amount if action["type"] == "add_diamond" else -amount
            success, new_balance = admin_adjust_diamonds_db(target_id, signed_amount)

            if not success:
                await event.respond("❌ کاربر پیدا نشد یا خطایی در دیتابیس رخ داد.")
                del admin_action_data[user_id]
                return

            if target_id in user_data:
                user_data[target_id]["diamonds"] = new_balance

            action_label = "افزایش" if action["type"] == "add_diamond" else "کاهش"
            log_admin_action(user_id, target_id, f"{action_label} الماس", f"مقدار: {amount}")

            await event.respond(
                f"✅ موجودی الماس کاربر {target_id} با موفقیت {action_label} یافت.\n"
                f"💎 موجودی جدید: {format_diamonds(new_balance)}"
            )

        elif action["type"] == "set_referral":
            if amount < 0:
                await event.respond("❌ تعداد رفرال نمی‌تواند منفی باشد.")
                return

            success, new_count = admin_set_referral_db(target_id, int(amount))
            if not success:
                await event.respond("❌ کاربر پیدا نشد یا خطایی در دیتابیس رخ داد.")
                del admin_action_data[user_id]
                return

            if target_id in user_data:
                user_data[target_id]["referral_count"] = new_count

            log_admin_action(user_id, target_id, "تغییر تعداد رفرال", f"مقدار جدید: {new_count}")

            await event.respond(f"✅ تعداد رفرال کاربر {target_id} به {new_count} تغییر یافت.")

        del admin_action_data[user_id]

        if target_id in user_data:
            await event.respond(
                "👤 برای مشاهده جزئیات بروزرسانی‌شده:",
                buttons=get_user_detail_buttons(target_id)
            )
        return

    # ====== پردازش پیام همگانی ======
    if user_id in broadcast_data and is_admin(user_id):
        broadcast = broadcast_data[user_id]

        if broadcast.get("type") == "search" and broadcast.get("step") == "get_user_id":
            try:
                target_id = int(text)
                if target_id in user_data:
                    await event.respond(
                        f"✅ کاربر {target_id} پیدا شد!",
                        buttons=get_user_detail_buttons(target_id)
                    )
                else:
                    await event.respond("❌ کاربر پیدا نشد!")
                del broadcast_data[user_id]
            except ValueError:
                await event.respond("❌ شناسه معتبر نیست. لطفاً یک عدد وارد کنید.")
            return

        if broadcast.get("step") == "get_message":
            broadcast["message"] = text
            broadcast["step"] = "confirm"

            if broadcast["type"] == "single":
                target_id = broadcast["target_id"]
                await event.respond(
                    f"📨 **تایید ارسال پیام به کاربر {target_id}**\n\n"
                    f"📝 متن پیام:\n"
                    f"---\n{text}\n---\n\n"
                    "آیا از ارسال این پیام مطمئن هستید؟",
                    buttons=[
                        [Button.inline("✅ بله، ارسال کن", b"broadcast_confirm")],
                        [Button.inline("❌ لغو", b"broadcast_cancel")]
                    ]
                )
            else:
                total_users, _ = get_user_stats()
                await event.respond(
                    f"📨 **تایید ارسال پیام همگانی**\n\n"
                    f"⚠️ این پیام برای **{total_users} نفر** ارسال خواهد شد!\n\n"
                    f"📝 متن پیام:\n"
                    f"---\n{text}\n---\n\n"
                    "آیا از ارسال این پیام مطمئن هستید؟",
                    buttons=[
                        [Button.inline("✅ بله، ارسال کن", b"broadcast_confirm")],
                        [Button.inline("❌ لغو", b"broadcast_cancel")]
                    ]
                )
            return

    # ====== پردازش ساخت خودکار حساب ======
    if user_id in generator_data:
        generator = generator_data[user_id]

        if generator["step"] == "get_phone":
            generator["phone"] = text

            await event.respond("⏳ در حال اتصال به سرورهای تلگرام...")

            try:
                client = TelegramClient(StringSession(), API_ID, API_HASH)
                await client.connect()

                send_code_result = await client.send_code_request(generator["phone"])
                active_signins[user_id] = client
                generator["phone_code_hash"] = send_code_result.phone_code_hash
                generator["step"] = "get_code"

                await event.respond(
                    "📩 **کد تایید ارسال شد!**\n\n"
                    "یک کد ۵ رقمی به تلگرام شما ارسال شده است.\n"
                    "لطفاً آن را از طریق دکمه‌های زیر وارد کنید:",
                    buttons=get_code_keyboard("")
                )
            except Exception as e:
                await event.respond(
                    f"❌ **خطا در ارسال کد:**\n\n`{str(e)}`\n\n"
                    "لطفاً مجدداً /start را بزنید و تلاش کنید."
                )
                if user_id in active_signins:
                    del active_signins[user_id]
                del generator_data[user_id]

            return

        if generator["step"] == "get_password":
            client = active_signins.get(user_id)

            if not client:
                await event.respond("❌ نشست منقضی شده است. لطفاً مجدداً /start را بزنید.")
                del generator_data[user_id]
                return

            try:
                await client.sign_in(password=text)
                session_string = client.session.save()

                user_data[user_id] = make_default_user(session=session_string, status=True, step="managed")
                save_user(user_id, user_data[user_id])
                register_active_client(user_id, client)

                await event.respond(
                    "✅ **ورود با رمز دو مرحله‌ای موفقیت‌آمیز بود!**\n\n"
                    "حساب شما با موفقیت به ربات متصل شد."
                )

                del generator_data[user_id]
                if user_id in active_signins:
                    del active_signins[user_id]

                await event.respond(
                    "🔗 **پنل مدیریت NovaSelf**\n"
                    "از طریق منوی زیر می‌توانید تنظیمات خود را مدیریت کنید:",
                    buttons=get_main_menu_keyboard(user_data[user_id])
                )
            except Exception as e:
                await event.respond(
                    f"❌ **رمز دو مرحله‌ای اشتباه است:**\n\n`{str(e)}`\n\n"
                    "لطفاً مجدداً رمز صحیح را وارد کنید:"
                )

            return

    # ====== دریافت سشن آماده ======
    # ====== تنظیم متن منشی ======
    if user_id in user_data and user_data[user_id].get("step") == "secretary_get_text":
        new_text = text if text else "مشغولم، بعداً پاسخ می‌دهم ✅"
        user_data[user_id]["secretary_text"] = new_text
        user_data[user_id]["step"] = "managed"
        save_user(user_id, user_data[user_id])

        await event.respond("✅ متن منشی با موفقیت ذخیره شد.")
        await event.respond(
            get_secretary_menu_text(user_data[user_id]),
            buttons=get_secretary_menu_keyboard(user_data[user_id])
        )
        return

    # ====== تنظیم تایم منشی ======
    if user_id in user_data and user_data[user_id].get("step") == "secretary_get_time":
        try:
            seconds = int(text)
            if seconds < 1 or seconds > 86400:
                raise ValueError
        except (ValueError, TypeError):
            await event.respond("❌ لطفاً یک عدد معتبر (بین 1 تا 86400) بر حسب ثانیه ارسال کنید.")
            return

        user_data[user_id]["secretary_delay"] = seconds
        user_data[user_id]["step"] = "managed"
        save_user(user_id, user_data[user_id])

        await event.respond(f"✅ زمان تأخیر منشی روی {seconds} ثانیه تنظیم شد.")
        await event.respond(
            get_secretary_menu_text(user_data[user_id]),
            buttons=get_secretary_menu_keyboard(user_data[user_id])
        )
        return

    # ====== انتقال الماس: مرحله اول (آیدی مقصد) ======
    if user_id in user_data and user_data[user_id].get("step") == "transfer_get_target":
        try:
            target_id = int(text)
        except ValueError:
            await event.respond("❌ آیدی عددی معتبر نیست. لطفاً فقط عدد ارسال کنید.", buttons=get_transfer_cancel_keyboard())
            return

        if target_id == user_id:
            await event.respond("❌ انتقال به خودتان امکان‌پذیر نیست.", buttons=get_transfer_cancel_keyboard())
            return

        if target_id not in user_data or not user_data[target_id].get("session"):
            await event.respond("❌ کاربری با این آیدی در سیستم ثبت‌نام نکرده است.", buttons=get_transfer_cancel_keyboard())
            return

        transfer_data[user_id] = {"target_id": target_id}
        user_data[user_id]["step"] = "transfer_get_amount"

        await event.respond(
            f"✅ کاربر مقصد یافت شد: `{target_id}`\n\n"
            "💎 حالا مقدار الماس موردنظر برای انتقال را وارد کنید:",
            buttons=get_transfer_cancel_keyboard()
        )
        return

    # ====== انتقال الماس: مرحله دوم (مقدار) ======
    if user_id in user_data and user_data[user_id].get("step") == "transfer_get_amount":
        pending = transfer_data.get(user_id)
        if not pending or "target_id" not in pending:
            user_data[user_id]["step"] = "managed"
            await event.respond("❌ عملیات منقضی شده. دوباره از منوی حساب کاربری اقدام کنید.")
            return

        try:
            amount = float(text)
        except ValueError:
            await event.respond("❌ لطفاً فقط عدد ارسال کنید.", buttons=get_transfer_cancel_keyboard())
            return

        if amount <= 0:
            await event.respond("❌ مقدار انتقال باید بیشتر از صفر باشد.", buttons=get_transfer_cancel_keyboard())
            return

        current_balance = user_data[user_id].get("diamonds", 0)
        if current_balance < amount:
            await event.respond(
                f"❌ موجودی شما کافی نیست.\n💎 موجودی فعلی: {format_diamonds(current_balance)}",
                buttons=get_transfer_cancel_keyboard()
            )
            return

        target_id = pending["target_id"]
        transfer_data[user_id]["amount"] = amount
        user_data[user_id]["step"] = "transfer_confirm"

        new_sender_balance = current_balance - amount
        target_balance = user_data.get(target_id, {}).get("diamonds", 0)
        new_receiver_balance = target_balance + amount

        await event.respond(
            "🧾 **تایید انتقال الماس**\n\n"
            f"👤 فرستنده: `{user_id}`\n"
            f"👤 گیرنده: `{target_id}`\n\n"
            f"💎 تعداد الماس: {format_diamonds(amount)}\n\n"
            f"موجودی فعلی شما: {format_diamonds(current_balance)}\n"
            f"موجودی شما پس از انتقال: {format_diamonds(new_sender_balance)}\n\n"
            "آیا از انجام این انتقال مطمئن هستید؟",
            buttons=get_transfer_confirm_keyboard()
        )
        return

    if user_id in user_data and user_data[user_id].get("step") == "get_session":
        # روش قدیمی «ثبت با سشن آماده» به‌طور کامل حذف شده است.
        return

# ======================== هندلر دکمه‌های تایید ارسال پیام ========================
@bot.on(events.CallbackQuery)
async def broadcast_callback_handler(event):
    user_id = event.sender_id
    data = event.data

    if not is_admin(user_id):
        await event.answer("❌ شما دسترسی ادمین ندارید!", alert=True)
        return

    if user_id not in broadcast_data:
        await event.answer("❌ عملیات فعالی وجود ندارد!", alert=True)
        return

    broadcast = broadcast_data[user_id]

    if data == b"broadcast_confirm":
        await safe_edit(event, "⏳ در حال ارسال پیام...")

        message = broadcast["message"]

        if broadcast["type"] == "single":
            target_id = broadcast["target_id"]
            try:
                await bot.send_message(target_id, message)
                await safe_edit(event,
                    f"✅ **پیام با موفقیت به کاربر {target_id} ارسال شد!**",
                    buttons=[Button.inline("🔙 بازگشت به پنل", b"admin_panel")]
                )
            except Exception as e:
                await safe_edit(event,
                    f"❌ **خطا در ارسال پیام:**\n\n`{str(e)}`",
                    buttons=[Button.inline("🔙 بازگشت", b"admin_panel")]
                )

        else:
            total_users = len(user_data)
            success_count = 0
            fail_count = 0

            for uid in user_data.keys():
                try:
                    await bot.send_message(uid, message)
                    success_count += 1
                    await asyncio.sleep(0.1)
                except Exception as e:
                    fail_count += 1
                    logging.error(f"❌ خطا در ارسال به {uid}: {e}")

            await safe_edit(event,
                f"✅ **ارسال پیام همگانی کامل شد!**\n\n"
                f"📨 تعداد کل: {total_users}\n"
                f"✅ موفق: {success_count}\n"
                f"❌ ناموفق: {fail_count}",
                buttons=[Button.inline("🔙 بازگشت به پنل", b"admin_panel")]
            )

        del broadcast_data[user_id]
        return

    elif data == b"broadcast_cancel":
        del broadcast_data[user_id]
        await safe_edit(event,
            "❌ **ارسال پیام لغو شد.**",
            buttons=[Button.inline("🔙 بازگشت به پنل", b"admin_panel")]
        )
        return

# ======================== اجرای اصلی ========================
if __name__ == "__main__":
    logging.info("🚀 راه‌اندازی ربات NovaSelf...")

    init_db()
    user_data = get_all_users()
    logging.info(f"📊 تعداد کاربران بارگذاری شده: {len(user_data)}")

    loop = asyncio.get_event_loop()
    loop.create_task(autostart_saved_users())

    webapp_app = create_webapp_app(
        bot_token=BOT_TOKEN,
        user_data=user_data,
        save_user=save_user,
        start_self_client=start_self_client,
        stop_self_client=stop_self_client,
        format_diamonds=format_diamonds,
        diamond_rate_per_hour=DIAMOND_RATE_PER_HOUR,
        allowed_origin=MINIAPP_ORIGIN,
    )
    loop.create_task(run_webapp_server(webapp_app, host="0.0.0.0", port=PORT))

    logging.info("✅ ربات با موفقیت راه‌اندازی شد!")
    logging.info(f"👑 تعداد ادمین‌ها: {len(ADMIN_IDS)}")

    bot.run_until_disconnected()
