import asyncio
import os
import pytz
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from telethon.tl.functions.account import UpdateProfileRequest

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# ربات مرکزی هلپر
bot = TelegramClient('helper_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

user_data = {}
active_clients = {}
generator_data = {} # ذخیره موقت مراحل ساخت سشن کاربران

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

async def self_bot_worker(user_id, client):
    last_time = ""
    try:
        me = await client.get_me()
        f_name = me.first_name or "User"
        while True:
            if user_id not in user_data or not user_data[user_id]["status"]:
                break
            ud = user_data[user_id]
            tz = pytz.timezone('Asia/Tehran')
            curr_time = datetime.now(tz).strftime("%H:%M")
            if curr_time != last_time:
                f_time = apply_font(curr_time, ud["font_id"])
                await client(UpdateProfileRequest(first_name=f_name, last_name=f_time))
                last_time = curr_time
            await asyncio.sleep(5)
    except Exception as e:
        print(f"Loop error for {user_id}: {e}")
    finally:
        await client.disconnect()

@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    user_id = event.sender_id
    # اگر کاربر در حال ساختن سشن است، منو را نشان ندهیم تا مراحلش خراب نشود
    if user_id in generator_data:
        return

    if user_id not in user_data:
        user_data[user_id] = {"session": None, "font_id": 1, "status": False, "task": None, "step": "menu"}
        
    ud = user_data[user_id]
    
    if ud["session"] is None:
        # کاربری که هنوز اکانت متصل نکرده است دو دکمه دارد
        btns = [
            [Button.inline("🔑 ساخت خودکار سشن (سریع)", b"start_gen")],
            [Button.inline("✍️ ارسال سشن آماده متنی", b"send_ready_session")]
        ]
        await event.respond("⚡️ به ربات مدیریت سلف‌بات خوش آمدید!\nلطفاً یکی از روش‌های زیر را برای متصل کردن اکانت انتخاب کنید:", buttons=btns)
    else:
        st = "🟢 روشن" if ud["status"] else "🔴 خاموش"
        ft = FONT_NAMES.get(ud["font_id"], "نامشخص")
        btns = [
            [Button.inline(f"وضعیت سلف: {st}", b"t_status")],
            [Button.inline(f"فونت ساعت: {ft}", b"t_font")],
            [Button.inline("❌ حذف اکانت", b"del")]
        ]
        await event.respond("🎛 پنل مدیریت سلف‌بات شما:", buttons=btns)

@bot.on(events.CallbackQuery)
async def callback_handler(event):
    user_id = event.sender_id
    data = event.data
    
    if data == b"send_ready_session":
        user_data[user_id]["step"] = "get_session"
        await event.edit("✍️ لطفاً کُد نشست (Session String) متنی تلتون خود را ارسال کنید:")
        return

    elif data == b"start_gen":
        # شروع فرآیند گرفتن ای‌پی‌آیدی و ای‌پی‌هش
        generator_data[user_id] = {"step": "get_api_id", "api_id": None, "api_hash": None, "phone": None, "client": None, "phone_code_hash": None}
        await event.edit("📥 قدم اول:\nلطفاً **API_ID** اکانت خود را بفرستید:\n(مثال: 123456)")
        return

    if user_id not in user_data:
        return
        
    if data == b"t_status":
        user_data[user_id]["status"] = not user_data[user_id]["status"]
        if user_data[user_id]["status"]:
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

# هندلر اصلی برای دریافت متن‌ها و کدهای سشن‌ساز و سشن آماده
@bot.on(events.NewMessage)
async def message_handler(event):
    user_id = event.sender_id
    text = event.text.strip()
    
    # بخش اول: اگر کاربر دارد سشن به صورت خودکار می‌سازد
    if user_id in generator_data:
        gd = generator_data[user_id]
        
        if gd["step"] == "get_api_id":
            if not text.isdigit():
                await event.respond("❌ لطفاً فقط عدد بفرستید! مجدداً API_ID را وارد کنید:")
                return
            gd["api_id"] = int(text)
            gd["step"] = "get_api_hash"
            await event.respond("📥 قدم دوم:\nلطفاً **API_HASH** اکانت خود را بفرستید:")
            
        elif gd["step"] == "get_api_hash":
            gd["api_hash"] = text
            gd["step"] = "get_phone"
            await event.respond("📞 قدم سوم:\nلطفاً **شماره تلفن** اکانت خود را همراه با کد کشور بفرستید:\n(مثال: `+989123456789`)")
            
        elif gd["step"] == "get_phone":
            gd["phone"] = text
            await event.respond("⏳ در حال برقراری ارتباط با تلگرام و ارسال کد تایید...")
            
            try:
                # ایجاد کلاینت موقت با اطلاعات اختصاصی خود کاربر
                client = TelegramClient(StringSession(), gd["api_id"], gd["api_hash"])
                await client.connect()
                
                # درخواست ارسال کد تایید به اکانت کاربر
                send_code_res = await client.send_code_request(gd["phone"])
                
                gd["client"] = client
                gd["phone_code_hash"] = send_code_res.phone_code_hash
                gd["step"] = "get_code"
                
                await event.respond("📩 قدم چهارم:\nیک کُد از طرف تلگرام برای شما ارسال شد. لطفاً آن را اینجا بفرستید:\n\n⚠️ **نکته مهم:** برای اینکه تلگرام کد را خراب نکند، بین اعداد آن فاصله بگذارید یا یک کاراکتر مثل خط تیره اضافه کنید. (مثال: `1-2-3-4-5` یا `1 2 3 4 5`)")
            except Exception as e:
                await event.respond(f"❌ خطایی رخ داد: {e}\nمراحل لغو شد. مجدداً /start کنید.")
                del generator_data[user_id]
                
        elif gd["step"] == "get_code":
            # تمیز کردن فاصله یا خط تیره‌ای که کاربر بین اعداد کد گذاشته است
            clean_code = text.replace(" ", "").replace("-", "").replace("_", "")
            client = gd["client"]
            
            try:
                # تلاش برای ورود با کد تایید
                await client.sign_in(gd["phone"], clean_code, phone_code_hash=gd["phone_code_hash"])
                
                # اگر ورود موفق بود، سشن ساخته می‌شود
                session_string = client.session.save()
                
                user_data[user_id] = {"session": session_string, "font_id": 1, "status": True, "task": None, "step": "managed"}
                active_clients[user_id] = client
                
                loop = asyncio.get_event_loop()
                user_data[user_id]["task"] = loop.create_task(self_bot_worker(user_id, client))
                
                await event.respond("🎉 فوق‌العاده است! سشن اکانت شما با موفقیت در پس‌زمینه ساخته و فعال شد!")
                del generator_data[user_id]
                
                # باز کردن پنل مدیریت برای کاربر
                st = "🟢 روشن"
                ft = FONT_NAMES[1]
                btns = [[Button.inline(f"وضعیت سلف: {st}", b"t_status")],[Button.inline(f"فونت ساعت: {ft}", b"t_font")],[Button.inline("❌ حذف اکانت", b"del")]]
                await event.respond("🎛 پنل مدیریت سلف‌بات شما:", buttons=btns)
                
            except SessionPasswordNeededError:
                # اگر اکانت رمز دو مرحله‌ای داشته باشد وارد این بخش می‌شود
                gd["step"] = "get_password"
                await event.respond("🔐 اکانت شما دارای **تایید دو مرحله‌ای** است!\nلطفاً رمز عبور دو مرحله‌ای خود را ارسال کنید:")
                
            except Exception as e:
                await event.respond(f"❌ کد اشتباه است یا خطایی رخ داد: {e}\nمجدداً کُد ارسالی را به درستی وارد کنید:")
                
        elif gd["step"] == "get_password":
            client = gd["client"]
            try:
                # ورود با استفاده از رمز دو مرحله‌ای
                await client.sign_in(password=text)
                
                session_string = client.session.save()
                user_data[user_id] = {"session": session_string, "font_id": 1, "status": True, "task": None, "step": "managed"}
                active_clients[user_id] = client
                
                loop = asyncio.get_event_loop()
                user_data[user_id]["task"] = loop.create_task(self_bot_worker(user_id, client))
                
                await event.respond("🎉 فوق‌العاده است! با رمز دو مرحله‌ای وارد شدید و سلف فعال شد!")
                del generator_data[user_id]
                
                st = "🟢 روشن"
                ft = FONT_NAMES[1]
                btns = [[Button.inline(f"وضعیت سلف: {st}", b"t_status")],[Button.inline(f"فونت ساعت: {ft}", b"t_font")],[Button.inline("❌ حذف اکانت", b"del")]]
                await event.respond("🎛 پنل مدیریت سلف‌بات شما:", buttons=btns)
            except Exception as e:
                await event.respond(f"❌ رمز عبور اشتباه است: {e}\nلطفاً مجدداً رمز صحیح را بفرستید:")
        return

    # بخش دوم: اگر کاربر تمایل داشت سشن آماده متنی بفرستد (همان قابلیت قبلی)
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
            
        user_data[user_id]["session"] = clean_session
        user_data[user_id]["step"] = "managed"
        user_data[user_id]["status"] = True
        active_clients[user_id] = client
        
        loop = asyncio.get_event_loop()
        user_data[user_id]["task"] = loop.create_task(self_bot_worker(user_id, client))
        await event.respond("✅ سلف با موفقیت به سرور متصل شد و زنده است! برای مدیریت دوباره /start بزنید.")

if __name__ == "__main__":
    bot.run_until_disconnected()
