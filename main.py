import asyncio
import os
import pytz
import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from telethon.tl.functions.account import UpdateProfileRequest, UpdateProfileRequest as UpdateBioRequest # جهت بیوگرافی
from telethon.tl.functions.messages import SetTypingRequest
from telethon.tl.types import (
    SendMessageTypingAction, SendMessageRecordAudioAction, SendMessageUploadPhotoAction,
    SendMessageRecordRoundAction, SendMessageUploadDocumentAction, SendMessageUploadVideoAction,
    SendMessageGamePlayAction, SendMessageChooseStickerAction
)

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

bot = TelegramClient('helper_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

active_clients = {}
generator_data = {}
active_signins = {}

# ----------------- دیتابیس ابری PostgreSQL -----------------
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    # ساخت جدول جدید با تمام ویژگی‌های درخواستی شما برای ذخیره ماندگار
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS novaself_users (
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
    cursor.close()
    conn.close()

def get_all_users():
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
            "active_action": row['active_action'], # ذخیره نام اکشن فعال یا 'none'
            "step": "managed",
            "task": None,
            "action_task": None
        }
    return data

def save_user(user_id, session, font_id, status, name_time, bio_time, active_action):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO novaself_users (user_id, session, font_id, status, name_time, bio_time, active_action)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id) 
        DO UPDATE SET session = EXCLUDED.session, font_id = EXCLUDED.font_id, status = EXCLUDED.status,
                      name_time = EXCLUDED.name_time, bio_time = EXCLUDED.bio_time, active_action = EXCLUDED.active_action
    ''', (user_id, session, font_id, int(status), int(name_time), int(bio_time), active_action))
    conn.commit()
    cursor.close()
    conn.close()

def delete_user_db(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM novaself_users WHERE user_id = %s", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()

init_db()
user_data = get_all_users()
# ---------------------------------------------------------

FONTS = {
    0: {'0':'0','1':'1','2':'2','3':'3','4':'4','5':'5','6':'6','7':'7','8':'8','9':'9'},
    1: {'0':'𝟬','1':'𝟭','2':'𝟮','3':'𝟯','4':'𝟰','5':'𝟱','6':'𝟲','7':'𝟳','8':'𝟴','9':'𝟵'},
    2: {'0':'𝟶','1':'𝟷','2':'𝟸','3':'𝟹','4':'𝟺','5':'𝟻','6':'𝟼','7':'𝟽','8':'𝟾','9':'𝟿'},
    3: {'0':'⓪','1':'①','2':'②','3':'③','4':'④','5':'⑤','6':'⑥','7':'⑦','8':'⑧','9':'⑨'},
    4: {'0':'🄀','1':'⒈','2':'⒉','3':'⒊','4':'⒋','5':'⒌','6':'6','7':'⒎','8':'⒏','9':'⒐'},
    5: {'0':'🄿','1':'🄱','2':'🄲','3':'🄳','4':'🄴','5':'🄵','6':'🄶','7':'🄷','8':'🄸','9':'🄹'},
    6: {'0':'𝟢','1':'𝟣','2':'𝟤','3':'𝟥','4':'𝟦','5':'𝟧','6':'𝟨','7':'𝟩','8':'𝟪','9':'𝟫'},
    7: {'0':'𝞯','1':'𝞱','2':'𝞲','3':'𝞳','4':'𝞴','5':'𝞵','6':'𝞶','7':'𝞷','8':'𝞸','9':'𝞹'},
    8: {'0':'۰','1':'۱','2':'۲','3':'۳','4':'۴','5':'۵','6':'۶','7':'۷','8':'۸','9':'۹'},
    9: {'0':'٠','1':'١','2':'٢','3':'٣','4':'٤','5':'٥','6':'٦','7':'٧','8':'٨','9':'٩'}
}

FONT_NAMES = {
    0: "معمولی (123)", 1: "بولد (𝟭𝟮𝟯)", 2: "ماشین تحریر (𝟷𝟸𝟹)", 
    3: "دایره‌ای (①②③)", 4: "نقطه‌دار (⒈⒉⒊)", 5: "مربعی (🄿🄱🄲)", 
    6: "کج (𝟢𝟣𝟤)", 7: "ریاضی (𝞯🞱🞲)", 8: "فارسی (۱۲۳)", 9: "عربی (١٢٣)"
}

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

def apply_font(t_str, font_id):
    f_dict = FONTS.get(font_id, FONTS[0])
    return "".join(f_dict.get(c, c) for c in t_str)

# وورکر فرستادن وضعیت‌های فیک اکشن به صورت مداوم
async def self_bot_action_worker(user_id, client):
    try:
        while True:
            if user_id not in user_data or not user_data[user_id]["status"]:
                break
            ud = user_data[user_id]
            act = ud["active_action"]
            if act == 'none' or act not in ACTIONS:
                await asyncio.sleep(4)
                continue
            
            # ارسال سیگنال اکشن به یک چت فیک یا کلی (خود کاربر)
            await client(SetTypingActionRequest(peer='me', action=ACTIONS[act][1]))
            await asyncio.sleep(4)
    except Exception:
        pass

async def self_bot_worker(user_id, client):
    last_time = ""
    try:
        me = await client.get_me()
        f_name = me.first_name or "User"
        # گرفتن بیوگرافی اولیه جهت آپدیت تایم روی آن
        full_user = await client.get_me()
        base_bio = "NovaSelf Bot"
        
        while True:
            if user_id not in user_data or not user_data[user_id]["status"]:
                break
            ud = user_data[user_id]
            tz = pytz.timezone('Asia/Tehran')
            curr_time = datetime.now(tz).strftime("%H:%M")
            
            if curr_time != last_time:
                f_time = apply_font(curr_time, ud["font_id"])
                
                # تنظیم ساعت روی نام
                if ud["name_time"]:
                    await client(UpdateProfileRequest(first_name=f_name, last_name=f_time))
                else:
                    await client(UpdateProfileRequest(first_name=f_name, last_name=""))
                
                # تنظیم ساعت روی بیو
                if ud["bio_time"]:
                    await client(UpdateProfileRequest(about=f"{base_bio} | {f_time}"))
                
                last_time = curr_time
            await asyncio.sleep(5)
    except Exception as e:
        print(f"Loop error for {user_id}: {e}")
    finally:
        try:
            await client.disconnect()
        except:
            pass

async def autostart_saved_users():
    await asyncio.sleep(5)
    for user_id, ud in list(user_data.items()):
        if ud["status"] and ud["session"]:
            try:
                client = TelegramClient(StringSession(ud["session"]), API_ID, API_HASH)
                await client.connect()
                if await client.is_user_authorized():
                    active_clients[user_id] = client
                    loop = asyncio.get_event_loop()
                    user_data[user_id]["task"] = loop.create_task(self_bot_worker(user_id, client))
                    user_data[user_id]["action_task"] = loop.create_task(self_bot_action_worker(user_id, client))
                    print(f"سلف اکانت {user_id} خودکار روشن شد.")
                else:
                    user_data[user_id]["status"] = False
                    save_user(user_id, ud["session"], ud["font_id"], False, ud["name_time"], ud["bio_time"], ud["active_action"])
            except Exception as e:
                print(f"خطا در اتواستارت {user_id}: {e}")

def get_keyboard_layout(current_code=""):
    display = current_code if current_code else "خالی"
    btns = [
        [Button.inline(f"🔢 کد وارد شده: {display}", b"void")],
        [Button.inline("1", b"k_1"), Button.inline("2", b"k_2"), Button.inline("3", b"k_3")],
        [Button.inline("4", b"k_4"), Button.inline("5", b"k_5"), Button.inline("6", b"k_6")],
        [Button.inline("7", b"k_7"), Button.inline("8", b"k_8"), Button.inline("9", b"k_9")],
        [Button.inline("❌ پاک کردن", b"k_clear"), Button.inline("0", b"k_0"), Button.inline("✅ تایید و ورود", b"k_submit")]
    ]
    return btns

# ساخت کیبورد منوی اصلی
def get_main_menu_keyboard(ud):
    st = "🟢 روشن" if ud["status"] else "🔴 خاموش"
    return [
        [Button.inline(f"وضعیت سلف: {st}", b"t_status")],
        [Button.inline("⏰ تنظیمات ساعت پروفایل", b"menu_time"), Button.inline("🎭 اکشن‌های فیک", b"menu_actions")],
        [Button.inline("❌ حذف اکانت", b"del")]
    ]

# ساخت کیبورد منوی ساعت پروفایل
def get_time_menu_keyboard(ud):
    nt = "✅ ساعت نام" if ud["name_time"] else "❌ ساعت نام"
    bt = "✅ ساعت بیو" if ud["bio_time"] else "❌ ساعت بیو"
    current_font_name = FONT_NAMES.get(ud["font_id"], "بولد")
    return [
        [Button.inline(nt, b"t_name_time"), Button.inline(bt, b"t_bio_time")],
        [Button.inline(f"⚙️ فونت ساعت: {current_font_name}", b"menu_fonts")],
        [Button.inline("🔙 بازگشت به منوی اصلی", b"back_to_main")]
    ]

# ساخت کیبورد لیست فونت‌ها با تیک هوشمند
def get_fonts_menu_keyboard(current_font_id):
    btns = []
    # چیدمان دکمه‌ها به صورت دو تایی برای زیبایی منو
    row = []
    for f_id, f_name in FONT_NAMES.items():
        display_name = f"🔹 {f_name}"
        if f_id == current_font_id:
            display_name = f"✅ {f_name}"
        row.append(Button.inline(display_name, f"setfont_{f_id}".encode()))
        if len(row) == 2:
            btns.append(row)
            row = []
    if row:
        btns.append(row)
    btns.append([Button.inline("🔙 بازگشت به تنظیمات ساعت", b"menu_time")])
    return btns

# ساخت کیبورد اکشن‌ها با تیک هوشمند
def get_actions_menu_keyboard(current_action):
    btns = []
    row = []
    for act_key, (act_name, _) in ACTIONS.items():
        display_name = f"⚪️ {act_name}"
        if act_key == current_action:
            display_name = f"🟢 {act_name} "
        row.append(Button.inline(display_name, f"setact_{act_key}".encode()))
        if len(row) == 2:
            btns.append(row)
            row = []
    if row:
        btns.append(row)
    btns.append([Button.inline("🔙 بازگشت به منوی اصلی", b"back_to_main")])
    return btns

@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    user_id = event.sender_id
    if user_id in generator_data:
        return

    if user_id not in user_data:
        # ساخت مقادیر پیش‌فرض درخواستی شما (ساعت نام فعال، ساعت بیو غیرفعال، فونت بولد=1)
        user_data[user_id] = {
            "session": None, "font_id": 1, "status": False, "name_time": True, 
            "bio_time": False, "active_action": "none", "task": None, "action_task": None, "step": "menu"
        }
        
    ud = user_data[user_id]
    
    if ud["session"] is None:
        btns = [
            [Button.inline("📱 ساخت خودکار سلف با شماره تلفن", b"start_gen_fast")],
            [Button.inline("✍️ ارسال سشن آماده متنی", b"send_ready_session")]
        ]
        await event.respond("⚡️ به ربات مدیریت نواسلف خوش آمدید!\nلطفاً یکی از روش‌های زیر را انتخاب کنید:", buttons=btns)
    else:
        await event.respond("🔗 پنل مدیریت نواسلف:", buttons=get_main_menu_keyboard(ud))

@bot.on(events.CallbackQuery)
async def callback_handler(event):
    user_id = event.sender_id
    data = event.data
    
    if data == b"void":
        await event.answer()
        return

    if data == b"send_ready_session":
        user_data[user_id]["step"] = "get_session"
        await event.edit("✍️ لطفاً کُد نشست (Session String) متنی تلتون خود را ارسال کنید:")
        return

    elif data == b"start_gen_fast":
        generator_data[user_id] = {"step": "get_phone", "phone": None, "phone_code_hash": None, "code_buffer": ""}
        await event.edit("📞 **مرحله اول:**\nلطفاً **شماره تلفن** اکانت خود را همراه با کد کشور بفرستید:\n(مثال: `+989123456789`)")
        return

    if user_id in generator_data and generator_data[user_id]["step"] == "get_code":
        gd = generator_data[user_id]
        if data.startswith(b"k_"):
            action = data.decode().split("_")[1]
            if action.isdigit():
                if len(gd["code_buffer"]) < 5:
                    gd["code_buffer"] += action
                await event.edit("📩 **مرحله دوم:**\nکد دریافتی از تلگرام را از روی کیپد زیر وارد کنید:", buttons=get_keyboard_layout(gd["code_buffer"]))
            elif action == "clear":
                gd["code_buffer"] = ""
                await event.edit("📩 **مرحله دوم:**\nکد دریافتی از تلگرام را از روی کیپد زیر وارد کنید:", buttons=get_keyboard_layout(gd["code_buffer"]))
            elif action == "submit":
                if len(gd["code_buffer"]) < 5:
                    await event.answer("⚠️ لطفاً کد ۵ رقمی را کامل وارد کنید!", alert=True)
                    return
                await event.edit("⏳ در حال بررسی کد و ورود به حساب...")
                await process_code_signin(event, user_id, gd["code_buffer"])
            return

    if user_id not in user_data:
        return
        
    ud = user_data[user_id]
        
    # --- ناوبری منوها ---
    if data == b"back_to_main":
        await event.edit("🔗 پنل مدیریت نواسلف:", buttons=get_main_menu_keyboard(ud))
        return
        
    elif data == b"menu_time":
        await event.edit("⏰ **تنظیمات ساعت پروفایل**\nدر این بخش می‌توانید نمایش زمان در نام یا بیوگرافی را مدیریت کنید:", buttons=get_time_menu_keyboard(ud))
        return
        
    elif data == b"menu_fonts":
        await event.edit("🔤 **فونت ساعت**\nلطفاً یکی از فونت‌های زیر را برای نمایش ساعت انتخاب کنید:", buttons=get_fonts_menu_keyboard(ud["font_id"]))
        return
        
    elif data == b"menu_actions":
        await event.edit("🎭 **منوی اکشن‌های فیک**\nبا انتخاب هر مورد، وضعیت شما به طور مداوم برای دیگران نمایش داده می‌شود:", buttons=get_actions_menu_keyboard(ud["active_action"]))
        return

    # --- تنظیمات اکشن‌ها و فونت‌ها از کال‌بک دکمه‌ها ---
    elif data.startswith(b"setfont_"):
        target_font = int(data.decode().split("_")[1])
        ud["font_id"] = target_font
        save_user(user_id, ud["session"], ud["font_id"], ud["status"], ud["name_time"], ud["bio_time"], ud["active_action"])
        await event.edit("🔤 **فونت ساعت**\nلطفاً یکی از فونت‌های زیر را برای نمایش ساعت انتخاب کنید:", buttons=get_fonts_menu_keyboard(ud["font_id"]))
        return

    elif data.startswith(b"setact_"):
        target_action = data.decode().split("_")[1]
        # سوئیچ کردن وضعیت دکمه: اگر دوباره روش کلیک شد غیرفعال بشه
        if ud["active_action"] == target_action:
            ud["active_action"] = "none"
        else:
            ud["active_action"] = target_action
            
        save_user(user_id, ud["session"], ud["font_id"], ud["status"], ud["name_time"], ud["bio_time"], ud["active_action"])
        await event.edit("🎭 **منوی اکشن‌های فیک**\nبا انتخاب هر مورد، وضعیت شما به طور مداوم برای دیگران نمایش داده می‌شود:", buttons=get_actions_menu_keyboard(ud["active_action"]))
        return

    # --- کنترل‌های وضعیت اصلی، نام و بیو ---
    elif data == b"t_status":
        ud["status"] = not ud["status"]
        save_user(user_id, ud["session"], ud["font_id"], ud["status"], ud["name_time"], ud["bio_time"], ud["active_action"])
        
        if ud["status"]:
            try:
                client = TelegramClient(StringSession(ud["session"]), API_ID, API_HASH)
                await client.connect()
                active_clients[user_id] = client
                loop = asyncio.get_event_loop()
                ud["task"] = loop.create_task(self_bot_worker(user_id, client))
                ud["action_task"] = loop.create_task(self_bot_action_worker(user_id, client))
            except Exception:
                await event.answer("خطا در روشن کردن مجدد سلف.", alert=True)
        else:
            if ud["task"]: ud["task"].cancel()
            if ud["action_task"]: ud["action_task"].cancel()
            if user_id in active_clients: del active_clients[user_id]
        await event.edit("🔗 پنل مدیریت نواسلف:", buttons=get_main_menu_keyboard(ud))
        return
            
    elif data == b"t_name_time":
        ud["name_time"] = not ud["name_time"]
        save_user(user_id, ud["session"], ud["font_id"], ud["status"], ud["name_time"], ud["bio_time"], ud["active_action"])
        await event.edit("⏰ **تنظیمات ساعت پروفایل**\nدر این بخش می‌توانید نمایش زمان در نام یا بیوگرافی را مدیریت کنید:", buttons=get_time_menu_keyboard(ud))
        return
        
    elif data == b"t_bio_time":
        ud["bio_time"] = not ud["bio_time"]
        save_user(user_id, ud["session"], ud["font_id"], ud["status"], ud["name_time"], ud["bio_time"], ud["active_action"])
        await event.edit("⏰ **تنظیمات ساعت پروفایل**\nدر این بخش می‌توانید نمایش زمان در نام یا بیوگرافی را مدیریت کنید:", buttons=get_time_menu_keyboard(ud))
        return
        
    elif data == b"del":
        if ud["task"]: ud["task"].cancel()
        if ud["action_task"]: ud["action_task"].cancel()
        if user_id in active_clients: del active_clients[user_id]
        delete_user_db(user_id)
        del user_data[user_id]
        await event.edit("🗑 اطلاعات شما کاملاً پاک شد. برای شروع مجدد /start بزنید.")
        return

async def process_code_signin(event, user_id, code):
    gd = generator_data[user_id]
    client = active_signins.get(user_id)
    if not client:
        await event.respond("❌ نشست شما منقضی شده است. دوباره /start بزنید.")
        del generator_data[user_id]
        return
        
    try:
        await client.sign_in(gd["phone"], code, phone_code_hash=gd["phone_code_hash"])
        session_string = client.session.save()
        
        # ثبت اولیه با تنظیمات پیش‌فرض درخواستی شما
        user_data[user_id] = {
            "session": session_string, "font_id": 1, "status": True, "name_time": True,
            "bio_time": False, "active_action": "none", "task": None, "action_task": None, "step": "managed"
        }
        active_clients[user_id] = client
        save_user(user_id, session_string, 1, True, True, False, "none")
        
        loop = asyncio.get_event_loop()
        user_data[user_id]["task"] = loop.create_task(self_bot_worker(user_id, client))
        user_data[user_id]["action_task"] = loop.create_task(self_bot_action_worker(user_id, client))
        
        await event.respond("🎉 **اکانت با موفقیت متصل و در دیتابیس ابری ذخیره شد!**\n\n⚙️ نواسلف شما هم‌اکنون روشن است.")
        del generator_data[user_id]
        if user_id in active_signins: del active_signins[user_id]
        
        await event.respond("🔗 پنل مدیریت نواسلف:", buttons=get_main_menu_keyboard(user_data[user_id]))
        
    except SessionPasswordNeededError:
        gd["step"] = "get_password"
        await event.respond("🔐 **حساب شما دارای تایید دو مرحله‌ای است!**\nلطفاً رمز عبور حساب خود را به صورت متنی ارسال کنید:")
    except Exception as e:
        gd["code_buffer"] = ""
        await event.respond(f"❌ خطایی رخ داد: {e}\nمجدداً تلاش کنید:")
        await event.respond("📩 مجدداً کد دریافتی را با دکمه‌ها وارد کنید:", buttons=get_keyboard_layout(""))

@bot.on(events.NewMessage)
async def message_handler(event):
    user_id = event.sender_id
    text = event.text.strip() if event.text else ""
    
    if user_id in generator_data:
        gd = generator_data[user_id]
        
        if gd["step"] == "get_phone":
            gd["phone"] = text
            await event.respond("⏳ در حال ارتباط مستقیم با سرورهای تلگرام...")
            try:
                client = TelegramClient(StringSession(), API_ID, API_HASH)
                await client.connect()
                
                send_code_res = await client.send_code_request(gd["phone"])
                active_signins[user_id] = client
                gd["phone_code_hash"] = send_code_res.phone_code_hash
                gd["step"] = "get_code"
                
                await event.respond(
                    "📩 **مرحله دوم:**\nکد تایید حساب برای تلگرام شما ارسال شد.\n\n"
                    "🔒 لطفاً کد ۵ رقمی را از طریق دکمه‌های زیر وارد کرده و دکمه تایید را بزنید:",
                    buttons=get_keyboard_layout("")
                )
            except Exception as e:
                await event.respond(f"❌ خطایی در ارسال کد رخ داد: {e}\nمراحل لغو شد. مجدداً /start کنید.")
                if user_id in active_signins: del active_signins[user_id]
                del generator_data[user_id]
                
        elif gd["step"] == "get_password":
            client = active_signins.get(user_id)
            if not client:
                await event.respond("❌ نشست منقضی شد. دوباره /start بزنید.")
                del generator_data[user_id]
                return
                
            try:
                await client.sign_in(password=text)
                session_string = client.session.save()
                
                user_data[user_id] = {
                    "session": session_string, "font_id": 1, "status": True, "name_time": True,
                    "bio_time": False, "active_action": "none", "task": None, "action_task": None, "step": "managed"
                }
                active_clients[user_id] = client
                save_user(user_id, session_string, 1, True, True, False, "none")
                
                loop = asyncio.get_event_loop()
                user_data[user_id]["task"] = loop.create_task(self_bot_worker(user_id, client))
                user_data[user_id]["action_task"] = loop.create_task(self_bot_action_worker(user_id, client))
                
                await event.respond("🎉 **با رمز دو مرحله‌ای وارد شدید و اکانت متصل شد!**")
                del generator_data[user_id]
                if user_id in active_signins: del active_signins[user_id]
                
                await event.respond("🔗 پنل مدیریت نواسلف:", buttons=get_main_menu_keyboard(user_data[user_id]))
            except Exception as e:
                await event.respond(f"❌ رمز عبور دو مرحله‌ای اشتباه است: {e}\nلطفاً مجدداً رمز صحیح را بفرستید:")
        return

    if user_id in user_data and user_data[user_id].get("step") == "get_session":
        clean_session = text.replace("\n", "").replace("\r", "").replace(" ", "")
        try:
            client = TelegramClient(StringSession(clean_session), API_ID, API_HASH)
            await client.connect()
            if not await client.is_user_authorized():
                await event.respond("❌ این سشن معتبر نیست یا منقضی شده است. دوباره تلاش کنید.")
                await client.disconnect()
                return
        except Exception:
            await event.respond("❌ ساختار متن ارسال شده اشتباه است.\nمطمئن شوید سشن تلتون (Telethon) است.")
            return
            
        user_data[user_id] = {
            "session": clean_session, "font_id": 1, "status": True, "name_time": True,
            "bio_time": False, "active_action": "none", "task": None, "action_task": None, "step": "managed"
        }
        active_clients[user_id] = client
        save_user(user_id, clean_session, 1, True, True, False, "none")
        
        loop = asyncio.get_event_loop()
        user_data[user_id]["task"] = loop.create_task(self_bot_worker(user_id, client))
        user_data[user_id]["action_task"] = loop.create_task(self_bot_action_worker(user_id, client))
        await event.respond("✅ سلف با موفقیت ثبت، اطلاعات از دیتابیس ابری زنده شد!")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(autostart_saved_users())
    bot.run_until_disconnected()
