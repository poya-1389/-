import asyncio
import os
import pytz
import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, FloodWaitError, AuthKeyDuplicatedError
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.messages import SetTypingRequest
from telethon.tl.types import (
    SendMessageTypingAction, SendMessageRecordAudioAction, SendMessageUploadPhotoAction,
    SendMessageRecordRoundAction, SendMessageUploadDocumentAction, SendMessageUploadVideoAction,
    SendMessageGamePlayAction, SendMessageChooseStickerAction,
    MessageEntityBold, MessageEntityItalic, MessageEntityUnderline, 
    MessageEntityStrike, MessageEntitySpoiler, MessageEntityCode,
    MessageEntityPre, MessageEntityBlockquote
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
reconnect_tasks = {}

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

# ======================== اکشن‌ها ========================
ACTIONS = {
    'typing': ('تایپ', SendMessageTypingAction()),
    'voice': ('ویس', SendMessageRecordAudioAction()),
    'photo': ('عکس', SendMessageUploadPhotoAction(0)),
    'round': ('ویدیوگرد', SendMessageRecordRoundAction()),
    'doc': ('سند', SendMessageUploadDocumentAction(0)),
    'video': ('ویدیو', SendMessageUploadVideoAction(0)),
    'game': ('بازی', SendMessageGamePlayAction()),
    'sticker': ('استیکر', SendMessageChooseStickerAction())
}

# ======================== حالت‌های متن ========================
TEXT_MODES = {
    'bold': ('بولد', MessageEntityBold),
    'italic': ('ایتالیک', MessageEntityItalic),
    'underline': ('زیر خط', MessageEntityUnderline),
    'strike': ('خط خورده', MessageEntityStrike),
    'spoiler': ('اسپویلر', MessageEntitySpoiler),
    'code': ('تک فاصله', MessageEntityCode),
    'pre': ('تدریجی', MessageEntityPre),
    'blockquote': ('نقل قول', MessageEntityBlockquote)
}

# ======================== انواع تقویم ========================
CALENDAR_TYPES = {
    'gregorian': 'میلادی',
    'hijri': 'قمری',
    'jalali': 'خورشیدی'
}

# ======================== توابع کمکی تقویم ========================
def get_jalali_date():
    try:
        from jdatetime import datetime as jdatetime
        now = jdatetime.now()
        return now.strftime("%Y/%m/%d")
    except:
        return datetime.now().strftime("%Y/%m/%d")

def get_hijri_date():
    try:
        from hijri_converter import convert
        now = datetime.now()
        hijri = convert.Gregorian(now.year, now.month, now.day).to_hijri()
        return f"{hijri.year}/{hijri.month:02d}/{hijri.day:02d}"
    except:
        return datetime.now().strftime("%Y/%m/%d")

def get_gregorian_date():
    return datetime.now().strftime("%Y/%m/%d")

def get_formatted_date(calendar_type, font_id):
    if calendar_type == 'jalali':
        date_str = get_jalali_date()
    elif calendar_type == 'hijri':
        date_str = get_hijri_date()
    else:
        date_str = get_gregorian_date()
    return apply_font(date_str, font_id)

# ======================== مدیریت دیتابیس ========================
def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'novaself_users'
            )
        """)
        table_exists = cursor.fetchone()[0]
        
        if not table_exists:
            cursor.execute('''
                CREATE TABLE novaself_users (
                    user_id BIGINT PRIMARY KEY,
                    session TEXT,
                    font_id INTEGER DEFAULT 1,
                    status INTEGER DEFAULT 0,
                    name_time INTEGER DEFAULT 1,
                    bio_time INTEGER DEFAULT 0,
                    active_action TEXT DEFAULT 'none',
                    text_mode TEXT DEFAULT 'none',
                    date_enabled INTEGER DEFAULT 0,
                    calendar_type TEXT DEFAULT 'jalali',
                    date_font_id INTEGER DEFAULT 1
                )
            ''')
            conn.commit()
            logging.info("✅ جدول novaself_users با موفقیت ایجاد شد.")
        else:
            columns_to_add = [
                ('text_mode', 'TEXT DEFAULT \'none\''),
                ('date_enabled', 'INTEGER DEFAULT 0'),
                ('calendar_type', 'TEXT DEFAULT \'jalali\''),
                ('date_font_id', 'INTEGER DEFAULT 1'),
                ('joined_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
            ]
            
            for col_name, col_def in columns_to_add:
                cursor.execute(f"""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_name = 'novaself_users' AND column_name = '{col_name}'
                    )
                """)
                if not cursor.fetchone()[0]:
                    cursor.execute(f'ALTER TABLE novaself_users ADD COLUMN {col_name} {col_def}')
                    conn.commit()
                    logging.info(f"✅ ستون {col_name} با موفقیت به جدول اضافه شد.")
        
        cursor.close()
        conn.close()
    except Exception as e:
        logging.error(f"❌ خطا در راه‌اندازی دیتابیس: {e}")

def get_all_users():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute("SELECT * FROM novaself_users ORDER BY joined_at DESC")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        
        data = {}
        for row in rows:
            user_id = row['user_id']
            data[user_id] = {
                "session": row['session'],
                "font_id": row['font_id'],
                "status": bool(row['status']),
                "name_time": bool(row['name_time']),
                "bio_time": bool(row['bio_time']),
                "active_action": row['active_action'],
                "text_mode": row.get('text_mode', 'none'),
                "date_enabled": bool(row.get('date_enabled', 0)),
                "calendar_type": row.get('calendar_type', 'jalali'),
                "date_font_id": row.get('date_font_id', 1),
                "joined_at": row.get('joined_at', datetime.now()),
                "step": "managed",
                "task": None,
                "action_task": None
            }
        return data
    except Exception as e:
        logging.error(f"❌ خطا در بارگذاری کاربران: {e}")
        return {}

def save_user(user_id, session, font_id, status, name_time, bio_time, active_action, 
              text_mode='none', date_enabled=False, calendar_type='jalali', date_font_id=1):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO novaself_users 
            (user_id, session, font_id, status, name_time, bio_time, active_action, 
             text_mode, date_enabled, calendar_type, date_font_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) 
            DO UPDATE SET 
                session = EXCLUDED.session,
                font_id = EXCLUDED.font_id,
                status = EXCLUDED.status,
                name_time = EXCLUDED.name_time,
                bio_time = EXCLUDED.bio_time,
                active_action = EXCLUDED.active_action,
                text_mode = EXCLUDED.text_mode,
                date_enabled = EXCLUDED.date_enabled,
                calendar_type = EXCLUDED.calendar_type,
                date_font_id = EXCLUDED.date_font_id
        ''', (user_id, session, font_id, int(status), int(name_time), int(bio_time), 
              active_action, text_mode, int(date_enabled), calendar_type, date_font_id))
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

# ======================== منوهای کاربر ========================
def get_main_menu_keyboard(user):
    status_text = "🟢 فعال" if user["status"] else "🔴 غیرفعال"
    return [
        [Button.inline(f"وضعیت سلف: {status_text}", b"toggle_status")],
        [Button.inline("⌚ ساعت", b"menu_time"), Button.inline("🎭 اکشن", b"menu_actions")],
        [Button.inline("📅 تاریخ", b"menu_date"), Button.inline("📝 حالت متن", b"menu_text_mode")],
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
        display = f"☑️ {action_name}" if action_key == current_action else f"▫️ {action_name}"
        row.append(Button.inline(display, f"setact_{action_key}".encode()))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([Button.inline("🔙 بازگشت", b"back_to_main")])
    return buttons

def get_text_mode_menu_keyboard(current_mode):
    buttons = []
    row = []
    for mode_key, (mode_name, _) in TEXT_MODES.items():
        display = f"☑️ {mode_name}" if mode_key == current_mode else f"▫️ {mode_name}"
        row.append(Button.inline(display, f"settext_{mode_key}".encode()))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([Button.inline("🔙 بازگشت", b"back_to_main")])
    return buttons

def get_date_menu_keyboard(user):
    date_status = "✅ فعال" if user.get("date_enabled", False) else "❌ غیرفعال"
    calendar_name = CALENDAR_TYPES.get(user.get("calendar_type", 'jalali'), 'خورشیدی')
    date_font_name = FONT_NAMES.get(user.get("date_font_id", 1), "بولد")
    
    return [
        [Button.inline(f"وضعیت تاریخ: {date_status}", b"toggle_date")],
        [Button.inline(f"📅 تقویم: {calendar_name}", b"menu_calendar")],
        [Button.inline(f"🔤 فونت تاریخ: {date_font_name}", b"menu_date_fonts")],
        [Button.inline("🔙 بازگشت", b"back_to_main")]
    ]

def get_calendar_menu_keyboard(current_calendar):
    buttons = []
    for cal_key, cal_name in CALENDAR_TYPES.items():
        display = f"☑️ {cal_name}" if cal_key == current_calendar else f"▫️ {cal_name}"
        buttons.append([Button.inline(display, f"setcal_{cal_key}".encode())])
    buttons.append([Button.inline("🔙 بازگشت به تاریخ", b"menu_date")])
    return buttons

def get_date_fonts_menu_keyboard(current_font_id):
    buttons = []
    row = []
    for font_id, font_name in FONT_NAMES.items():
        display = f"☑️ {font_name}" if font_id == current_font_id else f"▫️ {font_name}"
        row.append(Button.inline(display, f"setdatefont_{font_id}".encode()))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([Button.inline("🔙 بازگشت به تاریخ", b"menu_date")])
    return buttons

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

# ======================== توابع اصلی سلف با reconnect ========================
async def self_bot_worker_with_reconnect(user_id, client):
    """کارگر سلف با قابلیت reconnect خودکار"""
    max_retries = 5
    retry_delay = 10
    
    while True:
        try:
            if user_id not in user_data or not user_data[user_id]["status"]:
                break
                
            if not client.is_connected():
                logging.warning(f"⚠️ کلاینت کاربر {user_id} قطع است. در حال reconnect...")
                try:
                    await client.connect()
                    if not await client.is_user_authorized():
                        logging.error(f"❌ کاربر {user_id} احراز هویت نشد!")
                        user_data[user_id]["status"] = False
                        save_user(user_id, user_data[user_id]["session"], user_data[user_id]["font_id"], False,
                                 user_data[user_id]["name_time"], user_data[user_id]["bio_time"],
                                 user_data[user_id]["active_action"], user_data[user_id].get("text_mode", "none"),
                                 user_data[user_id].get("date_enabled", False),
                                 user_data[user_id].get("calendar_type", "jalali"),
                                 user_data[user_id].get("date_font_id", 1))
                        break
                except Exception as e:
                    logging.error(f"❌ خطا در reconnect کاربر {user_id}: {e}")
                    await asyncio.sleep(retry_delay)
                    continue
            
            # اجرای کارگر اصلی
            await self_bot_worker(user_id, client)
            
        except AuthKeyDuplicatedError:
            logging.warning(f"⚠️ AuthKeyDuplicatedError برای کاربر {user_id}. تلاش مجدد...")
            await asyncio.sleep(5)
            try:
                await client.disconnect()
            except:
                pass
            # ایجاد کلاینت جدید
            session_str = user_data[user_id]["session"]
            client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
            active_clients[user_id] = client
            await client.connect()
            if await client.is_user_authorized():
                logging.info(f"✅ کلاینت جدید برای کاربر {user_id} ایجاد شد.")
            else:
                logging.error(f"❌ کلاینت جدید برای کاربر {user_id} معتبر نیست!")
                break
                
        except Exception as e:
            logging.error(f"❌ خطا در سلف کاربر {user_id}: {e}")
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)
            continue

async def self_bot_worker(user_id, client):
    """کارگر اصلی سلف"""
    try:
        me = await client.get_me()
        first_name = me.first_name or "کاربر"
        last_time = ""
        
        while True:
            if user_id not in user_data or not user_data[user_id]["status"]:
                break
                
            user = user_data[user_id]
            tehran_tz = pytz.timezone('Asia/Tehran')
            current_time = datetime.now(tehran_tz).strftime("%H:%M")
            
            # ساخت بیوگرافی
            bio_parts = []
            if user.get("date_enabled", False):
                date_str = get_formatted_date(
                    user.get("calendar_type", 'jalali'),
                    user.get("date_font_id", 1)
                )
                bio_parts.append(date_str)
            
            if user["bio_time"]:
                formatted_time = apply_font(current_time, user["font_id"])
                bio_parts.append(formatted_time)
            
            bio_text = " | ".join(bio_parts) if bio_parts else ""
            
            # بروزرسانی نام و بیو
            if current_time != last_time:
                formatted_time = apply_font(current_time, user["font_id"])
                
                try:
                    if user["name_time"]:
                        await client(UpdateProfileRequest(first_name=first_name, last_name=formatted_time))
                    else:
                        await client(UpdateProfileRequest(first_name=first_name, last_name=""))
                    
                    await client(UpdateProfileRequest(about=bio_text))
                    last_time = current_time
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    logging.error(f"⚠️ خطا در بروزرسانی پروفایل کاربر {user_id}: {e}")
                    raise  # برای reconnect
                
            await asyncio.sleep(5)
            
    except Exception as e:
        logging.error(f"❌ خطای اصلی سلف برای کاربر {user_id}: {e}")
        raise

async def self_bot_action_worker(user_id, client):
    """کارگر نمایش اکشن با reconnect"""
    while True:
        try:
            if user_id not in user_data or not user_data[user_id]["status"]:
                break
                
            if not client.is_connected():
                await asyncio.sleep(2)
                continue
                
            user = user_data[user_id]
            action_key = user["active_action"]
            
            if action_key == 'none' or action_key not in ACTIONS:
                await asyncio.sleep(4)
                continue
            
            try:
                async for dialog in client.iter_dialogs(limit=5):
                    if dialog.is_user or dialog.is_group:
                        try:
                            await client(SetTypingRequest(
                                peer=dialog.input_entity,
                                action=ACTIONS[action_key][1]
                            ))
                        except:
                            pass
            except Exception as e:
                logging.error(f"⚠️ خطا در نمایش اکشن کاربر {user_id}: {e}")
            
            await asyncio.sleep(4)
            
        except Exception as e:
            logging.error(f"❌ خطای اکشن برای کاربر {user_id}: {e}")
            await asyncio.sleep(5)

async def restart_self_bot(user_id):
    """راه‌اندازی مجدد سلف یک کاربر"""
    if user_id not in user_data:
        return
    
    user = user_data[user_id]
    
    # توقف وظایف قبلی
    if user.get("task"):
        try:
            user["task"].cancel()
        except:
            pass
    if user.get("action_task"):
        try:
            user["action_task"].cancel()
        except:
            pass
    
    if user_id in active_clients:
        try:
            await active_clients[user_id].disconnect()
        except:
            pass
        del active_clients[user_id]
    
    if not user["status"] or not user["session"]:
        return
    
    try:
        # ایجاد کلاینت جدید
        client = TelegramClient(StringSession(user["session"]), API_ID, API_HASH)
        await client.connect()
        
        if await client.is_user_authorized():
            active_clients[user_id] = client
            loop = asyncio.get_event_loop()
            user["task"] = loop.create_task(self_bot_worker_with_reconnect(user_id, client))
            user["action_task"] = loop.create_task(self_bot_action_worker(user_id, client))
            logging.info(f"✅ سلف کاربر {user_id} با reconnect راه‌اندازی شد.")
        else:
            user["status"] = False
            save_user(user_id, user["session"], user["font_id"], False,
                     user["name_time"], user["bio_time"], user["active_action"],
                     user.get("text_mode", "none"), user.get("date_enabled", False),
                     user.get("calendar_type", "jalali"), user.get("date_font_id", 1))
    except Exception as e:
        logging.error(f"❌ خطا در راه‌اندازی مجدد کاربر {user_id}: {e}")

async def autostart_saved_users():
    """راه‌اندازی خودکار کاربران ذخیره شده با reconnect"""
    await asyncio.sleep(5)
    
    for user_id, user in list(user_data.items()):
        if user["status"] and user["session"]:
            try:
                client = TelegramClient(StringSession(user["session"]), API_ID, API_HASH)
                await client.connect()
                
                if await client.is_user_authorized():
                    active_clients[user_id] = client
                    loop = asyncio.get_event_loop()
                    user["task"] = loop.create_task(self_bot_worker_with_reconnect(user_id, client))
                    user["action_task"] = loop.create_task(self_bot_action_worker(user_id, client))
                    logging.info(f"✅ سلف کاربر {user_id} با reconnect راه‌اندازی شد.")
                else:
                    user["status"] = False
                    save_user(user_id, user["session"], user["font_id"], False,
                             user["name_time"], user["bio_time"], user["active_action"],
                             user.get("text_mode", "none"), user.get("date_enabled", False),
                             user.get("calendar_type", "jalali"), user.get("date_font_id", 1))
            except Exception as e:
                logging.error(f"❌ خطا در راه‌اندازی خودکار کاربر {user_id}: {e}")

# ======================== هندلرهای ربات ========================
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    user_id = event.sender_id
    
    if user_id in generator_data:
        return
    
    if user_id not in user_data:
        user_data[user_id] = {
            "session": None,
            "font_id": 1,
            "status": False,
            "name_time": True,
            "bio_time": False,
            "active_action": "none",
            "text_mode": "none",
            "date_enabled": False,
            "calendar_type": "jalali",
            "date_font_id": 1,
            "task": None,
            "action_task": None,
            "step": "menu",
            "joined_at": datetime.now()
        }
    
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
        if data == b"admin_panel":
            await event.edit(
                "👑 **پنل مدیریت NovaSelf**\n\n"
                "از طریق منوی زیر می‌توانید کاربران را مدیریت کنید:",
                buttons=get_admin_main_menu()
            )
            return
        
        if data == b"admin_stats":
            total, active = get_user_stats()
            await event.edit(
                f"📊 **آمار کاربران:**\n\n"
                f"👥 تعداد کل کاربران: {total}\n"
                f"🟢 کاربران فعال: {active}\n"
                f"🔴 کاربران غیرفعال: {total - active}\n\n"
                f"🕐 آخرین بروزرسانی: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                buttons=[Button.inline("🔙 بازگشت", b"admin_panel")]
            )
            return
        
        if data == b"admin_users_list":
            buttons = get_users_list_page(0)
            await event.edit(
                "📋 **لیست کاربران:**\n\n"
                "برای مشاهده جزئیات هر کاربر روی آن کلیک کنید:",
                buttons=buttons
            )
            return
        
        if data.startswith(b"admin_users_page_"):
            page = int(data.decode().split("_")[3])
            buttons = get_users_list_page(page)
            await event.edit(
                "📋 **لیست کاربران:**\n\n"
                "برای مشاهده جزئیات هر کاربر روی آن کلیک کنید:",
                buttons=buttons
            )
            return
        
        if data.startswith(b"admin_view_user_"):
            target_id = int(data.decode().split("_")[3])
            if target_id in user_data:
                user = user_data[target_id]
                status_text = "🟢 فعال" if user["status"] else "🔴 غیرفعال"
                font_name = FONT_NAMES.get(user["font_id"], "نامشخص")
                action_name = ACTIONS.get(user["active_action"], ("هیچ",))[0] if user["active_action"] != "none" else "هیچ"
                text_mode_name = TEXT_MODES.get(user.get("text_mode", "none"), ("غیرفعال", None))[0] if user.get("text_mode") != "none" else "غیرفعال"
                date_status = "✅ فعال" if user.get("date_enabled", False) else "❌ غیرفعال"
                calendar_name = CALENDAR_TYPES.get(user.get("calendar_type", "jalali"), "خورشیدی")
                
                await event.edit(
                    f"👤 **جزئیات کاربر:**\n\n"
                    f"🆔 شناسه: `{target_id}`\n"
                    f"📊 وضعیت: {status_text}\n"
                    f"🔤 فونت: {font_name}\n"
                    f"⌚ نمایش در نام: {'✅' if user['name_time'] else '❌'}\n"
                    f"⌚ نمایش در بیو: {'✅' if user['bio_time'] else '❌'}\n"
                    f"🎭 اکشن: {action_name}\n"
                    f"📝 حالت متن: {text_mode_name}\n"
                    f"📅 تاریخ: {date_status} - {calendar_name}\n"
                    f"📅 تاریخ ثبت: {user.get('joined_at', 'نامشخص')}\n\n"
                    f"💡 برای مدیریت این کاربر از دکمه‌های زیر استفاده کنید:",
                    buttons=get_user_detail_buttons(target_id)
                )
            else:
                await event.answer("❌ کاربر پیدا نشد!", alert=True)
            return
        
        if data.startswith(b"admin_toggle_user_"):
            target_id = int(data.decode().split("_")[3])
            if target_id in user_data:
                user = user_data[target_id]
                user["status"] = not user["status"]
                
                if user["status"]:
                    await restart_self_bot(target_id)
                else:
                    if user["task"]:
                        user["task"].cancel()
                    if user["action_task"]:
                        user["action_task"].cancel()
                    if target_id in active_clients:
                        try:
                            await active_clients[target_id].disconnect()
                        except:
                            pass
                        del active_clients[target_id]
                
                save_user(target_id, user["session"], user["font_id"], user["status"],
                         user["name_time"], user["bio_time"], user["active_action"],
                         user.get("text_mode", "none"), user.get("date_enabled", False),
                         user.get("calendar_type", "jalali"), user.get("date_font_id", 1))
                
                await event.answer("✅ وضعیت کاربر تغییر کرد!", alert=True)
                await event.edit(
                    f"👤 **جزئیات کاربر:**\n\n"
                    f"🆔 شناسه: `{target_id}`\n"
                    f"📊 وضعیت جدید: {'🟢 فعال' if user['status'] else '🔴 غیرفعال'}",
                    buttons=get_user_detail_buttons(target_id)
                )
            return
        
        if data.startswith(b"admin_delete_user_"):
            target_id = int(data.decode().split("_")[3])
            if target_id in user_data:
                user = user_data[target_id]
                if user["task"]:
                    user["task"].cancel()
                if user["action_task"]:
                    user["action_task"].cancel()
                if target_id in active_clients:
                    try:
                        await active_clients[target_id].disconnect()
                    except:
                        pass
                    del active_clients[target_id]
                
                delete_user_db(target_id)
                del user_data[target_id]
                
                await event.answer("✅ کاربر حذف شد!", alert=True)
                await event.edit(
                    "🗑️ **کاربر با موفقیت حذف شد.**",
                    buttons=[Button.inline("🔙 بازگشت به لیست", b"admin_users_list")]
                )
            return
        
        if data.startswith(b"admin_send_to_user_"):
            target_id = int(data.decode().split("_")[4])
            broadcast_data[user_id] = {
                "type": "single",
                "target_id": target_id,
                "step": "get_message"
            }
            await event.edit(
                f"📨 **ارسال پیام به کاربر {target_id}**\n\n"
                "لطفاً پیام خود را به صورت متن ارسال کنید.\n"
                "برای لغو عملیات، /cancel را بفرستید."
            )
            return
        
        if data == b"admin_broadcast":
            broadcast_data[user_id] = {
                "type": "broadcast",
                "step": "get_message"
            }
            await event.edit(
                "📨 **ارسال پیام همگانی**\n\n"
                "⚠️ این پیام برای **همه کاربران** ارسال خواهد شد!\n\n"
                "لطفاً پیام خود را به صورت متن ارسال کنید.\n"
                "برای لغو عملیات، /cancel را بفرستید."
            )
            return
        
        if data == b"admin_search_user":
            broadcast_data[user_id] = {
                "type": "search",
                "step": "get_user_id"
            }
            await event.edit(
                "🔍 **جستجوی کاربر**\n\n"
                "لطفاً شناسه (ID) کاربر مورد نظر را وارد کنید:"
            )
            return
        
        if data == b"admin_refresh_all":
            await event.edit("⏳ در حال بروزرسانی اطلاعات همه کاربران...")
            
            for uid in list(user_data.keys()):
                if user_data[uid]["status"]:
                    await restart_self_bot(uid)
            
            await event.edit(
                "✅ **همه کاربران با موفقیت بروزرسانی شدند!**",
                buttons=[Button.inline("🔙 بازگشت", b"admin_panel")]
            )
            return
    
    # ====== منوی کاربر (ادامه دارد...) ======
    if data == b"send_ready_session":
        user_data[user_id]["step"] = "get_session"
        await event.edit(
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
        await event.edit(
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
                
                await event.edit(
                    "📩 **مرحله دوم: وارد کردن کد تایید**\n\n"
                    "کد ۵ رقمی ارسال شده به تلگرام خود را وارد کنید:",
                    buttons=get_code_keyboard(generator["code_buffer"])
                )
                
            elif action == "clear":
                generator["code_buffer"] = ""
                await event.edit(
                    "📩 **مرحله دوم: وارد کردن کد تایید**\n\n"
                    "کد ۵ رقمی ارسال شده به تلگرام خود را وارد کنید:",
                    buttons=get_code_keyboard(generator["code_buffer"])
                )
                
            elif action == "submit":
                if len(generator["code_buffer"]) < 5:
                    await event.answer("⚠️ لطفاً کد ۵ رقمی را کامل وارد کنید!", alert=True)
                    return
                
                await event.edit("⏳ در حال بررسی کد و ورود به حساب...")
                await process_code_signin(event, user_id, generator["code_buffer"])
            
            return
    
    if user_id not in user_data:
        return
    
    user = user_data[user_id]
    
    if data == b"back_to_main":
        await event.edit(
            "🔗 **پنل مدیریت NovaSelf**\n"
            "از طریق منوی زیر می‌توانید تنظیمات خود را مدیریت کنید:",
            buttons=get_main_menu_keyboard(user)
        )
        return
    
    if data == b"menu_time":
        await event.edit(
            "⌚ **تنظیمات ساعت**\n\n"
            "در این بخش می‌توانید نحوه نمایش زمان در پروفایل خود را تنظیم کنید:",
            buttons=get_time_menu_keyboard(user)
        )
        return
    
    if data == b"menu_fonts":
        await event.edit(
            "🔤 **انتخاب فونت ساعت**\n\n"
            "لطفاً یکی از فونت‌های زیر را برای نمایش ساعت انتخاب کنید:",
            buttons=get_fonts_menu_keyboard(user["font_id"])
        )
        return
    
    if data == b"menu_actions":
        await event.edit(
            "🎭 **مدیریت اکشن‌های فیک**\n\n"
            "با انتخاب هر گزینه، وضعیت شما به‌صورت مداوم برای دیگران نمایش داده می‌شود:",
            buttons=get_actions_menu_keyboard(user["active_action"])
        )
        return
    
    if data == b"menu_text_mode":
        current_mode = user.get("text_mode", "none")
        if current_mode == "none":
            await event.edit(
                "📝 **حالت متن**\n\n"
                "هیچ حالتی فعال نیست. برای فعال‌سازی یکی از گزینه‌های زیر را انتخاب کنید:",
                buttons=get_text_mode_menu_keyboard(None)
            )
        else:
            mode_name = TEXT_MODES.get(current_mode, ("نامشخص", None))[0]
            await event.edit(
                f"📝 **حالت متن**\n\n"
                f"حالت فعلی: {mode_name}\n\n"
                "برای تغییر یا غیرفعال‌سازی، روی گزینه مورد نظر کلیک کنید:",
                buttons=get_text_mode_menu_keyboard(current_mode)
            )
        return
    
    if data.startswith(b"settext_"):
        mode_key = data.decode().split("_")[1]
        
        if user.get("text_mode") == mode_key:
            user["text_mode"] = "none"
            status_text = "غیرفعال"
        else:
            user["text_mode"] = mode_key
            status_text = TEXT_MODES.get(mode_key, ("نامشخص", None))[0]
        
        save_user(user_id, user["session"], user["font_id"], user["status"],
                 user["name_time"], user["bio_time"], user["active_action"],
                 user["text_mode"], user.get("date_enabled", False),
                 user.get("calendar_type", "jalali"), user.get("date_font_id", 1))
        
        if user["text_mode"] == "none":
            await event.edit(
                "📝 **حالت متن**\n\n"
                "✅ حالت متن با موفقیت غیرفعال شد.",
                buttons=get_text_mode_menu_keyboard(None)
            )
        else:
            await event.edit(
                "📝 **حالت متن**\n\n"
                f"✅ حالت «{status_text}» با موفقیت فعال شد.",
                buttons=get_text_mode_menu_keyboard(user["text_mode"])
            )
        return
    
    if data == b"menu_date":
        await event.edit(
            "📅 **تنظیمات تاریخ**\n\n"
            "در این بخش می‌توانید نمایش تاریخ را در بیوگرافی خود تنظیم کنید:",
            buttons=get_date_menu_keyboard(user)
        )
        return
    
    # ====== سایر تنظیمات ======
    if data == b"toggle_date":
        user["date_enabled"] = not user.get("date_enabled", False)
        save_user(user_id, user["session"], user["font_id"], user["status"],
                 user["name_time"], user["bio_time"], user["active_action"],
                 user.get("text_mode", "none"), user["date_enabled"],
                 user.get("calendar_type", "jalali"), user.get("date_font_id", 1))
        
        await event.edit(
            "📅 **تنظیمات تاریخ**\n\n"
            f"✅ وضعیت تاریخ به {'فعال' if user['date_enabled'] else 'غیرفعال'} تغییر یافت.",
            buttons=get_date_menu_keyboard(user)
        )
        return
    
    if data == b"menu_calendar":
        await event.edit(
            "📅 **انتخاب تقویم**\n\n"
            "لطفاً نوع تقویم مورد نظر خود را انتخاب کنید:",
            buttons=get_calendar_menu_keyboard(user.get("calendar_type", "jalali"))
        )
        return
    
    if data.startswith(b"setcal_"):
        cal_key = data.decode().split("_")[1]
        user["calendar_type"] = cal_key
        
        save_user(user_id, user["session"], user["font_id"], user["status"],
                 user["name_time"], user["bio_time"], user["active_action"],
                 user.get("text_mode", "none"), user.get("date_enabled", False),
                 cal_key, user.get("date_font_id", 1))
        
        cal_name = CALENDAR_TYPES.get(cal_key, "خورشیدی")
        await event.edit(
            "📅 **انتخاب تقویم**\n\n"
            f"✅ تقویم «{cal_name}» با موفقیت انتخاب شد.",
            buttons=get_calendar_menu_keyboard(cal_key)
        )
        return
    
    if data == b"menu_date_fonts":
        await event.edit(
            "🔤 **انتخاب فونت تاریخ**\n\n"
            "لطفاً یکی از فونت‌های زیر را برای نمایش تاریخ انتخاب کنید:",
            buttons=get_date_fonts_menu_keyboard(user.get("date_font_id", 1))
        )
        return
    
    if data.startswith(b"setdatefont_"):
        font_id = int(data.decode().split("_")[1])
        user["date_font_id"] = font_id
        
        save_user(user_id, user["session"], user["font_id"], user["status"],
                 user["name_time"], user["bio_time"], user["active_action"],
                 user.get("text_mode", "none"), user.get("date_enabled", False),
                 user.get("calendar_type", "jalali"), font_id)
        
        await event.edit(
            "🔤 **انتخاب فونت تاریخ**\n\n"
            f"✅ فونت «{FONT_NAMES[font_id]}» با موفقیت انتخاب شد.",
            buttons=get_date_fonts_menu_keyboard(font_id)
        )
        return
    
    if data.startswith(b"setfont_"):
        font_id = int(data.decode().split("_")[1])
        user["font_id"] = font_id
        
        save_user(user_id, user["session"], font_id, user["status"], 
                 user["name_time"], user["bio_time"], user["active_action"],
                 user.get("text_mode", "none"), user.get("date_enabled", False),
                 user.get("calendar_type", "jalali"), user.get("date_font_id", 1))
        
        await event.edit(
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
        
        save_user(user_id, user["session"], user["font_id"], user["status"],
                 user["name_time"], user["bio_time"], user["active_action"],
                 user.get("text_mode", "none"), user.get("date_enabled", False),
                 user.get("calendar_type", "jalali"), user.get("date_font_id", 1))
        
        await event.edit(
            "🎭 **مدیریت اکشن‌های فیک**\n\n"
            f"✅ وضعیت اکشن با موفقیت تغییر یافت.",
            buttons=get_actions_menu_keyboard(user["active_action"])
        )
        return
    
    if data == b"toggle_status":
        user["status"] = not user["status"]
        save_user(user_id, user["session"], user["font_id"], user["status"],
                 user["name_time"], user["bio_time"], user["active_action"],
                 user.get("text_mode", "none"), user.get("date_enabled", False),
                 user.get("calendar_type", "jalali"), user.get("date_font_id", 1))
        
        if user["status"]:
            await restart_self_bot(user_id)
        else:
            if user["task"]:
                user["task"].cancel()
            if user["action_task"]:
                user["action_task"].cancel()
            if user_id in active_clients:
                try:
                    await active_clients[user_id].disconnect()
                except:
                    pass
                del active_clients[user_id]
        
        await event.edit(
            "🔗 **پنل مدیریت NovaSelf**\n"
            "از طریق منوی زیر می‌توانید تنظیمات خود را مدیریت کنید:",
            buttons=get_main_menu_keyboard(user)
        )
        return
    
    if data == b"toggle_name_time":
        user["name_time"] = not user["name_time"]
        save_user(user_id, user["session"], user["font_id"], user["status"],
                 user["name_time"], user["bio_time"], user["active_action"],
                 user.get("text_mode", "none"), user.get("date_enabled", False),
                 user.get("calendar_type", "jalali"), user.get("date_font_id", 1))
        
        await event.edit(
            "⌚ **تنظیمات ساعت**\n\n"
            "در این بخش می‌توانید نحوه نمایش زمان در پروفایل خود را تنظیم کنید:",
            buttons=get_time_menu_keyboard(user)
        )
        return
    
    if data == b"toggle_bio_time":
        user["bio_time"] = not user["bio_time"]
        save_user(user_id, user["session"], user["font_id"], user["status"],
                 user["name_time"], user["bio_time"], user["active_action"],
                 user.get("text_mode", "none"), user.get("date_enabled", False),
                 user.get("calendar_type", "jalali"), user.get("date_font_id", 1))
        
        await event.edit(
            "⌚ **تنظیمات ساعت**\n\n"
            "در این بخش می‌توانید نحوه نمایش زمان در پروفایل خود را تنظیم کنید:",
            buttons=get_time_menu_keyboard(user)
        )
        return
    
    if data == b"delete_account":
        if user["task"]:
            user["task"].cancel()
        if user["action_task"]:
            user["action_task"].cancel()
        if user_id in active_clients:
            try:
                await active_clients[user_id].disconnect()
            except:
                pass
            del active_clients[user_id]
        
        delete_user_db(user_id)
        del user_data[user_id]
        
        await event.edit(
            "🗑️ **اکانت با موفقیت حذف شد!**\n\n"
            "برای شروع مجدد، دستور /start را ارسال کنید."
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
        
        user_data[user_id] = {
            "session": session_string,
            "font_id": 1,
            "status": True,
            "name_time": True,
            "bio_time": False,
            "active_action": "none",
            "text_mode": "none",
            "date_enabled": False,
            "calendar_type": "jalali",
            "date_font_id": 1,
            "task": None,
            "action_task": None,
            "step": "managed",
            "joined_at": datetime.now()
        }
        
        active_clients[user_id] = client
        save_user(user_id, session_string, 1, True, True, False, "none")
        
        loop = asyncio.get_event_loop()
        user_data[user_id]["task"] = loop.create_task(self_bot_worker_with_reconnect(user_id, client))
        user_data[user_id]["action_task"] = loop.create_task(self_bot_action_worker(user_id, client))
        
        await event.respond(
            "✅ **ورود با موفقیت انجام شد!**\n\n"
            "🔹 حساب شما به ربات متصل شد.\n"
            "🔹 اطلاعات در دیتابیس ابری ذخیره شد.\n"
            "🔹 سلف شما هم‌اکنون فعال است."
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
    
    if event.out:
        return
    
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
    
    # ====== پردازش حالت متن (ویرایش پیام خود کاربر) ======
    if user_id in user_data and user_data[user_id].get("session") is not None:
        user = user_data[user_id]
        mode = user.get("text_mode", "none")
        
        if mode != "none" and mode in TEXT_MODES and text and not text.startswith('/'):
            try:
                entities = []
                if mode == 'bold':
                    entities.append(MessageEntityBold(0, len(text)))
                elif mode == 'italic':
                    entities.append(MessageEntityItalic(0, len(text)))
                elif mode == 'underline':
                    entities.append(MessageEntityUnderline(0, len(text)))
                elif mode == 'strike':
                    entities.append(MessageEntityStrike(0, len(text)))
                elif mode == 'spoiler':
                    entities.append(MessageEntitySpoiler(0, len(text)))
                elif mode == 'code':
                    entities.append(MessageEntityCode(0, len(text)))
                elif mode == 'pre':
                    entities.append(MessageEntityPre(0, len(text), language=''))
                elif mode == 'blockquote':
                    entities.append(MessageEntityBlockquote(0, len(text)))
                
                client = active_clients.get(user_id)
                if client and client.is_connected():
                    await client(EditMessageRequest(
                        peer=event.chat_id,
                        id=event.id,
                        message=text,
                        entities=entities
                    ))
                else:
                    await event.edit(text, entities=entities)
                    
            except Exception as e:
                logging.error(f"❌ خطا در اعمال حالت متن: {e}")
    
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
                
                user_data[user_id] = {
                    "session": session_string,
                    "font_id": 1,
                    "status": True,
                    "name_time": True,
                    "bio_time": False,
                    "active_action": "none",
                    "text_mode": "none",
                    "date_enabled": False,
                    "calendar_type": "jalali",
                    "date_font_id": 1,
                    "task": None,
                    "action_task": None,
                    "step": "managed",
                    "joined_at": datetime.now()
                }
                
                active_clients[user_id] = client
                save_user(user_id, session_string, 1, True, True, False, "none")
                
                loop = asyncio.get_event_loop()
                user_data[user_id]["task"] = loop.create_task(self_bot_worker_with_reconnect(user_id, client))
                user_data[user_id]["action_task"] = loop.create_task(self_bot_action_worker(user_id, client))
                
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
        
        user_data[user_id] = {
            "session": clean_session,
            "font_id": 1,
            "status": True,
            "name_time": True,
            "bio_time": False,
            "active_action": "none",
            "text_mode": "none",
            "date_enabled": False,
            "calendar_type": "jalali",
            "date_font_id": 1,
            "task": None,
            "action_task": None,
            "step": "managed",
            "joined_at": datetime.now()
        }
        
        active_clients[user_id] = client
        save_user(user_id, clean_session, 1, True, True, False, "none")
        
        loop = asyncio.get_event_loop()
        user_data[user_id]["task"] = loop.create_task(self_bot_worker_with_reconnect(user_id, client))
        user_data[user_id]["action_task"] = loop.create_task(self_bot_action_worker(user_id, client))
        
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
        await event.edit("⏳ در حال ارسال پیام...")
        
        message = broadcast["message"]
        
        if broadcast["type"] == "single":
            target_id = broadcast["target_id"]
            try:
                await bot.send_message(target_id, message)
                await event.edit(
                    f"✅ **پیام با موفقیت به کاربر {target_id} ارسال شد!**",
                    buttons=[Button.inline("🔙 بازگشت به پنل", b"admin_panel")]
                )
            except Exception as e:
                await event.edit(
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
            
            await event.edit(
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
        await event.edit(
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
