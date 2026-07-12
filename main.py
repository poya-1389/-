import asyncio
import os
import pytz
import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.messages import SetTypingRequest
from telethon.tl.types import (
    SendMessageTypingAction, SendMessageRecordAudioAction, SendMessageUploadPhotoAction,
    SendMessageRecordRoundAction, SendMessageUploadDocumentAction, SendMessageUploadVideoAction,
    SendMessageGamePlayAction, SendMessageChooseStickerAction
)

# ======================== تنظیمات اولیه ========================
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

if not all([API_ID, API_HASH, BOT_TOKEN, DATABASE_URL]):
    raise ValueError("تمامی متغیرهای محیطی باید تنظیم شوند!")

bot = TelegramClient('helper_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# ======================== دیکشنری‌های عمومی ========================
active_clients = {}
generator_data = {}
active_signins = {}
user_data = {}

# ======================== فونت‌های کامل ========================
FONTS = {
    0: {'0': '0', '1': '1', '2': '2', '3': '3', '4': '4', '5': '5', '6': '6', '7': '7', '8': '8', '9': '9'},
    1: {'0': '𝟬', '1': '𝟭', '2': '𝟮', '3': '𝟯', '4': '𝟰', '5': '𝟱', '6': '𝟲', '7': '𝟳', '8': '𝟴', '9': '𝟵'},
    2: {'0': '𝟘', '1': '𝟙', '2': '𝟚', '3': '𝟛', '4': '𝟜', '5': '𝟝', '6': '𝟞', '7': '𝟟', '8': '𝟠', '9': '𝟡'},
    3: {'0': '𝟶', '1': '𝟷', '2': '𝟸', '3': '𝟹', '4': '𝟺', '5': '𝟻', '6': '𝟼', '7': '𝟽', '8': '𝟾', '9': '𝟿'},
    4: {'0': '𝟢', '1': '𝟣', '2': '𝟤', '3': '𝟥', '4': '𝟦', '5': '𝟧', '6': '𝟨', '7': '𝟩', '8': '𝟪', '9': '𝟫'},
    5: {'0': '𝟎', '1': '𝟏', '2': '𝟐', '3': '𝟑', '4': '𝟒', '5': '𝟓', '6': '𝟔', '7': '𝟕', '8': '𝟖', '9': '𝟗'},
    6: {'0': '０', '1': '１', '2': '２', '3': '３', '4': '４', '5': '５', '6': '６', '7': '۷', '8': '۸', '9': '۹'},
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

# ======================== مدیریت دیتابیس ========================
def get_db_connection():
    """ایجاد اتصال به دیتابیس PostgreSQL"""
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    """راه‌اندازی اولیه دیتابیس - ایجاد جدول در صورت عدم وجود"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # بررسی وجود جدول
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
                    active_action TEXT DEFAULT 'none'
                )
            ''')
            conn.commit()
            print("✅ جدول novaself_users با موفقیت ایجاد شد.")
        else:
            print("ℹ️ جدول novaself_users از قبل وجود دارد.")
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"❌ خطا در راه‌اندازی دیتابیس: {e}")

def get_all_users():
    """بارگذاری تمام کاربران از دیتابیس"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute("SELECT user_id, session, font_id, status, name_time, bio_time, active_action FROM novaself_users")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        
        data = {}
        for row in rows:
            data[row['user_id']] = {
                "session": row['session'],
                "font_id": row['font_id'],
                "status": bool(row['status']),
                "name_time": bool(row['name_time']),
                "bio_time": bool(row['bio_time']),
                "active_action": row['active_action'],
                "step": "managed",
                "task": None,
                "action_task": None
            }
        return data
    except Exception as e:
        print(f"❌ خطا در بارگذاری کاربران: {e}")
        return {}

def save_user(user_id, session, font_id, status, name_time, bio_time, active_action):
    """ذخیره یا بروزرسانی اطلاعات کاربر در دیتابیس"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO novaself_users (user_id, session, font_id, status, name_time, bio_time, active_action)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) 
            DO UPDATE SET 
                session = EXCLUDED.session,
                font_id = EXCLUDED.font_id,
                status = EXCLUDED.status,
                name_time = EXCLUDED.name_time,
                bio_time = EXCLUDED.bio_time,
                active_action = EXCLUDED.active_action
        ''', (user_id, session, font_id, int(status), int(name_time), int(bio_time), active_action))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"❌ خطا در ذخیره کاربر {user_id}: {e}")

def delete_user_db(user_id):
    """حذف کاربر از دیتابیس"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM novaself_users WHERE user_id = %s", (user_id,))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"❌ خطا در حذف کاربر {user_id}: {e}")

# ======================== توابع کمکی ========================
def apply_font(text, font_id):
    """اعمال فونت بر روی متن زمان"""
    font_dict = FONTS.get(font_id, FONTS[0])
    return "".join(font_dict.get(char, char) for char in text)

