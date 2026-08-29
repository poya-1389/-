# -*- coding: utf-8 -*-
"""
nova_state.py
====================================================================
هسته‌ی مشترک NovaSelf: تنظیمات محیطی، کلاینت بات، تمام دیکشنری/کش‌های
سراسریِ درون‌حافظه‌ای (user_data، active_clients، feature_locks و ...)،
داده‌های ثابت (فونت‌ها، اکشن‌ها، Triggerهای دستورات متنی) و چند تابع
کمکیِ کوچک و پرکاربرد که تقریباً همه‌ی ماژول‌های دیگر بهشان نیاز دارند
(safe_edit، is_admin، make_default_user، apply_font، format_date و...).

نکته‌ی حیاتی برای هر کسی که این فایل را ویرایش می‌کند:
تمام دیکشنری‌ها/لیست‌های این فایل باید همیشه با ارجاعِ همان شیء در
حافظه به‌روزرسانی شوند (مثل `user_data.update(...)` یا
`reaction_targets.clear(); reaction_targets.update(...)`), هرگز با
بازتخصیصِ کامل (`user_data = {...}`) — چون ماژول‌های دیگر با
`from nova_state import user_data` یک ارجاع به همان شیء گرفته‌اند؛
بازتخصیص کامل این ارجاع را در آن ماژول‌ها قطع می‌کند و باعث می‌شود
همه جز خودِ این فایل، نسخه‌ی قدیمی/خالی را ببینند.
====================================================================
"""

import os
import re
import asyncio
import logging
from datetime import datetime
import pytz
import jdatetime
from hijridate import Gregorian
from telethon import TelegramClient, events, helpers
from telethon.errors import MessageNotModifiedError
from telethon.tl.types import (
    SendMessageTypingAction, SendMessageRecordAudioAction, SendMessageUploadPhotoAction,
    SendMessageRecordRoundAction, SendMessageUploadDocumentAction, SendMessageUploadVideoAction,
    SendMessageGamePlayAction, SendMessageChooseStickerAction,
    MessageEntityBold, MessageEntityItalic, MessageEntityUnderline,
    MessageEntityStrike, MessageEntitySpoiler, MessageEntityCode,
    MessageEntityBlockquote,
)
from nova_utils import ClickDebouncer, wrap_panel_buttons

# ======================== تنظیمات اولیه ========================
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_IDS = [int(id.strip()) for id in os.environ.get("ADMIN_IDS", "").split(",") if id.strip()]
MINIAPP_ORIGIN = os.environ.get("MINIAPP_ORIGIN", "*")  # آدرس گیت‌هاب‌پیجز، مثل: https://username.github.io
PORT = int(os.environ.get("PORT", 8080))  # ریلوی این متغیر رو خودش ست می‌کنه

if not all([API_ID, API_HASH, BOT_TOKEN, DATABASE_URL]):
    raise ValueError("تمامی متغیرهای محیطی باید تنظیم شوند!")

if not ADMIN_IDS:
    logging.warning("⚠️ هشدار: هیچ ادمینی تنظیم نشده است!")

