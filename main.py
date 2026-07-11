import asyncio
from datetime import datetime
import pytz
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.account import UpdateProfileRequest
import os

# دریافت اطلاعات از متغیرهای محیطی ریلوی
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
SESSION_STRING = os.environ.get("SESSION_STRING").strip()

# راه اندازی کلاینت تلتون با سشن استرینگ شما
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

# تبدیل اعداد انگلیسی به فونت بولد درخواستی شما
def to_bold_font(time_str):
    bold_digits = {
        '0': '𝟬', '1': '𝟭', '2': '𝟮', '3': '𝟯', '4': '𝟰',
        '5': '𝟱', '6': '𝟲', '7': '𝟳', '8': '𝟴', '9': '𝟵', ':': ':'
    }
    return "".join(bold_digits.get(char, char) for char in time_str)

async def main():
    print("سلف تلتون با موفقیت روشن شد!")
    last_time = ""
    
    while True:
        try:
            # تنظیم تایم زون تهران
            tehran_tz = pytz.timezone('Asia/Tehran')
            now = datetime.now(tehran_tz)
            current_time = now.strftime("%H:%M")
            
            # فقط اگر زمان تغییر کرده بود اسم رو آپدیت کن
            if current_time != last_time:
                bold_time = to_bold_font(current_time)
                
                # آپدیت فامیلی با ساعت بولد شده
                await client(UpdateProfileRequest(last_name=bold_time))
                last_time = current_time
                print(f"ساعت به روز رسانی شد: {bold_time}")
                
        except Exception as e:
            print(f"خطایی رخ داد: {e}")
            
        await asyncio.sleep(30) # هر ۳۰ ثانیه چک می‌کنه

if __name__ == "__main__":
    client.start()
    client.loop.run_until_complete(main())
                    
                    # دریافت اطلاعات اکانت خودت برای حفظ نام کوچک
                    me = await app.get_me()
                    first_name = me.first_name or ""
                    
                    # آپدیت پروفایل با فامیلی جدید (ساعت بولد)
                    await app.update_profile(first_name=first_name, last_name=bold_time)
                    last_time = current_time
                    print(f"ساعت به روز رسانی شد: {bold_time}")
                    
            except Exception as e:
                print(f"خطایی رخ داد: {e}")
                
            await asyncio.sleep(30) # هر ۳۰ ثانیه چک می‌کنه

if __name__ == "__main__":
    app.run(main())