def get_main_menu_keyboard(user_data):
    """ساخت کیبورد منوی اصلی"""
    status_text = "🟢 فعال" if user_data["status"] else "🔴 غیرفعال"
    return [
        [Button.inline(f"وضعیت سلف: {status_text}", b"toggle_status")],
        [Button.inline("⌚ تنظیمات ساعت", b"menu_time"), Button.inline("🎭 مدیریت اکشن", b"menu_actions")],
        [Button.inline("🗑️ حذف اکانت", b"delete_account")]
    ]

def get_time_menu_keyboard(user_data):
    """ساخت کیبورد منوی تنظیمات ساعت"""
    name_status = "✅ فعال" if user_data["name_time"] else "❌ غیرفعال"
    bio_status = "✅ فعال" if user_data["bio_time"] else "❌ غیرفعال"
    current_font = FONT_NAMES.get(user_data["font_id"], "بولد")
    
    return [
        [Button.inline(f"نمایش در نام: {name_status}", b"toggle_name_time")],
        [Button.inline(f"نمایش در بیو: {bio_status}", b"toggle_bio_time")],
        [Button.inline(f"🔤 تغییر فونت: {current_font}", b"menu_fonts")],
        [Button.inline("🔙 بازگشت", b"back_to_main")]
    ]

def get_fonts_menu_keyboard(current_font_id):
    """ساخت کیبورد منوی انتخاب فونت"""
    buttons = []
    row = []
    
    for font_id, font_name in FONT_NAMES.items():
        display = f"✅ {font_name}" if font_id == current_font_id else f"🔹 {font_name}"
        row.append(Button.inline(display, f"setfont_{font_id}".encode()))
        
        if len(row) == 2:
            buttons.append(row)
            row = []
    
    if row:
        buttons.append(row)
    
    buttons.append([Button.inline("🔙 بازگشت به ساعت", b"menu_time")])
    return buttons

def get_actions_menu_keyboard(current_action):
    """ساخت کیبورد منوی اکشن‌ها"""
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

def get_code_keyboard(current_code=""):
    """ساخت کیبورد عددی برای وارد کردن کد"""
    display = current_code if current_code else "خالی"
    return [
        [Button.inline(f"🔢 کد وارد شده: {display}", b"void")],
        [Button.inline("1", b"k_1"), Button.inline("2", b"k_2"), Button.inline("3", b"k_3")],
        [Button.inline("4", b"k_4"), Button.inline("5", b"k_5"), Button.inline("6", b"k_6")],
        [Button.inline("7", b"k_7"), Button.inline("8", b"k_8"), Button.inline("9", b"k_9")],
        [Button.inline("❌ پاک کردن", b"k_clear"), Button.inline("0", b"k_0"), Button.inline("✅ تایید", b"k_submit")]
    ]

# ======================== توابع اصلی سلف ========================
async def self_bot_worker(user_id, client):
    """کارگر اصلی سلف برای بروزرسانی زمان در پروفایل"""
    try:
        me = await client.get_me()
        first_name = me.first_name or "کاربر"
        base_bio = "NovaSelf Bot"
        last_time = ""
        
        while True:
            if user_id not in user_data or not user_data[user_id]["status"]:
                break
                
            user = user_data[user_id]
            tehran_tz = pytz.timezone('Asia/Tehran')
            current_time = datetime.now(tehran_tz).strftime("%H:%M")
            
            if current_time != last_time:
                formatted_time = apply_font(current_time, user["font_id"])
                
                try:
                    if user["name_time"]:
                        await client(UpdateProfileRequest(first_name=first_name, last_name=formatted_time))
                    else:
                        await client(UpdateProfileRequest(first_name=first_name, last_name=""))
                    
                    if user["bio_time"]:
                        await client(UpdateProfileRequest(about=f"{base_bio} | {formatted_time}"))
                    
                    last_time = current_time
                except Exception as e:
                    print(f"⚠️ خطا در بروزرسانی پروفایل کاربر {user_id}: {e}")
            
            await asyncio.sleep(5)
            
    except Exception as e:
        print(f"❌ خطای اصلی سلف برای کاربر {user_id}: {e}")
    finally:
        try:
            if not client.is_connected():
                await client.disconnect()
        except:
            pass

async def self_bot_action_worker(user_id, client):
    """کارگر نمایش اکشن‌های فیک"""
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
                # نمایش اکشن برای دیالوگ‌های اخیر
                async for dialog in client.iter_dialogs(limit=10):
                    if dialog.is_user or dialog.is_group:
                        try:
                            await client(SetTypingRequest(
                                peer=dialog.input_entity,
                                action=ACTIONS[action_key][1]
                            ))
                        except:
                            pass
            except Exception as e:
                print(f"⚠️ خطا در نمایش اکشن کاربر {user_id}: {e}")
            
            await asyncio.sleep(4)
            
    except Exception as e:
        print(f"❌ خطای اکشن برای کاربر {user_id}: {e}")