bot = TelegramClient('helper_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ======================== تنظیمات سیستم الماس ========================
DIAMOND_RATE_PER_HOUR = 5       # مصرف الماس به ازای هر ساعت روشن بودن سلف
DIAMOND_PRICE_TOMAN = 20        # قیمت هر الماس به تومان
BILLING_INTERVAL_SECONDS = 60   # فاصله زمانی محاسبه و کسر الماس
MEOW_INTERVAL_SECONDS = 5 * 60 + 20   # فاصله‌ی پیش‌فرض ارسال پیام «میو» (۵ دقیقه و ۲۰ ثانیه) — قابل تغییر توسط کاربر
FISH_INTERVAL_SECONDS = 60 * 60 + 10  # فاصله‌ی ارسال پیام «ماهی» (۱ ساعت و ۱۰ ثانیه)
MEOWIEQBOT_USERNAME = "MeowieQBot"
FISH_RESPONSE_TIMEOUT = 15            # حداکثر انتظار برای اولین پاسخ ربات ماهی
FISH_EDIT_WAIT_SECONDS = 12           # حداکثر انتظار برای ادیت‌شدنِ پیام اولیه (استیکر) به متن اطلاعات
FISH_NUTRITION_BY_RARITY = {"معمولی": 1, "کمیاب": 2, "حماسی": 3, "افسانه‌ای": 5}
FISH_RARITY_TO_FIELD = {
    "معمولی": "fish_operation_common",
    "کمیاب": "fish_operation_rare",
    "حماسی": "fish_operation_epic",
    "افسانه‌ای": "fish_operation_legendary",
}
FISH_OPERATION_LABELS = {
    "sell": "فروش ماهی",
    "feed": "بده پیشی بخوره",
    "fridge": "بندازش تو یخچال",
}
FISH_OPERATION_NAMES_FA = {
    "sell": "فروش ماهی",
    "feed": "دادن به پیشی",
    "fridge": "انداختن تو یخچال",
}
FISH_OPERATION_FALLBACK_MARKERS = {
    "feed": ("سیر",),
    "fridge": ("یخچالجانداره", "یخچالپره"),
    "sell": (),
}
MEOWPOINT_INTERVAL_SECONDS = 45 * 60  # فاصله‌ی پیش‌فرض ارسال پیام «پیشی» (۴۵ دقیقه)
MEOWPOINT_RESPONSE_TIMEOUT = 15  # طبق تست واقعی، ۵ ثانیه کافی نبود و پاسخ ربات را از دست می‌داد
INTERVAL_STEP_SECONDS = 5 * 60         # هر کلیک ➕/➖ (برای ماهی، میو پوینت و یخچال) ۵ دقیقه تغییر می‌کند
FRIDGE_INTERVAL_SECONDS = 30 * 60      # فاصله‌ی پیش‌فرض بررسی یخچال میویی (۳۰ دقیقه)
GAMEBOT_ID = 8839105739                # آیدی عددی @MeowieQBot — برای تشخیص مطمئن‌تر پیام‌ها (بند ۳۸)

# ---------- سیستم Delay/Retry مرکزی برای همه‌ی قابلیت‌های وابسته به MeowieQBot (بند ۵ و ۳۱) ----------
GAME_CLICK_RETRY_DELAY = 3.0    # فاصله بین تلاش‌های مجدد کلیک روی یک دکمه
GAME_CLICK_MAX_ATTEMPTS = 3     # حداکثر تلاش برای هر دکمه (چون سرور MeowieQBot ممکنه شلوغ باشه)

def format_interval(total_seconds):
    """نمایش زمان به دقیقه (و ثانیه‌ی باقی‌مانده در صورت وجود)، مطابق درخواست بند ۷."""
    total_seconds = int(total_seconds or 0)
    minutes, secs = divmod(total_seconds, 60)
    if secs == 0:
        return f"{minutes} دقیقه"
    return f"{minutes} دقیقه و {secs} ثانیه"
SUPPORT_USERNAME = "@SayPouYa"

TEHRAN_TZ = pytz.timezone("Asia/Tehran")

def tehran_now():
    """
    اکنون بر حسب ساعت تهران — عمداً Naive برگردانده می‌شود (بدون tzinfo) تا با
    بقیه‌ی Datetimeهای پروژه (ستون‌های TIMESTAMP دیتابیس که با تنظیم Timezone نشست
    در get_db_connection همسو شده‌اند، و محاسبات قبلی پروژه) سازگار بماند و ریسک
    خطای «مقایسه Naive با Aware» پیش نیاید. این تابع جایگزین همه‌ی tehran_now()
    شد که در نمایش تاریخ/ساعت یا ثبت زمان به کاربر تأثیر می‌گذاشت.
    """
    return datetime.now(TEHRAN_TZ).replace(tzinfo=None)

_PHONE_DIGIT_TRANSLATION = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹" + "٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789"
)

