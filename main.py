import asyncio
import os
import pytz
import psycopg2
import jdatetime
from hijridate import Gregorian
from psycopg2.extras import DictCursor
from datetime import datetime
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

# ======================== تنظیمات اولیه ========================
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_IDS = [int(id.strip()) for id in os.environ.get("ADMIN_IDS", "").split(",") if id.strip()]

if not all([API_ID, API_HASH, BOT_TOKEN, DATABASE_URL]):
    raise ValueError("تمامی متغیرهای محیطی باید تنظیم شوند!")

if not ADMIN_IDS:
    logging.warning("⚠️ هشدار: هیچ ادمینی تنظیم نشده است!")

bot = TelegramClient('helper_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ======================== دیکشنری‌های عمومی ========================
active_clients = {}
generator_data = {}
active_signins = {}
user_data = {}
broadcast_data = {}
secretary_state = {}   # {user_id: {peer_id: {"replied": bool, "task": Task}}}
_auto_sent_marks = set()  # {(user_id, chat_id, message_id)} پیام‌هایی که خودمان خودکار فرستادیم (نباید توسط حالت متن ادیت شوند)

TAG_ADMIN_TRIGGERS = {".تگ_ادمین", ".تگادمین", ".tagadmins"}
TAG_MEMBERS_TRIGGERS = {".تگ_اعضا", ".تگاعضا", ".tagall"}

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
        ]
        for col_name, col_def in migration_columns:
            try:
                cursor.execute(f"ALTER TABLE novaself_users ADD COLUMN IF NOT EXISTS {col_name} {col_def}")
                conn.commit()
            except Exception as e:
                conn.rollback()
                logging.error(f"❌ خطا در افزودن ستون {col_name}: {e}")

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
                   secretary_enabled, secretary_text, secretary_delay
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
                "joined_at": row['joined_at'] or datetime.now(),
                "step": "managed",
                "task": None,
                "action_task": None
            }
        return data
    except Exception as e:
        logging.error(f"❌ خطا در بارگذاری کاربران: {e}")
        return {}

