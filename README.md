# پروژه نوا سلف (NovaSelf)

رباتِ سلف‌بات تلگرام با قابلیت‌های گسترده: مدیریت سلف کاربران، اقتصاد الماس،
منشی پیوی، ریکت خودکار، پاسخ خودکار، ابر چت، اتوماسیون بازیِ MeowieQBot و
پنل ادمینی کامل.

---

## آپدیت بزرگ ۲۰۲۶ — همگام‌سازی با تلگرام و بهبود بنیادین

این نسخه شامل بازبینی کامل کد بر اساس آپدیت‌های تلگرام (Bot API 9.0–10.3،
MTProto layer 218–225) و Telethon 1.40–1.45 است. بیش از **۱۸۶ باگ** شناسایی و
رفع شد. در ادامه خلاصه‌ی تغییرات آمده.

### تغییرات بحرانی (Critical)

#### امنیت دیتابیس (`nova_db.py`)
- **Connection Pool**: اضافه‌شدن `ThreadedConnectionPool` به‌جای اتصالِ per-call؛
  latency کاهش و جلوگیری از پر شدن `max_connections` پستگرس.
- **رفع SQL Injection در Backup/Restore**: استفاده از `psycopg2.sql.Identifier`
  و `psycopg2.sql.Placeholder` به‌جای f-string برای نام ستون‌ها/جدول‌ها.
- **رفع Pickle RCE**: تمام blob های pickle با امضای HMAC-SHA256 محافظت می‌شوند
  (`_signed_pickle` / `_signed_unpickle`). pickle های بدون امضا رد می‌شوند.
- **رفع صفر شدن موجودی**: `charge_diamonds_db` دیگر در صورتِ کافی‌نبودن موجودی،
  آن را صفر نمی‌کند؛ موجودی دست‌نخورده باقی می‌ماند.
- **رفع Connection Leak**: تمام توابع DB با `try/finally` و `release_db_connection`
  پوشانده شدند. قبلاً ۹ تابع در صورت خطا connection نشت می‌دادند.
- **رفع SQL Injection در `init_db` migration**: استفاده از `sql.Identifier`.
- **رفع Silent Rollback در Restore**: اضافه‌شدن اعتبارسنجی نسخه‌ی بکاپ و
  snapshot از کلیدهای جدول برای جلوگیری از abort کل transaction.
- **پاکسازی Cascade در `delete_user_db`**: حذف صریح رکوردهای مرتبط در ۸ جدول
  برای جلوگیری از orphan rows.
- **NaN/Inf Validation**: `transfer_diamonds_db` و `charge_diamonds_db` دیگر
  `NaN`/`Inf` را قبول نمی‌کنند.
- **افزودن Index ها**: ۱۱ ایندکس روی مسیرهای پرکاربرد (username, status,
  created_at, target_user_id و...).
- **تک‌Query در `get_user_stats`**: ترکیب دو `COUNT(*)` در یک query.

#### مدیریت کلاینت و Anti-Spam (`nova_self_features.py`)
- **Await کردن تسک‌های لغوشده**: `_teardown_existing_client` و `stop_self_client`
  حالا با `asyncio.wait_for(asyncio.gather(...), timeout=5)` صبر می‌کنند تا
  تسک‌ها واقعاً تموم بشن — قبلاً زامبی می‌موندن.
- **پاکسازی Event Handlers**: `client.list_event_handlers()` + `remove_event_handler`
  هنگام teardown — جلوگیری از handler دوبل در صورت reuse کلاینت.
- **رفع FloodWait از UpdateStatusRequest**: فاصله‌ی «همیشه آنلاین» از ۴ ثانیه
  به ۹۰ ثانیه (تلگرام آنلاین رو ۵ دقیقه نگه می‌داره).
- **رفع FloodWait از SetTypingRequest**: فاصله از ۴ ثانیه به ۳۰ ثانیه و فقط
  آخرین دیالوگ به‌جای ۱۰ دیالوگ. کش dialogs تا ۶۰ ثانیه.
- **کاهش sleep در `self_bot_worker`**: از ۵ ثانیه به ۳۰ ثانیه.
- **استفاده از `asyncio.to_thread` برای DB sync**: تمام `save_user`/`charge_diamonds_db`
  در worker ها به thread منتقل شد تا event loop بلاک نشه.