def normalize_phone_number(raw):
    """
    نرمال‌سازی شماره تلفن قبل از ارسال به تلگرام.

    آپدیت جدید: دیگر فقط شماره‌های ایران پذیرفته نمی‌شوند. چون منبع شماره
    الان همیشه دکمه‌ی رسمیِ تلگرام «ارسال شماره تلفن» است (نه تایپ دستی)،
    شماره‌ی هر کشوری که تلگرام برگرداند پذیرفته می‌شود؛ فقط طبق استاندارد
    بین‌المللیِ E.164 اعتبارسنجی می‌شود (۷ تا ۱۵ رقم، با یا بدون + یا ۰۰
    ابتدایی). هرگز Exception نمی‌دهد — همیشه (normalized یا None، پیام خطا
    یا None) برمی‌گرداند.
    خروجی: (normalized: str|None, error_message: str|None)
    """
    try:
        if not raw or not raw.strip():
            return None, "❌ شماره تلفن نامعتبر است. لطفاً دوباره ارسال کنید."

        cleaned = raw.strip().translate(_PHONE_DIGIT_TRANSLATION)
        for ch in (" ", "\u200c", "\u200f", "\u200e", "-", "(", ")"):
            cleaned = cleaned.replace(ch, "")

        if not cleaned:
            return None, "❌ شماره تلفن نامعتبر است. لطفاً دوباره ارسال کنید."

        if not re.fullmatch(r"\+?\d+", cleaned):
            return None, "❌ شماره تلفن فقط باید شامل عدد باشد. لطفاً دوباره ارسال کنید."

        has_plus = cleaned.startswith("+")
        digits = cleaned[1:] if has_plus else cleaned

        # حذف ۰۰ ابتدایی (شکلِ رایجِ نمایشِ بین‌المللی به‌جای +)
        if not has_plus and digits.startswith("00"):
            digits = digits[2:]

        # استاندارد E.164: حداکثر ۱۵ رقم؛ کوتاه‌ترین شماره‌های بین‌المللیِ واقعی
        # (کدِ کشور + شماره‌ی محلی) هم معمولاً حداقل ۷ رقم‌اند.
        if not (7 <= len(digits) <= 15):
            return None, (
                "❌ فرمت شماره تشخیص داده نشد.\n"
                "لطفاً شماره را همراه با کد کشور ارسال کنید."
            )

        return "+" + digits, None
    except Exception as e:
        logging.error(f"⚠️ خطا در نرمال‌سازی شماره تلفن: {e}")
        return None, "❌ خطا در پردازش شماره تلفن. لطفاً دوباره ارسال کنید."

# ======================== دیکشنری‌های عمومی ========================
active_clients = {}
BOT_USERNAME = None  # موقع اجرای برنامه از get_me() پر می‌شود (برای پنل درون‌چتی لازم است)
generator_data = {}
active_signins = {}
user_data = {}
broadcast_data = {}
secretary_state = {}   # {user_id: {peer_id: {"replied": bool, "task": Task}}}
_auto_sent_marks = set()  # {(user_id, chat_id, message_id)} پیام‌هایی که خودمان خودکار فرستادیم (نباید توسط حالت متن ادیت شوند)
transfer_data = {}     # {user_id: {"target_id":..., "amount":...}} وضعیت موقت انتقال الماس
purchase_data = {}     # {user_id: {"buffer":..., "amount":..., "toman":..., "order_id":...}} وضعیت موقت خرید الماس
meow_group_cache = {}  # {user_id: [(chat_id, title), ...]} کش موقت لیست گروه‌ها برای صفحه‌بندی انتخاب گروه میو
admin_action_data = {} # {admin_id: {"type":..., "target_id":..., "step":...}} وضعیت موقت عملیات مدیریتی روی الماس/رفرال
click_debouncer = ClickDebouncer(window_seconds=1.2)  # جلوگیری از پردازش کلیک تکراری روی دکمه‌ها