async def autostart_saved_users():
    """راه‌اندازی خودکار کاربران ذخیره شده"""
    await asyncio.sleep(5)
    
    for user_id, user in list(user_data.items()):
        if user["status"] and user["session"]:
            try:
                client = TelegramClient(StringSession(user["session"]), API_ID, API_HASH)
                await client.connect()
                
                if await client.is_user_authorized():
                    active_clients[user_id] = client
                    
                    loop = asyncio.get_event_loop()
                    user["task"] = loop.create_task(self_bot_worker(user_id, client))
                    user["action_task"] = loop.create_task(self_bot_action_worker(user_id, client))
                    
                    print(f"✅ سلف کاربر {user_id} راه‌اندازی شد.")
                else:
                    user["status"] = False
                    save_user(user_id, user["session"], user["font_id"], False, 
                             user["name_time"], user["bio_time"], user["active_action"])
            except Exception as e:
                print(f"❌ خطا در راه‌اندازی خودکار کاربر {user_id}: {e}")

# ======================== هندلرهای ربات ========================
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    """هندلر دستور /start"""
    user_id = event.sender_id
    
    # جلوگیری از تداخل با فرآیند ساخت حساب
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
            "task": None,
            "action_task": None,
            "step": "menu"
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

@bot.on(events.CallbackQuery)
async def callback_handler(event):
    """هندلر کلیک روی دکمه‌ها"""
    user_id = event.sender_id
    data = event.data
    
    # دکمه بی‌اثر
    if data == b"void":
        await event.answer()
        return
    
    # ====== ثبت با سشن آماده ======
    if data == b"send_ready_session":
        user_data[user_id]["step"] = "get_session"
        await event.edit(
            "✍️ **ارسال سشن آماده**\n\n"
            "لطفاً کد نشست (Session String) خود را که از Telethon دریافت کرده‌اید، ارسال کنید:"
        )
        return
    
    # ====== ساخت خودکار ======
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
    
    # ====== مدیریت کد تایید ======
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
    
    # ====== منوی اصلی ======
    if user_id not in user_data:
        return
    
    user = user_data[user_id]
    
    # بازگشت به منوی اصلی
    if data == b"back_to_main":
        await event.edit(
            "🔗 **پنل مدیریت NovaSelf**\n"
            "از طریق منوی زیر می‌توانید تنظیمات خود را مدیریت کنید:",
            buttons=get_main_menu_keyboard(user)
        )
        return
    
    # منوی تنظیمات ساعت
    if data == b"menu_time":
        await event.edit(
            "⌚ **تنظیمات ساعت**\n\n"
            "در این بخش می‌توانید نحوه نمایش زمان در پروفایل خود را تنظیم کنید:",
            buttons=get_time_menu_keyboard(user)
        )
        return
    
    # منوی انتخاب فونت
    if data == b"menu_fonts":
        await event.edit(
            "🔤 **انتخاب فونت ساعت**\n\n"
            "لطفاً یکی از فونت‌های زیر را برای نمایش ساعت انتخاب کنید:",
            buttons=get_fonts_menu_keyboard(user["font_id"])
        )
        return
    
    # منوی اکشن‌ها
    if data == b"menu_actions":
        await event.edit(
            "🎭 **مدیریت اکشن‌های فیک**\n\n"
            "با انتخاب هر گزینه، وضعیت شما به‌صورت مداوم برای دیگران نمایش داده می‌شود:",
            buttons=get_actions_menu_keyboard(user["active_action"])
        )
        return
    
    # تغییر فونت
    if data.startswith(b"setfont_"):
        font_id = int(data.decode().split("_")[1])
        user["font_id"] = font_id
        
        save_user(user_id, user["session"], font_id, user["status"], 
                 user["name_time"], user["bio_time"], user["active_action"])
        
        await event.edit(
            "🔤 **انتخاب فونت ساعت**\n\n"
            f"✅ فونت «{FONT_NAMES[font_id]}» با موفقیت انتخاب شد.",
            buttons=get_fonts_menu_keyboard(font_id)
        )
        return
    
    # تغییر اکشن
    if data.startswith(b"setact_"):
        action_key = data.decode().split("_")[1]
        
        if user["active_action"] == action_key:
            user["active_action"] = "none"
        else:
            user["active_action"] = action_key
        
        save_user(user_id, user["session"], user["font_id"], user["status"],
                 user["name_time"], user["bio_time"], user["active_action"])
        
        await event.edit(
            "🎭 **مدیریت اکشن‌های فیک**\n\n"
            f"✅ وضعیت اکشن با موفقیت تغییر یافت.",
            buttons=get_actions_menu_keyboard(user["active_action"])
        )
        return
    
    # تغییر وضعیت سلف (روشن/خاموش)
    if data == b"toggle_status":
        user["status"] = not user["status"]
        save_user(user_id, user["session"], user["font_id"], user["status"],
                 user["name_time"], user["bio_time"], user["active_action"])
        
        if user["status"]:
            try:
                client = TelegramClient(StringSession(user["session"]), API_ID, API_HASH)
                await client.connect()
                
                if await client.is_user_authorized():
                    active_clients[user_id] = client
                    loop = asyncio.get_event_loop()
                    user["task"] = loop.create_task(self_bot_worker(user_id, client))
                    user["action_task"] = loop.create_task(self_bot_action_worker(user_id, client))
                else:
                    user["status"] = False
                    await event.answer("❌ نشست منقضی شده است!", alert=True)
            except Exception as e:
                user["status"] = False
                await event.answer(f"❌ خطا در راه‌اندازی: {str(e)[:50]}", alert=True)
        else:
            if user["task"]:
                user["task"].cancel()
            if user["action_task"]:
                user["action_task"].cancel()
            if user_id in active_clients:
                del active_clients[user_id]
        
        await event.edit(
            "🔗 **پنل مدیریت NovaSelf**\n"
            "از طریق منوی زیر می‌توانید تنظیمات خود را مدیریت کنید:",
            buttons=get_main_menu_keyboard(user)
        )
        return
    
    # تغییر نمایش در نام
    if data == b"toggle_name_time":
        user["name_time"] = not user["name_time"]
        save_user(user_id, user["session"], user["font_id"], user["status"],
                 user["name_time"], user["bio_time"], user["active_action"])
        
        await event.edit(
            "⌚ **تنظیمات ساعت**\n\n"
            "در این بخش می‌توانید نحوه نمایش زمان در پروفایل خود را تنظیم کنید:",
            buttons=get_time_menu_keyboard(user)
        )
        return
    
    # تغییر نمایش در بیو
    if data == b"toggle_bio_time":
        user["bio_time"] = not user["bio_time"]
        save_user(user_id, user["session"], user["font_id"], user["status"],
                 user["name_time"], user["bio_time"], user["active_action"])
        
        await event.edit(
            "⌚ **تنظیمات ساعت**\n\n"
            "در این بخش می‌توانید نحوه نمایش زمان در پروفایل خود را تنظیم کنید:",
            buttons=get_time_menu_keyboard(user)
        )
        return
    
    # حذف اکانت
    if data == b"delete_account":
        if user["task"]:
            user["task"].cancel()
        if user["action_task"]:
            user["action_task"].cancel()
        if user_id in active_clients:
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
    """پردازش کد تایید و تکمیل ورود"""
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
            "task": None,
            "action_task": None,
            "step": "managed"
        }
        
        active_clients[user_id] = client
        save_user(user_id, session_string, 1, True, True, False, "none")
        
        loop = asyncio.get_event_loop()
        user_data[user_id]["task"] = loop.create_task(self_bot_worker(user_id, client))
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
    """هندلر پیام‌های متنی کاربران"""
    user_id = event.sender_id
    text = event.text.strip() if event.text else ""
    
    # ====== پردازش ساخت خودکار حساب ======
    if user_id in generator_data:
        generator = generator_data[user_id]
        
        # مرحله دریافت شماره
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
        
        # مرحله دریافت رمز دو مرحله‌ای
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
                    "task": None,
                    "action_task": None,
                    "step": "managed"
                }
                
                active_clients[user_id] = client
                save_user(user_id, session_string, 1, True, True, False, "none")
                
                loop = asyncio.get_event_loop()
                user_data[user_id]["task"] = loop.create_task(self_bot_worker(user_id, client))
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
            "task": None,
            "action_task": None,
            "step": "managed"
        }
        
        active_clients[user_id] = client
        save_user(user_id, clean_session, 1, True, True, False, "none")
        
        loop = asyncio.get_event_loop()
        user_data[user_id]["task"] = loop.create_task(self_bot_worker(user_id, client))
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

# ======================== اجرای اصلی ========================
if __name__ == "__main__":
    print("🚀 راه‌اندازی ربات NovaSelf...")
    
    # راه‌اندازی دیتابیس
    init_db()
    
    # بارگذاری کاربران
    user_data = get_all_users()
    print(f"📊 تعداد کاربران بارگذاری شده: {len(user_data)}")
    
    # اجرای ربات
    loop = asyncio.get_event_loop()
    loop.create_task(autostart_saved_users())
    
    print("✅ ربات با موفقیت راه‌اندازی شد!")
    bot.run_until_disconnected()
