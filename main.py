import asyncio
import os
import pytz
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.tl.functions.account import UpdateProfileRequest

# دریافت اطلاعات اصلی ربات از ریلوی
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN") # توکن رباتی که از BotFather گرفتید

# راه‌اندازی ربات اصلی
bot = TelegramClient('helper_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# دیتابیس موقت در حافظه سرور (در آینده به دیتابیس واقعی وصل میشه)
# ساختار: { user_id: {"session": "...", "font": "bold", "status": True, "task": Task_Object} }
user_data = {}

# تبدیل فونت اعداد
def to_bold_font(time_str):
    bold_digits = {'0': '𝟬', '1': '𝟭', '2': '𝟮', '3': '𝟯', '4': '𝟰', '5': '𝟱', '6': '𝟲', '7': '𝟳', '8': '𝟴', '9': '𝟵', ':': ':'}
    return "".join(bold_digits.get(char, char) for char in time_str)

# وظیفه پس‌زمینه برای آپدیت ساعت هر کاربر
async def self_bot_worker(user_id):
    last_time = ""
    while True:
        try:
            # اگر کاربر سلفش رو خاموش کرد یا اطلاعاتش نبود، حلقه متوقف بشه
            if user_id not in user_data or not user_data[user_id]["status"]:
                break
                
            ud = user_data[user_id]
            # ساخت کلاینت موقت برای اکانت کاربر
            client = TelegramClient(StringSession(ud["session"]), API_ID, API_HASH)
            
            async with client:
                tehran_tz = pytz.timezone('Asia/Tehran')
                current_time = datetime.now(tehran_tz).strftime("%H:%M")
                
                if current_time != last_time:
                    display_time = to_bold_font(current_time) if ud["font"] == "bold" else current_time
                    await client(UpdateProfileRequest(last_name=display_time))
                    last_time = current_time
                    
        except Exception as e:
            print(f"Error for user {user_id}: {e}")
            
        await asyncio.sleep(30)

# دستور استارت ربات
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    user_id = event.sender_id
    
    # اگر کاربر از قبل ثبت نام نکرده بود
    if user_id not in user_data:
        user_data[user_id] = {"session": None, "font": "bold", "status": False, "task": None, "step": "get_session"}
        await event.respond(
            "سلام! به ربات سلف‌ساز خوش آمدید.\n\n"
            "برای فعال‌سازی ساعت روی فامیلی خود، لطفاً **Session String (تلتون)** اکانت خود را ارسال کنید:\n"
            "⚠️ دقت کنید سشن حتماً با تلتون گرفته شده باشد."
        )
        return

    # اگر ثبت نام کرده بود، پنل مدیریت شیشه‌ای رو نشون بده
    await send_manager_panel(event, user_id)

# تابع ساخت و ارسال پنل مدیریت
async def send_manager_panel(event, user_id):
    ud = user_data[user_id]
    status_text = "🟢 روشن" if ud["status"] else "🔴 خاموش"
    font_text = "بولد (𝟭𝟮𝟯)" if ud["font"] == "bold" else "معمولی (123)"
    
    buttons = [
        [Button.inline(f"وضعیت سلف: {status_text}", b"toggle_status")],
        [Button.inline(f"فونت ساعت: {font_text}", b"toggle_font")],
        [Button.inline("❌ حذف اکانت و خروج", b"delete_account")]
    ]
    
    await event.respond("🎛 **پنل مدیریت سلف‌بات شما:**", buttons=buttons)

# دریافت متن سشن از کاربر
@bot.on(events.NewMessage)
async def message_handler(event):
    user_id = event.sender_id
    if user_id in user_data and user_data[user_id].get("step") == "get_session":
        session_text = event.text.strip()
        
        # یک تست اولیه برای صحت سشن
        try:
            test_client = TelegramClient(StringSession(session_text), API_ID, API_HASH)
            await test_client.connect()
            if not await test_client.is_user_authorized():
                await event.respond("❌ این سشن معتبر نیست یا منقضی شده است. لطفا دوباره ارسال کنید.")
                await test_client.disconnect()
                return
            await test_client.disconnect()
        except Exception:
            await event.respond("❌ خطا در بررسی سشن. مطمئن شوید متن سشن تلتون را درست کپی کرده‌اید.")
            return
        
        # ذخیره سشن و انتقال به پنل
        user_data[user_id]["session"] = session_text
        user_data[user_id]["step"] = "managed"
        user_data[user_id]["status"] = True
        
        # روشن کردن تسک پس‌زمینه برای این کاربر
        loop = asyncio.get_event_loop()
        user_data[user_id]["task"] = loop.create_task(self_bot_worker(user_id))
        
        await event.respond("✅