reaction_targets = {}   # {owner_id: {target_user_id: {"emoji":..., "username":...}}} کش ریکت (بند ۳-۴)
autoreply_cache = {}    # {owner_id: [{"local_id":..., "trigger_text":..., "response_text":..., "entities":..., "media_kind":..., "media_bytes":..., "media_filename":..., "media_mime":...}, ...]} کش پاسخ خودکار (بند ۵-۹)
autoreply_draft = {}    # {owner_id: {"trigger_text":...}} وضعیت موقت افزودن پاسخ خودکار (دو مرحله‌ای)
feature_locks = {}      # {user_id: {feature_key, ...}} کش قفل قابلیت‌ها توسط ادمین
backup_upload_pending = {}  # {admin_id: dump_dict} بکاپ آپلودشده‌ای که هنوز تأیید نشده
join_channels_cache = []  # لیست کانال‌های فعالِ جوین اجباری (کش)
# توجه: دیگر هیچ کش/دیتابیسی از «کاربران تأییدشده» نگه‌داشته نمی‌شود؛ عضویت هر
# بار که لازم باشد، زنده و مستقیم از تلگرام چک می‌شود (check_user_joined_all).
_background_tasks = set()  # نگه‌داشتن رفرنس Taskهای پس‌زمینه‌ی کوتاه‌مدت تا با GC زودهنگام لغو نشوند

def _spawn_background_task(coro):
    """
    اجرای یک Task پس‌زمینه (مثلاً تأخیر ۱ ثانیه‌ای قبل از ریکت) با نگه‌داشتن یک
    رفرنس قوی به آن؛ بدون این کار، asyncio ممکن است در میانه‌ی اجرا Task را
    Garbage Collect و بی‌صدا لغو کند (یک نکته‌ی شناخته‌شده در مستندات asyncio).
    بعد از پایان Task، رفرنس خودش از مجموعه پاک می‌شود تا حافظه بی‌نهایت رشد نکند.
    """
    task = asyncio.get_event_loop().create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task

TAG_ADMIN_TRIGGERS = {".تگ ادمین", ".تگادمین", ".tagadmins"}
TAG_MEMBERS_TRIGGERS = {".تگ اعضا", ".تگاعضا", ".tagall"}
PANEL_TRIGGERS = {".پنل", ".panel"}
PING_TRIGGERS = {".پینگ", ".ping"}
WHOIS_TRIGGERS = {".آیدی", ".id"}
BALANCE_TRIGGERS = {".موجودی", ".balance"}
REACTION_SET_PREFIXES = (".ریکت ", ".react ")
REACTION_REMOVE_TRIGGERS = {".حذف ریکت", ".remove react"}
REACTION_APPLY_DELAY = 1.0  # طبق بند «اجرای خودکار»: حدود ۱ ثانیه تأخیر قبل از ریکت
AUTOREPLY_MATCH_TYPES = {"exact": "برابر", "prefix": "پیشوند", "contains": "شامل"}

# ====== آپدیت جدید: حذف/پاکسازی، بلاک/آن‌بلاک ======
CLEANUP_COMMAND_RE = re.compile(r"^\.(?:حذف|delete)\s+([0-9۰-۹٠-٩]+)$", re.IGNORECASE)
CLEANUP_MAX_COUNT = 100  # سقف امنیتی برای جلوگیری از فشار/FloodWait بیش از حد در یک اجرا

_ZWNJ = "\u200c"

def _normalize_block_cmd(s):
    """نیم‌فاصله و فاصله‌های اضافی را حذف می‌کند تا اشکال مختلف نوشتاریِ دستور تشخیص داده شوند."""
    return s.replace(_ZWNJ, "").replace(" ", "")

BLOCK_TRIGGERS_NORMALIZED = {".بلاک", ".block"}
UNBLOCK_TRIGGERS_NORMALIZED = {".آنبلاک", ".unblock"}
VIDEOMESSAGE_TRIGGERS = {".ویدیو مسیج", ".video message", ".videomessage"}
MAX_AUTOREPLY_MEDIA_MB = 15
MAX_AUTOREPLY_MEDIA_BYTES = MAX_AUTOREPLY_MEDIA_MB * 1024 * 1024