def save_user(user_id, user):
    """ذخیره یکجای تمام تنظیمات کاربر (جلوگیری از باگ‌های ناشی از آرگومان‌های جداگانه)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO novaself_users
                (user_id, session, font_id, status, name_time, bio_time, active_action,
                 date_enabled, date_type, date_font, text_mode,
                 secretary_enabled, secretary_text, secretary_delay)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            user.get("secretary_delay", 60)
        ))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logging.error(f"❌ خطا در ذخیره کاربر {user_id}: {e}")

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
        "task": None,
        "action_task": None,
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
    status_text = "🟢 فعال" if user["status"] else "🔴 غیرفعال"
    return [
        [Button.inline(f"وضعیت سلف: {status_text}", b"toggle_status")],
        [
            Button.inline("📅 تاریخ", b"menu_date"),
            Button.inline("🎭 اکشن", b"menu_actions"),
            Button.inline("⌚ ساعت", b"menu_time"),
        ],
        [
            Button.inline("🖊️ حالت متن", b"menu_textmode"),
            Button.inline("🏷️ تگ", b"menu_tag"),
        ],
        [Button.inline("🧑‍💼 منشی", b"menu_secretary")],
        [Button.inline("🗑️ حذف اکانت", b"delete_account")]
    ]

def get_time_menu_keyboard(user):
    name_status = "✅ فعال" if user["name_time"] else "❌ غیرفعال"
    bio_status = "✅ فعال" if user["bio_time"] else "❌ غیرفعال"
    current_font = FONT_NAMES.get(user["font_id"], "بولد")

    return [
        [Button.inline(f"نمایش در نام: {name_status}", b"toggle_name_time")],
        [Button.inline(f"نمایش در بیو: {bio_status}", b"toggle_bio_time")],
        [Button.inline(f"🔤 تغییر فونت: {current_font}", b"menu_fonts")],
        [Button.inline("🔙 بازگشت", b"back_to_main")]
    ]

def get_fonts_menu_keyboard(current_font_id):
    buttons = []
    row = []

    for font_id, font_name in FONT_NAMES.items():
        display = f"✅ {font_name}" if font_id == current_font_id else f"▫️ {font_name}"
        row.append(Button.inline(display, f"setfont_{font_id}".encode()))

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
        display = f"🟢 {action_name}" if action_key == current_action else f"⚪ {action_name}"
        row.append(Button.inline(display, f"setact_{action_key}".encode()))

        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([Button.inline("🔙 بازگشت", b"back_to_main")])
    return buttons

def get_date_menu_keyboard(user):
    enabled_status = "✅ فعال" if user.get("date_enabled") else "❌ غیرفعال"
    current_type = user.get("date_type", "shamsi")
    current_font = FONT_NAMES.get(user.get("date_font", 1), "بولد")

    type_row = []
    for type_key, type_name in DATE_TYPE_NAMES.items():
        display = f"✅ {type_name}" if type_key == current_type else f"▫️ {type_name}"
        type_row.append(Button.inline(display, f"setdatetype_{type_key}".encode()))

    return [
        [Button.inline(f"نمایش تاریخ در بیو: {enabled_status}", b"toggle_date_enabled")],
        type_row,
        [Button.inline(f"🔤 تغییر فونت تاریخ: {current_font}", b"menu_date_fonts")],
        [Button.inline("🔙 بازگشت", b"back_to_main")]
    ]

def get_date_fonts_menu_keyboard(current_font_id):
    buttons = []
    row = []

    for font_id, font_name in FONT_NAMES.items():
        display = f"✅ {font_name}" if font_id == current_font_id else f"▫️ {font_name}"
        row.append(Button.inline(display, f"setdatefont_{font_id}".encode()))

        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([Button.inline("🔙 بازگشت به تاریخ", b"menu_date")])
    return buttons

def get_textmode_menu_keyboard(current_mode):
    buttons = []
    row = []

    for mode_id, mode_name in TEXTMODE_NAMES.items():
        display = f"☑️ {mode_name}" if mode_id == current_mode else f"▫️ {mode_name}"
        row.append(Button.inline(display, f"settextmode_{mode_id}".encode()))

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
        "▫️ `.تگ_ادمین` — منشن تمام ادمین‌های همان گروه.\n"
        "▫️ `.تگ_اعضا` — منشن تمام اعضای همان گروه.\n\n"
        "نکات:\n"
        "▫️ فقط داخل گروه/سوپرگروه کار می‌کند و در چت خصوصی غیرفعال است.\n"
        "▫️ اگر دستور را روی پیامی ریپلای کنید، خروجی هم روی همان پیام ریپلای می‌شود.\n"
        "▫️ در گروه‌های بزرگ، پیام‌ها به چند بخش تقسیم می‌شوند تا محدودیت تلگرام رعایت شود."
    )

def get_tag_menu_keyboard():
    return [[Button.inline("🔙 بازگشت", b"back_to_main")]]

def get_secretary_menu_text(user):
    status = "🟢 فعال" if user.get("secretary_enabled") else "🔴 غیرفعال"
    delay = user.get("secretary_delay", 60)
    text_preview = user.get("secretary_text") or "مشغولم، بعداً پاسخ می‌دهم ✅"
    return (
        "🧑‍💼 **منشی**\n\n"
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
            Button.inline("☑️ روشن" if on else "▫️ روشن", b"secretary_on"),
            Button.inline("▫️ خاموش" if on else "☑️ خاموش", b"secretary_off"),
        ],
        [Button.inline("📝 تنظیم متن", b"secretary_set_text")],
        [Button.inline(f"⏱️ تنظیم تایم ({delay} ثانیه)", b"secretary_set_time")],
        [Button.inline("🔙 بازگشت", b"back_to_main")]
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
            status_icon = "🟢" if user[1] else "🔴"
            buttons.append([Button.inline(
                f"{status_icon} کاربر {user[0]}",
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

async def _send_mentions(event, users_list, header, user_id):
    """ساخت و ارسال پیام‌های منشن‌دار به‌صورت تکه‌تکه (رعایت محدودیت تلگرام + مدیریت FloodWait)."""
    if not users_list:
        return

    chunk_size = 25
    reply_to = event.reply_to_msg_id if event.is_reply else None

    for i in range(0, len(users_list), chunk_size):
        chunk = users_list[i:i + chunk_size]
        body = (header + "\n") if i == 0 else ""
        entities = []
        cursor = len(helpers.add_surrogate(body))

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

        for attempt in range(3):
            try:
                sent = await event.client.send_message(
                    event.chat_id, body, formatting_entities=entities,
                    reply_to=reply_to if i == 0 else None
                )
                _mark_auto_sent(user_id, sent.chat_id, sent.id)
                break
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 1)
            except RPCError as e:
                logging.error(f"⚠️ خطا در ارسال پیام تگ: {e}")
                break
            except Exception as e:
                logging.error(f"⚠️ خطای غیرمنتظره در ارسال تگ: {e}")
                break

        await asyncio.sleep(1.5)

async def handle_tag_admins(event, user_id):
    try:
        admins = await _gather_chat_admins(event)
        if not admins:
            await event.reply("❌ ادمینی برای منشن پیدا نشد یا دسترسی کافی برای دریافت لیست ادمین‌ها وجود ندارد.")
            return
        await _send_mentions(event, admins, "🔔 **تگ ادمین‌ها:**", user_id)
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

        await _send_mentions(event, members, "🔔 **تگ اعضا:**", user_id)
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
    """توقف کامل و امن کلاینت سلف یک کاربر (تسک‌ها + قطع اتصال + پاکسازی وضعیت منشی)."""
    user = user_data.get(user_id)
    if user:
        if user.get("task"):
            user["task"].cancel()
            user["task"] = None
        if user.get("action_task"):
            user["action_task"].cancel()
            user["action_task"] = None

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

async def autostart_saved_users():
    await asyncio.sleep(5)

    for user_id, user in list(user_data.items()):
        if user["status"] and user["session"]:
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
            [Button.inline("📱 ثبت خودکار با شماره", b"start_gen_fast")],
            [Button.inline("✍️ ثبت با سشن آماده", b"send_ready_session")]
        ]
        await event.respond(
            "🌟 **به ربات مدیریت NovaSelf خوش آمدید!**\n\n"
            "لطفاً یکی از روش‌های زیر را برای اتصال حساب خود انتخاب کنید:",
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

                status_text = "🟢 فعال" if user["status"] else "🔴 غیرفعال"
                font_name = FONT_NAMES.get(user["font_id"], "نامشخص")
                action_name = ACTIONS.get(user["active_action"], ("هیچ",))[0] if user["active_action"] != "none" else "هیچ"
                date_text = (
                    f"✅ {DATE_TYPE_NAMES.get(user.get('date_type', 'shamsi'), '؟')}"
                    if user.get("date_enabled") else "❌ غیرفعال"
                )
                textmode_text = TEXTMODE_NAMES.get(user.get("text_mode", 0), "خاموش") if user.get("text_mode") else "خاموش"
                secretary_text = (
                    f"✅ فعال ({user.get('secretary_delay', 60)} ثانیه)"
                    if user.get("secretary_enabled") else "❌ غیرفعال"
                )

                await safe_edit(event,
                    f"👤 **جزئیات کاربر:**\n\n"
                    f"🆔 شناسه: `{target_id}`\n"
                    f"📊 وضعیت: {status_text}\n"
                    f"🔤 فونت: {font_name}\n"
                    f"⌚ نمایش در نام: {'✅' if user['name_time'] else '❌'}\n"
                    f"⌚ نمایش در بیو: {'✅' if user['bio_time'] else '❌'}\n"
                    f"📅 تاریخ: {date_text}\n"
                    f"🖊️ حالت متن: {textmode_text}\n"
                    f"🧑‍💼 منشی: {secretary_text}\n"
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
                    client = await start_self_client(target_id, user["session"])
                    if not client:
                        user["status"] = False
                        await event.answer("❌ خطا در راه‌اندازی (نشست نامعتبر است)", alert=True)
                else:
                    await stop_self_client(target_id)

                save_user(target_id, user)

                await event.answer("✅ وضعیت کاربر تغییر کرد!", alert=True)
                await safe_edit(event,
                    f"👤 **جزئیات کاربر:**\n\n"
                    f"🆔 شناسه: `{target_id}`\n"
                    f"📊 وضعیت جدید: {'🟢 فعال' if user['status'] else '🔴 غیرفعال'}",
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
    if data == b"send_ready_session":
        user_data[user_id]["step"] = "get_session"
        await safe_edit(event,
            "✍️ **ارسال سشن آماده**\n\n"
            "لطفاً کد نشست (Session String) خود را که از Telethon دریافت کرده‌اید، ارسال کنید:"
        )
        return

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
            "⌚ **تنظیمات ساعت**\n\n"
            "در این بخش می‌توانید نحوه نمایش زمان در پروفایل خود را تنظیم کنید:",
            buttons=get_time_menu_keyboard(user)
        )
        return

    if data == b"menu_fonts":
        await safe_edit(event,
            "🔤 **انتخاب فونت ساعت**\n\n"
            "لطفاً یکی از فونت‌های زیر را برای نمایش ساعت انتخاب کنید:",
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
            "📅 **تنظیمات تاریخ**\n\n"
            "در این بخش می‌توانید نمایش تاریخ در بیو را مدیریت کنید:",
            buttons=get_date_menu_keyboard(user)
        )
        return

    if data == b"toggle_date_enabled":
        user["date_enabled"] = not user.get("date_enabled", False)
        save_user(user_id, user)
        await safe_edit(event,
            "📅 **تنظیمات تاریخ**\n\n"
            "در این بخش می‌توانید نمایش تاریخ در بیو را مدیریت کنید:",
            buttons=get_date_menu_keyboard(user)
        )
        return

    if data.startswith(b"setdatetype_"):
        date_type = data.decode().split("_", 1)[1]
        if date_type in DATE_TYPE_NAMES:
            user["date_type"] = date_type
            save_user(user_id, user)
        await safe_edit(event,
            "📅 **تنظیمات تاریخ**\n\n"
            f"✅ نوع تاریخ روی «{DATE_TYPE_NAMES.get(user.get('date_type'), '؟')}» تنظیم شد.",
            buttons=get_date_menu_keyboard(user)
        )
        return

    if data == b"menu_date_fonts":
        await safe_edit(event,
            "🔤 **انتخاب فونت تاریخ**\n\n"
            "لطفاً یکی از فونت‌های زیر را برای نمایش تاریخ انتخاب کنید:",
            buttons=get_date_fonts_menu_keyboard(user.get("date_font", 1))
        )
        return

    if data.startswith(b"setdatefont_"):
        font_id = int(data.decode().split("_")[1])
        user["date_font"] = font_id
        save_user(user_id, user)
        await safe_edit(event,
            "🔤 **انتخاب فونت تاریخ**\n\n"
            f"✅ فونت «{FONT_NAMES[font_id]}» با موفقیت انتخاب شد.",
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

        await safe_edit(event,
            "🔤 **انتخاب فونت ساعت**\n\n"
            f"✅ فونت «{FONT_NAMES[font_id]}» با موفقیت انتخاب شد.",
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
            client = await start_self_client(user_id, user["session"])
            if not client:
                user["status"] = False
                await event.answer("❌ نشست منقضی شده یا خطا در اتصال!", alert=True)
        else:
            await stop_self_client(user_id)

        save_user(user_id, user)

        await safe_edit(event,
            "🔗 **پنل مدیریت NovaSelf**\n"
            "از طریق منوی زیر می‌توانید تنظیمات خود را مدیریت کنید:",
            buttons=get_main_menu_keyboard(user)
        )
        return

    if data == b"toggle_name_time":
        user["name_time"] = not user["name_time"]
        save_user(user_id, user)

        await safe_edit(event,
            "⌚ **تنظیمات ساعت**\n\n"
            "در این بخش می‌توانید نحوه نمایش زمان در پروفایل خود را تنظیم کنید:",
            buttons=get_time_menu_keyboard(user)
        )
        return

    if data == b"toggle_bio_time":
        user["bio_time"] = not user["bio_time"]
        save_user(user_id, user)

        await safe_edit(event,
            "⌚ **تنظیمات ساعت**\n\n"
            "در این بخش می‌توانید نحوه نمایش زمان در پروفایل خود را تنظیم کنید:",
            buttons=get_time_menu_keyboard(user)
        )
        return

    if data == b"delete_account":
        await stop_self_client(user_id)
        delete_user_db(user_id)
        del user_data[user_id]

        await safe_edit(event,
            "🗑️ **اکانت با موفقیت حذف شد!**\n\n"
            "برای شروع مجدد، دستور /start را ارسال کنید."
        )
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
        await safe_edit(event, get_secretary_menu_text(user), buttons=get_secretary_menu_keyboard(user))
        return

    if data == b"secretary_off":
        user["secretary_enabled"] = False
        save_user(user_id, user)
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
    if text == "/cancel" and user_id in broadcast_data:
        del broadcast_data[user_id]
        await event.respond("❌ عملیات لغو شد.")
        if is_admin(user_id):
            await event.respond("👑 پنل ادمین:", buttons=get_admin_main_menu())
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

    if user_id in user_data and user_data[user_id].get("step") == "get_session":
        clean_session = text.replace("\n", "").replace("\r", "").replace(" ", "")

        try:
            client = TelegramClient(StringSession(clean_session), API_ID, API_HASH)
            await client.connect()

            if not await client.is_user_authorized():
                await event.respond(
                    "❌ **سشن نامعتبر است!**\n\n"
                    "سشن ارسال شده منقضی شده یا معتبر نیست.\n"
                    "لطفاً مجدداً تلاش کنید."
                )
                await client.disconnect()
                return
        except Exception as e:
            await event.respond(
                f"❌ **خطا در سشن:**\n\n`{str(e)}`\n\n"
                "مطمئن شوید که سشن Telethon معتبر ارسال کرده‌اید."
            )
            return

        user_data[user_id] = make_default_user(session=clean_session, status=True, step="managed")
        save_user(user_id, user_data[user_id])
        register_active_client(user_id, client)

        await event.respond(
            "✅ **سشن با موفقیت ثبت شد!**\n\n"
            "سلف شما هم‌اکنون فعال است و اطلاعات در دیتابیس ابری ذخیره شد."
        )

        await event.respond(
            "🔗 **پنل مدیریت NovaSelf**\n"
            "از طریق منوی زیر می‌توانید تنظیمات خود را مدیریت کنید:",
            buttons=get_main_menu_keyboard(user_data[user_id])
        )

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

    logging.info("✅ ربات با موفقیت راه‌اندازی شد!")
    logging.info(f"👑 تعداد ادمین‌ها: {len(ADMIN_IDS)}")

    bot.run_until_disconnected()