- **استارت موازی `autostart_saved_users`**: با semaphore (حداکثر ۱۰ هم‌زمان)
  به‌جای استارت سریال — با ۱۰۰ کاربر از ۲۰۰ ثانیه به ~۲۰ ثانیه.
- **استفاده از `TEHRAN_TZ` از nova_state**: به‌جای ساختن `pytz.timezone` در هر
  چرخه‌ی worker.
- **بررسی `status` در worker های game**: `meow_worker` و سایرین حالا `status`
  رو هم چک می‌کنن نه فقط `*_enabled`.
- **پاکسازی `panel_registry`** هنگام `stop_self_client`.

#### پایداری روی Railway (`main.py`)
- **Signal Handler برای SIGTERM/SIGINT**: هندلر `add_signal_handler` که قبل
  از خروج همه‌ی کلاینت‌ها/نشست‌ها رو تمیز می‌کنه — جلوگیری از invalid شدن
  session در redeploy.
- **Retry در `_load_bot_username`**: ۵ تلاش با backoff ۳ ثانیه + fallback به
  استخراج آیدی از BOT_TOKEN — جلوگیری از crash loop هنگام cold start.
- **استفاده از `_spawn_background_task`** به‌جای `loop.create_task` مستقیم
  برای نگه‌داشتن رفرنس تسک‌های autostart و webapp.
- **استفاده از `asyncio.new_event_loop()`** به‌جای `get_event_loop()` (deprecated).
- **Broadcast در پس‌زمینه**: استفاده از `safe_call` + `_spawn_background_task`
  به‌جای حلقه‌ی سریال که event loop رو بلاک می‌کرد.
- **`admin_message_delete_` در پس‌زمینه**: با `safe_call` و rate-limit ۵۰ms.

#### رابط کاربری (`nova_menus.py`)
- **رفع Markdown Injection**: اضافه‌شدن `escape_md` به `nova_utils.py` و
  استفاده در `get_secretary_menu_text` و سایر توابعی که متن کاربر رو در
  markdown قرار می‌دن. قبلاً کاربر می‌تونست با `**` یا `_` منو رو خراب کنه.
- **کش فونت در `_load_card_font`**: `_FONT_CACHE` برای کاهش I/O.
- **رفع باگ `bold=False`** در `_load_card_font` که قبلاً فونت Bold برمی‌گردوند.
- **Offload PIL به thread**: `build_panel_card_image` با `asyncio.to_thread`
  کار رندر رو به thread منتقل می‌کنه — event loop بلاک نمی‌شه.
- **رفع Connection Leak در `get_users_list_page`**: با `try/finally`.
- **مخفی‌کردن دکمه‌ی «بعدی»** در صفحه‌ی آخر pagination.
- **ترتیب دکمه‌ها در `get_account_delete_warning_keyboard`**: تایید اول،
  بازگشت دوم — یکسان با بقیه‌ی confirmation dialog ها.

#### ابزارهای کمکی (`nova_utils.py`)
- **`escape_md(text)`**: escape کاراکترهای MarkdownV2.
- **`safe_int_id(data, prefix, default)`**: پارس امنِ شناسه از callback_data.
- **`safe_split_id(data, sep, index, default)`**: پارس امن با split.
- **`is_finite_number(value)`**: رد NaN/Inf.
- **`safe_call_bg`**: نسخه‌ی پس‌زمینه‌ی `safe_call` برای عملیات non-critical.

#### تنظیمات (`nova_state.py`)
- **پارامترهای اتصال Telethon**: `connection_retries`, `retry_delay`,
  `request_retries`, `timeout` قابل تنظیم با env vars.
- **`TELETHON_SESSION_NAME`**: نام session قابل تنظیم برای volume persistent.
- **افزایش فاصله‌ی میو از ۵ دقیقه به ۱۵ دقیقه**: سازگار با anti-spam جدید.
- **`jittered_sleep`**: اضافه‌کردن jitter تصادفی به sleep برای کاهش flood مشترک.

### قابلیت‌های جدید همگام با تلگرام

- **دکمه‌های رنگی (Bot API 9.4)**: `styled_button` با fallback امن که از
  Telethon 1.43+ به بعد پشتیبانی می‌کنه.
- **CORS محدود و Headerهای امنیتی** در Mini App API.
- **اعتبارسنجی نسخه‌ی بکاپ** در restore.
- **پشتیبانی از اعداد فارسی/عربی** در ماشین حساب.