# ======================== فونت‌های کامل ========================
FONTS = {
    0: {'0': '0', '1': '1', '2': '2', '3': '3', '4': '4', '5': '5', '6': '6', '7': '7', '8': '8', '9': '9'},
    1: {'0': '𝟬', '1': '𝟭', '2': '𝟮', '3': '𝟯', '4': '𝟰', '5': '𝟱', '6': '𝟲', '7': '𝟳', '8': '𝟴', '9': '𝟵'},
    2: {'0': '𝟘', '1': '𝟙', '2': '𝟚', '3': '𝟛', '4': '𝟜', '5': '𝟝', '6': '𝟞', '7': '𝟟', '8': '𝟠', '9': '𝟡'},
    3: {'0': '𝟶', '1': '𝟷', '2': '𝟸', '3': '𝟹', '4': '𝟺', '5': '𝟻', '6': '𝟼', '7': '𝟽', '8': '𝟾', '9': '𝟿'},
    4: {'0': '𝟢', '1': '𝟣', '2': '𝟤', '3': '𝟥', '4': '𝟦', '5': '𝟧', '6': '𝟨', '7': '𝟩', '8': '𝟪', '9': '𝟫'},
    5: {'0': '𝟎', '1': '𝟏', '2': '𝟐', '3': '𝟑', '4': '𝟒', '5': '𝟓', '6': '𝟔', '7': '𝟕', '8': '𝟖', '9': '𝟗'},
    6: {'0': '０', '1': '１', '2': '２', '3': '３', '4': '４', '5': '５', '6': '６', '7': '７', '8': '８', '9': '９'},
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
    'sticker': ('در حال انتخاب استیکر', SendMessageChooseStickerAction()),
    # نکته: «همیشه آنلاین» مثل بقیه‌ی اکشن‌ها فقط یکی از آن‌ها هم‌زمان قابل انتخاب
    # است، اما مکانیزم اجرایش با بقیه فرق دارد (UpdateStatusRequest به‌جای
    # SetTypingRequest) - همین‌جا در self_bot_action_worker قبل از حلقه‌ی
    # تایپ/آپلود جداگانه هندل می‌شود، پس مقدار دومِ تاپل اینجا استفاده نمی‌شود.
    'online': ('همیشه آنلاین', None),
}

# ======================== انواع تاریخ ========================
DATE_TYPE_NAMES = {
    "gregorian": "میلادی",
    "shamsi": "شمسی",
    "qamari": "قمری",
}

# ======================== حالت‌های متن ========================
TEXTMODE_NAMES = {
    1: "نقل قول",
    2: "بولد",
    3: "زیرخط",
    4: "ایتالیک",
    5: "اسپویلر",
    6: "خط خورده",
    7: "تدریجی",
    8: "تک‌فاصله",
}

def format_diamonds(value):
    """
    نمایش موجودی الماس همیشه به‌صورت گردشده (بدون اعشار) در تمام قسمت‌های
    ربات - طبق درخواست صریح، حتی اگر مقدار واقعی در دیتابیس اعشاری باشد
    (مثلاً به‌خاطر محاسبه‌ی لحظه‌ایِ کسر ساعتی).
    """
    value = float(value or 0)
    return f"{round(value):,}"

def format_toman(diamonds):
    toman = float(diamonds or 0) * DIAMOND_PRICE_TOMAN
    return f"{toman:,.0f}"

