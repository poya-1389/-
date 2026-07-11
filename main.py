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

FONTS = {
    0: {'0':'0','1':'1','2':'2','3':'3','4':'4','5':'5','6':'6','7':'7','8':'8','9':'9'},
    1: {'0':'𝟬','1':'𝟭','2':'𝟮','3':'𝟯','4':'𝟰','5':'𝟱','6':'𝟲','7':'𝟳','8':'𝟴','9':'𝟵'},
    2: {'0':'𝟶','1':'𝟷','2':'𝟸','3':'𝟹','4':'𝟺','5':'𝟻','6':'𝟼','7':'𝟽','8':'𝟾','9':'𝟿'},
    3: {'0':'⓪','1':'①','2':'②','3':'③','4':'④','5':'⑤','6':'⑥','7':'⑦','8':'⑧','9':'⑨'},
    4: {'0':'🄀','1':'⒈','2':'⒉','3':'⒊','4':'⒋','5':'⒌','6':'⒍','7':'⒎','8':'⒏','9':'⒐'},
    5: {'0':'🄿','1':'🄱','2':'🄲','3':'🄳','4':'🄴','5':'🄵','6':'🄶','7':'🄷','8':'🄸','9':'🄹'},
    6: {'0':'𝟢','1':'𝟣','2':'𝟤','3':'𝟥','4':'𝟦','5':'𝟧','6':'𝟨','7':'𝟩','8':'𝟪','9':'𝟫'},
    7: {'0':'𝞯','1':'𝞱','2':'𝞲','3':'𝞳','4':'𝞴','5':'𝞵','6':'𝞶','7':'𝞷','8':'𝞸','9':'𝞹'},
    8: {'0':'۰','1':'۱','2':'۲','3':'۳','4':'۴','5':'۵','6':'۶','7':'۷','8':'۸','9':'۹'},
    9: {'0':'٠','1':'١','2':'٢','3':'٣','4':'٤','5':'٥','6':'٦','7':'٧','8':'٨','9':'٩'}
}

FONT_NAMES = {
    0: "معمولی (123)", 1: "بولد (𝟭𝟮𝟯)", 2: "ماشین تحریر (𝟷𝟸𝟹)", 
    3: "دایره‌ای (①②③)", 4: "نقطه‌دار (⒈⒉⒊)", 5: "مربعی (🄿🄱🄲)", 
    6: "کج (𝟢𝟣𝟤)", 7: "ماتماتیک (𝞯🞱🞲)", 8: "فارسی (۱۲۳)", 9: "عربی (١٢٣)"
}

def apply_font(t_str, font_id):
    f_dict = FONTS.get(font_id, FONTS[0])
    return "".join(f_dict.get(c, c) for c in t_str)

async def self_bot_worker(user_id):
    last_time = ""
    while True:
        try:
            if user_id not in user_data or not user_data[user_id]["status"]:
                break
            ud = user_data[user_id]
            
            # پاکسازی کامل فضاهای خالی از ابتدا و انتها و خطوط جدید در سشن
            clean_session = ud["session"].strip().replace("\n", "").replace("\r", "")
            client = TelegramClient(StringSession(clean_session), API_ID, API_HASH)
            
            async with client:
                if not await client.is_user_authorized():
                    print(f"User {user_id} is not authorized.")
                    break
                    
                me = await client.get_me()
                f_name = me.first_name or "User"
                
                tz = pytz.timezone('Asia/Tehran')
                curr_time = datetime.now(tz).strftime("%H:%M")
                
                if curr_time != last_time:
                    f_time = apply_font(curr_time, ud["font_id"])
                    await client(UpdateProfileRequest(first_name=f_name, last_name=f_time))
                    last_time = curr_time
        except Exception as e:
            print(f"Error for {user_id}: {e}")
        await asyncio.sleep(30)

@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    user_id = event.sender_id
    if user_id not in user_data:
        user_data[user_id] = {"session": None, "font_id": 1, "status": False, "task": None, "step": "get_session"}
        await event.respond("سلام!\nلطفاً کد نشست (Session String) تلتون اکانت خود را بفرستید:")
        return
    ud = user_data[user_id]
    st = "🟢 روشن" if ud["status"] else "🔴 خاموش"
    ft = FONT_NAMES.get(ud["font_id"], "نامشخص")
    btns = [[Button.inline(f"وضعیت سلف: {st}", b"t_status")],[Button.inline(f"فونت ساعت: {ft}", b"t_font")],[Button.inline("❌ حذف اکانت", b"del")]]
    await event.respond("🎛 پنل مدیریت سلف‌بات:", buttons=btns)

@bot.on(events.NewMessage)
async def message_handler(event):
    user_id = event.sender_id
    if user_id in user_data and user_data[user_id].get("step") == "get_session":
        # دریافت سشن و اعمال فیلترهای اولیه حذف فضاهای خالی
        raw_session = event.text.strip()
        user_data[user_id]["session"] = raw_session
        user_data[user_id]["step"] = "managed"
        user_data[user_id]["status"] = True
        
        loop = asyncio.get_event_loop()
        user_data[user_id]["task"] = loop.create_task(self_bot_worker(user_id))
        await event.respond("✅ سلف با موفقیت ثبت شد! برای مدیریت دکمه‌ها دستور /start را مجدداً ارسال کنید.")

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
        user_data[user_id]["font_id"] = (user_data[user_id]["font_id"] + 1) % 10
    elif data == b"del":
        if user_data[user_id]["task"]: user_data[user_id]["task"].cancel()
        del user_data[user_id]
        await event.edit("🗑 اطلاعات شما پاک شد.")
        return
    ud = user_data[user_id]
    st = "🟢 روشن" if ud["status"] else "🔴 خاموش"
    ft = FONT_NAMES.get(ud["font_id"], "نامشخص")
    btns = [[Button.inline(f"وضعیت سلف: {st}", b"t_status")],[Button.inline(f"فونت ساعت: {ft}", b"t_font")],[Button.inline("❌ حذف اکانت", b"del")]]
    await event.edit("🎛 پنل مدیریت سلف‌بات:", buttons=btns)

if __name__ == "__main__":
    bot.run_until_disconnected()
