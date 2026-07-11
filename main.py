import asyncio
import os
import pytz
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.tl.functions.account import UpdateProfileRequest

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

bot = TelegramClient('helper_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
user_data = {}

def to_bold_font(t_str):
    bold_digits = {'0':'𝟬','1':'𝟭','2':'𝟮','3':'𝟯','4':'𝟰','5':'𝟱','6':'𝟲','7':'𝟳','8':'𝟴','9':'𝟵',':':':'}
    return "".join(bold_digits.get(c, c) for c in t_str)

async def self_bot_worker(user_id):
    last_time = ""
    while True:
        try:
            if user_id not in user_data or not user_data[user_id]["status"]:
                break
            ud = user_data[user_id]
            client = TelegramClient(StringSession(ud["session"]), API_ID, API_HASH)
            async with client:
                tz = pytz.timezone('Asia/Tehran')
                curr_time = datetime.now(tz).strftime("%H:%M")
                if curr_time != last_time:
                    f_time = to_bold_font(curr_time) if ud["font"] == "bold" else curr_time
                    await client(UpdateProfileRequest(last_name=f_time))
                    last_time = curr_time
        except Exception as e:
            print(f"Error: {e}")
        await asyncio.sleep(30)

@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    user_id = event.sender_id
    if user_id not in user_data:
        user_data[user_id] = {"session": None, "font": "bold", "status": False, "task": None, "step": "get_session"}
        await event.respond("سلام!\nلطفاً کد نشست (Session String) اکانت خود را بفرستید:")
        return
    ud = user_data[user_id]
    st = "🟢 روشن" if ud["status"] else "🔴 خاموش"
    ft = "بولد (𝟭𝟮𝟯)" if ud["font"] == "bold" else "معمولی (123)"
    btns = [[Button.inline(f"وضعیت سلف: {st}", b"t_status")],[Button.inline(f"فونت: {ft}", b"t_font")],[Button.inline("❌ حذف اکانت", b"del")]]
    await event.respond("🎛 پنل مدیریت سلف‌بات:", buttons=btns)

@bot.on(events.NewMessage)
async def message_handler(event):
    user_id = event.sender_id
    if user_id in user_data and user_data[user_id].get("step") == "get_session":
        user_data[user_id]["session"] = event.text.strip()
        user_data[user_id]["step"] = "managed"
        user_data[user_id]["status"] = True
        loop = asyncio.get_event_loop()
        user_data[user_id]["task"] = loop.create_task(self_bot_worker(user_id))
        await event.respond("✅ سلف با موفقیت فعال شد! برای مدیریت دوباره /start بزنید.")

@bot.on(events.CallbackQuery)
async def callback_handler(event):
    user_id = event.sender_id
    data = event.data
    if user_id not in user_data:
        return
    if data == b"t_status":
        user_data[user_id]["status"] = not user_data[user_id]["status"]
        if user_data[user_id]["status"]:
            loop = asyncio.get_event_loop()
            user_data[user_id]["task"] = loop.create_task(self_bot_worker(user_id))
        else:
            if user_data[user_id]["task"]: user_data[user_id]["task"].cancel()
    elif data == b"t_font":
        user_data[user_id]["font"] = "normal" if user_data[user_id]["font"] == "bold" else "bold"
    elif data == b"del":
        if user_data[user_id]["task"]: user_data[user_id]["task"].cancel()
        del user_data[user_id]
        await event.edit("🗑 اطلاعات شما پاک شد.")
        return
    ud = user_data[user_id]
    st = "🟢 روشن" if ud["status"] else "🔴 خاموش"
    ft = "بولد (𝟭𝟮𝟯)" if ud["font"] == "bold" else "معمولی (123)"
    btns = [[Button.inline(f"وضعیت سلف: {st}", b"t_status")],[Button.inline(f"فونت: {ft}", b"t_font")],[Button.inline("❌ حذف اکانت", b"del")]]
    await event.edit("🎛 پنل مدیریت سلف‌بات:", buttons=btns)

if __name__ == "__main__":
    bot.run_until_disconnected()