def format_expiry(diamonds):
    diamonds = float(diamonds or 0)
    if diamonds <= 0 or not DIAMOND_RATE_PER_HOUR:
        return "منقضی شده"
    total_hours = diamonds / DIAMOND_RATE_PER_HOUR
    days = int(total_hours // 24)
    hours = int(total_hours % 24)
    if days > 0:
        return f"{days} روز و {hours} ساعت"
    return f"{hours} ساعت"

# ======================== توابع کمکی ========================
def apply_font(text, font_id):
    font_dict = FONTS.get(font_id, FONTS[0])
    return "".join(font_dict.get(char, char) for char in text)

def is_admin(user_id):
    return user_id in ADMIN_IDS

def make_default_user(session=None, status=False, step="menu"):
    return {
        "session": session,
        "font_id": 1,
        "status": status,
        "name_time": True,
        "bio_time": False,
        "active_action": "none",
        "date_enabled": False,
        "date_type": "shamsi",
        "date_font": 1,
        "text_mode": 0,
        "secretary_enabled": False,
        "secretary_text": "مشغولم، بعداً پاسخ می‌دهم ✅",
        "secretary_delay": 60,
        "secretary_entities": None,
        "secretary_media_kind": None,
        "secretary_media_bytes": None,
        "secretary_media_filename": None,
        "secretary_media_mime": None,
        "diamonds": 0.0,
        "referral_count": 0,
        "username": None,
        "last_charge_at": tehran_now(),
        "meow_enabled": False,
        "meow_chat_id": None,
        "meow_chat_title": None,
        "meow_last_sent_at": None,
        "reaction_enabled": False,
        "autoreply_enabled": False,
        "autoreply_match_type": "exact",
        "autoseen_enabled": False,
        "meow_interval_seconds": MEOW_INTERVAL_SECONDS,
        "fish_enabled": False,
        "fish_last_run_at": None,
        "fish_interval_seconds": FISH_INTERVAL_SECONDS,
        "meowpoint_enabled": False,
        "meowpoint_interval_seconds": MEOWPOINT_INTERVAL_SECONDS,
        "meowpoint_last_run_at": None,
        "streetcat_enabled": False,
        "fridge_enabled": False,
        "fridge_interval_seconds": FRIDGE_INTERVAL_SECONDS,
        "fridge_last_run_at": None,
        "fish_operation_common": "feed",
        "fish_operation_rare": "feed",
        "fish_operation_epic": "feed",
        "fish_operation_legendary": "fridge",
        "task": None,
        "action_task": None,
        "billing_task": None,
        "meow_task": None,
        "fish_task": None,
        "meowpoint_task": None,
        "fridge_task": None,
        "step": step,
        "joined_at": tehran_now()
    }

def format_date(dt, date_type):
    """تبدیل datetime به رشته تاریخ بر اساس نوع انتخابی (میلادی/شمسی/قمری)."""
    try:
        if date_type == "shamsi":
            jd = jdatetime.datetime.fromgregorian(datetime=dt)
            return jd.strftime("%Y/%m/%d")
        elif date_type == "qamari":
            h = Gregorian(dt.year, dt.month, dt.day).to_hijri()
            return f"{h.year}/{h.month:02d}/{h.day:02d}"
        else:
            return dt.strftime("%Y/%m/%d")
    except Exception as e:
        logging.error(f"⚠️ خطا در محاسبه تاریخ ({date_type}): {e}")
        return dt.strftime("%Y/%m/%d")

def make_blockquote_entity(offset, length, collapsed=False):
    """سازگار با نسخه‌های مختلف Telethon برای نقل‌قول تدریجی (collapsed)."""
    try:
        return MessageEntityBlockquote(offset=offset, length=length, collapsed=collapsed)
    except TypeError:
        return MessageEntityBlockquote(offset=offset, length=length)

def build_format_entities(text, mode):
    """ساخت entity قالب‌بندی مناسب برای متن کامل پیام بر اساس حالت انتخابی."""
    if not text or not mode or mode not in TEXTMODE_NAMES:
        return None

    surrogated = helpers.add_surrogate(text)
    length = len(surrogated)
    if length == 0:
        return None
    offset = 0

    if mode == 1:
        return [make_blockquote_entity(offset, length, collapsed=False)]
    if mode == 2:
        return [MessageEntityBold(offset, length)]
    if mode == 3:
        return [MessageEntityUnderline(offset, length)]
    if mode == 4:
        return [MessageEntityItalic(offset, length)]
    if mode == 5:
        return [MessageEntitySpoiler(offset, length)]
    if mode == 6:
        return [MessageEntityStrike(offset, length)]
    if mode == 7:
        return [make_blockquote_entity(offset, length, collapsed=True)]
    if mode == 8:
        return [MessageEntityCode(offset, length)]
    return None

def _describe_message_kind(msg):
    """برچسب فارسیِ نوع محتوای پیام (برای پیش‌نمایش تایید ارسال و لیست پیام‌های ادمین)."""
    if getattr(msg, "photo", None):
        return "🖼 عکس"
    if getattr(msg, "video", None):
        return "🎥 ویدیو"
    if getattr(msg, "voice", None):
        return "🎙 پیام صوتی"
    if getattr(msg, "video_note", None):
        return "⭕ Video Note"
    if getattr(msg, "gif", None):
        return "🌀 GIF/انیمیشن"
    if getattr(msg, "sticker", None):
        return "🌀 استیکر"
    if getattr(msg, "audio", None):
        return "🎵 موزیک"
    if getattr(msg, "document", None):
        return "📄 فایل"
    if getattr(msg, "poll", None):
        return "📊 نظرسنجی"
    if getattr(msg, "contact", None):
        return "👤 مخاطب"
    if getattr(msg, "geo", None):
        return "📍 موقعیت مکانی"
    return "📝 متن"

def _media_kind_key(msg):
    """کلید داخلی (نه لیبل فارسی) برای نوع رسانه‌ی پیام — برای تصمیم‌گیری در ارسال مجدد پاسخ خودکار."""
    if getattr(msg, "voice", None):
        return "voice"
    if getattr(msg, "video_note", None):
        return "video_note"
    if getattr(msg, "gif", None):
        return "gif"
    if getattr(msg, "sticker", None):
        return "sticker"
    if getattr(msg, "video", None):
        return "video"
    if getattr(msg, "audio", None):
        return "audio"
    if getattr(msg, "photo", None):
        return "photo"
    if getattr(msg, "document", None):
        return "document"
    return None

async def _copy_message_to(client, target_id, src_msg):
    """
    یک نسخه‌ی کامل از پیام (متن + Formatting + هر نوع رسانه: عکس/ویدیو/فایل/ویس/
    Video Note/استیکر/GIF/موزیک/Poll/Contact/Location) را برای target_id ارسال می‌کند.
    اگر پیام مبدا خودش Forward بوده، با forward_messages به‌صورت Forward واقعی
    (حفظ هدر «Forwarded from») ارسال می‌شود؛ در غیر این صورت با پاس‌دادن مستقیمِ شیء
    Message به send_message، Telethon خودش متن/Entityها/رسانه را کپی می‌کند (بدون
    هدر Forward) — این رفتار رسمیِ Telethon برای «کپی پیام» است و متن را Plain نمی‌کند.
    خروجی: شیء Message ارسال‌شده (برای ثبت message_id جهت حذف بعدی).
    """
    if getattr(src_msg, "forward", None):
        result = await client.forward_messages(target_id, messages=src_msg.id, from_peer=src_msg.chat_id)
        return result[0] if isinstance(result, list) else result
    return await client.send_message(target_id, src_msg)

async def safe_edit(event, text, buttons=None):
    """
    ویرایش امن پیام + پاسخ فوری به Callback (برای جلوگیری از تأخیر/اسپینر روی دکمه‌ها).
    جلوگیری از کرش شدن هندلرها به‌خاطر خطای ویرایش پیام (مثل MessageNotModified).

    اگر این کلیک از یک «پنل درون‌چتی» (ساخته‌شده با Inline Mode) آمده باشد،
    دکمه‌های صفحه‌ی بعدی را هم خودکار با پیشوند مالکیت بازپیچی می‌کنیم تا
    تمام مراحل ناوبری پنل، نه فقط صفحه‌ی اول، محدود به صاحب Self بماند (بند ۱۰).
    """
    if buttons and getattr(event, "_is_inline_panel", False):
        owner_id = getattr(event, "_panel_owner_id", None)
        if owner_id:
            buttons = wrap_panel_buttons(buttons, owner_id)

    try:
        await event.edit(text, buttons=buttons)
    except MessageNotModifiedError:
        pass
    except Exception as e:
        logging.error(f"⚠️ خطا در ویرایش پیام: {e}")
        try:
            await event.answer("❌ خطا در بروزرسانی پیام، دوباره تلاش کنید.", alert=True)
            return
        except Exception:
            pass
    try:
        await event.answer()
    except Exception:
        pass