### متغیرهای محیطی جدید

```bash
# اضافه‌شده در ۲۰۲۶:
TELETHON_CONNECTION_RETRIES=5      # تعداد retry اتصال
TELETHON_RETRY_DELAY=5             # فاصله‌ی retry (ثانیه)
TELETHON_REQUEST_RETRIES=3          # تعداد retry درخواست
TELETHON_TIMEOUT=30                 # timeout درخواست‌ها (ثانیه)
TELETHON_SESSION_NAME=helper_bot   # نام فایل session

# موجود قبلاً:
API_ID, API_HASH, BOT_TOKEN, DATABASE_URL, ADMIN_IDS, PORT, MINIAPP_ORIGIN
```

### بکاپ و بازیابی

- جدول‌های `novaself_settings` و `novaself_referrals` حالا در backup شامل
  می‌شن (قبلاً گم می‌شدن).
- اعتبارسنجی نسخه‌ی بکاپ — نسخه‌های آینده قابل تشخیص.
- بعد از restore، کش‌های درون‌حافظه‌ای خودکار تازه می‌شن.

### پیشنهادات عملیاتی

1. **Volume Persistent روی Railway**: فایل‌های `.session` رو روی یک volume
   persist کنید تا در redeploy نیاز به re-auth نباشه.
2. **Telegram Premium برای colored buttons**: اگر صاحب بات Premium باشه،
   دکمه‌های رنگی نمایش داده می‌شن.
3. **اتصال به کانال‌های جوین اجباری**: بات باید عضو/ادمین همه‌ی کانال‌های
   جوین اجباری باشه تا `check_user_joined_all` کار کنه.
4. **Update Telethon**: ارتقا به Telethon 1.45 (layer 229) برای بهره‌مندی
   از fix های reconnect و server-salt.
5. **SOCKS5 Proxy**: در محیط‌های ایران، از SOCKS5 proxy با IP ثابت استفاده
   کنید تا از soft-ban جلوگیری بشه.

---

## ساختار فایل‌ها

```
nova_utils.py            ابزارهای مستقل (escape_md، safe_call، styled_button)
nova_state.py            تنظیمات، کلاینت بات، کش‌های سراسری
nova_db.py               لایه‌ی دیتابیس (Connection Pool، backup، economy)
nova_menus.py            توابع UI (متن/دکمه/تصویر کارت پنل)
nova_self_features.py    منطق سلف (دستورات، worker ها، lifecycle کلاینت)
main.py                  Handler های سطح‌بالای بات + اجرای اصلی
webapp_api.py            بک‌اند Mini App (aiohttp)
```

## قابلیت‌های موجود

- 🐱 میو / 🐟 ماهی / 🪙 میو پوینت / ❄️ یخچال میویی (اتوماسیون MeowieQBot)
- 🏷️ تگ ادمین/اعضا / 🏓 پینگ / 🪪 اطلاعات کاربر
- 👍 ریکت خودکار / 🤖 پاسخ خودکار / 🧑‍💼 منشی پیوی
- ☁️ ابر چت (ذخیره رسانه/پیام حذف‌شده/ویرایش‌شده)
- 🎭 اکشن‌ها (در حال تایپ، ضبط صدا، همیشه آنلاین و...)
- 💎 اقتصاد الماس (کسر ساعتی، انتقال، خرید کارت‌به‌کارت)
- 🎁 کد هدیه / 👥 رفرال
- 🔒 قفل قابلیت‌ها توسط ادمین
- 📢 ارسال پیام همگانی
- 🔐 جوین اجباری (بررسی زنده)
- 📊 پنل ادمینی کامل + Mini App
- ⌨ ماشین حساب
- 🧹 حذف و پاکسازی / 🚫 بلاک و آن‌بلاک
- 🎥 ویدیو مسیج

## استقرار روی Railway

1. متغیرهای محیطی رو در Railway تنظیم کنید (لیست بالا).
2. یک volume برای `/app` (یا مسیر پروژه) بسازید تا session ها persist بشن.
3. دستور start: `python main.py`.
4. پورت به‌صورت خودکار توسط Railway ست می‌شه (متغیر `PORT`).

## پشتیبانی

💻 پشتیبانی: @SayPouYa
