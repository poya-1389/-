import asyncio
import os
import pytz
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.tl.functions.account import UpdateProfileRequest

# تنظیمات اولیه ربات از ریلوی
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# راه‌اندازی ربات هلپر
bot = TelegramClient('helper_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# دیتابیس موقت در حافظه سرور
user_data = {}

def to_bold_font(time_str):
    bold_digits = {'0': '𝟬', '1': '𝟭', '2': '𝟮', '3': '𝟯', '4': '𝟰', '5': '𝟱', '6': '𝟲', '7': '𝟳', '8': '𝟴', '9': '𝟵', ':': ':'}
    return "".join(bold_digits.get(char, char) for char in time_str)

async def self_bot_worker(user_id):
    last_time = ""
    while True:
        try:
            if user_id not in user_data or not user_data[user_id]["status"]:
                break
                
            ud = user_data[user_id]
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

@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    user_id = event.sender_id
    
    if user_id not in user_data:
        user_data[user_id] = {"session": None, "font": "bold", "status": False, "task": None, "step": "get_session"}
        msg = "سلام!\nلطفاً کُد نشست (Session String) تلتون اکانت خود را ارسال کنید:"
        await event.respond(msg)
        return

    await send_manager_panel(event, user_id)

async def send_manager_panel(event, user_id):
    ud = user_data[user_id]
    status_text = "🟢 روشن" if ud["status"] else "🔴 خاموش"
    font_text = "بولد (𝟭𝟮𝟯)" if ud["font"] == "bold" else "معمولی (123)"
    
    buttons = [
        [Button.inline(f"وضعیت سلف: {status_text}", b"toggle_status")],
        [Button.inline(f"فونت ساعت: {font_text}", b"toggle_font")],
        [Button.inline("❌ حذف اکانت و خروج", b"delete_account")]
    ]
    await event.respond("🎛 پنل مدیریت سلف‌بات شما:", buttons=buttons)

@bot.on(events.NewMessage)
async def message_handler(event):
    user_id = event.sender_id
    if user_id in user_data and user_data[user_id].get("step") == "get_session":
        session_text = event.text.strip()
        
        try:
            test_client = TelegramClient(StringSession(session_text), API_ID, API_HASH)
            await test_client.connect()
