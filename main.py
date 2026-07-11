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

# ربات مرکزی هلپر
bot = TelegramClient('helper_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
user_data = {}
active_clients = {}  # برای زنده نگه داشتن کلاینت کاربران بدون دیسکانکت شدن

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

def apply_font(t_str, font_id):
    f_dict = FONTS.get(font_id, FONTS[0])
    return "".join(f_dict.get(c, c) for c in t_str)

# پردازشگر لحظه‌ای و متصل برای تغییر ساعت
async def self_bot_worker(user_id, client):
    last_time = ""
    try:
        me = await client.get_me()
        f_name = me.first_name or "User"
        
        while True:
            # اگر کاربر سلف را خاموش کرد، حلقه کاملاً متوقف شود
            if user_id not in user_data or not user_data[user_id]["status"]:
                break
                
            ud = user_data[user_id]
            tz = pytz.timezone('Asia/Tehran')
            curr_time = datetime.now(tz).strftime("%H:%M")
            
            # تغییر لحظه‌ای اسم به محض تغییر دقیقه ساعت گوشی
            if curr_time != last_time:
                f_time = apply_font(curr_time, ud["font_id"])
                await client(UpdateProfileRequest(first_name=f_name, last_name=f_time))
                last_time = curr_time
                print(f"ساعت اکانت {user_id} آپدیت شد به: {f_time}")
                
            await asyncio.sleep(5) # هر ۵ ثانیه چک میکند که آیا دقیقه عوض شده یا نه (بدون مصرف رم زیاد)
            
    except Exception as e:
        print(f"خطای داخلی در اجرای سلف {user_id}: {e}")
    finally:
        await client.disconnect()

@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    user_id = event.sender_id
    if user_id not in user_data:
        user_data[user_id] = {"session": None, "font_id": 1, "status": False, "task": None, "step": "get_session"}
        await event.respond("سلام! ⚡️\nلطفاً کُد نشست (Session String) تلتون خود را ارسال کنید:")
        return
    ud = user_data[user_id]
    st = "🟢 روشن" if ud["status"] else "🔴 خاموش"
    ft = FONT_NAMES.get(ud["font_id"], "نامشخص")
    btns = [[Button.inline(f"وضعیت سلف: {st}", b"t_status")],[Button.inline(f"فونت ساعت: {ft}", b"t_font")],[Button.inline("❌ حذف اکانت", b"del")]]
    await event.respond("🎛 پنل مدیریت سلف‌بات شما:", buttons=btns)

@bot.on(events.NewMessage)
async def message_handler(event):
    user_id = event.sender_id
    if user_id in user_data and user_data[user_id].get("step") == "get_session":
        # پاکسازی تمام فضاهای خالی پنهان تلگرام
        clean_session = event.text.strip().replace("\n", "").replace("\r", "").replace(" ", "")
        
        # تست زنده و آنی سشن قبل از هرکاری برای جلوگیری از ارور دیسک
        try:
            client = TelegramClient(StringSession(clean_session), API_ID, API_HASH)
            await client.connect()
            if not await client.is_user_authorized():
                await event.respond("❌ این سشن معتبر نیست یا منقضی شده است. دوباره تلاش کنید.")
                await client.disconnect()
                return
        except Exception:
            await event.respond("❌ ساختار متن ارسال شده اشتباه است و تلتون آن را نمی‌شناسد.\nمطمئن شوید سشن تلتون (Telethon) است.")
            return
            
        # ذخیره اطلاعات و زنده نگه داشتن کلاینت
        user_data[user_id]["session"] = clean_session
        user_data[user_id]["step"] = "managed"
        user_data[user_id]["status"] = True
        active_clients[user_id] = client
        
        loop = asyncio.get_event_loop()
        user_data[user_id]["task"] = loop.create_task(self_bot_worker(user_id, client))
        await event.respond("✅ سلف با موفقیت به سرور متصل شد و زنده است! برای مدیریت دوباره /start بزنید.")

@bot.on(events.CallbackQuery)
async def callback_handler(event):
    user_id = event.sender_id
    data = event.data
    if user_id not in user_data:
        return
        
    if data == b"t_status":
        user_data[user_id]["status"] = not user_data[user_id]["status"]
        if user_data[user_id]["status"]:
            # روشن کردن مجدد و ساخت کلاینت پایدار
            try:
                client = TelegramClient(StringSession(user_data[user_id]["session"]), API_ID, API_HASH)
                await client.connect()
                active_clients[user_id] = client
                loop = asyncio.get_event_loop()
                user_data[user_id]["task"] = loop.create_task(self_bot_worker(user_id, client))
            except Exception:
                await event.answer("خطا در روشن کردن مجدد سلف.", alert=True)
        else:
            if user_data[user_id]["task"]: user_data[user_id]["task"].cancel()
            if user_id in active_clients: del active_clients[user_id]
            
    elif data == b"t_font":
        user_data[user_id]["font_id"] = (user_data[user_id]["font_id"] + 1) % 10
        
    elif data == b"del":
        if user_data[user_id]["task"]: user_data[user_id]["task"].cancel()
        if user_id in active_clients: del active_clients[user_id]
        del user_data[user_id]
        await event.edit("🗑 اطلاعات شما کاملاً پاک شد. برای شروع مجدد /start بزنید.")
        return
        
    ud = user_data[user_id]
    st = "🟢 روشن" if ud["status"] else "🔴 خاموش"
    ft = FONT_NAMES.get(ud["font_id"], "نامشخص")
    btns = [[Button.inline(f"وضعیت سلف: {st}", b"t_status")],[Button.inline(f"فونت ساعت: {ft}", b"t_font")],[Button.inline("❌ حذف اکانت", b"del")]]
    await event.edit("🎛 پنل مدیریت سلف‌بات شما:", buttons=btns)

if __name__ == "__main__":
    bot.run_until_disconnected()
