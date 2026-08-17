import asyncio
import time
import re
import os
import secrets
import string
import pickle
import json
import base64
import io
import pytz
import psycopg2
import jdatetime
from hijridate import Gregorian
from psycopg2.extras import DictCursor
from datetime import datetime, timedelta
from telethon import TelegramClient, events, Button, helpers
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError, FloodWaitError, MessageNotModifiedError, RPCError,
    ChatWriteForbiddenError, UserBannedInChannelError, ChannelPrivateError,
    UserNotParticipantError, ChatAdminRequiredError,
)
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.messages import SetTypingRequest, GetFullChatRequest, CheckChatInviteRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.types import (
    SendMessageTypingAction, SendMessageRecordAudioAction, SendMessageUploadPhotoAction,
    SendMessageRecordRoundAction, SendMessageUploadDocumentAction, SendMessageUploadVideoAction,
    SendMessageGamePlayAction, SendMessageChooseStickerAction,
    MessageEntityBold, MessageEntityItalic, MessageEntityUnderline,
    MessageEntityStrike, MessageEntitySpoiler, MessageEntityCode,
    MessageEntityBlockquote, ChannelParticipantsAdmins, InputMessageEntityMentionName,
    DocumentAttributeAnimated, ChatInviteAlready,
)
import logging
from webapp_api import create_webapp_app, run_webapp_server
from nova_utils import (
    status_icon, toggle_label, build_clock_preview, build_date_preview,
    build_sender_receipt, build_receiver_receipt, ClickDebouncer, safe_call,
    log_diamond_transfer, log_self_toggle, log_settings_change, log_internal_error,
    styled_button, toggle_button, STYLE_ON, STYLE_OFF, STYLE_INFO, wrap_panel_buttons,
)

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

# catch_up=True: بدون این، Telethon پیش‌فرض روی False است و آپدیت‌هایی که در
# حین قطعی/ری‌استارت (مثلاً روی Railway) رخ داده‌اند (از جمله «ربات به فلان کانال
# اضافه/ادمین شد») از دست می‌روند و کش انتیتیِ کانال هیچ‌وقت پر نمی‌شود — حتی اگر
# ربات واقعاً عضو/ادمین آن کانال باشد (همان دلیل اصلیِ خطای گمراه‌کننده‌ی
# «ربات ادمین نشده» در بخش جوین اجباری، وقتی ربات از قبل واقعاً ادمین بوده است).
# catch_up=True: بدون این، Telethon پیش‌فرض روی False است و آپدیت‌هایی که در
# حین قطعی/ری‌استارت (مثلاً روی Railway) رخ داده‌اند (از جمله «ربات به فلان کانال
# اضافه/ادمین شد») از دست می‌روند و کش انتیتیِ کانال هیچ‌وقت پر نمی‌شود — حتی اگر
# ربات واقعاً عضو/ادمین آن کانال باشد (همان دلیل اصلیِ خطای گمراه‌کننده‌ی
# «ربات ادمین نشده» در بخش جوین اجباری، وقتی ربات از قبل واقعاً ادمین بوده است).
bot = TelegramClient('helper_bot', API_ID, API_HASH, catch_up=True).start(bot_token=BOT_TOKEN)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ======================== تنظیمات سیستم الماس ========================
# ======================== تنظیمات جوین اجباری ========================
# مدت اعتبار یک تأیید عضویت. بعد از این مدت، دفعه‌ی بعد که کاربر تعامل کند
# (کلیک/پیام/استارت)، عضویتش دوباره واقعاً از تلگرام استعلام می‌شود — تا کسی که
# از کانال لفت داده برای همیشه معاف نماند. مقدار کم باعث افزایش تماس با API
# تلگرام می‌شود و مقدار خیلی زیاد اثر «اجباری بودن» را کم می‌کند؛ ۶ ساعت تعادل خوبی است.
JOIN_GATE_RECHECK_SECONDS = 6 * 60 * 60

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
    نرمال‌سازی هوشمند شماره تلفن قبل از ارسال به تلگرام: اعداد فارسی/عربی به
    انگلیسی، حذف فاصله/نیم‌فاصله/خط‌تیره/پرانتز، تشخیص صفر ابتدایی و حالت بدون
    +۹۸، و افزودن خودکار +۹۸. تمام حالت‌های 0912x../912x../+98912x../۰۹۱۲x../۹۱۲x..
    پشتیبانی می‌شوند. هرگز Exception نمی‌دهد — همیشه (normalized یا None, پیام خطا یا None)
    برمی‌گرداند.
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

        example_error = (
            "❌ فرمت شماره تشخیص داده نشد.\n"
            "نمونه‌های معتبر: `0912xxxxxxx` یا `+98912xxxxxxx`"
        )

        if digits.startswith("0098"):
            digits = digits[4:]
        elif digits.startswith("98") and len(digits) == 12:
            pass
        elif digits.startswith("0") and len(digits) == 11:
            digits = digits[1:]
        elif len(digits) == 10 and digits.startswith("9"):
            pass
        else:
            return None, example_error

        if not digits.startswith("98"):
            digits = "98" + digits

        normalized = "+" + digits

        if not re.fullmatch(r"\+989\d{9}", normalized):
            return None, example_error

        return normalized, None
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
global_feature_locks = set()  # {feature_key, ...} کش قفل سراسری (برای همه‌ی کاربران)
backup_upload_pending = {}  # {admin_id: dump_dict} بکاپ آپلودشده‌ای که هنوز تأیید نشده
join_channels_cache = []  # لیست کانال‌های فعالِ جوین اجباری (کش)
# {user_id: {"verified_at": datetime, "snapshot": str}, ...}
# برخلاف نسخه‌ی قبلی (یک set ساده که یعنی «یک‌بار برای همیشه تأیید شده»)، اینجا
# برای هر کاربر زمانِ آخرین تأیید و «عکسِ لحظه‌ایِ» کانال‌های فعال در آن لحظه هم
# نگه‌داری می‌شود؛ همین دو مقدار است که به needs_join_check() اجازه می‌دهد تشخیص
# بدهد یک تأییدِ قدیمی هنوز معتبر است یا باید دوباره از کاربر خواسته شود.
verified_users = {}
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
REACTION_SET_PREFIXES = (".ریکت ", ".react ")
REACTION_REMOVE_TRIGGERS = {".حذف ریکت", ".remove react"}
REACTION_APPLY_DELAY = 1.0  # طبق بند «اجرای خودکار»: حدود ۱ ثانیه تأخیر قبل از ریکت
AUTOREPLY_MATCH_TYPES = {"exact": "برابر", "prefix": "پیشوند", "contains": "شامل"}
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
    'sticker': ('در حال انتخاب استیکر', SendMessageChooseStickerAction())
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

# ======================== مدیریت دیتابیس ========================
def get_db_connection():
    """
    اتصال جدید به Postgres. بلافاصله بعد از اتصال، Timezone نشست روی Asia/Tehran
    تنظیم می‌شود تا مقادیر CURRENT_TIMESTAMP/NOW() که در ستون‌های TIMESTAMP (بدون
    Timezone) ذخیره می‌شوند، بر حسب ساعت تهران محاسبه شوند — نه ساعت سرور (که روی
    Railway معمولاً UTC است). این باگِ «تایم/تاریخ اشتباه در بعضی قسمت‌ها» را حل می‌کند.
    """
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    try:
        with conn.cursor() as cursor:
            cursor.execute("SET TIME ZONE 'Asia/Tehran'")
        conn.commit()
    except Exception as e:
        logging.error(f"⚠️ خطا در تنظیم Timezone اتصال دیتابیس: {e}")
    return conn

def init_db():
    """ایجاد جدول و افزودن ستون‌های جدید در صورت نیاز (idempotent و امن برای ری‌استارت)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS novaself_users (
                user_id BIGINT PRIMARY KEY,
                session TEXT,
                font_id INTEGER DEFAULT 1,
                status INTEGER DEFAULT 0,
                name_time INTEGER DEFAULT 1,
                bio_time INTEGER DEFAULT 0,
                active_action TEXT DEFAULT 'none',
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

        migration_columns = [
            ("date_enabled", "INTEGER DEFAULT 0"),
            ("date_type", "TEXT DEFAULT 'shamsi'"),
            ("date_font", "INTEGER DEFAULT 1"),
            ("text_mode", "INTEGER DEFAULT 0"),
            ("secretary_enabled", "INTEGER DEFAULT 0"),
            ("secretary_text", "TEXT DEFAULT 'مشغولم، بعداً پاسخ می‌دهم ✅'"),
            ("secretary_delay", "INTEGER DEFAULT 60"),
            ("diamonds", "DOUBLE PRECISION DEFAULT 0"),
            ("referral_count", "INTEGER DEFAULT 0"),
            ("username", "TEXT"),
            ("last_charge_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("meow_enabled", "INTEGER DEFAULT 0"),
            ("meow_chat_id", "BIGINT"),
            ("meow_last_sent_at", "TIMESTAMP"),
            ("meow_interval_seconds", "INTEGER DEFAULT 320"),
            ("fish_enabled", "INTEGER DEFAULT 0"),
            ("fish_last_run_at", "TIMESTAMP"),
            ("fish_interval_seconds", "INTEGER DEFAULT 3610"),
            ("meowpoint_enabled", "INTEGER DEFAULT 0"),
            ("meowpoint_interval_seconds", "INTEGER DEFAULT 2700"),
            ("meowpoint_last_run_at", "TIMESTAMP"),
            ("streetcat_enabled", "INTEGER DEFAULT 0"),
            ("fridge_enabled", "INTEGER DEFAULT 0"),
            ("fridge_interval_seconds", "INTEGER DEFAULT 1800"),
            ("fridge_last_run_at", "TIMESTAMP"),
            ("fish_operation_common", "TEXT DEFAULT 'feed'"),
            ("fish_operation_rare", "TEXT DEFAULT 'feed'"),
            ("fish_operation_epic", "TEXT DEFAULT 'feed'"),
            ("fish_operation_legendary", "TEXT DEFAULT 'fridge'"),
            ("meow_chat_title", "TEXT"),
            ("reaction_enabled", "BOOLEAN DEFAULT FALSE"),
            ("autoreply_enabled", "BOOLEAN DEFAULT FALSE"),
            ("autoreply_match_type", "TEXT DEFAULT 'exact'"),
        ]
        for col_name, col_def in migration_columns:
            try:
                cursor.execute(f"ALTER TABLE novaself_users ADD COLUMN IF NOT EXISTS {col_name} {col_def}")
                conn.commit()
            except Exception as e:
                conn.rollback()
                logging.error(f"❌ خطا در افزودن ستون {col_name}: {e}")

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS novaself_admin_logs (
                id SERIAL PRIMARY KEY,
                admin_id BIGINT,
                target_id BIGINT,
                action TEXT,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS novaself_gift_codes (
                code TEXT PRIMARY KEY,
                diamonds DOUBLE PRECISION NOT NULL,
                is_active INTEGER DEFAULT 1,
                expires_at TIMESTAMP,
                created_by BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS novaself_gift_code_uses (
                code TEXT REFERENCES novaself_gift_codes(code) ON DELETE CASCADE,
                user_id BIGINT,
                used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (code, user_id)
            )
        ''')
        conn.commit()

        # ---------- سفارش‌های خرید الماس (بخش خرید الماس / کارت‌به‌کارت) ----------
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS novaself_orders (
                order_id TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                username TEXT,
                amount_diamonds DOUBLE PRECISION NOT NULL,
                amount_toman BIGINT NOT NULL,
                payment_method TEXT DEFAULT 'card_to_card',
                status TEXT DEFAULT 'invoice',
                receipt_chat_id BIGINT,
                receipt_message_id BIGINT,
                receipt_file_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                approved_at TIMESTAMP,
                approved_by BIGINT,
                rejected_at TIMESTAMP,
                rejected_by BIGINT,
                rejection_reason TEXT
            )
        ''')
        conn.commit()

        # ---------- لاگ پیام‌های ارسالی ادمین (تکی/همگانی) برای مدیریت/حذف بعدی ----------
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS novaself_broadcasts (
                broadcast_id TEXT PRIMARY KEY,
                admin_id BIGINT,
                kind TEXT,
                target_id BIGINT,
                summary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS novaself_broadcast_deliveries (
                id SERIAL PRIMARY KEY,
                broadcast_id TEXT REFERENCES novaself_broadcasts(broadcast_id) ON DELETE CASCADE,
                user_id BIGINT,
                chat_id BIGINT,
                message_id BIGINT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

        # ---------- قابلیت ریکت (بند ۳-۴) ----------
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS novaself_reactions (
                owner_id BIGINT NOT NULL,
                target_user_id BIGINT NOT NULL,
                target_username TEXT,
                emoji TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (owner_id, target_user_id)
            )
        ''')
        conn.commit()

        # ---------- قابلیت پاسخ خودکار (بند ۵-۱۰) ----------
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS novaself_autoreplies (
                id SERIAL PRIMARY KEY,
                owner_id BIGINT NOT NULL,
                local_id INTEGER NOT NULL,
                trigger_text TEXT NOT NULL,
                response_text TEXT,
                response_entities BYTEA,
                response_media_kind TEXT,
                response_media_bytes BYTEA,
                response_media_filename TEXT,
                response_media_mime TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (owner_id, local_id)
            )
        ''')
        conn.commit()

        # ---------- قفل کردن قابلیت‌ها توسط ادمین ----------
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS novaself_feature_locks (
                user_id BIGINT NOT NULL,
                feature_key TEXT NOT NULL,
                locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, feature_key)
            )
        ''')
        conn.commit()

        # ---------- قفل سراسری قابلیت‌ها (برای همه‌ی کاربران) ----------
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS novaself_global_locks (
                feature_key TEXT PRIMARY KEY,
                locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

        # ---------- جوین اجباری ----------
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS novaself_join_channels (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                identifier TEXT NOT NULL,
                invite_link TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS novaself_join_verified (
                user_id BIGINT PRIMARY KEY,
                verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                channels_snapshot TEXT DEFAULT ''
            )
        ''')
        conn.commit()

        # ستون channels_snapshot برای دیپلوی‌های قدیمی‌تر که این جدول را از قبل
        # (بدون این ستون) دارند، اضافه می‌شود تا نیازی به دراپ‌کردن دستی جدول نباشد.
        try:
            cursor.execute("ALTER TABLE novaself_join_verified ADD COLUMN IF NOT EXISTS channels_snapshot TEXT DEFAULT ''")
            conn.commit()
        except Exception as e:
            conn.rollback()
            logging.error(f"❌ خطا در افزودن ستون channels_snapshot: {e}")

        # ---------- سیستم بکاپ ----------
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS novaself_backups (
                id SERIAL PRIMARY KEY,
                created_by BIGINT,
                label TEXT,
                size_bytes INTEGER,
                data BYTEA,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

        logging.info("✅ دیتابیس با موفقیت راه‌اندازی/بروزرسانی شد.")
        cursor.close()
        conn.close()
    except Exception as e:
        logging.error(f"❌ خطا در راه‌اندازی دیتابیس: {e}")

def get_all_users():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)

        cursor.execute("""
            SELECT user_id, session, font_id, status, name_time, bio_time, active_action,
                   joined_at, date_enabled, date_type, date_font, text_mode,
                   secretary_enabled, secretary_text, secretary_delay,
                   diamonds, referral_count, username, last_charge_at,
                   meow_enabled, meow_chat_id, meow_last_sent_at, meow_interval_seconds,
                   fish_enabled, fish_last_run_at, fish_interval_seconds,
                   meowpoint_enabled, meowpoint_interval_seconds, meowpoint_last_run_at,
                   streetcat_enabled,
                   fridge_enabled, fridge_interval_seconds, fridge_last_run_at,
                   fish_operation_common, fish_operation_rare, fish_operation_epic, fish_operation_legendary,
                   meow_chat_title, reaction_enabled, autoreply_enabled, autoreply_match_type
            FROM novaself_users
            ORDER BY joined_at DESC
        """)

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        data = {}
        for row in rows:
            user_id = row['user_id']
            data[user_id] = {
                "session": row['session'],
                "font_id": row['font_id'] if row['font_id'] is not None else 1,
                "status": bool(row['status']),
                "name_time": bool(row['name_time']),
                "bio_time": bool(row['bio_time']),
                "active_action": row['active_action'] or "none",
                "date_enabled": bool(row['date_enabled']) if row['date_enabled'] is not None else False,
                "date_type": row['date_type'] or "shamsi",
                "date_font": row['date_font'] if row['date_font'] is not None else 1,
                "text_mode": row['text_mode'] if row['text_mode'] is not None else 0,
                "secretary_enabled": bool(row['secretary_enabled']) if row['secretary_enabled'] is not None else False,
                "secretary_text": row['secretary_text'] or "مشغولم، بعداً پاسخ می‌دهم ✅",
                "secretary_delay": row['secretary_delay'] if row['secretary_delay'] is not None else 60,
                "diamonds": float(row['diamonds']) if row['diamonds'] is not None else 0.0,
                "referral_count": row['referral_count'] if row['referral_count'] is not None else 0,
                "username": row['username'],
                "last_charge_at": row['last_charge_at'] or tehran_now(),
                "joined_at": row['joined_at'] or tehran_now(),
                "meow_enabled": bool(row['meow_enabled']) if row['meow_enabled'] is not None else False,
                "meow_chat_id": row['meow_chat_id'],
                "meow_last_sent_at": row['meow_last_sent_at'],
                "meow_interval_seconds": row['meow_interval_seconds'] if row['meow_interval_seconds'] else MEOW_INTERVAL_SECONDS,
                "fish_enabled": bool(row['fish_enabled']) if row['fish_enabled'] is not None else False,
                "fish_last_run_at": row['fish_last_run_at'],
                "fish_interval_seconds": row['fish_interval_seconds'] if row['fish_interval_seconds'] else FISH_INTERVAL_SECONDS,
                "meowpoint_enabled": bool(row['meowpoint_enabled']) if row['meowpoint_enabled'] is not None else False,
                "meowpoint_interval_seconds": row['meowpoint_interval_seconds'] if row['meowpoint_interval_seconds'] else MEOWPOINT_INTERVAL_SECONDS,
                "meowpoint_last_run_at": row['meowpoint_last_run_at'],
                "streetcat_enabled": bool(row['streetcat_enabled']) if row['streetcat_enabled'] is not None else False,
                "fridge_enabled": bool(row['fridge_enabled']) if row['fridge_enabled'] is not None else False,
                "fridge_interval_seconds": row['fridge_interval_seconds'] if row['fridge_interval_seconds'] else FRIDGE_INTERVAL_SECONDS,
                "fridge_last_run_at": row['fridge_last_run_at'],
                "fish_operation_common": row['fish_operation_common'] or "feed",
                "fish_operation_rare": row['fish_operation_rare'] or "feed",
                "fish_operation_epic": row['fish_operation_epic'] or "feed",
                "fish_operation_legendary": row['fish_operation_legendary'] or "fridge",
                "meow_chat_title": row['meow_chat_title'],
                "reaction_enabled": bool(row['reaction_enabled']),
                "autoreply_enabled": bool(row['autoreply_enabled']),
                "autoreply_match_type": row['autoreply_match_type'] or "exact",
                "step": "managed",
                "task": None,
                "action_task": None,
                "billing_task": None,
                "meow_task": None,
                "fish_task": None,
                "meowpoint_task": None,
                "fridge_task": None
            }
        return data
    except Exception as e:
        logging.error(f"❌ خطا در بارگذاری کاربران: {e}")
        return {}

def save_user(user_id, user):
    """
    ذخیره تنظیمات عمومی کاربر (نه فیلدهای اقتصادی).
    diamonds / referral_count / last_charge_at عمداً اینجا آپدیت نمی‌شوند چون به‌صورت
    اتمیک توسط charge_diamonds_db / transfer_diamonds_db / admin_adjust_diamonds مدیریت
    می‌شوند؛ آپدیت آن‌ها از این تابع می‌تواند مقدار تازه‌ی دیتابیس را با مقدار قدیمیِ
    حافظه بازنویسی کند و باعث ناسازگاری/از دست رفتن موجودی شود.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO novaself_users
                (user_id, session, font_id, status, name_time, bio_time, active_action,
                 date_enabled, date_type, date_font, text_mode,
                 secretary_enabled, secretary_text, secretary_delay,
                 diamonds, referral_count, username, last_charge_at,
                 meow_enabled, meow_chat_id, meow_last_sent_at, meow_interval_seconds,
                 fish_enabled, fish_last_run_at, fish_interval_seconds,
                 meowpoint_enabled, meowpoint_interval_seconds, meowpoint_last_run_at,
                 streetcat_enabled,
                 fridge_enabled, fridge_interval_seconds, fridge_last_run_at,
                 fish_operation_common, fish_operation_rare, fish_operation_epic, fish_operation_legendary,
                 meow_chat_title, reaction_enabled, autoreply_enabled, autoreply_match_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET
                session = EXCLUDED.session,
                font_id = EXCLUDED.font_id,
                status = EXCLUDED.status,
                name_time = EXCLUDED.name_time,
                bio_time = EXCLUDED.bio_time,
                active_action = EXCLUDED.active_action,
                date_enabled = EXCLUDED.date_enabled,
                date_type = EXCLUDED.date_type,
                date_font = EXCLUDED.date_font,
                text_mode = EXCLUDED.text_mode,
                secretary_enabled = EXCLUDED.secretary_enabled,
                secretary_text = EXCLUDED.secretary_text,
                secretary_delay = EXCLUDED.secretary_delay,
                meow_enabled = EXCLUDED.meow_enabled,
                meow_chat_id = EXCLUDED.meow_chat_id,
                meow_last_sent_at = EXCLUDED.meow_last_sent_at,
                meow_interval_seconds = EXCLUDED.meow_interval_seconds,
                fish_enabled = EXCLUDED.fish_enabled,
                fish_last_run_at = EXCLUDED.fish_last_run_at,
                fish_interval_seconds = EXCLUDED.fish_interval_seconds,
                meowpoint_enabled = EXCLUDED.meowpoint_enabled,
                meowpoint_interval_seconds = EXCLUDED.meowpoint_interval_seconds,
                meowpoint_last_run_at = EXCLUDED.meowpoint_last_run_at,
                streetcat_enabled = EXCLUDED.streetcat_enabled,
                fridge_enabled = EXCLUDED.fridge_enabled,
                fridge_interval_seconds = EXCLUDED.fridge_interval_seconds,
                fridge_last_run_at = EXCLUDED.fridge_last_run_at,
                fish_operation_common = EXCLUDED.fish_operation_common,
                fish_operation_rare = EXCLUDED.fish_operation_rare,
                fish_operation_epic = EXCLUDED.fish_operation_epic,
                fish_operation_legendary = EXCLUDED.fish_operation_legendary,
                meow_chat_title = EXCLUDED.meow_chat_title,
                reaction_enabled = EXCLUDED.reaction_enabled,
                autoreply_enabled = EXCLUDED.autoreply_enabled,
                autoreply_match_type = EXCLUDED.autoreply_match_type
        ''', (
            user_id, user.get("session"), user.get("font_id", 1), int(user.get("status", False)),
            int(user.get("name_time", True)), int(user.get("bio_time", False)),
            user.get("active_action", "none"),
            int(user.get("date_enabled", False)), user.get("date_type", "shamsi"),
            user.get("date_font", 1), user.get("text_mode", 0),
            int(user.get("secretary_enabled", False)), user.get("secretary_text", "مشغولم، بعداً پاسخ می‌دهم ✅"),
            user.get("secretary_delay", 60),
            user.get("diamonds", 0), user.get("referral_count", 0), user.get("username"),
            user.get("last_charge_at", tehran_now()),
            int(user.get("meow_enabled", False)), user.get("meow_chat_id"), user.get("meow_last_sent_at"),
            user.get("meow_interval_seconds", MEOW_INTERVAL_SECONDS),
            int(user.get("fish_enabled", False)), user.get("fish_last_run_at"),
            user.get("fish_interval_seconds", FISH_INTERVAL_SECONDS),
            int(user.get("meowpoint_enabled", False)), user.get("meowpoint_interval_seconds", MEOWPOINT_INTERVAL_SECONDS),
            user.get("meowpoint_last_run_at"),
            int(user.get("streetcat_enabled", False)),
            int(user.get("fridge_enabled", False)), user.get("fridge_interval_seconds", FRIDGE_INTERVAL_SECONDS),
            user.get("fridge_last_run_at"),
            user.get("fish_operation_common", "feed"), user.get("fish_operation_rare", "feed"),
            user.get("fish_operation_epic", "feed"), user.get("fish_operation_legendary", "fridge"),
            user.get("meow_chat_title"),
            user.get("reaction_enabled", False), user.get("autoreply_enabled", False),
            user.get("autoreply_match_type", "exact")
        ))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logging.error(f"❌ خطا در ذخیره کاربر {user_id}: {e}")

def update_username_db(user_id, username):
    """بروزرسانی مستقل نام‌کاربری (بدون تداخل با فیلدهای اقتصادی)."""
    if not username:
        return
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE novaself_users SET username = %s WHERE user_id = %s", (username, user_id))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logging.error(f"❌ خطا در بروزرسانی نام‌کاربری {user_id}: {e}")

def delete_user_db(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM novaself_users WHERE user_id = %s", (user_id,))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logging.error(f"❌ خطا در حذف کاربر {user_id}: {e}")

def get_user_stats():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM novaself_users")
        total_users = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM novaself_users WHERE status = 1")
        active_users = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        return total_users, active_users
    except Exception as e:
        logging.error(f"❌ خطا در دریافت آمار: {e}")
        return 0, 0

def log_admin_action(admin_id, target_id, action, details=""):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO novaself_admin_logs (admin_id, target_id, action, details) VALUES (%s, %s, %s, %s)",
            (admin_id, target_id, action, details)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logging.error(f"❌ خطا در ثبت لاگ مدیریتی: {e}")

def get_recent_admin_logs(limit=15):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT admin_id, target_id, action, details, created_at "
            "FROM novaself_admin_logs ORDER BY created_at DESC LIMIT %s",
            (limit,)
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows
    except Exception as e:
        logging.error(f"❌ خطا در دریافت لاگ‌های مدیریتی: {e}")
        return []

# ======================== سیستم اقتصادی الماس (اتمیک و امن در برابر Race Condition) ========================
def charge_diamonds_db(user_id, cost):
    """
    کسر اتمیک الماس (برای بیلینگِ روشن‌بودن سلف).
    خروجی: (success: bool, new_balance: float یا None در صورت خطا)
    success=False یعنی موجودی برای این هزینه کافی نبود (و موجودی صفر شده است).
    """
    if cost <= 0:
        return True, None
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT diamonds FROM novaself_users WHERE user_id = %s FOR UPDATE", (user_id,))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return False, None

        current = float(row[0] or 0)
        if current <= 0:
            conn.rollback()
            return False, 0.0

        new_balance = current - cost
        insufficient = new_balance < 0
        if insufficient:
            new_balance = 0.0

        cursor.execute(
            "UPDATE novaself_users SET diamonds = %s, last_charge_at = %s WHERE user_id = %s",
            (new_balance, tehran_now(), user_id)
        )
        conn.commit()
        return (not insufficient), new_balance
    except Exception as e:
        logging.error(f"❌ خطا در کسر الماس کاربر {user_id}: {e}")
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return False, None
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass

def transfer_diamonds_db(sender_id, receiver_id, amount):
    """
    انتقال اتمیک الماس بین دو کاربر (با قفل ردیف به ترتیب ثابت برای جلوگیری از Deadlock).
    خروجی: (success: bool, message: str, sender_balance, receiver_balance)
    """
    if sender_id == receiver_id:
        return False, "❌ انتقال به خودتان امکان‌پذیر نیست.", None, None
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return False, "❌ مقدار وارد شده معتبر نیست.", None, None
    if amount <= 0:
        return False, "❌ مقدار انتقال باید بیشتر از صفر باشد.", None, None

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        ids_sorted = sorted([sender_id, receiver_id])
        cursor.execute(
            "SELECT user_id, diamonds FROM novaself_users WHERE user_id IN (%s, %s) ORDER BY user_id FOR UPDATE",
            (ids_sorted[0], ids_sorted[1])
        )
        rows = {r[0]: float(r[1] or 0) for r in cursor.fetchall()}

        if sender_id not in rows:
            conn.rollback()
            return False, "❌ حساب فرستنده پیدا نشد.", None, None
        if receiver_id not in rows:
            conn.rollback()
            return False, "❌ کاربر گیرنده در سیستم ثبت‌نام نکرده است.", None, None

        sender_balance = rows[sender_id]
        if sender_balance < amount:
            conn.rollback()
            return False, "❌ موجودی شما کافی نیست.", None, None

        new_sender = sender_balance - amount
        new_receiver = rows[receiver_id] + amount

        cursor.execute("UPDATE novaself_users SET diamonds = %s WHERE user_id = %s", (new_sender, sender_id))
        cursor.execute("UPDATE novaself_users SET diamonds = %s WHERE user_id = %s", (new_receiver, receiver_id))
        conn.commit()
        return True, "✅ انتقال با موفقیت انجام شد.", new_sender, new_receiver
    except Exception as e:
        logging.error(f"❌ خطا در انتقال الماس بین {sender_id} و {receiver_id}: {e}")
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return False, "❌ خطای دیتابیس در حین انتقال رخ داد.", None, None
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass

def create_gift_code_db(code, diamonds, expires_at, created_by):
    """ساخت یک کد هدیه‌ی جدید توسط ادمین. خروجی: (success, error_message یا None)."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO novaself_gift_codes (code, diamonds, is_active, expires_at, created_by) "
            "VALUES (%s, %s, 1, %s, %s)",
            (code, diamonds, expires_at, created_by)
        )
        conn.commit()
        return True, None
    except psycopg2.errors.UniqueViolation:
        if conn:
            conn.rollback()
        return False, "این کد از قبل وجود دارد."
    except Exception as e:
        logging.error(f"❌ خطا در ساخت کد هدیه {code}: {e}")
        if conn:
            conn.rollback()
        return False, "خطای دیتابیس رخ داد."
    finally:
        if conn:
            conn.close()

def set_gift_code_active_db(code, is_active):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE novaself_gift_codes SET is_active = %s WHERE code = %s", (int(is_active), code))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"❌ خطا در تغییر وضعیت کد هدیه {code}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def list_gift_codes_db(limit=20):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute(
            "SELECT code, diamonds, is_active, expires_at, created_at FROM novaself_gift_codes "
            "ORDER BY created_at DESC LIMIT %s", (limit,)
        )
        return cursor.fetchall()
    except Exception as e:
        logging.error(f"❌ خطا در دریافت لیست کدهای هدیه: {e}")
        return []
    finally:
        if conn:
            conn.close()

def redeem_gift_code_db(code, user_id):
    """
    اعتبارسنجی و مصرف اتمیک کد هدیه برای یک کاربر.
    خروجی: (success: bool, message: str, new_balance یا None)
    شرط‌ها: وجود کد، فعال بودن، منقضی نشدن، و عدم استفاده‌ی قبلی همین کاربر
    (با قفل ردیف کد + کلید یکتای (code, user_id) در جدول مصرف، برای جلوگیری از Race Condition).
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)

        cursor.execute("SELECT * FROM novaself_gift_codes WHERE code = %s FOR UPDATE", (code,))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return False, "❌ چنین کدی وجود ندارد.", None
        if not row["is_active"]:
            conn.rollback()
            return False, "❌ این کد غیرفعال شده است.", None
        if row["expires_at"] and row["expires_at"] < tehran_now():
            conn.rollback()
            return False, "❌ این کد منقضی شده است.", None

        try:
            cursor.execute(
                "INSERT INTO novaself_gift_code_uses (code, user_id) VALUES (%s, %s)",
                (code, user_id)
            )
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            return False, "❌ شما قبلاً از این کد استفاده کرده‌اید.", None

        cursor.execute("SELECT diamonds FROM novaself_users WHERE user_id = %s FOR UPDATE", (user_id,))
        user_row = cursor.fetchone()
        if not user_row:
            conn.rollback()
            return False, "❌ حساب کاربری شما پیدا نشد.", None

        new_balance = float(user_row["diamonds"] or 0) + float(row["diamonds"])
        cursor.execute("UPDATE novaself_users SET diamonds = %s WHERE user_id = %s", (new_balance, user_id))
        conn.commit()
        return True, f"✅ کد هدیه با موفقیت اعمال شد! {format_diamonds(row['diamonds'])} الماس به حساب شما اضافه شد.", new_balance
    except Exception as e:
        logging.error(f"❌ خطا در مصرف کد هدیه {code} برای کاربر {user_id}: {e}")
        if conn:
            conn.rollback()
        return False, "❌ خطای دیتابیس رخ داد.", None
    finally:
        if conn:
            conn.close()

def get_gift_code_detail_db(code):
    """جزئیات کامل یک کد هدیه به‌همراه تعداد دفعات استفاده (برای صفحه مدیریت کد)."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute("SELECT * FROM novaself_gift_codes WHERE code = %s", (code,))
        row = cursor.fetchone()
        if not row:
            return None
        cursor.execute("SELECT COUNT(*) FROM novaself_gift_code_uses WHERE code = %s", (code,))
        uses = cursor.fetchone()[0]
        result = dict(row)
        result["uses_count"] = uses
        return result
    except Exception as e:
        logging.error(f"❌ خطا در دریافت جزئیات کد هدیه {code}: {e}")
        return None
    finally:
        if conn:
            conn.close()

def update_gift_code_amount_db(code, new_diamonds):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE novaself_gift_codes SET diamonds = %s WHERE code = %s", (new_diamonds, code))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"❌ خطا در تغییر مقدار الماس کد هدیه {code}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def update_gift_code_expiry_db(code, new_expires_at):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE novaself_gift_codes SET expires_at = %s WHERE code = %s", (new_expires_at, code))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"❌ خطا در تغییر انقضای کد هدیه {code}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def delete_gift_code_db(code):
    """حذف کامل کد هدیه (و رکوردهای استفاده‌ی مرتبط با آن، به‌واسطه‌ی CASCADE)."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM novaself_gift_codes WHERE code = %s", (code,))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"❌ خطا در حذف کد هدیه {code}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def admin_adjust_diamonds_db(target_id, amount):
    """
    افزایش/کاهش دستی موجودی الماس توسط ادمین (amount می‌تواند منفی باشد).
    خروجی: (success: bool, new_balance: float یا None)
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT diamonds FROM novaself_users WHERE user_id = %s FOR UPDATE", (target_id,))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return False, None

        current = float(row[0] or 0)
        new_balance = max(current + float(amount), 0.0)

        cursor.execute("UPDATE novaself_users SET diamonds = %s WHERE user_id = %s", (new_balance, target_id))
        conn.commit()
        return True, new_balance
    except Exception as e:
        logging.error(f"❌ خطا در تغییر موجودی الماس کاربر {target_id}: {e}")
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return False, None
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass

def admin_set_referral_db(target_id, new_count):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE novaself_users SET referral_count = %s WHERE user_id = %s RETURNING referral_count",
            (max(int(new_count), 0), target_id)
        )
        row = cursor.fetchone()
        conn.commit()
        return (row is not None), (row[0] if row else None)
    except Exception as e:
        logging.error(f"❌ خطا در تغییر تعداد رفرال کاربر {target_id}: {e}")
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return False, None
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass

def get_live_balance_db(user_id):
    """خواندن لحظه‌ای موجودی از دیتابیس (برای صفحه حساب کاربری)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT diamonds, referral_count, username FROM novaself_users WHERE user_id = %s",
            (user_id,)
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if not row:
            return None
        return {
            "diamonds": float(row[0] or 0),
            "referral_count": row[1] or 0,
            "username": row[2]
        }
    except Exception as e:
        logging.error(f"❌ خطا در خواندن موجودی لحظه‌ای کاربر {user_id}: {e}")
        return None

def _generate_unique_code(length=8, alphabet=string.ascii_uppercase + string.digits):
    return "".join(secrets.choice(alphabet) for _ in range(length))

# ======================== سفارش‌های خرید الماس ========================
def create_order_db(user_id, username, amount_diamonds, amount_toman, payment_method="card_to_card"):
    """
    ساخت یک سفارش جدید با Order ID یکتا. تلاش می‌شود تا در صورت برخورد نادر با
    یک کد تکراری، دوباره یک کد جدید تولید و امتحان شود.
    خروجی: order_id در صورت موفقیت، یا None در صورت خطا.
    """
    conn = None
    for _ in range(5):
        order_id = _generate_unique_code(8)
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO novaself_orders "
                "(order_id, user_id, username, amount_diamonds, amount_toman, payment_method, status) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'invoice')",
                (order_id, user_id, username, amount_diamonds, amount_toman, payment_method)
            )
            conn.commit()
            return order_id
        except psycopg2.errors.UniqueViolation:
            if conn:
                conn.rollback()
            continue
        except Exception as e:
            logging.error(f"❌ خطا در ساخت سفارش برای کاربر {user_id}: {e}")
            if conn:
                conn.rollback()
            return None
        finally:
            if conn:
                conn.close()
                conn = None
    return None

def get_order_db(order_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute("SELECT * FROM novaself_orders WHERE order_id = %s", (order_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    except Exception as e:
        logging.error(f"❌ خطا در خواندن سفارش {order_id}: {e}")
        return None
    finally:
        if conn:
            conn.close()

def set_order_receipt_db(order_id, chat_id, message_id, file_id):
    """
    ثبت رسید و انتقال اتمیک سفارش از وضعیت 'invoice' به 'pending_review'.
    اگر سفارش از قبل در همین وضعیت نباشد (مثلاً قبلاً رسید ارسال شده)، عملیات رد می‌شود
    تا از ارسال چند رسید برای یک سفارش جلوگیری شود.
    خروجی: (success, order_dict یا None)
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute("SELECT * FROM novaself_orders WHERE order_id = %s FOR UPDATE", (order_id,))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return False, None
        if row["status"] != "invoice":
            conn.rollback()
            return False, dict(row)

        cursor.execute(
            "UPDATE novaself_orders SET status = 'pending_review', receipt_chat_id = %s, "
            "receipt_message_id = %s, receipt_file_id = %s, updated_at = %s WHERE order_id = %s",
            (chat_id, message_id, file_id, tehran_now(), order_id)
        )
        conn.commit()
        row = dict(row)
        row["status"] = "pending_review"
        return True, row
    except Exception as e:
        logging.error(f"❌ خطا در ثبت رسید سفارش {order_id}: {e}")
        if conn:
            conn.rollback()
        return False, None
    finally:
        if conn:
            conn.close()

def approve_order_db(order_id, admin_id):
    """
    تأیید اتمیک سفارش: فقط اگر سفارش دقیقاً در وضعیت 'pending_review' باشد پردازش می‌شود
    (با قفل ردیف سفارش)، سپس موجودی کاربر با قفل جداگانه افزایش می‌یابد. اگر دو ادمین
    همزمان تأیید کنند، دومی روی همین SELECT...FOR UPDATE بلاک شده و بعد از Commit اولی،
    وضعیت را 'approved' می‌بیند و خروجی already_processed برمی‌گرداند.
    خروجی: (success, status_code, order_dict)
    status_code یکی از: 'ok', 'not_found', 'already_processed'
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute("SELECT * FROM novaself_orders WHERE order_id = %s FOR UPDATE", (order_id,))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return False, "not_found", None
        if row["status"] != "pending_review":
            conn.rollback()
            return False, "already_processed", dict(row)

        user_id = row["user_id"]
        cursor.execute("SELECT diamonds FROM novaself_users WHERE user_id = %s FOR UPDATE", (user_id,))
        user_row = cursor.fetchone()
        if not user_row:
            conn.rollback()
            return False, "user_not_found", dict(row)

        new_balance = float(user_row["diamonds"] or 0) + float(row["amount_diamonds"])
        now = tehran_now()
        cursor.execute("UPDATE novaself_users SET diamonds = %s WHERE user_id = %s", (new_balance, user_id))
        cursor.execute(
            "UPDATE novaself_orders SET status = 'approved', approved_at = %s, approved_by = %s, "
            "updated_at = %s WHERE order_id = %s",
            (now, admin_id, now, order_id)
        )
        conn.commit()

        result = dict(row)
        result["status"] = "approved"
        result["approved_at"] = now
        result["approved_by"] = admin_id
        result["_new_balance"] = new_balance
        return True, "ok", result
    except Exception as e:
        logging.error(f"❌ خطا در تأیید سفارش {order_id}: {e}")
        if conn:
            conn.rollback()
        return False, "error", None
    finally:
        if conn:
            conn.close()

def reject_order_db(order_id, admin_id, reason):
    """رد اتمیک سفارش؛ فقط اگر هنوز در وضعیت 'pending_review' باشد (مشابه approve_order_db)."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute("SELECT * FROM novaself_orders WHERE order_id = %s FOR UPDATE", (order_id,))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return False, "not_found", None
        if row["status"] != "pending_review":
            conn.rollback()
            return False, "already_processed", dict(row)

        now = tehran_now()
        cursor.execute(
            "UPDATE novaself_orders SET status = 'rejected', rejected_at = %s, rejected_by = %s, "
            "rejection_reason = %s, updated_at = %s WHERE order_id = %s",
            (now, admin_id, reason, now, order_id)
        )
        conn.commit()
        result = dict(row)
        result["status"] = "rejected"
        result["rejection_reason"] = reason
        return True, "ok", result
    except Exception as e:
        logging.error(f"❌ خطا در رد سفارش {order_id}: {e}")
        if conn:
            conn.rollback()
        return False, "error", None
    finally:
        if conn:
            conn.close()

# ======================== لاگ پیام‌های ادمین (تکی/همگانی) ========================
def create_broadcast_record_db(admin_id, kind, target_id, summary):
    conn = None
    for _ in range(5):
        broadcast_id = _generate_unique_code(10)
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO novaself_broadcasts (broadcast_id, admin_id, kind, target_id, summary) "
                "VALUES (%s, %s, %s, %s, %s)",
                (broadcast_id, admin_id, kind, target_id, (summary or "")[:200])
            )
            conn.commit()
            return broadcast_id
        except psycopg2.errors.UniqueViolation:
            if conn:
                conn.rollback()
            continue
        except Exception as e:
            logging.error(f"❌ خطا در ثبت رکورد پیام ادمین: {e}")
            if conn:
                conn.rollback()
            return None
        finally:
            if conn:
                conn.close()
                conn = None
    return None

def add_broadcast_delivery_db(broadcast_id, user_id, chat_id, message_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO novaself_broadcast_deliveries (broadcast_id, user_id, chat_id, message_id) "
            "VALUES (%s, %s, %s, %s)",
            (broadcast_id, user_id, chat_id, message_id)
        )
        conn.commit()
    except Exception as e:
        logging.error(f"❌ خطا در ثبت رسید ارسال پیام ({broadcast_id}): {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

def list_broadcasts_db(limit=15):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute(
            "SELECT broadcast_id, admin_id, kind, target_id, summary, created_at "
            "FROM novaself_broadcasts ORDER BY created_at DESC LIMIT %s", (limit,)
        )
        return cursor.fetchall()
    except Exception as e:
        logging.error(f"❌ خطا در دریافت لیست پیام‌های ارسالی: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_broadcast_deliveries_db(broadcast_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute(
            "SELECT user_id, chat_id, message_id FROM novaself_broadcast_deliveries WHERE broadcast_id = %s",
            (broadcast_id,)
        )
        return cursor.fetchall()
    except Exception as e:
        logging.error(f"❌ خطا در دریافت رسیدهای پیام {broadcast_id}: {e}")
        return []
    finally:
        if conn:
            conn.close()

def delete_broadcast_record_db(broadcast_id):
    """حذف رکورد پیام و همه‌ی رسیدهای مرتبط (CASCADE) بعد از حذف پیام‌ها از چت کاربران."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM novaself_broadcasts WHERE broadcast_id = %s", (broadcast_id,))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"❌ خطا در حذف رکورد پیام {broadcast_id}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

# ======================== قابلیت ریکت (ذخیره‌سازی) ========================
def get_user_reactions_db(owner_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute(
            "SELECT target_user_id, target_username, emoji FROM novaself_reactions WHERE owner_id = %s ORDER BY created_at",
            (owner_id,)
        )
        return cursor.fetchall()
    except Exception as e:
        logging.error(f"❌ خطا در خواندن لیست ریکت کاربر {owner_id}: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_all_reactions_db():
    """برای بارگذاری کش تمام کاربران در استارتاپ."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute("SELECT owner_id, target_user_id, target_username, emoji FROM novaself_reactions")
        return cursor.fetchall()
    except Exception as e:
        logging.error(f"❌ خطا در بارگذاری اولیه‌ی ریکت‌ها: {e}")
        return []
    finally:
        if conn:
            conn.close()

def set_user_reaction_db(owner_id, target_user_id, target_username, emoji):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO novaself_reactions (owner_id, target_user_id, target_username, emoji)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (owner_id, target_user_id) DO UPDATE SET
                target_username = EXCLUDED.target_username,
                emoji = EXCLUDED.emoji
        ''', (owner_id, target_user_id, target_username, emoji))
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"❌ خطا در ذخیره ریکت (owner={owner_id} target={target_user_id}): {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def remove_user_reaction_db(owner_id, target_user_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM novaself_reactions WHERE owner_id = %s AND target_user_id = %s",
            (owner_id, target_user_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"❌ خطا در حذف ریکت (owner={owner_id} target={target_user_id}): {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def load_reactions_cache():
    """بارگذاری کش ریکت‌ها در استارتاپ (بند «Restart نباید تنظیمات را از بین ببرد»)."""
    global reaction_targets
    fresh = {}
    for row in get_all_reactions_db():
        fresh.setdefault(row["owner_id"], {})[row["target_user_id"]] = {
            "emoji": row["emoji"], "username": row["target_username"]
        }
    reaction_targets = fresh
    logging.info(f"👍 کش ریکت بارگذاری شد: {sum(len(v) for v in fresh.values())} کاربر هدف در {len(fresh)} حساب.")

# ======================== قابلیت پاسخ خودکار (ذخیره‌سازی) ========================
def add_autoreply_db(owner_id, trigger_text, response_text, entities, media_kind, media_bytes, media_filename, media_mime):
    """
    یک پاسخ خودکار جدید ذخیره می‌کند و شماره‌ی نمایشیِ بعدیِ (local_id) مخصوصِ همان
    کاربر را برمی‌گرداند (۱، ۲، ۳ ...). Entityهای Formatting با pickle سریالایز
    می‌شوند چون این‌ها اشیاء TL تلگرام هستند نه دیتای ساده — pickle این‌جا امن است
    چون فقط توسط خودِ سرور نوشته و خوانده می‌شود (نه ورودی خارجی/غیرقابل‌اعتماد).
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COALESCE(MAX(local_id), 0) + 1 FROM novaself_autoreplies WHERE owner_id = %s", (owner_id,))
        local_id = cursor.fetchone()[0]

        entities_blob = psycopg2.Binary(pickle.dumps(entities)) if entities else None
        media_blob = psycopg2.Binary(media_bytes) if media_bytes else None

        cursor.execute('''
            INSERT INTO novaself_autoreplies
                (owner_id, local_id, trigger_text, response_text, response_entities,
                 response_media_kind, response_media_bytes, response_media_filename, response_media_mime)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (owner_id, local_id, trigger_text, response_text, entities_blob,
              media_kind, media_blob, media_filename, media_mime))
        conn.commit()
        return local_id
    except Exception as e:
        logging.error(f"❌ خطا در ذخیره پاسخ خودکار برای کاربر {owner_id}: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            conn.close()

def delete_autoreply_db(owner_id, local_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM novaself_autoreplies WHERE owner_id = %s AND local_id = %s",
            (owner_id, local_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"❌ خطا در حذف پاسخ خودکار (owner={owner_id} local_id={local_id}): {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def get_all_autoreplies_db():
    """برای بارگذاری کش تمام کاربران در استارتاپ."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute("SELECT * FROM novaself_autoreplies ORDER BY owner_id, local_id")
        return cursor.fetchall()
    except Exception as e:
        logging.error(f"❌ خطا در بارگذاری اولیه‌ی پاسخ‌های خودکار: {e}")
        return []
    finally:
        if conn:
            conn.close()

def load_autoreplies_cache():
    """بارگذاری کش پاسخ‌های خودکار در استارتاپ، شامل Unpickle کردن Entityها."""
    global autoreply_cache
    fresh = {}
    for row in get_all_autoreplies_db():
        entities = None
        if row["response_entities"]:
            try:
                entities = pickle.loads(bytes(row["response_entities"]))
            except Exception as e:
                log_internal_error("unpickle_autoreply_entities", f"owner={row['owner_id']} local_id={row['local_id']} err={e}")
        media_bytes = bytes(row["response_media_bytes"]) if row["response_media_bytes"] else None
        fresh.setdefault(row["owner_id"], []).append({
            "local_id": row["local_id"],
            "trigger_text": row["trigger_text"],
            "response_text": row["response_text"],
            "entities": entities,
            "media_kind": row["response_media_kind"],
            "media_bytes": media_bytes,
            "media_filename": row["response_media_filename"],
            "media_mime": row["response_media_mime"],
        })
    autoreply_cache = fresh
    logging.info(f"🤖 کش پاسخ خودکار بارگذاری شد: {sum(len(v) for v in fresh.values())} پاسخ در {len(fresh)} حساب.")

# ======================== قفل کردن قابلیت‌ها توسط ادمین ========================
FEATURE_LOCK_DEFS = [
    ("time", "⌚ ساعت"),
    ("date", "📅 تاریخ"),
    ("actions", "🎭 اکشن"),
    ("textmode", "🖊️ حالت متن"),
    ("secretary", "🧑‍💼 منشی پیوی"),
    ("tag", "🏷️ تگ"),
    ("meow", "🐱 میو"),
    ("fish", "🐟 ماهی"),
    ("meowpoint", "🪙 میو پوینت"),
    ("streetcat", "🐈 نجات پیشی"),
    ("fridge", "❄️ یخچال میویی"),
    ("ping", "🏓 پینگ"),
    ("whois", "🪪 اطلاعات"),
    ("reaction", "👍 ریکت"),
    ("autoreply", "🤖 پاسخ خودکار"),
]
FEATURE_LOCK_LABELS = dict(FEATURE_LOCK_DEFS)

def get_all_feature_locks_db():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, feature_key FROM novaself_feature_locks")
        return cursor.fetchall()
    except Exception as e:
        logging.error(f"❌ خطا در بارگذاری اولیه‌ی قفل قابلیت‌ها: {e}")
        return []
    finally:
        if conn:
            conn.close()

def load_feature_locks_cache():
    """بارگذاری کش قفل‌ها در استارتاپ (تا Restart تنظیمات قفل را از بین نبرد)."""
    global feature_locks
    fresh = {}
    for owner_id, feature_key in get_all_feature_locks_db():
        fresh.setdefault(owner_id, set()).add(feature_key)
    feature_locks = fresh
    logging.info(f"🔒 کش قفل قابلیت‌ها بارگذاری شد: {sum(len(v) for v in fresh.values())} قفل روی {len(fresh)} کاربر.")

def lock_feature_db(user_id, feature_key):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO novaself_feature_locks (user_id, feature_key)
            VALUES (%s, %s)
            ON CONFLICT (user_id, feature_key) DO NOTHING
        ''', (user_id, feature_key))
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"❌ خطا در قفل کردن قابلیت {feature_key} برای {user_id}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def unlock_feature_db(user_id, feature_key):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM novaself_feature_locks WHERE user_id = %s AND feature_key = %s",
            (user_id, feature_key)
        )
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"❌ خطا در باز کردن قفل {feature_key} برای {user_id}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def is_feature_locked(user_id, feature_key):
    return feature_key in feature_locks.get(user_id, set()) or feature_key in global_feature_locks

def is_feature_globally_locked(feature_key):
    return feature_key in global_feature_locks

def get_all_global_locks_db():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT feature_key FROM novaself_global_locks")
        return [r[0] for r in cursor.fetchall()]
    except Exception as e:
        logging.error(f"❌ خطا در بارگذاری قفل‌های سراسری: {e}")
        return []
    finally:
        if conn:
            conn.close()

def load_global_locks_cache():
    global global_feature_locks
    global_feature_locks = set(get_all_global_locks_db())
    logging.info(f"🌐 کش قفل سراسری بارگذاری شد: {len(global_feature_locks)} قابلیت قفل‌شده برای همه.")

def lock_feature_globally_db(feature_key):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO novaself_global_locks (feature_key) VALUES (%s) ON CONFLICT (feature_key) DO NOTHING",
            (feature_key,)
        )
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"❌ خطا در قفل سراسری {feature_key}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def unlock_feature_globally_db(feature_key):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM novaself_global_locks WHERE feature_key = %s", (feature_key,))
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"❌ خطا در باز کردن قفل سراسری {feature_key}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

# ======================== جوین اجباری ========================
def create_join_channel_db(title, identifier, invite_link):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO novaself_join_channels (title, identifier, invite_link) VALUES (%s, %s, %s) RETURNING id",
            (title, identifier, invite_link)
        )
        new_id = cursor.fetchone()[0]
        conn.commit()
        return new_id
    except Exception as e:
        logging.error(f"❌ خطا در افزودن کانال جوین اجباری: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            conn.close()

def list_join_channels_db(active_only=False):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        if active_only:
            cursor.execute("SELECT * FROM novaself_join_channels WHERE is_active = TRUE ORDER BY id")
        else:
            cursor.execute("SELECT * FROM novaself_join_channels ORDER BY id")
        return cursor.fetchall()
    except Exception as e:
        logging.error(f"❌ خطا در خواندن لیست کانال‌های جوین اجباری: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_join_channel_db(channel_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute("SELECT * FROM novaself_join_channels WHERE id = %s", (channel_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    except Exception as e:
        logging.error(f"❌ خطا در خواندن کانال جوین اجباری {channel_id}: {e}")
        return None
    finally:
        if conn:
            conn.close()

def update_join_channel_link_db(channel_id, new_link):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE novaself_join_channels SET invite_link = %s WHERE id = %s", (new_link, channel_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"❌ خطا در تغییر لینک کانال {channel_id}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def set_join_channel_active_db(channel_id, active):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE novaself_join_channels SET is_active = %s WHERE id = %s", (active, channel_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"❌ خطا در تغییر وضعیت کانال {channel_id}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def delete_join_channel_db(channel_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM novaself_join_channels WHERE id = %s", (channel_id,))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"❌ خطا در حذف کانال {channel_id}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def mark_user_verified_db(user_id, channels_snapshot, verified_at=None):
    """
    برخلاف نسخه‌ی قبلی (INSERT ... DO NOTHING که فقط یک‌بار برای همیشه ثبت می‌کرد و
    دیگر هیچ‌وقت آپدیت نمی‌شد)، این نسخه هر بار که کاربر با موفقیت دوباره تأیید
    می‌شود، هم verified_at و هم channels_snapshot (عکسِ لحظه‌ایِ کانال‌های فعال در
    زمان تأیید) را آپدیت می‌کند. این snapshot دقیقاً همان چیزی است که در حافظه هم
    نگه‌داری می‌شود تا بعد از هر ری‌استارت، وضعیت «باید دوباره چک شود یا نه» درست
    از دیتابیس بازسازی شود.
    """
    verified_at = verified_at or tehran_now()
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO novaself_join_verified (user_id, verified_at, channels_snapshot)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                verified_at = EXCLUDED.verified_at,
                channels_snapshot = EXCLUDED.channels_snapshot
        ''', (user_id, verified_at, channels_snapshot))
        conn.commit()
    except Exception as e:
        logging.error(f"❌ خطا در ثبت تأیید عضویت کاربر {user_id}: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

def clear_user_verified_db(user_id):
    """پاک‌کردن رکورد تأیید یک کاربر (مثلاً اگر ادمین بخواهد کاربری را دستی مجبور به جوین مجدد کند)."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM novaself_join_verified WHERE user_id = %s", (user_id,))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"❌ خطا در حذف تأیید عضویت کاربر {user_id}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def get_all_verified_users_db():
    """
    خروجی: دیکشنری {user_id: {"verified_at": datetime, "snapshot": str}}
    (قبلاً فقط لیست ساده‌ی آیدی‌ها برمی‌گشت که امکان تشخیص «قدیمی/منقضی‌شده» را نمی‌داد.)
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, verified_at, channels_snapshot FROM novaself_join_verified")
        result = {}
        for row in cursor.fetchall():
            result[row[0]] = {"verified_at": row[1], "snapshot": row[2] or ""}
        return result
    except Exception as e:
        logging.error(f"❌ خطا در بارگذاری کاربران تأییدشده: {e}")
        return {}
    finally:
        if conn:
            conn.close()

def get_verified_count_db():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM novaself_join_verified")
        return cursor.fetchone()[0]
    except Exception as e:
        logging.error(f"❌ خطا در شمارش کاربران تأییدشده: {e}")
        return 0
    finally:
        if conn:
            conn.close()

# ======================== سیستم بکاپ ========================
# لیست تمام جداول قابل بکاپ به‌همراه (کلید اصلی، ستون‌های محافظت‌شده که هنگام
# بازیابی هرگز رونویسی نمی‌شوند). محافظت از session کاربران طبق تأکید صریح
# درخواست («بازیابی بکاپ نباید باعث حذف Session کاربران شود») است.
BACKUP_TABLE_PKS = {
    "novaself_users": (["user_id"], ["session"]),
    "novaself_gift_codes": (["code"], []),
    "novaself_gift_code_uses": (["code", "user_id"], []),
    "novaself_orders": (["order_id"], []),
    "novaself_broadcasts": (["broadcast_id"], []),
    "novaself_broadcast_deliveries": (["id"], []),
    "novaself_reactions": (["owner_id", "target_user_id"], []),
    "novaself_autoreplies": (["id"], []),
    "novaself_feature_locks": (["user_id", "feature_key"], []),
    "novaself_global_locks": (["feature_key"], []),
    "novaself_join_channels": (["id"], []),
    "novaself_join_verified": (["user_id"], []),
    "novaself_admin_logs": (["id"], []),
}

def _backup_row_to_jsonable(row_dict):
    """تبدیل یک ردیف دیتابیس (شامل bytes/datetime) به دیکشنری قابل JSON."""
    out = {}
    for k, v in row_dict.items():
        if isinstance(v, (bytes, memoryview)):
            out[k] = {"__bytes__": base64.b64encode(bytes(v)).decode("ascii")}
        elif isinstance(v, datetime):
            out[k] = {"__datetime__": v.isoformat()}
        else:
            out[k] = v
    return out

def _backup_jsonable_to_row(row_dict):
    """معکوس _backup_row_to_jsonable برای بازیابی."""
    out = {}
    for k, v in row_dict.items():
        if isinstance(v, dict) and "__bytes__" in v:
            out[k] = base64.b64decode(v["__bytes__"])
        elif isinstance(v, dict) and "__datetime__" in v:
            out[k] = datetime.fromisoformat(v["__datetime__"])
        else:
            out[k] = v
    return out

def build_backup_payload():
    """
    دامپ کامل تمام جداول پروژه به یک دیکشنری JSON-پذیر.
    خروجی: (payload_dict, error یا None)
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        dump = {
            "meta": {
                "created_at": tehran_now().isoformat(),
                "version": 1,
                "tables": list(BACKUP_TABLE_PKS.keys()),
            }
        }
        for table in BACKUP_TABLE_PKS:
            try:
                cursor.execute(f"SELECT * FROM {table}")
                rows = cursor.fetchall()
                dump[table] = [_backup_row_to_jsonable(dict(r)) for r in rows]
            except Exception as e:
                logging.error(f"⚠️ خطا در دامپ جدول {table}: {e}")
                dump[table] = []
        return dump, None
    except Exception as e:
        logging.error(f"❌ خطا در ساخت بکاپ: {e}")
        return None, str(e)
    finally:
        if conn:
            conn.close()

def create_backup_db(admin_id, label=None):
    """
    یک بکاپ کامل می‌سازد و مستقیماً داخل خودِ دیتابیس (جدول novaself_backups)
    ذخیره می‌کند — این‌طوری بکاپ‌ها مستقل از فایل‌سیستم موقتِ Railway باقی می‌مانند.
    خروجی: (backup_id, size_bytes) یا (None, 0) در صورت خطا.
    """
    dump, error = build_backup_payload()
    if dump is None:
        return None, 0

    payload_bytes = json.dumps(dump, ensure_ascii=False).encode("utf-8")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO novaself_backups (created_by, label, size_bytes, data) VALUES (%s, %s, %s, %s) RETURNING id",
            (admin_id, label, len(payload_bytes), psycopg2.Binary(payload_bytes))
        )
        new_id = cursor.fetchone()[0]
        conn.commit()
        return new_id, len(payload_bytes)
    except Exception as e:
        logging.error(f"❌ خطا در ذخیره بکاپ: {e}")
        if conn:
            conn.rollback()
        return None, 0
    finally:
        if conn:
            conn.close()

def list_backups_db():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute(
            "SELECT id, created_by, label, size_bytes, created_at FROM novaself_backups ORDER BY created_at DESC"
        )
        return cursor.fetchall()
    except Exception as e:
        logging.error(f"❌ خطا در دریافت لیست بکاپ‌ها: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_backup_data_db(backup_id):
    """محتوای کامل یک بکاپ (بایت خام JSON) را برمی‌گرداند، یا None."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT data FROM novaself_backups WHERE id = %s", (backup_id,))
        row = cursor.fetchone()
        return bytes(row[0]) if row else None
    except Exception as e:
        logging.error(f"❌ خطا در خواندن بکاپ {backup_id}: {e}")
        return None
    finally:
        if conn:
            conn.close()

def delete_backup_db(backup_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM novaself_backups WHERE id = %s", (backup_id,))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"❌ خطا در حذف بکاپ {backup_id}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def restore_backup_payload(dump):
    """
    بازیابیِ یک دامپِ JSON روی دیتابیس فعلی. برای هر جدول از INSERT ... ON CONFLICT
    DO UPDATE استفاده می‌شود (نه TRUNCATE/DELETE) — یعنی هیچ رکورد کاربر یا دیتای
    دیگری هرگز حذف نمی‌شود، فقط رونویسی/افزوده می‌شود. ستون‌های محافظت‌شده (مثل
    session کاربران) هرگز در SET قرار نمی‌گیرند، پس مقدار زنده‌ی فعلی‌شان دست‌نخورده
    باقی می‌ماند؛ برای کاربرِ کاملاً جدید (که در DB فعلی وجود ندارد) session از
    خودِ بکاپ درج می‌شود چون در آن حالت چیزی برای «شکستن» وجود ندارد.
    خروجی: (success: bool, summary: dict جدول->تعداد ردیف بازیابی‌شده, error یا None)
    """
    conn = None
    summary = {}
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        for table, (pk_cols, protect_cols) in BACKUP_TABLE_PKS.items():
            rows = dump.get(table) or []
            restored = 0
            for raw_row in rows:
                row = _backup_jsonable_to_row(raw_row)
                cols = list(row.keys())
                if not cols or not all(pk in cols for pk in pk_cols):
                    continue

                placeholders = ", ".join(["%s"] * len(cols))
                col_list = ", ".join(cols)
                update_cols = [c for c in cols if c not in pk_cols and c not in protect_cols]

                if update_cols:
                    set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
                    conflict_clause = f"ON CONFLICT ({', '.join(pk_cols)}) DO UPDATE SET {set_clause}"
                else:
                    conflict_clause = f"ON CONFLICT ({', '.join(pk_cols)}) DO NOTHING"

                sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) {conflict_clause}"
                try:
                    cursor.execute(sql, [row[c] for c in cols])
                    restored += 1
                except Exception as e:
                    logging.error(f"⚠️ خطا در بازیابی یک ردیف از {table}: {e}")

            summary[table] = restored

        conn.commit()
        return True, summary, None
    except Exception as e:
        logging.error(f"❌ خطا در بازیابی بکاپ: {e}")
        if conn:
            conn.rollback()
        return False, summary, str(e)
    finally:
        if conn:
            conn.close()

def reload_join_channels_cache():
    """کش کانال‌های فعال را از دیتابیس تازه می‌کند (بعد از هر افزودن/حذف/ویرایش ادمین)."""
    global join_channels_cache
    join_channels_cache = list(list_join_channels_db(active_only=True))

def load_join_gate_cache():
    """بارگذاری اولیه‌ی کش‌های جوین اجباری در استارتاپ."""
    global verified_users
    reload_join_channels_cache()
    verified_users = get_all_verified_users_db()
    logging.info(f"🔐 جوین اجباری: {len(join_channels_cache)} کانال فعال، {len(verified_users)} کاربر تأییدشده.")

def _join_channels_snapshot():
    """
    یک رشته‌ی کوتاه و پایدار که «هویتِ» ست فعلیِ کانال‌های فعال را نشان می‌دهد
    (آیدی‌های کانال‌های فعال، مرتب‌شده). هر بار که ادمین کانالی اضافه/حذف/غیرفعال
    کند، این رشته عوض می‌شود؛ همین تغییر است که باعث می‌شود کاربرانی که قبلاً با
    ست قدیمیِ کانال‌ها تأیید شده بودند، دوباره وارد مسیر بررسی شوند.
    """
    return ",".join(str(ch["id"]) for ch in sorted(join_channels_cache, key=lambda c: c["id"]))

def needs_join_check(user_id):
    """
    تصمیم می‌گیرد که آیا باید عضویت این کاربر را دوباره واقعاً از تلگرام استعلام
    کنیم یا تأییدِ قبلی‌اش هنوز معتبر است. این تابع سبک است (فقط یک lookup روی
    دیکشنری در حافظه)، پس صدا زدنش در هر تعامل (نه فقط /start) هزینه‌ی محسوسی ندارد؛
    تماسِ واقعی و نسبتاً سنگین با API تلگرام (check_user_joined_all) فقط وقتی این
    تابع True برگرداند اجرا می‌شود.
    """
    if not join_channels_cache or is_admin(user_id):
        return False

    record = verified_users.get(user_id)
    if not record:
        return True

    # کانال‌های اجباری از آخرین تأیید این کاربر تغییر کرده‌اند (کانال جدید اضافه/
    # حذف/غیرفعال شده) — باید دوباره برای ستِ جدید چک شود.
    if record.get("snapshot") != _join_channels_snapshot():
        return True

    # تأیید قدیمی منقضی شده — دوباره چک می‌کنیم تا کسانی که کانال را ترک کرده‌اند
    # برای همیشه معاف نمانند.
    verified_at = record.get("verified_at")
    if not verified_at:
        return True
    age_seconds = (tehran_now() - verified_at).total_seconds()
    return age_seconds > JOIN_GATE_RECHECK_SECONDS

def _mark_user_verified(user_id):
    """کاربر را هم در حافظه و هم در دیتابیس، همراه با عکسِ لحظه‌ایِ کانال‌های فعال، تأییدشده ثبت می‌کند."""
    snapshot = _join_channels_snapshot()
    now = tehran_now()
    verified_users[user_id] = {"verified_at": now, "snapshot": snapshot}
    mark_user_verified_db(user_id, snapshot, now)

async def check_user_joined_all(user_id):
    """
    بررسی عضویت کاربر در تمام کانال‌های فعالِ جوین اجباری با کلاینت بات.

    فقط UserNotParticipantError به معنای واقعیِ «کاربر عضو نیست» است. هر خطای
    دیگر (مثلاً ChatAdminRequiredError چون بات در آن کانال ادمین نیست) یعنی ما
    اصلاً نمی‌توانیم عضویت را تأیید کنیم — و طبق منطق درست برای یک قابلیت
    امنیتی/محدودکننده، این حالت هم باید Fail-Closed باشد (یعنی کاربر را عضو در
    نظر نگیریم)، نه Fail-Open که کل جوین اجباری را بی‌اثر می‌کرد.

    نکته‌ی مهم (خودترمیمی بعد از هر ری‌دیپلوی روی Railway): چون bot با یک سشنِ
    فایلیِ SQLite بالا می‌آید (`TelegramClient('helper_bot', ...)`) و روی Railway
    فایل‌سیستم معمولاً پایدار/دائمی نیست، بعد از هر ری‌دیپلوی/ری‌استارت این کش
    entity به‌طور کامل از بین می‌رود؛ یعنی تلاش اول (با شناسه‌ی عددی خامِ ذخیره‌شده)
    ممکن است شکست بخورد، حتی اگر بات هنوز واقعاً عضو/ادمین همان کانال باشد. اگر
    فقط به همین تلاش اول بسنده می‌کردیم، جوین اجباری بعد از هر ری‌دیپلوی از کار
    می‌افتاد تا ادمین دستی دوباره کانال را اضافه کند. برای همین، اگر تلاش اول با
    شناسه‌ی خام شکست بخورد (و علتش «کاربر عضو نیست» نباشد)، یک‌بار دیگر از روی
    همان لینک دعوتیِ ذخیره‌شده (با _resolve_channel_from_link، دقیقاً همان تابعی
    که هنگام افزودن کانال استفاده می‌شود) entity را تازه resolve کرده و دوباره
    امتحان می‌کنیم — بدون نیاز به هیچ دخالت دستی.

    خروجی: (all_joined: bool, missing_channels: list[dict])
    """
    missing = []
    for ch in join_channels_cache:
        identifier = ch["identifier"]
        try:
            identifier = int(identifier)
        except (ValueError, TypeError):
            pass

        try:
            perms = await bot.get_permissions(identifier, user_id)
            if not perms or not perms.is_member:
                missing.append(ch)
            continue
        except UserNotParticipantError:
            missing.append(ch)
            continue
        except Exception:
            pass  # می‌رویم سراغ تلاش دوم (resolve تازه از روی لینک) پایین

        resolved_entity, resolve_err = await _resolve_channel_from_link(ch.get("invite_link", ""))
        if resolved_entity is None:
            bot_mention = f"@{BOT_USERNAME}" if BOT_USERNAME else "ربات"
            logging.error(
                f"⚠️ جوین اجباری: {bot_mention} به کانال «{ch['title']}» (شناسه: {ch['identifier']}) دسترسی کافی "
                f"ندارد یا در آن عضو/ادمین نیست ({resolve_err}). این کانال به‌عنوان «عضو نشده» در نظر گرفته می‌شود "
                f"تا قابلیت جوین اجباری بی‌اثر نشود — لطفاً از پنل ادمین بررسی کنید که خودِ {bot_mention} "
                "(نه اکانت سلف کاربران) در این کانال عضو/ادمین باشد."
            )
            missing.append(ch)
            continue

        try:
            perms = await bot.get_permissions(resolved_entity, user_id)
            if not perms or not perms.is_member:
                missing.append(ch)
        except UserNotParticipantError:
            missing.append(ch)
        except Exception as e:
            log_internal_error("check_joined", f"channel_id={ch.get('id')} identifier={identifier} err={e}")
            missing.append(ch)
    return (len(missing) == 0), missing

async def _resolve_channel_from_link(link):
    """
    مطمئن‌ترین راهِ resolve کردنِ یک کانال برای اکانت بات، بدون هیچ وابستگی به
    کش/سشن قبلی، دیالوگ‌ها، یا فوروارد پیام:

    - اگر لینک عمومی باشد (t.me/username): مستقیماً با ResolveUsername حل می‌شود.
      این متد همیشه برای بات کار می‌کند چون نیازی به access_hash از قبل ندارد.

    - اگر لینک دعوتیِ خصوصی باشد (t.me/+HASH یا t.me/joinchat/HASH): با
      CheckChatInviteRequest بررسی می‌شود. طبق مستندات رسمی تلگرام، اگر اکانتِ
      فراخوان (اینجا بات) از قبل واقعاً عضوِ آن چت باشد، تلگرام یک شیء
      ChatInviteAlready برمی‌گرداند که فیلدِ chat آن، entity کامل و معتبر (با
      access_hash درست) است — دقیقاً چیزی که لازم داریم، مستقل از اینکه بات قبلاً
      این کانال را از راه دیگری «دیده» باشد یا نه. این روش جایگزینِ دو تلاش قبلی
      (fwd.chat / fwd.get_chat و جست‌وجو در iter_dialogs) شد، چون آن‌ها یا فقط
      نسخه‌ی ناقص/min برمی‌گرداندند یا اصلاً برای اکانت بات کار نمی‌کردند
      (iter_dialogs یک متدِ مخصوصِ اکانت کاربری است، نه بات).

    خروجی: (entity یا None, پیام‌خطا یا None)
    """
    link = (link or "").strip()
    m = re.match(r'^(?:https?://)?(?:www\.)?t\.me/(.+)$', link, re.IGNORECASE)
    tail = m.group(1) if m else link.lstrip("@")
    tail = tail.split("?")[0].strip("/")

    if not tail:
        return None, "لینک نامعتبر است."

    try:
        if tail.startswith("+"):
            invite_hash = tail[1:]
        elif tail.lower().startswith("joinchat/"):
            invite_hash = tail[len("joinchat/"):]
        else:
            invite_hash = None

        if invite_hash:
            try:
                result = await bot(CheckChatInviteRequest(invite_hash))
            except Exception as e:
                return None, e
            if isinstance(result, ChatInviteAlready):
                return result.chat, None
            return None, (
                "طبق پاسخ تلگرام، ربات هنوز از طریق این لینک عضو این کانال نشده است "
                "(لینک معتبر است، ولی ربات را باید یک ادمین دستی به کانال اضافه کند؛ "
                "بات‌ها معمولاً نمی‌توانند صرفاً با لینک دعوت خودشان عضو شوند)."
            )

        # لینک عمومی: بخشی که بعد از t.me/ آمده، یوزرنیم کانال است.
        username = tail.split("/")[0]
        try:
            entity = await bot.get_entity(username)
            return entity, None
        except Exception as e:
            return None, e
    except Exception as e:
        return None, e

# ======================== رابط کاربری جوین اجباری (سمت کاربر) ========================
JOIN_REQUIRED_TEXT = (
    "برای استفاده‌ی دائمی از امکانات ربات، فقط کافیه یک‌بار در کانال‌های ما عضو بشی!\n\n"
    "✅ بعد از عضویت در کانال، روی دکمه «تایید عضویت» کلیک کن."
)

def get_join_required_keyboard(missing_channels):
    rows = []
    for ch in missing_channels:
        rows.append([Button.url(f"🔔 {ch['title']}", ch["invite_link"])])
    rows.append([styled_button("تایید عضویت ☑️", b"join_verify_check", style=STYLE_ON)])
    return rows

async def _send_join_gate(event, user_id, missing_channels):
    await event.respond(JOIN_REQUIRED_TEXT, buttons=get_join_required_keyboard(missing_channels))

# ======================== مدیریت جوین اجباری در پنل ادمین ========================
def get_joingate_admin_text():
    channels = list_join_channels_db()
    verified_count = get_verified_count_db()
    recheck_hours = JOIN_GATE_RECHECK_SECONDS // 3600
    lines = [
        "🔔 **مدیریت جوین اجباری**\n",
        f"تعداد کانال‌ها: {len(channels)}",
        f"کاربران تأییدشده (حداکثر تا {recheck_hours} ساعت اخیر): {verified_count}\n",
        "ℹ️ عضویت هر کاربر همیشگی نیست: هر چند ساعت یک‌بار و هر بار که کانال‌های این "
        "لیست تغییر کند (افزوده/حذف/غیرفعال شود)، دوباره از تلگرام استعلام می‌شود.\n",
        "برای مدیریت هر کانال روی آن کلیک کنید:"
    ]
    return "\n".join(lines)

def get_joingate_admin_keyboard():
    channels = list_join_channels_db()
    buttons = [[styled_button("➕ افزودن کانال", b"admin_joingate_add", style=STYLE_ON)]]
    for ch in channels:
        state = status_icon(bool(ch["is_active"]))
        buttons.append([styled_button(
            f"{state} {ch['title']}",
            f"admin_joingate_manage_{ch['id']}".encode(),
            style=STYLE_ON if ch["is_active"] else STYLE_OFF
        )])
    buttons.append([styled_button("➜ بازگشت", b"admin_panel", style=STYLE_OFF)])
    return buttons

def get_joingate_manage_text(ch):
    state = "فعال ✓" if ch["is_active"] else "غیرفعال ✕"
    return (
        f"🔔 **مدیریت کانال** «{ch['title']}»\n\n"
        f"شناسه/یوزرنیم: `{ch['identifier']}`\n"
        f"لینک: {ch['invite_link']}\n"
        f"وضعیت: {state}"
    )

def get_joingate_manage_keyboard(ch):
    cid = ch["id"]
    active = bool(ch["is_active"])
    return [
        [styled_button("✏️ تغییر لینک کانال", f"admin_joingate_editlink_{cid}".encode(), style=STYLE_INFO)],
        [styled_button(
            "✕ غیرفعال کردن" if active else "✓ فعال کردن",
            f"admin_joingate_toggle_{cid}".encode(),
            style=STYLE_OFF if active else STYLE_ON
        )],
        [styled_button("🗑 حذف کانال", f"admin_joingate_delete_{cid}".encode(), style=STYLE_OFF)],
        [styled_button("➜ بازگشت", b"admin_joingate", style=STYLE_OFF)]
    ]

def get_joingate_delete_confirm_keyboard(cid):
    return [
        [styled_button("🗑 بله، حذف شود", f"admin_joingate_delete_confirm_{cid}".encode(), style=STYLE_OFF)],
        [styled_button("➜ بازگشت", f"admin_joingate_manage_{cid}".encode(), style=STYLE_OFF)]
    ]

# ======================== رابط کاربری قفل سراسری قابلیت‌ها (پنل ادمین) ========================
def get_globallock_menu_text():
    count = len(global_feature_locks)
    return (
        "🌐 **قفل سراسری قابلیت‌ها**\n\n"
        f"تعداد قابلیت‌های قفل‌شده برای همه‌ی کاربران: {count}\n\n"
        "روی هر قابلیت کلیک کنید تا وضعیت قفل/باز آن برای **همه‌ی کاربران** عوض شود:"
    )

def get_globallock_menu_keyboard():
    buttons = []
    row = []
    for key, label in FEATURE_LOCK_DEFS:
        locked = key in global_feature_locks
        text = f"{label} 🔒" if locked else label
        row.append(styled_button(text, f"admin_globallock_toggle_{key}".encode(), style=STYLE_OFF if locked else STYLE_ON))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([styled_button("➜ بازگشت", b"admin_panel", style=STYLE_OFF)])
    return buttons

# ======================== رابط کاربری سیستم بکاپ (پنل ادمین) ========================
def _format_bytes(n):
    n = n or 0
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n/1024:.1f} KB"
    return f"{n/(1024*1024):.1f} MB"

def get_backup_menu_text():
    backups = list_backups_db()
    total_size = sum(b["size_bytes"] or 0 for b in backups)
    return (
        "💾 **سیستم بکاپ**\n\n"
        f"تعداد بکاپ‌های موجود: {len(backups)}\n"
        f"حجم کل: {_format_bytes(total_size)}\n\n"
        "بکاپ‌ها مستقیماً داخل خودِ دیتابیس ذخیره می‌شوند، اما پیشنهاد می‌شود بعد از "
        "ساخت هر بکاپ، حتماً یک نسخه هم با «دانلود» روی گوشی/کامپیوتر خودتان نگه دارید."
    )

def get_backup_menu_keyboard():
    return [
        [styled_button("➕ ایجاد بکاپ جدید", b"admin_backup_create", style=STYLE_ON)],
        [styled_button("📋 مشاهده بکاپ‌ها", b"admin_backup_list", style=STYLE_INFO)],
        [styled_button("⬆️ بارگذاری و بازیابی بکاپ", b"admin_backup_upload", style=STYLE_INFO)],
        [styled_button("➜ بازگشت", b"admin_panel", style=STYLE_OFF)]
    ]

def get_backup_list_text():
    backups = list_backups_db()
    if not backups:
        return "📋 **لیست بکاپ‌ها**\n\nهنوز هیچ بکاپی ساخته نشده است."
    return "📋 **لیست بکاپ‌ها**\n\nبرای مدیریت هر بکاپ روی آن کلیک کنید:"

def get_backup_list_keyboard():
    backups = list_backups_db()
    buttons = []
    for b in backups:
        ts = b["created_at"].strftime("%Y-%m-%d %H:%M") if b["created_at"] else "؟"
        label = f"💾 {ts} — {_format_bytes(b['size_bytes'])}"
        buttons.append([styled_button(label, f"admin_backup_manage_{b['id']}".encode(), style=STYLE_INFO)])
    buttons.append([styled_button("➜ بازگشت", b"admin_backup", style=STYLE_OFF)])
    return buttons

def get_backup_manage_text(b):
    ts = b["created_at"].strftime("%Y-%m-%d %H:%M") if b["created_at"] else "؟"
    creator = b["created_by"] or "نامشخص"
    return (
        f"💾 **بکاپ شماره {b['id']}**\n\n"
        f"تاریخ ساخت: {ts}\n"
        f"حجم: {_format_bytes(b['size_bytes'])}\n"
        f"ساخته‌شده توسط: {creator}"
    )

def get_backup_manage_keyboard(bid):
    return [
        [styled_button("⬇️ دانلود", f"admin_backup_download_{bid}".encode(), style=STYLE_INFO)],
        [styled_button("♻️ بازیابی این بکاپ", f"admin_backup_restore_{bid}".encode(), style=STYLE_ON)],
        [styled_button("🗑 حذف بکاپ", f"admin_backup_delete_{bid}".encode(), style=STYLE_OFF)],
        [styled_button("➜ بازگشت", b"admin_backup_list", style=STYLE_OFF)]
    ]

def get_backup_delete_confirm_keyboard(bid):
    return [
        [styled_button("🗑 بله، حذف شود", f"admin_backup_delete_confirm_{bid}".encode(), style=STYLE_OFF)],
        [styled_button("➜ بازگشت", f"admin_backup_manage_{bid}".encode(), style=STYLE_OFF)]
    ]

def get_backup_restore_confirm_text(source_label):
    return (
        f"⚠️ **بازیابی بکاپ «{source_label}»**\n\n"
        "قبل از بازیابی، یک بکاپ خودکار از وضعیت فعلی دیتابیس گرفته می‌شود تا در "
        "صورت بروز مشکل قابل برگشت باشد.\n\n"
        "Session کاربران دست‌نخورده باقی می‌ماند و هیچ رکوردی حذف نمی‌شود (فقط "
        "بروزرسانی/افزوده می‌شود).\n\n"
        "آیا مطمئن هستید؟"
    )

def get_backup_restore_confirm_keyboard(token):
    return [
        [styled_button("♻️ بله، بازیابی شود", f"admin_backup_restore_confirm_{token}".encode(), style=STYLE_ON)],
        [styled_button("➜ بازگشت", b"admin_backup_list", style=STYLE_OFF)]
    ]

def format_diamonds(value):
    value = float(value or 0)
    if value == int(value):
        return f"{int(value):,}"
    return f"{value:,.2f}"

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

# ======================== منوهای کاربر ========================
PANEL_TEXT = "🔘 **پنـل مدیریـت نـوا سـلف**\nاز طریق منوی زیر سلف خود را مدیریت کنید:"

def get_panel_root_keyboard(user):
    """
    ریشه‌ی پنل خصوصی (`.پنل`). دکمه‌ی «✕ بستن پنل» نیازی به افزودن دستی ندارد چون
    این پنل همیشه در بستر Inline (wrap_panel_buttons) رندر می‌شود و آن دکمه خودش
    به‌صورت خودکار اضافه می‌شود؛ چون این صفحه ریشه است، «➜ بازگشت» ندارد.
    """
    expiry_text = format_expiry(user.get("diamonds", 0))
    return [
        [toggle_button(f"وضعیت سلف  |  ⏳ {expiry_text}", user["status"], b"toggle_status")],
        [
            styled_button("⚙ تنظیمات سلف", b"settings_root", style=STYLE_INFO),
            styled_button("👤 حساب کاربری", b"panel_account", style=STYLE_INFO),
        ],
    ]

def get_settings_root_keyboard(user_id):
    """صفحه‌ی «⚙ تنظیمات سلف» — دسترسی به تمام قابلیت‌های سلف، طبق چیدمان درخواستی."""
    locks = feature_locks.get(user_id, set())

    def btn(key, text, callback):
        # قفل سراسری (برای همه‌ی کاربران) با رنگ قرمز نشان داده می‌شود تا از قفل
        # شخصیِ همان کاربر (که فقط 🔒 می‌گیرد ولی آبی می‌ماند) قابل تشخیص باشد.
        if key in global_feature_locks:
            return styled_button(f"{text} 🔒", callback, style=STYLE_OFF)
        if key in locks:
            return styled_button(f"{text} 🔒", callback, style=STYLE_INFO)
        return styled_button(text, callback, style=STYLE_INFO)

    return [
        [
            btn("date", "📅 تاریخ", b"menu_date"),
            btn("actions", "🎭 اکشن", b"menu_actions"),
            btn("time", "⌚ ساعت", b"menu_time"),
        ],
        [
            btn("textmode", "🖊️ حالت متن", b"menu_textmode"),
            btn("secretary", "🧑‍💼 منشی پیوی", b"menu_secretary"),
        ],
        [
            btn("tag", "🏷️ تگ", b"menu_tag"),
            btn("meow", "🐱 میو", b"menu_meow"),
            btn("ping", "🏓 پینگ", b"menu_ping"),
        ],
        [
            btn("autoreply", "🤖 پاسخ خودکار", b"menu_autoreply"),
            btn("reaction", "👍 ریکت", b"menu_reaction"),
            btn("whois", "🪪 اطلاعات", b"menu_whois"),
        ],
        [styled_button("➜ بازگشت", b"panel_root", style=STYLE_OFF)]
    ]

def get_panel_account_text(user_id, user):
    username = user.get("username")
    header = f" @{username}" if username else ""
    return f"👤 **حساب کاربری**{header}"

def get_panel_account_keyboard(user_id, user):
    """
    صفحه‌ی نمایشیِ حساب کاربری در `.پنل`: هر ردیف یک جفت دکمه (برچسب + مقدار) است،
    هر دو آبی و غیرفعال (callback=void) — طبق درخواست «فقط نمایشی، با کلیک هیچ
    اتفاقی نیفتد».
    """
    username = user.get("username")
    username_display = username if username else "ثبت نشده"
    diamonds = format_diamonds(user.get("diamonds", 0))
    toman = format_toman(user.get("diamonds", 0))
    expiry = format_expiry(user.get("diamonds", 0))

    def info_row(label, value):
        # ترتیب دکمه‌ها در آرایه = ترتیب نمایش چپ‌به‌راست در تلگرام (مستقل از جهت
        # متن)؛ طبق درخواست، مقدار باید سمت چپ و عنوان سمت راست باشد یعنی مقدار
        # اول در لیست بیاید.
        return [
            styled_button(str(value), b"void", style=STYLE_INFO),
            styled_button(label, b"void", style=STYLE_INFO),
        ]

    return [
        info_row("👤 نام کاربری:", username_display),
        info_row("🆔 آیدی عددی:", user_id),
        info_row("👥 تعداد رفرال:", user.get("referral_count", 0)),
        info_row("💎 موجودی الماس:", diamonds),
        info_row("💰 معادل تومانی:", f"{toman} تومان"),
        info_row("💱 نرخ فعلی:", f"{DIAMOND_RATE_PER_HOUR} الماس در ساعت"),
        info_row("⏳ انقضای تخمینی:", expiry),
        [styled_button("➜ بازگشت", b"panel_root", style=STYLE_OFF)]
    ]

def get_ping_menu_text():
    return (
        "قابلیت پینگ\n"
        "▫️ `.پینگ`\n"
        "— نمایش پینگ سرور سلف شما"
    )

def get_ping_menu_keyboard():
    return [[styled_button("➜ بازگشت", b"settings_root", style=STYLE_OFF)]]

def get_whois_menu_text():
    return (
        "قابلیت اطلاعات\n"
        "▫️ `.آیدی`\n"
        "— برای نمایش اطلاعات شخص روی پیام او ریپلای کن"
    )

def get_whois_menu_keyboard():
    return [[styled_button("➜ بازگشت", b"settings_root", style=STYLE_OFF)]]

# ======================== منوی ریکت ========================
def get_reaction_menu_text(user_id, user):
    count = len(reaction_targets.get(user_id, {}))
    return (
        f"👍 **قابلیت ریکت** ({status_icon(user.get('reaction_enabled', False))})\n\n"
        f"تعداد کاربران دارای ریکت: {count}\n\n"
        "برای تنظیم ریکت روی یک کاربر، در هر چتی روی پیام او Reply کنید و بفرستید:\n"
        "`.ریکت 🤣`\n\n"
        "برای حذف ریکت آن کاربر، روی پیامش Reply کنید و بفرستید:\n"
        "`.حذف ریکت`"
    )

def get_reaction_menu_keyboard(user):
    return [
        [toggle_button("ریکت", user.get("reaction_enabled", False), b"reaction_toggle")],
        [styled_button("لیست ریکت", b"reaction_list", style=STYLE_INFO)],
        [styled_button("➜ بازگشت", b"settings_root", style=STYLE_OFF)]
    ]

def get_reaction_list_text(user_id):
    targets = reaction_targets.get(user_id, {})
    if not targets:
        return "👍 **لیست ریکت**\n\nهنوز هیچ کاربری اضافه نشده است."
    lines = ["👍 **لیست ریکت**\n"]
    for i, (target_id, info) in enumerate(targets.items(), start=1):
        username = info.get("username")
        label = f"@{username}" if username else str(target_id)
        lines.append(f"{i}. {label} ← {info.get('emoji')}")
    lines.append("\nبرای حذف هرکدام، روی پیام همان شخص Reply کنید و `.حذف ریکت` را بفرستید.")
    return "\n".join(lines)

def get_reaction_list_keyboard():
    return [[styled_button("➜ بازگشت", b"menu_reaction", style=STYLE_OFF)]]

# ======================== منوی پاسخ خودکار ========================
def get_autoreply_menu_text(user_id, user):
    count = len(autoreply_cache.get(user_id, []))
    match_label = AUTOREPLY_MATCH_TYPES.get(user.get("autoreply_match_type", "exact"), "برابر")
    return (
        "قابلیت پاسخ خودکار\n\n"
        f"وضعیت: {status_icon(user.get('autoreply_enabled', False))}\n\n"
        f"لیست پاسخ‌ها: {count}\n\n"
        f"نوع تطبیق: {match_label}"
    )

def get_autoreply_menu_keyboard(user):
    match_type = user.get("autoreply_match_type", "exact")
    match_label = AUTOREPLY_MATCH_TYPES.get(match_type, "برابر")
    return [
        [toggle_button("پاسخ خودکار", user.get("autoreply_enabled", False), b"autoreply_toggle")],
        [styled_button("افزودن پاسخ خودکار", b"autoreply_add", style=STYLE_ON)],
        [styled_button("حذف پاسخ خودکار", b"autoreply_remove", style=STYLE_OFF)],
        [styled_button("لیست پاسخ‌های خودکار", b"autoreply_list", style=STYLE_INFO)],
        [styled_button(f"نوع تطبیق: {match_label}", b"autoreply_matchtype", style=STYLE_INFO)],
        [styled_button("➜ بازگشت", b"settings_root", style=STYLE_OFF)]
    ]

def get_autoreply_matchtype_text():
    return "🔠 **نوع تطبیق Trigger**\n\nفقط یکی از این حالت‌ها می‌تواند فعال باشد:"

def get_autoreply_matchtype_keyboard(current):
    buttons = []
    for key, label in AUTOREPLY_MATCH_TYPES.items():
        selected = (key == current)
        buttons.append([styled_button(f"{status_icon(selected)} {label}", f"autoreply_setmatch_{key}".encode(),
                                       style=STYLE_ON if selected else STYLE_OFF)])
    buttons.append([styled_button("➜ بازگشت", b"menu_autoreply", style=STYLE_OFF)])
    return buttons

def get_autoreply_list_text(user_id):
    items = autoreply_cache.get(user_id, [])
    if not items:
        return "📋 **لیست پاسخ‌های خودکار**\n\nهنوز هیچ پاسخی اضافه نشده است."
    lines = ["📋 **لیست پاسخ‌های خودکار**\n\nبرای مشاهده/حذف هرکدام، روی آن کلیک کنید:"]
    return "\n".join(lines)

def get_autoreply_list_keyboard(user_id):
    items = autoreply_cache.get(user_id, [])
    buttons = []
    for item in items:
        label = f"{item['local_id']}. {item['trigger_text'][:30]}"
        buttons.append([styled_button(label, f"autoreply_view_{item['local_id']}".encode(), style=STYLE_INFO)])
    buttons.append([styled_button("➜ بازگشت", b"menu_autoreply", style=STYLE_OFF)])
    return buttons

def get_autoreply_view_text(item):
    kind = item.get("media_kind")
    media_line = f"\n\n📎 نوع پاسخ: {kind}" if kind else ""
    resp_preview = (item.get("response_text") or "")[:200]
    return (
        f"🔹 **پاسخ خودکار شماره {item['local_id']}**\n\n"
        f"Trigger:\n{item['trigger_text']}\n\n"
        f"پیش‌نمایش پاسخ:\n{resp_preview or '(فقط رسانه، بدون متن)'}"
        f"{media_line}"
    )

def get_autoreply_view_keyboard(local_id):
    return [
        [styled_button("🗑 حذف این پاسخ", f"autoreply_delete_{local_id}".encode(), style=STYLE_OFF)],
        [styled_button("➜ بازگشت", b"autoreply_list", style=STYLE_OFF)]
    ]

def get_time_menu_keyboard(user):
    return [
        [toggle_button("ساعت نام", user["name_time"], b"toggle_name_time")],
        [toggle_button("ساعت بیو", user["bio_time"], b"toggle_bio_time")],
        [styled_button("فونت ساعت", b"menu_fonts", style=STYLE_INFO)],
        [styled_button("➜ بازگشت", b"settings_root", style=STYLE_OFF)]
    ]

def get_time_menu_text(user):
    font_name = FONT_NAMES.get(user["font_id"], "بولد")
    preview = build_clock_preview(apply_font, user["font_id"], now=tehran_now())
    return (
        "⌚ **تنظیمات ساعت**\n\n"
        f"فونت ساعت: {font_name}\n\n"
        f"{preview}"
    )

def get_fonts_menu_text(user):
    font_name = FONT_NAMES.get(user["font_id"], "بولد")
    preview = build_clock_preview(apply_font, user["font_id"], now=tehran_now())
    return (
        "🔤 **انتخاب فونت ساعت**\n\n"
        f"فونت ساعت: {font_name}\n\n"
        f"{preview}"
    )

def get_fonts_menu_keyboard(current_font_id):
    buttons = []
    row = []

    for font_id, font_name in FONT_NAMES.items():
        selected = (font_id == current_font_id)
        row.append(styled_button(f"{status_icon(selected)} {font_name}", f"setfont_{font_id}".encode(),
                                  style=STYLE_ON if selected else STYLE_OFF))

        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([styled_button("➜ بازگشت", b"menu_time", style=STYLE_OFF)])
    return buttons

def get_actions_menu_keyboard(current_action):
    buttons = []
    row = []

    for action_key, (action_name, _) in ACTIONS.items():
        selected = (action_key == current_action)
        row.append(styled_button(f"{status_icon(selected)} {action_name}", f"setact_{action_key}".encode(),
                                  style=STYLE_ON if selected else STYLE_OFF))

        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([styled_button("➜ بازگشت", b"settings_root", style=STYLE_OFF)])
    return buttons

def get_date_menu_keyboard(user):
    current_type = user.get("date_type", "shamsi")

    type_row = []
    for type_key, type_name in DATE_TYPE_NAMES.items():
        selected = (type_key == current_type)
        type_row.append(styled_button(f"{status_icon(selected)} {type_name}", f"setdatetype_{type_key}".encode(),
                                       style=STYLE_ON if selected else STYLE_OFF))

    return [
        [toggle_button("تاریخ بیو", user.get("date_enabled"), b"toggle_date_enabled")],
        type_row,
        [styled_button("فونت تاریخ", b"menu_date_fonts", style=STYLE_INFO)],
        [styled_button("➜ بازگشت", b"settings_root", style=STYLE_OFF)]
    ]

def get_date_menu_text(user):
    preview = build_date_preview(apply_font, format_date, user.get("date_font", 1), user.get("date_type", "shamsi"), now=tehran_now())
    return (
        "📅 **تنظیمات تاریخ**\n\n"
        f"{preview}"
    )

def get_date_fonts_menu_keyboard(current_font_id):
    buttons = []
    row = []

    for font_id, font_name in FONT_NAMES.items():
        selected = (font_id == current_font_id)
        row.append(styled_button(f"{status_icon(selected)} {font_name}", f"setdatefont_{font_id}".encode(),
                                  style=STYLE_ON if selected else STYLE_OFF))

        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([styled_button("➜ بازگشت", b"menu_date", style=STYLE_OFF)])
    return buttons

def get_date_fonts_menu_text(user):
    font_name = FONT_NAMES.get(user.get("date_font", 1), "بولد")
    preview = build_date_preview(apply_font, format_date, user.get("date_font", 1), user.get("date_type", "shamsi"), now=tehran_now())
    return (
        "🔤 **انتخاب فونت تاریخ**\n\n"
        f"فونت تاریخ: {font_name}\n\n"
        f"{preview}"
    )

def get_textmode_menu_keyboard(current_mode):
    buttons = []
    row = []

    for mode_id, mode_name in TEXTMODE_NAMES.items():
        selected = (mode_id == current_mode)
        row.append(styled_button(f"{status_icon(selected)} {mode_name}", f"settextmode_{mode_id}".encode(),
                                  style=STYLE_ON if selected else STYLE_OFF))

        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([styled_button("➜ بازگشت", b"settings_root", style=STYLE_OFF)])
    return buttons

def get_tag_menu_text():
    return (
        "🏷️ **قابلیت تگ**\n\n"
        "این قابلیت با ارسال یکی از دستورات زیر (توسط خودتان) داخل هر گروه فعال می‌شود:\n\n"
        "▫️ `.تگ ادمین` — منشن تمام ادمین‌های همان گروه.\n"
        "▫️ `.تگ اعضا` — منشن تمام اعضای همان گروه.\n\n"
        "نکات:\n"
        "▫️ فقط داخل گروه/سوپرگروه کار می‌کند و در چت خصوصی غیرفعال است.\n"
        "▫️ اگر دستور را روی پیامی ریپلای کنید، خروجی هم روی همان پیام ریپلای می‌شود.\n"
        "▫️ در گروه‌های بزرگ، پیام‌ها به چند بخش تقسیم می‌شوند تا محدودیت تلگرام رعایت شود."
    )

def get_tag_menu_keyboard():
    return [[styled_button("➜ بازگشت", b"settings_root", style=STYLE_OFF)]]

def get_secretary_menu_text(user):
    status = status_icon(user.get("secretary_enabled"))
    delay = user.get("secretary_delay", 60)
    text_preview = user.get("secretary_text") or "مشغولم، بعداً پاسخ می‌دهم ✅"
    return (
        "🧑‍💼 **منشی پیوی**\n\n"
        f"وضعیت: {status}\n"
        f"⏱️ تأخیر پاسخ: {delay} ثانیه\n"
        f"📝 متن فعلی:\n{text_preview}\n\n"
        "وقتی روشن باشد، به اولین پیام خصوصی هر شخص (که هنوز پاسخ منشی نگرفته) "
        "بعد از تأخیر تعیین‌شده، این متن ارسال می‌شود؛ تا وقتی طرف پیام تازه‌ای ندهد، دوباره ارسال نمی‌شود."
    )

def get_meow_menu_text(user):
    return "🐱 **بخش میو**\n\nیکی از قابلیت‌های زیر را برای مدیریت انتخاب کنید:"

def get_meow_menu_keyboard(user_id, user):
    group_title = user.get("meow_chat_title")
    group_label = f"📍 گروه: {group_title[:28]}" if group_title else "📍 گروه: انتخاب نشده"
    locks = feature_locks.get(user_id, set())

    def sub_button(key, label, flag, callback):
        text = toggle_label(label, flag)
        if key in global_feature_locks:
            text += " 🔒"
            style = STYLE_OFF
        elif key in locks:
            text += " 🔒"
            style = STYLE_ON if flag else STYLE_OFF
        else:
            style = STYLE_ON if flag else STYLE_OFF
        return styled_button(text, callback, style=style)

    return [
        [styled_button(group_label, b"meow_select_group", style=STYLE_INFO if group_title else STYLE_OFF)],
        [toggle_button("🐱 میو", user.get("meow_enabled", False), b"meow_settings")],
        [sub_button("fish", "🐟 ماهی", user.get("fish_enabled", False), b"fish_settings")],
        [sub_button("meowpoint", "🪙 میو پوینت", user.get("meowpoint_enabled", False), b"meowpoint_settings")],
        [sub_button("streetcat", "🐈 نجات پیشی", user.get("streetcat_enabled", False), b"streetcat_settings")],
        [sub_button("fridge", "❄️ یخچال میویی", user.get("fridge_enabled", False), b"fridge_settings")],
        [styled_button("➜ بازگشت", b"settings_root", style=STYLE_OFF)]
    ]

def get_meow_settings_text(user):
    chat_id = user.get("meow_chat_id")
    group_title = user.get("meow_chat_title")
    group_line = (group_title or f"`{chat_id}`") if chat_id else "هنوز انتخاب نشده"
    last_sent = user.get("meow_last_sent_at")
    last_line = last_sent.strftime("%Y-%m-%d %H:%M:%S") if last_sent else "—"
    interval = user.get("meow_interval_seconds", MEOW_INTERVAL_SECONDS)
    return (
        "🐱 **تنظیمات میو**\n\n"
        f"گروه انتخاب‌شده (مشترک برای همه‌ی قابلیت‌های میو): {group_line}\n"
        f"آخرین ارسال: {last_line}\n"
        f"فاصله‌ی ارسال: {format_interval(interval)}"
    )

def get_meow_settings_keyboard(user):
    interval = user.get("meow_interval_seconds", MEOW_INTERVAL_SECONDS)
    return [
        [toggle_button("میو", user.get("meow_enabled", False), b"meow_toggle")],
        [
            styled_button("➖", b"meow_interval_dec", style=STYLE_OFF),
            styled_button(f"⏱️ {format_interval(interval)}", b"void", style=STYLE_INFO),
            styled_button("➕", b"meow_interval_inc", style=STYLE_ON),
        ],
        [styled_button("➜ بازگشت", b"menu_meow", style=STYLE_OFF)]
    ]

def get_fish_settings_text(user):
    last_run = user.get("fish_last_run_at")
    last_line = last_run.strftime("%Y-%m-%d %H:%M:%S") if last_run else "—"
    interval = user.get("fish_interval_seconds", FISH_INTERVAL_SECONDS)
    return (
        "🐟 **تنظیمات ماهی**\n\n"
        f"آخرین اجرا: {last_line}\n"
        f"فاصله‌ی اجرا: {format_interval(interval)}"
    )

def get_fish_settings_keyboard(user):
    interval = user.get("fish_interval_seconds", FISH_INTERVAL_SECONDS)
    return [
        [toggle_button("ماهی", user.get("fish_enabled", False), b"fish_toggle")],
        [
            styled_button("➖", b"fish_interval_dec", style=STYLE_OFF),
            styled_button(f"⏱️ {format_interval(interval)}", b"void", style=STYLE_INFO),
            styled_button("➕", b"fish_interval_inc", style=STYLE_ON),
        ],
        [styled_button("⚙️ عملیات ماهی", b"fish_ops_menu", style=STYLE_INFO)],
        [styled_button("➜ بازگشت", b"menu_meow", style=STYLE_OFF)]
    ]

FISH_OPS_RARITY_LABELS = [
    ("common", "معمولی"), ("rare", "کمیاب"), ("epic", "حماسی"), ("legendary", "افسانه‌ای"),
]

def get_fish_ops_menu_text(user):
    lines = ["⚙️ **عملیات ماهی بر اساس سطح**\n"]
    for key, label in FISH_OPS_RARITY_LABELS:
        op = user.get(f"fish_operation_{key}") or ("fridge" if key == "legendary" else "feed")
        lines.append(f"{label}: {FISH_OPERATION_NAMES_FA.get(op, op)}")
    return "\n".join(lines)

def get_fish_ops_menu_keyboard(user):
    buttons = []
    for key, label in FISH_OPS_RARITY_LABELS:
        buttons.append([styled_button(label, f"fishop_rarity_{key}".encode(), style=STYLE_INFO)])
    buttons.append([styled_button("➜ بازگشت", b"fish_settings", style=STYLE_OFF)])
    return buttons

def get_fish_op_rarity_keyboard(user, rarity_key):
    current = user.get(f"fish_operation_{rarity_key}") or ("fridge" if rarity_key == "legendary" else "feed")
    buttons = []
    for op_key in ("sell", "feed", "fridge"):
        selected = (op_key == current)
        buttons.append([styled_button(
            f"{status_icon(selected)} {FISH_OPERATION_NAMES_FA[op_key]}",
            f"fishop_set_{rarity_key}_{op_key}".encode(),
            style=STYLE_ON if selected else STYLE_OFF
        )])
    buttons.append([styled_button("➜ بازگشت", b"fish_ops_menu", style=STYLE_OFF)])
    return buttons

def get_meowpoint_settings_text(user):
    last_run = user.get("meowpoint_last_run_at")
    last_line = last_run.strftime("%Y-%m-%d %H:%M:%S") if last_run else "—"
    interval = user.get("meowpoint_interval_seconds", MEOWPOINT_INTERVAL_SECONDS)
    return (
        "🪙 **تنظیمات میو پوینت**\n\n"
        f"آخرین اجرا: {last_line}\n"
        f"فاصله‌ی اجرا: {format_interval(interval)}"
    )

def get_meowpoint_settings_keyboard(user):
    interval = user.get("meowpoint_interval_seconds", MEOWPOINT_INTERVAL_SECONDS)
    return [
        [toggle_button("میو پوینت", user.get("meowpoint_enabled", False), b"meowpoint_toggle")],
        [
            styled_button("➖", b"meowpoint_interval_dec", style=STYLE_OFF),
            styled_button(f"⏱️ {format_interval(interval)}", b"void", style=STYLE_INFO),
            styled_button("➕", b"meowpoint_interval_inc", style=STYLE_ON),
        ],
        [styled_button("➜ بازگشت", b"menu_meow", style=STYLE_OFF)]
    ]

def get_streetcat_settings_text(user):
    return "🐈 **تنظیمات نجات پیشی**\n\nاین قابلیت رویدادمحوره (بدون زمان‌بندی) و به‌محض دیدن پیام مربوطه در گروه انتخاب‌شده، فعال می‌شود."

def get_streetcat_settings_keyboard(user):
    return [
        [toggle_button("نجات پیشی", user.get("streetcat_enabled", False), b"streetcat_toggle")],
        [styled_button("➜ بازگشت", b"menu_meow", style=STYLE_OFF)]
    ]

def get_fridge_settings_text(user):
    last_run = user.get("fridge_last_run_at")
    last_line = last_run.strftime("%Y-%m-%d %H:%M:%S") if last_run else "—"
    interval = user.get("fridge_interval_seconds", FRIDGE_INTERVAL_SECONDS)
    return (
        "❄️ **تنظیمات یخچال میویی**\n\n"
        f"آخرین بررسی: {last_line}\n"
        f"فاصله‌ی بررسی: {format_interval(interval)}"
    )

def get_fridge_settings_keyboard(user):
    interval = user.get("fridge_interval_seconds", FRIDGE_INTERVAL_SECONDS)
    return [
        [toggle_button("یخچال میویی", user.get("fridge_enabled", False), b"fridge_toggle")],
        [
            styled_button("➖", b"fridge_interval_dec", style=STYLE_OFF),
            styled_button(f"⏱️ {format_interval(interval)}", b"void", style=STYLE_INFO),
            styled_button("➕", b"fridge_interval_inc", style=STYLE_ON),
        ],
        [styled_button("➜ بازگشت", b"menu_meow", style=STYLE_OFF)]
    ]

def get_meow_group_list_keyboard(groups, page, current_chat_id):
    page_size = 6
    start = page * page_size
    page_groups = groups[start:start + page_size]

    buttons = []
    for chat_id, title in page_groups:
        selected = (chat_id == current_chat_id)
        label = f"{status_icon(selected)} {title[:30]}"
        buttons.append([styled_button(label, f"meow_setgroup_{chat_id}".encode(),
                                       style=STYLE_ON if selected else STYLE_OFF)])

    nav = []
    if page > 0:
        nav.append(styled_button("⬅️ قبلی", f"meow_grouppage_{page - 1}".encode(), style=STYLE_INFO))
    if start + page_size < len(groups):
        nav.append(styled_button("➡️ بعدی", f"meow_grouppage_{page + 1}".encode(), style=STYLE_INFO))
    if nav:
        buttons.append(nav)

    buttons.append([styled_button("➜ بازگشت", b"menu_meow", style=STYLE_OFF)])
    return buttons

def get_secretary_menu_keyboard(user):
    on = user.get("secretary_enabled", False)
    delay = user.get("secretary_delay", 60)
    return [
        [toggle_button("منشی", on, b"secretary_toggle")],
        [styled_button("📝 تنظیم متن", b"secretary_set_text", style=STYLE_INFO)],
        [styled_button(f"⏱️ تنظیم تایم ({delay} ثانیه)", b"secretary_set_time", style=STYLE_INFO)],
        [styled_button("➜ بازگشت", b"settings_root", style=STYLE_OFF)]
    ]

def get_start_account_text(user_id, user):
    diamonds = format_diamonds(user.get("diamonds", 0))
    toman = format_toman(user.get("diamonds", 0))
    return (
        "👤 **حساب کاربری**\n\n"
        f"🆔 آیدی عددی : {user_id}\n"
        f"👥 تعداد رفرال : {user.get('referral_count', 0)}\n"
        f"💎 موجودی الماس : {diamonds}\n"
        f"💸 معادل تومانی : {toman} تومان"
    )

def get_start_account_keyboard():
    return [
        [
            styled_button("💎 خرید الماس", b"account_buy_diamond", style=STYLE_ON),
            styled_button("💸 انتقال الماس", b"account_transfer_start", style=STYLE_ON),
        ],
        [styled_button("➜ بازگشت", b"start_root", style=STYLE_OFF)]
    ]

def get_account_delete_warning_keyboard():
    return [
        [styled_button("➜ بازگشت", b"start_manage_self", style=STYLE_OFF)],
        [styled_button("✅ تایید و حذف حساب کاربری", b"account_delete_final", style=STYLE_OFF)]
    ]

def get_start_root_text():
    return "🔘 **پنـل اصـلی مدیریـت نـوا سـلف**"

def get_start_root_keyboard(user):
    rows = []
    if not user.get("session"):
        rows.append([styled_button("✦ نصب نوا سلف", b"start_gen_fast", style=STYLE_ON)])
    rows.append([styled_button("💠 مدیریت سلف", b"start_manage_self", style=STYLE_ON)])

    rows.append([
        styled_button("👤 حساب کاربری", b"start_account", style=STYLE_INFO),
        styled_button("🎁 کد هدیه", b"account_giftcode_start", style=STYLE_INFO),
    ])
    rows.append([styled_button("💳 خرید الماس", b"account_buy_diamond", style=STYLE_ON)])
    rows.append([
        Button.url("💻 پشتیبانی", "https://t.me/SaYPouYa"),
        Button.url("📢 کانال نوا سلف", "https://t.me/NovaCodeR"),
    ])
    rows.append([styled_button("💡 سلف چیه؟", b"start_about", style=STYLE_OFF)])
    return rows

def get_start_manage_self_text(user):
    connected = "متصل شده!" if user.get("session") else "متصل نشده!"
    return (
        "🔘 **پنـل اصـلی مدیریـت نـوا سـلف**\n\n"
        "وضعیت اتصال به حساب:\n\n"
        f"{connected}"
    )

def get_start_manage_self_keyboard(user):
    expiry_text = format_expiry(user.get("diamonds", 0))
    return [
        [toggle_button(f"وضعیت سلف  |  ⏳ {expiry_text}", user["status"], b"toggle_status")],
        [
            styled_button("بازیابی نشست", b"account_recover_session", style=STYLE_INFO),
            styled_button("حذف سلف", b"account_delete_confirm", style=STYLE_OFF),
        ],
        [styled_button("➜ بازگشت", b"start_root", style=STYLE_OFF)]
    ]

def get_start_about_text():
    return (
        "💡 **سلف چیست؟**\n\n"
        "سلف یک ربات است که قابلیت‌های زیادی به اکانت شما اضافه می‌کند.\n\n"
        "• آنلاین بودن ۱۰۰ درصدی اکانت به‌صورت ۲۴ ساعته\n\n"
        "• نمایش ساعت و تاریخ به‌صورت لحظه‌ای در کنار نام و بیو\n\n"
        "• حالت‌های متنی متنوع\n\n"
        "• اکشن‌های چت\n\n"
        "• فارمر ربات‌های ترند تلگرام\n\n"
        "• منشی و پاسخ خودکار حتی در زمان آفلاین بودن\n\n"
        "• ریکت خودکار و نمایش اطلاعات\n\n"
        "• و ده‌ها قابلیت جذاب دیگر..."
    )

def get_start_about_keyboard():
    return [[styled_button("➜ بازگشت", b"start_root", style=STYLE_OFF)]]

def get_transfer_cancel_keyboard():
    return [[styled_button("➜ بازگشت", b"transfer_cancel", style=STYLE_OFF)]]

def get_transfer_confirm_keyboard():
    return [
        [styled_button("✅ تایید انتقال", b"transfer_confirm_execute", style=STYLE_ON)],
        [styled_button("➜ بازگشت", b"transfer_cancel", style=STYLE_OFF)]
    ]

def get_code_keyboard(current_code=""):
    display = current_code if current_code else "خالی"
    return [
        [Button.inline(f"🔢 کد وارد شده: {display}", b"void")],
        [Button.inline("1", b"k_1"), Button.inline("2", b"k_2"), Button.inline("3", b"k_3")],
        [Button.inline("4", b"k_4"), Button.inline("5", b"k_5"), Button.inline("6", b"k_6")],
        [Button.inline("7", b"k_7"), Button.inline("8", b"k_8"), Button.inline("9", b"k_9")],
        [
            styled_button("❌ پاک کردن", b"k_clear", style=STYLE_OFF),
            Button.inline("0", b"k_0"),
            styled_button("✅ تایید", b"k_submit", style=STYLE_ON),
        ],
        [styled_button("✕ لغو نصب", b"install_cancel", style=STYLE_OFF)]
    ]

# ======================== خرید الماس (کیبورد عددی + State Machine) ========================
MAX_BUY_DIAMONDS_DIGITS = 7  # جلوگیری از وارد کردن اعداد نجومی/بی‌معنی

def get_buy_amount_keyboard(buffer_str):
    display = buffer_str if buffer_str else "0"
    try:
        preview_toman = f"{int(buffer_str) * DIAMOND_PRICE_TOMAN:,}" if buffer_str else "0"
    except ValueError:
        preview_toman = "0"
    return [
        [Button.inline(f"💎 تعداد: {display}  |  💰 {preview_toman} تومان", b"void")],
        [Button.inline("1", b"buy_k_1"), Button.inline("2", b"buy_k_2"), Button.inline("3", b"buy_k_3")],
        [Button.inline("4", b"buy_k_4"), Button.inline("5", b"buy_k_5"), Button.inline("6", b"buy_k_6")],
        [Button.inline("7", b"buy_k_7"), Button.inline("8", b"buy_k_8"), Button.inline("9", b"buy_k_9")],
        [
            styled_button("⌫", b"buy_k_back", style=STYLE_OFF),
            Button.inline("0", b"buy_k_0"),
            styled_button("✅ تأیید", b"buy_k_submit", style=STYLE_ON),
        ],
        [styled_button("➜ بازگشت", b"start_account", style=STYLE_OFF)]
    ]

def get_buy_confirm_text(amount):
    toman = amount * DIAMOND_PRICE_TOMAN
    return (
        "💎 **تأیید مقدار خرید**\n\n"
        f"💎 تعداد الماس : {format_diamonds(amount)}\n"
        f"💰 مبلغ قابل پرداخت : {toman:,.0f} تومان"
    )

def get_buy_confirm_keyboard():
    return [
        [styled_button("✅ تأیید", b"buy_amount_confirm", style=STYLE_ON)],
        [styled_button("➜ بازگشت", b"buy_amount_back", style=STYLE_OFF)]
    ]

def get_buy_payment_text(amount):
    toman = amount * DIAMOND_PRICE_TOMAN
    return (
        "💳 **انتخاب روش پرداخت**\n\n"
        f"تعداد الماس : {format_diamonds(amount)}\n"
        f"مبلغ قابل پرداخت : {toman:,.0f} تومان\n\n"
        "یکی از روش‌های پرداخت زیر را انتخاب کنید."
    )

def get_buy_payment_keyboard():
    return [
        [
            styled_button("💳 کارت به کارت", b"buy_pay_card", style=STYLE_ON),
            styled_button("🔒 درگاه پرداخت", b"buy_pay_gateway", style=STYLE_OFF),
        ],
        [styled_button("➜ بازگشت", b"buy_payment_back", style=STYLE_OFF)]
    ]

def get_buy_invoice_text(order_id, user_id, username, amount, toman, created_at):
    username_display = f"@{username}" if username else "ثبت نشده"
    return (
        "🧾 **فاکتور خرید الماس**\n\n"
        f"👤 نام کاربر : {username_display}\n"
        f"🆔 آیدی عددی : {user_id}\n"
        f"💎 تعداد الماس : {format_diamonds(amount)}\n"
        f"💰 مبلغ : {toman:,.0f} تومان\n"
        f"🧾 کد سفارش : {order_id}\n"
        f"⏱ زمان ایجاد : {created_at.strftime('%Y/%m/%d %H:%M')}\n"
        "📌 وضعیت : در انتظار پرداخت"
    )

def get_buy_invoice_keyboard():
    return [
        [styled_button("✅ تأیید فاکتور", b"buy_invoice_confirm", style=STYLE_ON)],
        [styled_button("➜ بازگشت", b"buy_invoice_back", style=STYLE_OFF)]
    ]

CARD_TO_CARD_NUMBER = "6219861854957841"
CARD_TO_CARD_OWNER = "محمدپویا حیدری‌فتسمی"

def get_buy_waiting_receipt_text(toman):
    # شماره کارت به‌صورت مونواسپیس (`...`) نمایش داده می‌شود چون در همه‌ی کلاینت‌های
    # رسمی تلگرام، متن با فرمت Code به‌صورت خودکار با یک لمس قابل کپی‌شدن است —
    # نیازی به دکمه‌ی مجزا برای Copy نیست (سازگار با همه‌ی نسخه‌های Telethon/کلاینت).
    return (
        "💳 **کارت به کارت**\n\n"
        f"مبلغ {toman:,.0f} تومان رو به کارت زیر واریز کن:\n\n"
        f"💳 شماره کارت (برای کپی لمس کنید) : `{CARD_TO_CARD_NUMBER}`\n"
        f"👤 به نام : {CARD_TO_CARD_OWNER}\n\n"
        "بعد از واریز، عکس رسید رو همینجا بفرست تا بررسی و تأیید بشه ✅"
    )

def get_buy_waiting_receipt_keyboard():
    return [
        [styled_button("➜ بازگشت", b"buy_receipt_back", style=STYLE_OFF)]
    ]

# ======================== منوهای ادمین ========================
def get_admin_main_menu():
    total, active = get_user_stats()
    return [
        [styled_button(f"📊 آمار کاربران ({total} نفر)", b"admin_stats", style=STYLE_INFO)],
        [styled_button("📋 لیست کاربران", b"admin_users_list", style=STYLE_INFO)],
        [styled_button("📨 ارسال پیام همگانی", b"admin_broadcast", style=STYLE_INFO)],
        [styled_button("🔍 جستجوی کاربر", b"admin_search_user", style=STYLE_INFO)],
        [styled_button("🎁 مدیریت کدهای هدیه", b"admin_giftcodes", style=STYLE_INFO)],
        [styled_button("🧾 پیام‌های ارسالی", b"admin_messages_list", style=STYLE_INFO)],
        [styled_button("🔔 جوین اجباری", b"admin_joingate", style=STYLE_INFO)],
        [styled_button("🌐 قفل سراسری قابلیت‌ها", b"admin_globallock", style=STYLE_INFO)],
        [styled_button("💾 سیستم بکاپ", b"admin_backup", style=STYLE_INFO)],
        [styled_button("📜 لاگ‌های مدیریتی اخیر", b"admin_logs", style=STYLE_INFO)],
        [styled_button("🔄 بروزرسانی همه کاربران", b"admin_refresh_all", style=STYLE_INFO)]
    ]

def get_giftcodes_admin_text():
    codes = list_gift_codes_db()
    if not codes:
        return "🎁 **مدیریت کدهای هدیه**\n\nهنوز هیچ کدی ساخته نشده است.\n\nبرای مدیریت هر کد، روی آن کلیک کنید."

    lines = ["🎁 **مدیریت کدهای هدیه**\n\nبرای مدیریت هر کد (تغییر مقدار/انقضا/فعال‌سازی/حذف)، روی آن کلیک کنید:\n"]
    for c in codes:
        state = status_icon(bool(c["is_active"]))
        expiry = c["expires_at"].strftime("%Y-%m-%d") if c["expires_at"] else "بدون انقضا"
        lines.append(f"`{c['code']}` — {format_diamonds(c['diamonds'])} 💎 — {state} — انقضا: {expiry}")
    return "\n".join(lines)

def get_giftcodes_admin_keyboard():
    codes = list_gift_codes_db()
    buttons = [[styled_button("➕ ساخت کد جدید", b"admin_giftcode_create", style=STYLE_ON)]]

    for c in codes:
        active = bool(c["is_active"])
        buttons.append([styled_button(
            f"{status_icon(active)} {c['code']} — {format_diamonds(c['diamonds'])} 💎",
            f"admin_giftcode_manage_{c['code']}".encode(),
            style=STYLE_ON if active else STYLE_OFF
        )])

    buttons.append([styled_button("➜ بازگشت", b"admin_panel", style=STYLE_OFF)])
    return buttons

def get_giftcode_manage_text(detail):
    state = status_icon(bool(detail["is_active"]))
    expiry = detail["expires_at"].strftime("%Y-%m-%d %H:%M") if detail["expires_at"] else "بدون انقضا"
    created = detail["created_at"].strftime("%Y-%m-%d %H:%M") if detail["created_at"] else "—"
    return (
        f"🎁 **مدیریت کد هدیه** `{detail['code']}`\n\n"
        f"💎 مقدار الماس: {format_diamonds(detail['diamonds'])}\n"
        f"👥 تعداد استفاده: {detail['uses_count']}\n"
        f"📌 وضعیت: {state} {'فعال' if detail['is_active'] else 'غیرفعال'}\n"
        f"⏱ تاریخ ایجاد: {created}\n"
        f"📅 تاریخ انقضا: {expiry}"
    )

def get_giftcode_manage_keyboard(detail):
    code = detail["code"]
    active = bool(detail["is_active"])
    return [
        [styled_button("💎 تغییر مقدار الماس", f"admin_giftcode_editamount_{code}".encode(), style=STYLE_INFO)],
        [styled_button("⏱ تغییر انقضا", f"admin_giftcode_editexpiry_{code}".encode(), style=STYLE_INFO)],
        [styled_button(
            "✕ غیرفعال کردن" if active else "✓ فعال کردن",
            f"admin_giftcode_toggle_{code}".encode(),
            style=STYLE_OFF if active else STYLE_ON
        )],
        [styled_button("🗑 حذف کد", f"admin_giftcode_delete_{code}".encode(), style=STYLE_OFF)],
        [styled_button("➜ بازگشت", b"admin_giftcodes", style=STYLE_OFF)]
    ]

def get_giftcode_delete_confirm_keyboard(code):
    return [
        [styled_button("🗑 بله، حذف شود", f"admin_giftcode_delete_confirm_{code}".encode(), style=STYLE_OFF)],
        [styled_button("➜ بازگشت", f"admin_giftcode_manage_{code}".encode(), style=STYLE_OFF)]
    ]

# ======================== لیست پیام‌های ارسالی توسط ادمین (تکی/همگانی) ========================
def get_broadcasts_admin_text():
    rows = list_broadcasts_db()
    if not rows:
        return "🧾 **پیام‌های ارسالی**\n\nهنوز هیچ پیامی از این بخش ارسال نشده است."
    return "🧾 **پیام‌های ارسالی اخیر**\n\nبرای مشاهده‌ی وضعیت یا حذف هر پیام، روی آن کلیک کنید:"

def get_broadcasts_admin_keyboard():
    rows = list_broadcasts_db()
    buttons = []
    for r in rows:
        kind_label = "همگانی" if r["kind"] == "broadcast" else f"تکی ← {r['target_id']}"
        ts = r["created_at"].strftime("%m-%d %H:%M") if r["created_at"] else "؟"
        label = f"📨 [{kind_label}] {ts}"
        buttons.append([styled_button(label, f"admin_message_view_{r['broadcast_id']}".encode(), style=STYLE_INFO)])
    buttons.append([styled_button("➜ بازگشت", b"admin_panel", style=STYLE_OFF)])
    return buttons

def get_broadcast_detail_text(record, deliveries_count):
    kind_label = "ارسال همگانی" if record["kind"] == "broadcast" else f"ارسال تکی به کاربر {record['target_id']}"
    ts = record["created_at"].strftime("%Y-%m-%d %H:%M") if record["created_at"] else "؟"
    summary = record["summary"] or "(بدون متن / رسانه)"
    return (
        f"🧾 **جزئیات پیام ارسالی**\n\n"
        f"نوع: {kind_label}\n"
        f"زمان ارسال: {ts}\n"
        f"تعداد گیرندگانِ موفق: {deliveries_count}\n\n"
        f"پیش‌نمایش متن:\n{summary[:300]}"
    )

def get_broadcast_detail_keyboard(broadcast_id):
    return [
        [styled_button("🗑 حذف این پیام از چت کاربران", f"admin_message_delete_{broadcast_id}".encode(), style=STYLE_OFF)],
        [styled_button("➜ بازگشت", b"admin_messages_list", style=STYLE_OFF)]
    ]

def get_users_list_page(page=0, per_page=10):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        offset = page * per_page

        cursor.execute("""
            SELECT user_id, status, joined_at
            FROM novaself_users
            ORDER BY joined_at DESC
            LIMIT %s OFFSET %s
        """, (per_page, offset))

        users = cursor.fetchall()
        cursor.close()
        conn.close()

        buttons = []
        for user in users:
            is_active = bool(user[1])
            buttons.append([styled_button(
                f"{status_icon(is_active)} کاربر {user[0]}",
                f"admin_view_user_{user[0]}".encode(),
                style=STYLE_ON if is_active else STYLE_OFF
            )])

        nav_buttons = []
        if page > 0:
            nav_buttons.append(styled_button("⬅️ قبلی", f"admin_users_page_{page-1}".encode(), style=STYLE_INFO))
        nav_buttons.append(styled_button(f"📄 صفحه {page+1}", b"void", style=STYLE_INFO))
        nav_buttons.append(styled_button("➡️ بعدی", f"admin_users_page_{page+1}".encode(), style=STYLE_INFO))
        buttons.append(nav_buttons)

        buttons.append([styled_button("➜ بازگشت", b"admin_panel", style=STYLE_OFF)])

        return buttons
    except Exception as e:
        logging.error(f"❌ خطا در دریافت لیست کاربران: {e}")
        return [[styled_button("➜ بازگشت", b"admin_panel", style=STYLE_OFF)]]

def get_user_detail_buttons(user_id):
    return [
        [styled_button("🔄 تغییر وضعیت", f"admin_toggle_user_{user_id}".encode(), style=STYLE_INFO)],
        [
            styled_button("➕ افزایش الماس", f"admin_add_diamond_{user_id}".encode(), style=STYLE_ON),
            styled_button("➖ کاهش الماس", f"admin_sub_diamond_{user_id}".encode(), style=STYLE_OFF),
        ],
        [styled_button("👥 تغییر تعداد رفرال", f"admin_set_referral_{user_id}".encode(), style=STYLE_INFO)],
        [styled_button("⚙️ مدیریت قابلیت‌ها", f"admin_features_{user_id}".encode(), style=STYLE_INFO)],
        [styled_button("🔒 قفل کردن قابلیت‌ها", f"admin_lock_features_{user_id}".encode(), style=STYLE_OFF)],
        [styled_button("❌ حذف کاربر", f"admin_delete_user_{user_id}".encode(), style=STYLE_OFF)],
        [styled_button("📨 ارسال پیام به این کاربر", f"admin_send_to_user_{user_id}".encode(), style=STYLE_INFO)],
        [styled_button("➜ بازگشت", b"admin_users_list", style=STYLE_OFF)]
    ]

def get_lock_features_text(user_id):
    locks = feature_locks.get(user_id, set())
    return (
        f"🔒 **قفل کردن قابلیت‌ها برای کاربر** `{user_id}`\n\n"
        f"تعداد قابلیت‌های قفل‌شده: {len(locks)}\n\n"
        "با زدن هر دکمه، وضعیت قفل همان قابلیت تغییر می‌کند (🔒 = قفل، ✓ = باز):"
    )

def get_lock_features_keyboard(user_id):
    locks = feature_locks.get(user_id, set())
    buttons = []
    for key, label in FEATURE_LOCK_DEFS:
        locked = key in locks
        text = f"{label} 🔒" if locked else f"{label} ✓"
        buttons.append([styled_button(
            text, f"admin_togglelock_{key}_{user_id}".encode(),
            style=STYLE_OFF if locked else STYLE_ON
        )])
    buttons.append([styled_button("➜ بازگشت", f"admin_view_user_{user_id}".encode(), style=STYLE_OFF)])
    return buttons

# قابلیت‌های قابل مدیریت توسط ادمین برای هر کاربر: (کلید_در_دیتابیس، برچسب نمایشی)
ADMIN_MANAGEABLE_FEATURES = [
    ("name_time", "ساعت نام"),
    ("bio_time", "ساعت بیو"),
    ("date_enabled", "تاریخ بیو"),
    ("secretary_enabled", "منشی پیوی"),
]

def get_user_features_text(user_id):
    return f"⚙️ **مدیریت قابلیت‌های کاربر** `{user_id}`\n\nبا زدن هر دکمه، همان قابلیت روشن/خاموش می‌شود:"

def get_user_features_keyboard(user_id, user):
    buttons = []
    for field, label in ADMIN_MANAGEABLE_FEATURES:
        current = bool(user.get(field))
        buttons.append([toggle_button(label, current, f"admin_togglefeat_{field}_{user_id}".encode())])
    buttons.append([styled_button("🔤 فونت ساعت", f"admin_userfont_{user_id}".encode(), style=STYLE_INFO)])
    buttons.append([styled_button("🔤 فونت تاریخ", f"admin_userdatefont_{user_id}".encode(), style=STYLE_INFO)])
    buttons.append([styled_button("🖊️ حالت متن", f"admin_usertextmode_{user_id}".encode(), style=STYLE_INFO)])
    buttons.append([styled_button("🎭 اکشن‌ها", f"admin_useractions_{user_id}".encode(), style=STYLE_INFO)])
    buttons.append([styled_button("➜ بازگشت", f"admin_view_user_{user_id}".encode(), style=STYLE_OFF)])
    return buttons

def get_admin_font_grid_keyboard(target_id, current_font_id):
    buttons = []
    row = []
    for font_id, font_name in FONT_NAMES.items():
        selected = (font_id == current_font_id)
        row.append(styled_button(f"{status_icon(selected)} {font_name}",
                                  f"admin_setfont_{target_id}_{font_id}".encode(),
                                  style=STYLE_ON if selected else STYLE_OFF))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([styled_button("➜ بازگشت", f"admin_features_{target_id}".encode(), style=STYLE_OFF)])
    return buttons

def get_admin_datefont_grid_keyboard(target_id, current_font_id):
    buttons = []
    row = []
    for font_id, font_name in FONT_NAMES.items():
        selected = (font_id == current_font_id)
        row.append(styled_button(f"{status_icon(selected)} {font_name}",
                                  f"admin_setdatefont_{target_id}_{font_id}".encode(),
                                  style=STYLE_ON if selected else STYLE_OFF))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([styled_button("➜ بازگشت", f"admin_features_{target_id}".encode(), style=STYLE_OFF)])
    return buttons

def get_admin_textmode_grid_keyboard(target_id, current_mode):
    buttons = []
    row = []
    for mode_id, mode_name in TEXTMODE_NAMES.items():
        selected = (mode_id == current_mode)
        row.append(styled_button(f"{status_icon(selected)} {mode_name}",
                                  f"admin_settextmode_{target_id}_{mode_id}".encode(),
                                  style=STYLE_ON if selected else STYLE_OFF))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([styled_button("➜ بازگشت", f"admin_features_{target_id}".encode(), style=STYLE_OFF)])
    return buttons

def get_admin_actions_grid_keyboard(target_id, current_action):
    buttons = []
    row = []
    for action_key, (action_name, _) in ACTIONS.items():
        selected = (action_key == current_action)
        row.append(styled_button(f"{status_icon(selected)} {action_name}",
                                  f"admin_setaction_{target_id}_{action_key}".encode(),
                                  style=STYLE_ON if selected else STYLE_OFF))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([styled_button("➜ بازگشت", f"admin_features_{target_id}".encode(), style=STYLE_OFF)])
    return buttons

# ======================== کمکی: پیام‌های خودکار (نباید توسط حالت متن دوباره ادیت شوند) ========================
def _mark_auto_sent(user_id, chat_id, message_id):
    _auto_sent_marks.add((user_id, chat_id, message_id))

def _pop_auto_sent(user_id, chat_id, message_id):
    key = (user_id, chat_id, message_id)
    if key in _auto_sent_marks:
        _auto_sent_marks.discard(key)
        return True
    return False

# ======================== قابلیت تگ ========================
async def _gather_chat_admins(event):
    """دریافت لیست ادمین‌های چت؛ سازگار با سوپرگروه/کانال و گروه‌های قدیمی."""
    admins = []
    try:
        chat = await event.get_chat()
        async for u in event.client.iter_participants(chat, filter=ChannelParticipantsAdmins()):
            if not u.bot and not u.deleted:
                admins.append(u)
        return admins
    except Exception:
        pass

    try:
        full = await event.client(GetFullChatRequest(event.chat_id))
        admin_ids = {
            p.user_id for p in full.full_chat.participants.participants
            if p.__class__.__name__ in ("ChatParticipantAdmin", "ChatParticipantCreator")
        }
        for u in full.users:
            if u.id in admin_ids and not u.bot and not u.deleted:
                admins.append(u)
    except Exception as e:
        logging.error(f"⚠️ خطا در دریافت ادمین‌های چت: {e}")

    return admins

async def _send_mentions(event, users_list, user_id):
    """ساخت و ارسال پیام‌های منشن‌دار به‌صورت تکه‌تکه (فقط منشن، بدون هیچ متن اضافه) + مدیریت FloodWait."""
    if not users_list:
        return

    chunk_size = 25
    reply_to = event.reply_to_msg_id if event.is_reply else None

    for i in range(0, len(users_list), chunk_size):
        chunk = users_list[i:i + chunk_size]
        body = ""
        entities = []
        cursor = 0

        for u in chunk:
            name = (u.first_name or "کاربر").strip() or "کاربر"
            mention_text = name + " "
            surrogated_piece = helpers.add_surrogate(mention_text)
            try:
                input_user = await event.client.get_input_entity(u)
                entities.append(InputMessageEntityMentionName(
                    offset=cursor, length=len(surrogated_piece.rstrip()), user_id=input_user
                ))
            except Exception:
                pass
            body += mention_text
            cursor += len(surrogated_piece)

        try:
            sent = await safe_call(
                event.client.send_message, event.chat_id, body,
                formatting_entities=entities, reply_to=reply_to if i == 0 else None
            )
            _mark_auto_sent(user_id, sent.chat_id, sent.id)
        except RPCError as e:
            logging.error(f"⚠️ خطا در ارسال پیام تگ: {e}")
        except Exception as e:
            logging.error(f"⚠️ خطای غیرمنتظره در ارسال تگ: {e}")

        await asyncio.sleep(1.5)

async def handle_tag_admins(event, user_id):
    try:
        admins = await _gather_chat_admins(event)
        if not admins:
            await event.reply("❌ ادمینی برای منشن پیدا نشد یا دسترسی کافی برای دریافت لیست ادمین‌ها وجود ندارد.")
            return
        await _send_mentions(event, admins, user_id)
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
    except Exception as e:
        logging.error(f"⚠️ خطا در تگ ادمین (کاربر {user_id}): {e}")

async def handle_tag_members(event, user_id):
    try:
        chat = await event.get_chat()
        members = []
        try:
            async for u in event.client.iter_participants(chat, limit=1000):
                if not u.bot and not u.deleted:
                    members.append(u)
        except (RPCError, Exception) as e:
            logging.error(f"⚠️ خطا در دریافت اعضای گروه: {e}")
            await event.reply("❌ دریافت لیست اعضا با خطا مواجه شد (ممکن است دسترسی کافی نباشد یا گروه محدودیت داشته باشد).")
            return

        if not members:
            await event.reply("❌ عضوی برای منشن پیدا نشد.")
            return

        await _send_mentions(event, members, user_id)
    except Exception as e:
        logging.error(f"⚠️ خطا در تگ اعضا (کاربر {user_id}): {e}")

# ======================== هندلر یکپارچه پیام‌های خروجی (حالت متن + دستورات تگ) ========================
async def handle_panel_command(event, user_id):
    """
    ساخت «پنل درون‌چتی» با استفاده از ترفند Inline Mode: چون اکانت سلف (کاربر عادی)
    اجازه‌ی ضمیمه‌کردن دکمه به پیام‌های خودش را ندارد (محدودیت خودِ تلگرام)، به‌جایش
    از طریق Inline Mode به بات NovaSelf کوئری می‌زنیم و نتیجه‌ی برگشتی (که واقعاً
    از طرف بات و همراه با دکمه است) را در همین چت درج می‌کنیم.
    """
    try:
        await event.delete()
    except Exception:
        pass

    if not BOT_USERNAME:
        return

    try:
        results = await event.client.inline_query(BOT_USERNAME, "")
        if not results:
            return
        reply_to = event.reply_to_msg_id if event.is_reply else None
        await results[0].click(event.chat_id, reply_to=reply_to)
    except Exception as e:
        logging.error(f"⚠️ خطا در ساخت پنل درون‌چتی برای کاربر {user_id}: {e}")

# ======================== دستور .پینگ ========================
async def handle_ping_command(event, user_id):
    """
    تأخیر واقعیِ سرور Self با زمان‌سنجیِ یک RPC واقعی (get_me) اندازه‌گیری می‌شود
    (رایج‌ترین و دقیق‌ترین روش سنجش Ping در پروژه‌های مبتنی بر Telethon)، سپس همان
    پیام دستور با نتیجه ویرایش و به‌صورت Blockquote (نقل‌قول تلگرامی) نمایش داده می‌شود.
    """
    try:
        client = event.client
        t0 = time.monotonic()
        await client.get_me()
        elapsed_ms = (time.monotonic() - t0) * 1000

        result_text = f"پینگ : {elapsed_ms:.0f} ms"
        surrogated = helpers.add_surrogate(result_text)
        entities = [make_blockquote_entity(0, len(surrogated))]

        await asyncio.sleep(0.2)
        await safe_call(client.edit_message, event.chat_id, event.id, result_text, formatting_entities=entities)
    except MessageNotModifiedError:
        pass
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
    except Exception as e:
        log_internal_error("ping_command", e)

# ======================== دستور .آیدی ========================
async def handle_whois_command(event, user_id):
    """فقط زمانی کار می‌کند که دستور روی پیام یک کاربر Reply شده باشد."""
    try:
        if not event.is_reply:
            await event.reply("❌ برای استفاده از `.آیدی` باید روی پیام یک کاربر Reply کنید.")
            return

        reply = await event.get_reply_message()
        if not reply or not reply.sender_id:
            await event.reply("❌ اطلاعات این کاربر در دسترس نیست.")
            return

        client = event.client
        try:
            target = await reply.get_sender()
        except Exception as e:
            log_internal_error("whois_get_sender", e)
            target = None

        if not target:
            await event.reply("❌ اطلاعات این کاربر در دسترس نیست.")
            return

        bio = ""
        try:
            full = await client(GetFullUserRequest(target.id))
            bio = getattr(full.full_user, "about", "") or ""
        except Exception as e:
            log_internal_error("whois_get_full_user", e)

        photo_count = 0
        try:
            photos = await client.get_profile_photos(target, limit=1)
            photo_count = getattr(photos, "total", None)
            if photo_count is None:
                photo_count = len(photos)
        except Exception as e:
            log_internal_error("whois_get_profile_photos", e)

        name = " ".join(filter(None, [getattr(target, "first_name", None), getattr(target, "last_name", None)])) or "—"
        username = f"@{target.username}" if getattr(target, "username", None) else "ندارد"

        caption = (
            "🪪 **اطلاعات کاربر**\n\n"
            f"• نام کاربر : {name}\n"
            f"• بیوگرافی : {bio or 'ندارد'}\n"
            f"• آیدی عددی : {target.id}\n"
            f"• یوزرنیم : {username}\n"
            f"• تعداد تصاویر پروفایل : {photo_count}"
        )

        photo_bytes = None
        try:
            photo_bytes = await client.download_profile_photo(target, file=bytes)
        except Exception as e:
            log_internal_error("whois_download_photo", e)

        if photo_bytes:
            file_obj = io.BytesIO(photo_bytes)
            file_obj.name = "profile.jpg"
            await safe_call(client.send_file, event.chat_id, file_obj, caption=caption, reply_to=reply.id)
        else:
            # طبق نکته‌ی «اگر کاربر عکس پروفایل نداشت، بدون خطا کار کند»
            await safe_call(client.send_message, event.chat_id, caption, reply_to=reply.id)
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
    except Exception as e:
        log_internal_error("whois_command", e)
        try:
            await event.reply("❌ خطا در دریافت اطلاعات کاربر.")
        except Exception:
            pass

# ======================== دستورات .ریکت و .حذف ریکت ========================
async def handle_set_reaction_command(event, user_id):
    """کاربر فقط زمانی وارد لیست ریکت می‌شود که دستور روی پیام خودش Reply شده باشد."""
    try:
        parts = event.raw_text.strip().split(None, 1)
        if len(parts) < 2 or not parts[1].strip():
            await event.reply("❌ فرمت صحیح: `.ریکت 🤣` (با Reply روی پیام کاربر موردنظر)")
            return
        emoji = parts[1].strip()

        if not event.is_reply:
            await event.reply("❌ برای تنظیم ریکت باید روی پیام همان کاربر Reply کنید.")
            return

        reply = await event.get_reply_message()
        if not reply or not reply.sender_id:
            await event.reply("❌ اطلاعات این کاربر در دسترس نیست.")
            return

        target_id = reply.sender_id
        username = None
        try:
            target = await reply.get_sender()
            username = getattr(target, "username", None) if target else None
        except Exception:
            pass

        if not set_user_reaction_db(user_id, target_id, username, emoji):
            await event.reply("❌ خطا در ذخیره‌سازی. دوباره تلاش کنید.")
            return

        reaction_targets.setdefault(user_id, {})[target_id] = {"emoji": emoji, "username": username}
        log_settings_change(user_id, "reaction_target", f"{target_id}={emoji}")

        # اگر قابلیت ریکت هنوز از پنل روشن نشده، همین‌جا خودکار روشن می‌شود — چون
        # ثبت یک ریکت با دستور یعنی قصد استفاده از قابلیت را دارد؛ این باگ اصلیِ
        # «ثبت می‌شود ولی ریکت اعمال نمی‌شود» را حل می‌کند (اکثر مواقع علتش همین
        # روشن‌نبودنِ سوییچِ اصلیِ قابلیت در منو بوده، نه خرابی خودِ ثبت).
        owner = user_data.get(user_id)
        note = ""
        if owner and not owner.get("reaction_enabled"):
            owner["reaction_enabled"] = True
            save_user(user_id, owner)
            log_settings_change(user_id, "reaction_enabled", True)
            note = "\n\n(قابلیت ریکت هم به‌صورت خودکار فعال شد.)"

        await event.reply(f"✅ از این به بعد پیام‌های این کاربر به‌صورت خودکار با {emoji} ریکت می‌شوند.{note}")
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
    except Exception as e:
        log_internal_error("set_reaction_command", e)

async def handle_remove_reaction_command(event, user_id):
    try:
        if not event.is_reply:
            await event.reply("❌ برای حذف ریکت باید روی پیام همان کاربر Reply کنید.")
            return

        reply = await event.get_reply_message()
        if not reply or not reply.sender_id:
            await event.reply("❌ اطلاعات این کاربر در دسترس نیست.")
            return

        target_id = reply.sender_id
        removed = remove_user_reaction_db(user_id, target_id)
        if user_id in reaction_targets:
            reaction_targets[user_id].pop(target_id, None)

        if removed:
            log_settings_change(user_id, "reaction_target_removed", str(target_id))
            await event.reply("✅ ریکت این کاربر حذف شد.")
        else:
            await event.reply("❌ این کاربر در لیست ریکت شما نبود.")
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
    except Exception as e:
        log_internal_error("remove_reaction_command", e)

def make_outgoing_handler(user_id):
    async def handler(event):
        try:
            if _pop_auto_sent(user_id, event.chat_id, event.id):
                return

            user = user_data.get(user_id)
            if not user or not user.get("status"):
                return

            raw_text = event.raw_text
            text_stripped = raw_text.strip() if raw_text else ""

            # --- دستور ساخت پنل درون‌چتی (در هر نوع چتی، برخلاف دستورات تگ) ---
            if text_stripped and text_stripped.lower() in PANEL_TRIGGERS:
                await handle_panel_command(event, user_id)
                return

            # --- پینگ (در هر نوع چتی) ---
            if text_stripped and text_stripped.lower() in PING_TRIGGERS:
                if is_feature_locked(user_id, "ping"):
                    await event.reply("این قابلیت برای شما قفل شده است.")
                    return
                await handle_ping_command(event, user_id)
                return

            # --- اطلاعات/آیدی (در هر نوع چتی، فقط با Reply) ---
            if text_stripped and text_stripped.lower() in WHOIS_TRIGGERS:
                if is_feature_locked(user_id, "whois"):
                    await event.reply("این قابلیت برای شما قفل شده است.")
                    return
                await handle_whois_command(event, user_id)
                return

            # --- تنظیم/حذف ریکت (در هر نوع چتی، فقط با Reply) ---
            if text_stripped:
                lowered_cmd = text_stripped.lower()
                is_reaction_cmd = lowered_cmd.startswith(REACTION_SET_PREFIXES) or lowered_cmd in REACTION_REMOVE_TRIGGERS
                if is_reaction_cmd and is_feature_locked(user_id, "reaction"):
                    await event.reply("این قابلیت برای شما قفل شده است.")
                    return
                if lowered_cmd.startswith(REACTION_SET_PREFIXES):
                    await handle_set_reaction_command(event, user_id)
                    return
                if lowered_cmd in REACTION_REMOVE_TRIGGERS:
                    await handle_remove_reaction_command(event, user_id)
                    return

            # --- دستورات تگ (فقط داخل گروه/سوپرگروه) ---
            if text_stripped and not event.is_private:
                lowered = text_stripped.lower()
                is_tag_cmd = lowered in TAG_ADMIN_TRIGGERS or lowered in TAG_MEMBERS_TRIGGERS
                if is_tag_cmd and is_feature_locked(user_id, "tag"):
                    await event.reply("این قابلیت برای شما قفل شده است.")
                    return
                if lowered in TAG_ADMIN_TRIGGERS:
                    await handle_tag_admins(event, user_id)
                    return
                if lowered in TAG_MEMBERS_TRIGGERS:
                    await handle_tag_members(event, user_id)
                    return

            # --- حالت متن ---
            mode = user.get("text_mode", 0)
            if not mode or not text_stripped:
                return

            entities = build_format_entities(raw_text, mode)
            if not entities:
                return

            await asyncio.sleep(0.2)
            await event.client.edit_message(
                event.chat_id, event.id, raw_text, formatting_entities=entities
            )
        except Exception as e:
            logging.error(f"⚠️ خطا در پردازش پیام خروجی کاربر {user_id}: {e}")

    return handler

# ======================== قابلیت منشی (پاسخ‌گوی خودکار) ========================
def make_secretary_incoming_handler(user_id):
    async def handler(event):
        try:
            if not event.is_private:
                return

            user = user_data.get(user_id)
            if not user or not user.get("status") or not user.get("secretary_enabled"):
                return

            peer_id = event.sender_id
            if not peer_id:
                return

            # رفع باگ: منشی نباید به ربات‌های تلگرامی پاسخ بدهد (فقط پیوی کاربران واقعی)
            try:
                sender = await event.get_sender()
                if sender is None or getattr(sender, "bot", False):
                    return
            except Exception:
                return

            state = secretary_state.setdefault(user_id, {})
            peer_state = state.get(peer_id)

            # اگر تسک تأخیریِ فعالی برای این نفر در جریان است، تسک تازه‌ای نساز (جلوگیری از Task اضافی)
            if peer_state and peer_state.get("task") and not peer_state["task"].done() and not peer_state.get("replied"):
                return

            delay = max(1, int(user.get("secretary_delay", 60)))
            reply_text = user.get("secretary_text") or "مشغولم، بعداً پاسخ می‌دهم ✅"

            async def _delayed_reply():
                try:
                    await asyncio.sleep(delay)
                    cur_user = user_data.get(user_id)
                    if not cur_user or not cur_user.get("status") or not cur_user.get("secretary_enabled"):
                        return
                    client = active_clients.get(user_id)
                    if not client:
                        return
                    sent = await client.send_message(peer_id, cur_user.get("secretary_text") or reply_text)
                    _mark_auto_sent(user_id, sent.chat_id, sent.id)
                    if user_id in secretary_state and peer_id in secretary_state[user_id]:
                        secretary_state[user_id][peer_id]["replied"] = True
                except asyncio.CancelledError:
                    pass
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    logging.error(f"⚠️ خطا در ارسال پیام منشی کاربر {user_id}: {e}")

            task = asyncio.get_event_loop().create_task(_delayed_reply())
            state[peer_id] = {"replied": False, "task": task}
        except Exception as e:
            logging.error(f"⚠️ خطای منشی کاربر {user_id}: {e}")

    return handler

def _cleanup_secretary_state(user_id):
    """لغو تسک‌های در انتظار منشی و آزادسازی حافظه (جلوگیری از Memory Leak)."""
    peer_states = secretary_state.pop(user_id, None)
    if peer_states:
        for st in peer_states.values():
            t = st.get("task")
            if t and not t.done():
                t.cancel()

def make_streetcat_handler(user_id):
    """
    برخلاف میو/ماهی/میو‌پوینت/یخچال، «نجات پیشی» تایمر ندارد (بند ۸) — چون پیام‌های
    @MeowieQBot با فاصله‌ی نامشخص می‌آیند، این‌جا فقط منتظر پیام‌های جدیدِ همون
    گروهِ انتخاب‌شده می‌مانیم و هر پیام را با کلیدواژه/دکمه چک می‌کنیم.

    مکانیزم جدید (بند ۲-۴): هر پیام تا ۳ «شانس» (دکمه‌ی نجات) دارد. برای هر شانس
    تا ۳ بار تلاش می‌شود (چون سرور MeowieQBot ممکنه شلوغ باشه)، و به‌محض حذف‌شدنِ
    آن شانس (دکمه دیگر نبود)، بدون تلاش اضافه سراغ شانس بعدی می‌رویم.
    """
    async def handler(event):
        try:
            if event.out:
                return

            user = user_data.get(user_id)
            if not user or not user.get("streetcat_enabled"):
                return

            chat_id = user.get("meow_chat_id")
            if not chat_id or event.chat_id != chat_id:
                return

            message = event.message
            has_button = _find_streetcat_button(message) is not None
            if not has_button and not _is_streetcat_text(message.text or ""):
                return  # این پیام ربطی به نجات پیشی نداشت

            for chance_num in range(1, 4):  # حداکثر ۳ شانس
                try:
                    fresh = await event.client.get_messages(chat_id, ids=message.id)
                except Exception as e:
                    logging.error(f"⚠️ خطا در خواندن پیام نجات پیشی برای کاربر {user_id}: {e}")
                    log_internal_error("streetcat_refetch_error", e)
                    return

                buttons_now = _find_all_streetcat_buttons(fresh) if fresh else []
                if not buttons_now:
                    return  # دیگه هیچ شانسی نمونده — کار تمومه (طبق بند ۴)

                count_before = len(buttons_now)

                for attempt in range(1, GAME_CLICK_MAX_ATTEMPTS + 1):
                    try:
                        current = await event.client.get_messages(chat_id, ids=message.id)
                    except Exception as e:
                        logging.error(f"⚠️ خطا در خواندن پیام نجات پیشی (تلاش {attempt}): {e}")
                        return

                    current_buttons = _find_all_streetcat_buttons(current) if current else []
                    if len(current_buttons) < count_before:
                        break  # این شانس با موفقیت حذف شد، برو سراغ شانس بعدی

                    if not current_buttons:
                        return  # دیگه هیچ دکمه‌ای نمونده

                    try:
                        await safe_call(current_buttons[0].click)
                    except FloodWaitError as e:
                        logging.warning(f"⏳ FloodWait نجات پیشی برای کاربر {user_id}: {e.seconds} ثانیه")
                        await asyncio.sleep(e.seconds + 1)
                        continue
                    except Exception as e:
                        logging.warning(
                            f"⚠️ کاربر {user_id}: خطا در کلیک نجات پیشی (شانس {chance_num}، تلاش {attempt}): {e}"
                        )
                        log_internal_error("streetcat_click_error", e)

                    await asyncio.sleep(GAME_CLICK_RETRY_DELAY)
                # اگه بعد از GAME_CLICK_MAX_ATTEMPTS بار تلاش هم دکمه هنوز بود، طبق
                # بند ۳ (مرحله‌ی ۶) باز هم سراغ شانس بعدی می‌ریم، نه که کل کار متوقف بشه.

        except Exception as e:
            logging.error(f"⚠️ خطای غیرمنتظره در نجات پیشی برای کاربر {user_id}: {e}")
            log_internal_error("streetcat_unexpected_error", e)

    return handler

# ======================== قابلیت ریکت (اجرای خودکار) ========================
def make_reaction_handler(user_id):
    """
    وقتی یکی از کاربران داخل «لیست ریکت» در گروهی که Self هم عضو آن است پیام
    جدیدی بفرستد، بعد از ~۱ ثانیه Delay، همان ایموجی روی پیامش ریکت زده می‌شود.
    طبق بند «ریکت در چت‌هایی اجرا شود که Self و کاربر هدف هر دو در آن حضور دارند»
    (یعنی گروه/سوپرگروه مشترک)، در پیوی اجرا نمی‌شود. هر کاربر مستقل مدیریت می‌شود؛
    چون Delay فقط ۱ ثانیه است، برای هر پیام یک Task کوتاه‌مدت جدید ساخته می‌شود
    (نه یک Task دائمی) تا با پیام‌های پی‌درپی تداخل/تجمع پیدا نکند.
    """
    async def handler(event):
        try:
            if event.out or event.is_private:
                return

            user = user_data.get(user_id)
            if not user or not user.get("status") or not user.get("reaction_enabled"):
                return

            if is_feature_locked(user_id, "reaction"):
                return

            sender_id = event.sender_id
            if not sender_id:
                return

            targets = reaction_targets.get(user_id)
            if not targets or sender_id not in targets:
                return

            emoji = targets[sender_id]["emoji"]
            chat_id = event.chat_id
            message_id = event.id

            async def _delayed_react():
                try:
                    await asyncio.sleep(REACTION_APPLY_DELAY)
                    cur_user = user_data.get(user_id)
                    if not cur_user or not cur_user.get("status") or not cur_user.get("reaction_enabled"):
                        return
                    if is_feature_locked(user_id, "reaction"):
                        return
                    cur_targets = reaction_targets.get(user_id)
                    if not cur_targets or sender_id not in cur_targets:
                        return  # ریکت این کاربر بین این فاصله حذف شده
                    client = active_clients.get(user_id)
                    if not client:
                        return

                    emoji = cur_targets[sender_id]["emoji"]
                    # روی نسخه‌های مختلف Telethon، پارامتر reaction گاهی یک رشته و
                    # گاهی لیستی از رشته/ReactionEmoji قبول می‌کند؛ برای اطمینان از کار
                    # کردن ریکت (باگ گزارش‌شده: «ثبت می‌شود ولی ریکت اعمال نمی‌شود»)،
                    # اول به شکل رشته‌ی تکی امتحان می‌شود و در صورت خطا، به شکل لیست.
                    try:
                        await safe_call(client.send_reaction, chat_id, message_id, reaction=emoji)
                    except TypeError:
                        await safe_call(client.send_reaction, chat_id, message_id, reaction=[emoji])
                except asyncio.CancelledError:
                    pass
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    log_internal_error("apply_reaction", f"user={user_id} target={sender_id} err={e}")

            _spawn_background_task(_delayed_react())
        except Exception as e:
            logging.error(f"⚠️ خطای هندلر ریکت برای کاربر {user_id}: {e}")
            log_internal_error("reaction_handler_unexpected", e)

    return handler

# ======================== قابلیت پاسخ خودکار (اجرای خودکار) ========================
def make_autoreply_handler(user_id):
    """پیام‌های متنیِ دریافتی در هر چتی بررسی و در صورت تطبیق Trigger، پاسخ ارسال می‌شود."""
    async def handler(event):
        try:
            if event.out:
                return

            user = user_data.get(user_id)
            if not user or not user.get("status") or not user.get("autoreply_enabled"):
                return

            if is_feature_locked(user_id, "autoreply"):
                return

            text = (event.raw_text or "").strip()
            if not text:
                return  # فقط پیام‌های متنی به‌عنوان Trigger در نظر گرفته می‌شوند

            items = autoreply_cache.get(user_id)
            if not items:
                return

            match_type = user.get("autoreply_match_type", "exact")
            matched = None
            for item in items:
                trig = item.get("trigger_text") or ""
                if not trig:
                    continue
                if match_type == "exact" and text == trig:
                    matched = item
                    break
                if match_type == "prefix" and text.startswith(trig):
                    matched = item
                    break
                if match_type == "contains" and trig in text:
                    matched = item
                    break

            if not matched:
                return

            client = event.client
            caption = matched.get("response_text") or ""
            entities = matched.get("entities")
            media_bytes = matched.get("media_bytes")

            if media_bytes:
                file_obj = io.BytesIO(media_bytes)
                file_obj.name = matched.get("media_filename") or "file"
                send_kwargs = {
                    "caption": caption,
                    "formatting_entities": entities,
                    "reply_to": event.id,
                }
                kind = matched.get("media_kind")
                if kind == "voice":
                    send_kwargs["voice_note"] = True
                elif kind == "video_note":
                    send_kwargs["video_note"] = True
                elif kind == "gif":
                    send_kwargs["attributes"] = [DocumentAttributeAnimated()]
                # نکته: استیکر از بایت خام (بدون stickerset اصلی) به‌صورت عکس/فایل معمولی
                # دوباره ارسال می‌شود؛ حفظ کامل خاصیت «استیکر» چون از یک حساب دیگر
                # (پنل بات) دانلود و توسط اکانت Self دوباره آپلود می‌شود، ممکن نیست.
                sent = await safe_call(client.send_file, event.chat_id, file_obj, **send_kwargs)
            elif caption:
                sent = await safe_call(client.send_message, event.chat_id, caption,
                                        formatting_entities=entities, reply_to=event.id)
            else:
                sent = None

            # علامت‌گذاری پیام ارسالی به‌عنوان «خودکار» تا make_outgoing_handler دوباره
            # آن را پردازش نکند (مثلاً حالت متن روی متنِ ذخیره‌شده‌ی پاسخ خودکار اعمال
            # نشود) — دقیقاً همان مکانیزم استفاده‌شده در قابلیت منشی.
            if sent:
                _mark_auto_sent(user_id, sent.chat_id, sent.id)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logging.error(f"⚠️ خطای پاسخ خودکار برای کاربر {user_id}: {e}")
            log_internal_error("autoreply_handler_unexpected", e)

    return handler

# ======================== مدیریت چرخه حیات کلاینت سلف ========================
async def _teardown_existing_client(user_id):
    """
    قبل از ساخت کلاینت جدید برای یک کاربر، اگر از قبل کلاینت/تسک‌های فعالی برایش
    ثبت شده، اول آن‌ها را کامل و تمیز جمع می‌کند. بدون این کار، اگر یک کلاینت جدید
    با همان Session ساخته و متصل شود درحالی‌که کلاینت قبلی هنوز زنده است، تلگرام
    هر دو اتصال را به‌عنوان استفاده‌ی هم‌زمان از یک Session از دو IP تشخیص می‌دهد
    و کل نشست را باطل می‌کند (دقیقاً همان چیزی که باعث Logout ناخواسته می‌شود).
    """
    old_client = active_clients.pop(user_id, None)
    user = user_data.get(user_id)
    current = asyncio.current_task()

    if user:
        for key in ("task", "action_task", "billing_task", "meow_task", "fish_task", "meowpoint_task", "fridge_task"):
            t = user.get(key)
            if t and t is not current and not t.done():
                t.cancel()
            user[key] = None

    if old_client:
        try:
            if old_client.is_connected():
                await old_client.disconnect()
        except Exception as e:
            log_internal_error("teardown_existing_client_disconnect", e)

def register_active_client(user_id, client):
    """ثبت کلاینتِ از قبل متصل و احراز‌هویت‌شده (بدون اتصال مجدد)."""
    active_clients[user_id] = client
    client.add_event_handler(make_outgoing_handler(user_id), events.NewMessage(outgoing=True))
    client.add_event_handler(make_secretary_incoming_handler(user_id), events.NewMessage(incoming=True))
    client.add_event_handler(make_streetcat_handler(user_id), events.NewMessage(incoming=True))
    client.add_event_handler(make_reaction_handler(user_id), events.NewMessage(incoming=True))
    client.add_event_handler(make_autoreply_handler(user_id), events.NewMessage(incoming=True))

    loop = asyncio.get_event_loop()
    if user_id in user_data:
        user_data[user_id]["task"] = loop.create_task(self_bot_worker(user_id, client))
        user_data[user_id]["action_task"] = loop.create_task(self_bot_action_worker(user_id, client))
        user_data[user_id]["billing_task"] = loop.create_task(diamond_billing_worker(user_id, client))
        # میو: فقط اگر قبلاً فعال بوده (مثلاً بعد از Restart) خودکار دوباره استارت می‌شود
        if user_data[user_id].get("meow_enabled") and user_data[user_id].get("meow_chat_id"):
            user_data[user_id]["meow_task"] = loop.create_task(meow_worker(user_id, client))
        # ماهی: همانند میو، فقط اگر قبلاً فعال بوده و گروه هنوز ست است
        if user_data[user_id].get("fish_enabled") and user_data[user_id].get("meow_chat_id"):
            user_data[user_id]["fish_task"] = loop.create_task(fish_worker(user_id, client))
        # میو پوینت: همانند میو/ماهی
        if user_data[user_id].get("meowpoint_enabled") and user_data[user_id].get("meow_chat_id"):
            user_data[user_id]["meowpoint_task"] = loop.create_task(meowpoint_worker(user_id, client))
        # یخچال میویی: همانند میو/ماهی/میو‌پوینت
        if user_data[user_id].get("fridge_enabled") and user_data[user_id].get("meow_chat_id"):
            user_data[user_id]["fridge_task"] = loop.create_task(fridge_worker(user_id, client))

async def start_self_client(user_id, session_string):
    """ساخت یک کلاینت جدید از روی سشن ذخیره‌شده، اتصال و ثبت آن (بعد از جمع‌کردن ایمن کلاینت قبلی در صورت وجود)."""
    if not session_string:
        return None

    await _teardown_existing_client(user_id)

    try:
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            return None
    except Exception as e:
        logging.error(f"❌ خطا در اتصال کلاینت کاربر {user_id}: {e}")
        return None

    register_active_client(user_id, client)
    return client

async def stop_self_client(user_id):
    """
    توقف کامل و امن کلاینت سلف یک کاربر (تسک‌ها + قطع اتصال + پاکسازی وضعیت منشی).
    این تابع ممکن است از داخل خودِ یکی از تسک‌ها (مثلاً diamond_billing_worker هنگام اتمام
    موجودی) صدا زده شود؛ برای جلوگیری از خودکنسل‌کردنِ تسکِ در حال اجرا، تسک جاری را
    از لیست کنسل‌شدنی مستثنی می‌کنیم.
    """
    user = user_data.get(user_id)
    current = asyncio.current_task()

    if user:
        for key in ("task", "action_task", "billing_task", "meow_task", "fish_task", "meowpoint_task", "fridge_task"):
            t = user.get(key)
            if t and t is not current:
                t.cancel()
            user[key] = None

    _cleanup_secretary_state(user_id)

    client = active_clients.pop(user_id, None)
    if client:
        try:
            if client.is_connected():
                await client.disconnect()
        except Exception:
            pass

# ======================== توابع اصلی سلف ========================
async def self_bot_worker(user_id, client):
    try:
        me = await client.get_me()
        first_name = me.first_name or "کاربر"
        last_signature = None

        if user_id in user_data and user_data[user_id].get("username") != me.username:
            user_data[user_id]["username"] = me.username
            update_username_db(user_id, me.username)

        while True:
            if user_id not in user_data or not user_data[user_id]["status"]:
                break

            user = user_data[user_id]
            tehran_tz = pytz.timezone('Asia/Tehran')
            now = datetime.now(tehran_tz)
            current_time = now.strftime("%H:%M")
            current_date_raw = format_date(now, user.get("date_type", "shamsi"))

            signature = (
                current_time, current_date_raw,
                user["name_time"], user["bio_time"], user["font_id"],
                user.get("date_enabled", False), user.get("date_type", "shamsi"),
                user.get("date_font", 1)
            )

            if signature != last_signature:
                formatted_time = apply_font(current_time, user["font_id"])
                formatted_date = apply_font(current_date_raw, user.get("date_font", 1))

                try:
                    if user["name_time"]:
                        await client(UpdateProfileRequest(first_name=first_name, last_name=formatted_time))
                    else:
                        await client(UpdateProfileRequest(first_name=first_name, last_name=""))

                    bio_parts = []
                    if user["bio_time"]:
                        bio_parts.append(formatted_time)
                    if user.get("date_enabled"):
                        bio_parts.append(formatted_date)

                    if bio_parts:
                        await client(UpdateProfileRequest(about=" | ".join(bio_parts)))

                    last_signature = signature
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    logging.error(f"⚠️ خطا در بروزرسانی پروفایل کاربر {user_id}: {e}")

            await asyncio.sleep(5)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logging.error(f"❌ خطای اصلی سلف برای کاربر {user_id}: {e}")
    finally:
        try:
            if active_clients.get(user_id) is client:
                active_clients.pop(user_id, None)
            if client and client.is_connected():
                await client.disconnect()
        except Exception:
            pass

async def self_bot_action_worker(user_id, client):
    try:
        while True:
            if user_id not in user_data or not user_data[user_id]["status"]:
                break

            user = user_data[user_id]
            action_key = user["active_action"]

            if action_key == 'none' or action_key not in ACTIONS:
                await asyncio.sleep(4)
                continue

            try:
                async for dialog in client.iter_dialogs(limit=10):
                    if dialog.is_user or dialog.is_group:
                        try:
                            await client(SetTypingRequest(
                                peer=dialog.input_entity,
                                action=ACTIONS[action_key][1]
                            ))
                        except Exception:
                            pass
            except Exception as e:
                logging.error(f"⚠️ خطا در نمایش اکشن کاربر {user_id}: {e}")

            await asyncio.sleep(4)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logging.error(f"❌ خطای اکشن برای کاربر {user_id}: {e}")

async def meow_worker(user_id, client):
    """
    هر MEOW_INTERVAL_SECONDS ثانیه، پیام «میو» را به گروه انتخاب‌شده‌ی کاربر می‌فرستد.
    خطاهای رایج (حذف از گروه، نبودِ دسترسی ارسال، محدودیت اکانت، FloodWait) گرفته
    می‌شوند طوری که هیچ‌کدام سرویس اصلیِ Self را متوقف نکنند؛ فقط خودِ قابلیت میو
    خاموش و به کاربر اطلاع داده می‌شود.
    """
    while True:
        if user_id not in user_data or not user_data[user_id].get("meow_enabled"):
            break

        chat_id = user_data[user_id].get("meow_chat_id")
        if not chat_id:
            break

        try:
            await safe_call(client.send_message, chat_id, "میو")
            user_data[user_id]["meow_last_sent_at"] = tehran_now()
            save_user(user_id, user_data[user_id])

        except (ChatWriteForbiddenError, UserBannedInChannelError, ChannelPrivateError,
                UserNotParticipantError, ChatAdminRequiredError) as e:
            # این‌ها یعنی سلف دیگر اجازه/عضویت لازم برای ارسال در آن گروه را ندارد؛
            # قابلیت میو را خاموش می‌کنیم تا هر ۵ دقیقه دوباره همین خطا تکرار نشود.
            logging.warning(f"⚠️ میو برای کاربر {user_id} به‌دلیل عدم دسترسی در گروه {chat_id} غیرفعال شد: {e}")
            log_internal_error("meow_permission_lost", e)
            if user_id in user_data:
                user_data[user_id]["meow_enabled"] = False
                save_user(user_id, user_data[user_id])
            try:
                await bot.send_message(
                    user_id,
                    "⛔ **میو غیرفعال شد.**\n\n"
                    "دیگر دسترسی لازم برای ارسال پیام در گروه انتخاب‌شده وجود ندارد "
                    "(احتمالاً از گروه حذف شده‌اید یا دسترسی ارسال پیام گرفته شده)."
                )
            except Exception:
                pass
            break

        except Exception as e:
            # خطای ناشناخته/موقت (مثلاً قطعی شبکه): فقط لاگ می‌شود، سرویس اصلی سلف
            # و بقیه‌ی Taskها متوقف نمی‌شوند و چرخه در تلاش بعدی ادامه پیدا می‌کند.
            logging.error(f"⚠️ خطا در ارسال میو برای کاربر {user_id}: {e}")
            log_internal_error("meow_send_error", e)

        interval = user_data.get(user_id, {}).get("meow_interval_seconds", MEOW_INTERVAL_SECONDS)
        await asyncio.sleep(interval)

STREETCAT_KEYWORDS = ("پیشیخیابونی", "پیشیخیابانی")
STREETCAT_BUTTON_LABELS = ("نجات پیشی خیابونی", "نجات پیشی خیابانی")

def _is_streetcat_text(text):
    t = _normalize_fa(text)
    return any(k in t for k in STREETCAT_KEYWORDS)

def _find_streetcat_button(message):
    for label in STREETCAT_BUTTON_LABELS:
        btn = _find_button(message, label)
        if btn:
            return btn
    return None

def _find_all_streetcat_buttons(message):
    """همه‌ی دکمه‌های «نجات پیشی» باقی‌مانده در پیام را برمی‌گرداند (برای مکانیزم ۳ شانس)."""
    if not message or not message.buttons:
        return []
    found = []
    for row in message.buttons:
        for btn in row:
            normalized_btn = _normalize_fa(btn.text or "")
            if any(_normalize_fa(label) in normalized_btn for label in STREETCAT_BUTTON_LABELS):
                found.append(btn)
    return found

def _is_meowpoint_text(text):
    t = _normalize_fa(text)
    return "میوپوینت" in t or "شکمم" in t or "مقام" in t

def _is_fish_result_text(text):
    if _is_meowpoint_text(text):
        return False
    t = _normalize_fa(text)
    return "سطح" in t or "خواب" in t or "صبرکنی" in t

async def _click_with_retry(client, chat_id, message_id, find_button_fn,
                             max_attempts=GAME_CLICK_MAX_ATTEMPTS, retry_delay=GAME_CLICK_RETRY_DELAY):
    """
    سیستم مرکزی Delay/Retry برای کلیک روی دکمه‌های پیام‌های MeowieQBot (بند ۵ و ۳۱).
    هر بار پیام را دوباره (تازه) می‌خواند، با find_button_fn دکمه‌ی مدنظر را پیدا
    می‌کند و کلیک می‌کند. اگر در هر مرحله دکمه دیگر پیدا نشد، یعنی یا کلیک قبلی
    جواب داده یا پیام/دکمه منقضی شده — در هر دو حالت True برمی‌گرداند و متوقف
    می‌شود (بدون تلاش اضافه). اگر بعد از max_attempts هنوز دکمه بود، False
    برمی‌گرداند. FloodWait به‌صورت خودکار مدیریت می‌شود.
    """
    for attempt in range(max_attempts):
        try:
            fresh = await client.get_messages(chat_id, ids=message_id)
        except Exception as e:
            logging.error(f"⚠️ خطا در خواندن پیام هنگام کلیک (تلاش {attempt + 1}): {e}")
            log_internal_error("game_click_refetch_error", e)
            return False

        if not fresh:
            return False

        btn = find_button_fn(fresh)
        if not btn:
            return True  # دکمه دیگه نیست — یا موفق شده یا دیگه لازم نیست

        try:
            await safe_call(btn.click)
        except FloodWaitError as e:
            logging.warning(f"⏳ FloodWait حین کلیک: {e.seconds} ثانیه صبر می‌کنیم.")
            await asyncio.sleep(e.seconds + 1)
            continue
        except Exception as e:
            logging.warning(f"⚠️ خطا در کلیک (تلاش {attempt + 1}/{max_attempts}): {e}")
            log_internal_error("game_click_error", e)

        await asyncio.sleep(retry_delay)

    return False

async def _wait_for_game_reply(client, chat_id, after_id, timeout, is_ready, is_valid):
    """
    منتظر پاسخ صحیحِ ربات می‌ماند. چون میو/ماهی/میو‌پوینت/پیشی‌خیابونی ممکن است
    مستقل و هم‌زمان به همین گروه پیام بفرستند یا در آن ظاهر شوند، فقط «اولین
    پیام ورودی جدید» کافی نیست — ممکن است پیامِ قابلیت دیگری باشد. برای هر
    پیامِ ورودیِ جدید:
      ۱) با is_ready صبر می‌کند تا کامل شود (مثلاً استیکر که چند ثانیه بعد ادیت می‌شود)
      ۲) با is_valid چک می‌کند که واقعاً مربوط به همین قابلیت است؛ اگر نبود، آن را
         رد کرده و به دنبال پیام بعدی می‌گردد.
    """
    last_seen_id = after_id
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        try:
            msgs = await client.get_messages(chat_id, limit=8)
        except Exception as e:
            logging.error(f"⚠️ خطا در خواندن پیام‌های چت هنگام انتظار پاسخ ربات: {e}")
            msgs = []

        candidates = sorted([m for m in msgs if m.id > last_seen_id and not m.out], key=lambda m: m.id)

        for m in candidates:
            info = m
            edit_deadline = time.monotonic() + FISH_EDIT_WAIT_SECONDS
            while time.monotonic() < edit_deadline and not is_ready(info.text or ""):
                await asyncio.sleep(1.5)
                try:
                    fresh = await client.get_messages(chat_id, ids=m.id)
                    if fresh:
                        info = fresh
                except Exception:
                    break

            if is_valid(info.text or ""):
                return info

            last_seen_id = m.id  # این پیام مال قابلیت دیگری بود؛ رد شو و دنبال پیام بعدی بگرد

        await asyncio.sleep(1.5)

    return None

async def _wait_for_bot_message(client, chat_id, after_id, timeout):
    """
    منتظر اولین پیام جدیدِ ورودی (غیر از پیام‌های خودِ سلف) بعد از شناسه‌ی
    after_id در این چت می‌ماند. عمداً روی فیلترِ from_user تکیه نمی‌کند، چون
    اگر یوزرنیم ربات به هر دلیلی (مثلاً هنوز در کش کلاینت resolve نشده) قابل
    شناسایی نباشد، آن فیلتر بی‌سروصدا هیچ نتیجه‌ای برنمی‌گرداند و کل قابلیت
    همیشه با «به‌موقع پاسخ نداد» مواجه می‌شود؛ این نسخه چنین وابستگی‌ای ندارد.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            msgs = await client.get_messages(chat_id, limit=8)
        except Exception as e:
            logging.error(f"⚠️ خطا در خواندن پیام‌های چت هنگام انتظار پاسخ ربات: {e}")
            msgs = []
        for m in msgs:
            if m.id > after_id and not m.out:
                return m
        await asyncio.sleep(1.5)
    return None

def _normalize_fa(text):
    """برای تشخیص مقاوم‌تر متن فارسی: نیم‌فاصله و فاصله‌های اضافه را نادیده می‌گیرد
    (چون ممکن است پیام واقعی ربات با کاراکتر متفاوتی از چیزی که اینجا نوشته شده باشد)."""
    if not text:
        return ""
    return text.replace("\u200c", "").replace(" ", "")

def _find_button(message, label_contains):
    if not message or not message.buttons:
        return None
    target = _normalize_fa(label_contains)
    for row in message.buttons:
        for btn in row:
            if target in _normalize_fa(btn.text or ""):
                return btn
    return None

async def fish_worker(user_id, client):
    """
    هر FISH_INTERVAL_SECONDS ثانیه، «ماهی» را در همان گروه انتخاب‌شده‌ی میو می‌فرستد،
    منتظر پاسخ @MeowieQBot می‌ماند، سطح ماهی را تشخیص می‌دهد و طبق آن خودکار
    «بده پیشی بخوره» یا «فروش ماهی» را می‌زند (بند ۷-۸-۹).
    """
    while True:
        if user_id not in user_data or not user_data[user_id].get("fish_enabled"):
            break

        chat_id = user_data[user_id].get("meow_chat_id")
        if not chat_id:
            break

        cooldown_override = None

        try:
            sent = await safe_call(client.send_message, chat_id, "ماهی")
            user_data[user_id]["fish_last_run_at"] = tehran_now()
            save_user(user_id, user_data[user_id])

            info = await _wait_for_game_reply(
                client, chat_id, sent.id, FISH_RESPONSE_TIMEOUT,
                is_ready=_is_fish_result_text, is_valid=_is_fish_result_text
            )
            if not info:
                logging.warning(f"⚠️ کاربر {user_id}: MeowieQBot به‌موقع پاسخ نداد.")
            else:
                normalized_text = _normalize_fa(info.text)
                rarity = next((r for r in FISH_NUTRITION_BY_RARITY if _normalize_fa(r) in normalized_text), None)

                if rarity:
                    field = FISH_RARITY_TO_FIELD[rarity]
                    default_op = "fridge" if rarity == "افسانه‌ای" else "feed"
                    operation = user_data.get(user_id, {}).get(field) or default_op
                    target_label = FISH_OPERATION_LABELS.get(operation, "بده پیشی بخوره")
                    fallback_markers = FISH_OPERATION_FALLBACK_MARKERS.get(operation, ())

                    clicked = await _click_with_retry(
                        client, chat_id, info.id, lambda m, lbl=target_label: _find_button(m, lbl)
                    )

                    if clicked and fallback_markers:
                        # چک می‌کنیم به یه دلیلی (پیشی سیره / یخچال پره) عملیات رد نشده باشه
                        await asyncio.sleep(2.5)
                        try:
                            after_click = await client.get_messages(chat_id, ids=info.id)
                        except Exception:
                            after_click = None
                        full_text_norm = _normalize_fa(after_click.text if after_click else "")
                        if any(marker in full_text_norm for marker in fallback_markers):
                            await _click_with_retry(
                                client, chat_id, info.id, lambda m: _find_button(m, "فروش ماهی")
                            )
                elif "خواب" in normalized_text or "صبرکنی" in normalized_text:
                    # ماهی‌ها هنوز کول‌داون دارند؛ این خطا نیست، فقط باید صبر کرد.
                    # اگه زمان دقیق تو پیام باشه (مثل 33:01)، دقیقاً همون‌قدر می‌خوابیم
                    # تا هر چند دقیقه بی‌خودی دوباره تلاش نکنیم.
                    m = re.search(r'(\d+):(\d+)', info.text or "")
                    if m:
                        cooldown_override = int(m.group(1)) * 60 + int(m.group(2)) + 5
                        logging.info(f"ℹ️ کاربر {user_id}: ماهی‌ها در کول‌داون هستند، {cooldown_override} ثانیه صبر می‌کنیم.")
                    else:
                        logging.info(f"ℹ️ کاربر {user_id}: ماهی‌ها در کول‌داون هستند.")
                else:
                    preview = (info.text or "(بدون متن)")[:300]
                    logging.warning(
                        f"⚠️ کاربر {user_id}: سطح ماهی از پیام دریافتی قابل تشخیص نبود. متن دریافتی: {preview!r}"
                    )
                    log_internal_error("fish_rarity_not_detected", preview)

        except (ChatWriteForbiddenError, UserBannedInChannelError, ChannelPrivateError,
                UserNotParticipantError, ChatAdminRequiredError) as e:
            logging.warning(f"⚠️ ماهی برای کاربر {user_id} به‌دلیل عدم دسترسی در گروه {chat_id} غیرفعال شد: {e}")
            log_internal_error("fish_permission_lost", e)
            if user_id in user_data:
                user_data[user_id]["fish_enabled"] = False
                save_user(user_id, user_data[user_id])
            try:
                await bot.send_message(user_id, "⛔ **ماهی غیرفعال شد.** دیگر دسترسی لازم در گروه انتخاب‌شده وجود ندارد.")
            except Exception:
                pass
            break

        except Exception as e:
            logging.error(f"⚠️ خطا در چرخه‌ی ماهی برای کاربر {user_id}: {e}")
            log_internal_error("fish_cycle_error", e)

        if cooldown_override:
            await asyncio.sleep(cooldown_override)
        else:
            fish_interval = user_data.get(user_id, {}).get("fish_interval_seconds", FISH_INTERVAL_SECONDS)
            await asyncio.sleep(fish_interval)

async def meowpoint_worker(user_id, client):
    """
    هر meowpoint_interval_seconds (پیش‌فرض ۴۵ دقیقه)، «پیشی» را در گروه انتخاب‌شده‌ی
    میو می‌فرستد، حدود ۵ ثانیه منتظر پاسخ ربات می‌ماند، و فقط یک‌بار روی دکمه‌ی
    «برداشت میو پوینت ها» کلیک می‌کند (بند ۴-۵). فرض شده پاسخ از همان ربات ماهی
    (@MeowieQBot) می‌آید؛ اگر ربات دیگری این پیام را جواب می‌دهد، کافیست مقدار
    MEOWIEQBOT_USERNAME یا این تابع به‌صورت جدا اصلاح شود.
    """
    while True:
        if user_id not in user_data or not user_data[user_id].get("meowpoint_enabled"):
            break

        chat_id = user_data[user_id].get("meow_chat_id")
        if not chat_id:
            break

        try:
            sent = await safe_call(client.send_message, chat_id, "پیشی")
            user_data[user_id]["meowpoint_last_run_at"] = tehran_now()
            save_user(user_id, user_data[user_id])

            info = await _wait_for_game_reply(
                client, chat_id, sent.id, MEOWPOINT_RESPONSE_TIMEOUT,
                is_ready=_is_meowpoint_text, is_valid=_is_meowpoint_text
            )
            if not info:
                logging.warning(f"⚠️ کاربر {user_id}: ربات پیشی به‌موقع پاسخ نداد.")
            else:
                has_btn = _find_button(info, "برداشت میو پوینت") is not None
                if has_btn:
                    await _click_with_retry(
                        client, chat_id, info.id, lambda m: _find_button(m, "برداشت میو پوینت")
                    )
                else:
                    preview = (info.text or "(بدون متن)")[:300]
                    logging.warning(f"⚠️ کاربر {user_id}: دکمه‌ی برداشت میو پوینت پیدا نشد. متن دریافتی: {preview!r}")
                    log_internal_error("meowpoint_button_not_found", preview)

        except (ChatWriteForbiddenError, UserBannedInChannelError, ChannelPrivateError,
                UserNotParticipantError, ChatAdminRequiredError) as e:
            logging.warning(f"⚠️ میو پوینت برای کاربر {user_id} به‌دلیل عدم دسترسی در گروه {chat_id} غیرفعال شد: {e}")
            log_internal_error("meowpoint_permission_lost", e)
            if user_id in user_data:
                user_data[user_id]["meowpoint_enabled"] = False
                save_user(user_id, user_data[user_id])
            try:
                await bot.send_message(user_id, "⛔ **میو پوینت غیرفعال شد.** دیگر دسترسی لازم در گروه انتخاب‌شده وجود ندارد.")
            except Exception:
                pass
            break

        except Exception as e:
            logging.error(f"⚠️ خطا در چرخه‌ی میو پوینت برای کاربر {user_id}: {e}")
            log_internal_error("meowpoint_cycle_error", e)

        interval = user_data.get(user_id, {}).get("meowpoint_interval_seconds", MEOWPOINT_INTERVAL_SECONDS)
        await asyncio.sleep(interval)

# ---------- یخچال میویی ----------
def _is_fridge_text(text):
    t = _normalize_fa(text)
    return "یخچالمیویی" in t or ("یخچال" in t and "ظرفیتیخچال" in t)

def _is_fridge_empty(text):
    t = _normalize_fa(text)
    return "یخچالخالیاست" in t or "یخچالخالیه" in t

FISH_ENTRY_RE = re.compile(r'[^\n]*\|[^\n]*\|[^\n]*\([^\n]*\)')

def _parse_fridge_fish_entries(text):
    """هر ماهیِ داخل یخچال را از روی ساختار پیام (نه اعداد Hardcode‌شده) تشخیص می‌دهد."""
    if not text:
        return []
    entries = []
    for line in FISH_ENTRY_RE.findall(text):
        is_raw = "خام" in line and "پخته" not in line
        entries.append({"raw": is_raw, "line": line})
    return entries

def _flatten_buttons(message):
    if not message or not message.buttons:
        return []
    flat = []
    for row in message.buttons:
        flat.extend(row)
    return flat

def _flatten_fridge_fish_buttons(message):
    """
    دکمه‌های مربوط به ماهی‌های داخل یخچال را برمی‌گرداند، بدون دکمه‌ی «ارتقا سطح
    یخچال» (که همیشه ردیف اول است و نباید کلیک شود - بند ۱۲). ماهی‌ها از ردیف
    دوم به بعد، هر ردیف حداکثر ۳ تا، می‌آیند.
    """
    upgrade_marker = _normalize_fa("ارتقا سطح یخچال")
    return [b for b in _flatten_buttons(message) if upgrade_marker not in _normalize_fa(b.text or "")]

async def _wait_for_message_change(client, chat_id, message_id, is_target, timeout=FISH_RESPONSE_TIMEOUT):
    """
    منتظر می‌ماند تا پیامی با همین شناسه (که ادیت می‌شود، نه پیام جدید) به حالت
    مدنظر برسد. این الگو برای فلوهای چندمرحله‌ایِ MeowieQBot (انتخاب ماهی → منوی
    عملیات → تایید پخت) استفاده می‌شود، چون این ربات مراحل را با ادیت همان پیام
    نشان می‌دهد، نه با پیام جدید.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            msg = await client.get_messages(chat_id, ids=message_id)
        except Exception as e:
            logging.error(f"⚠️ خطا در خواندن پیام: {e}")
            return None
        if msg and is_target(msg):
            return msg
        await asyncio.sleep(1.5)
    return None

def _pick_cook_button(message):
    """دکمه‌ی پخت را با روش حذفی پیدا می‌کند (بند ۱۷): هر دکمه‌ای که فروش/دادن‌به‌پیشی نباشد."""
    if not message or not message.buttons:
        return None
    for row in message.buttons:
        for btn in row:
            t = _normalize_fa(btn.text or "")
            if _normalize_fa("فروش ماهی") in t or _normalize_fa("بده پیشی بخوره") in t:
                continue
            return btn
    return None

def _pick_confirm_button(message):
    """دکمه‌ی تایید (✅) را پیدا می‌کند؛ چون ممکنه Premium Emoji بدون متن باشه، در
    نبود تطبیق متنی، از موقعیت (اولین دکمه) به‌عنوان fallback استفاده می‌شود."""
    if not message or not message.buttons:
        return None
    for row in message.buttons:
        for btn in row:
            if "✅" in (btn.text or "") or "تایید" in _normalize_fa(btn.text or ""):
                return btn
    first_row = message.buttons[0] if message.buttons else []
    return first_row[0] if first_row else None

async def _process_fridge_fish(client, chat_id, fish_message_id, fish_button, user_id):
    """یک ماهیِ خامِ داخل یخچال را انتخاب، پخت، و تایید می‌کند؛ بدون منتظر ماندن تا پایان پخت (بند ۲۰)."""
    try:
        await safe_call(fish_button.click)
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds + 1)
        return
    except Exception as e:
        logging.warning(f"⚠️ خطا در انتخاب ماهی یخچال برای کاربر {user_id}: {e}")
        log_internal_error("fridge_select_fish_error", e)
        return

    menu_msg = await _wait_for_message_change(
        client, chat_id, fish_message_id,
        is_target=lambda m: _find_button(m, "فروش ماهی") is not None
    )
    if not menu_msg:
        logging.warning(f"⚠️ کاربر {user_id}: منوی عملیات ماهیِ یخچال به‌موقع ظاهر نشد.")
        return

    cook_btn = _pick_cook_button(menu_msg)
    if not cook_btn:
        logging.warning(f"⚠️ کاربر {user_id}: دکمه‌ی پخت برای ماهی یخچال پیدا نشد.")
        return

    try:
        await safe_call(cook_btn.click)
    except Exception as e:
        logging.warning(f"⚠️ خطا در انتخاب گزینه‌ی پخت برای کاربر {user_id}: {e}")
        log_internal_error("fridge_pick_cook_error", e)
        return

    confirm_msg = await _wait_for_message_change(
        client, chat_id, fish_message_id,
        is_target=lambda m: "اطمینان" in _normalize_fa(m.text or "") or bool(m.buttons)
    )
    if not confirm_msg:
        logging.warning(f"⚠️ کاربر {user_id}: پیام تاییدِ پخت به‌موقع ظاهر نشد.")
        return

    confirm_btn = _pick_confirm_button(confirm_msg)
    if not confirm_btn:
        return

    try:
        await safe_call(confirm_btn.click)
    except Exception as e:
        logging.warning(f"⚠️ خطا در تایید پخت برای کاربر {user_id}: {e}")
        log_internal_error("fridge_confirm_cook_error", e)
        return

    # طبق بند ۲۰: به‌محض دیدن «درحال پخیدن»، همین ماهی تمومه؛ منتظر پایان پخت نمی‌مانیم.
    await _wait_for_message_change(
        client, chat_id, fish_message_id,
        is_target=lambda m: "درحالپخیدن" in _normalize_fa(m.text or ""),
        timeout=10
    )

async def fridge_worker(user_id, client):
    """
    هر fridge_interval_seconds (پیش‌فرض ۳۰ دقیقه)، یخچال میویی را بررسی می‌کند:
    اگر خالی بود کاری نمی‌کند (و دکمه‌ی «ارتقا سطح یخچال» را کلیک نمی‌کند - بند ۱۲)،
    وگرنه هر ماهیِ خام را مستقل انتخاب/پخت/تایید می‌کند (بند ۱۰-۲۱).
    """
    while True:
        if user_id not in user_data or not user_data[user_id].get("fridge_enabled"):
            break

        chat_id = user_data[user_id].get("meow_chat_id")
        if not chat_id:
            break

        try:
            sent = await safe_call(client.send_message, chat_id, "یخچال میویی")
            user_data[user_id]["fridge_last_run_at"] = tehran_now()
            save_user(user_id, user_data[user_id])

            info = await _wait_for_game_reply(
                client, chat_id, sent.id, FISH_RESPONSE_TIMEOUT,
                is_ready=_is_fridge_text, is_valid=_is_fridge_text
            )
            if not info:
                logging.warning(f"⚠️ کاربر {user_id}: MeowieQBot به یخچال پاسخ نداد.")
            elif _is_fridge_empty(info.text):
                logging.info(f"ℹ️ کاربر {user_id}: یخچال میویی خالیه.")
            else:
                entries = _parse_fridge_fish_entries(info.text)
                buttons = _flatten_fridge_fish_buttons(info)
                for idx, entry in enumerate(entries):
                    if not user_data.get(user_id, {}).get("fridge_enabled"):
                        break  # اگه وسط کار خاموش شد، فوری متوقف شو
                    if not entry["raw"] or idx >= len(buttons):
                        continue
                    try:
                        await _process_fridge_fish(client, chat_id, info.id, buttons[idx], user_id)
                    except Exception as e:
                        logging.error(f"⚠️ خطا در پردازش ماهی یخچال (index {idx}) برای کاربر {user_id}: {e}")
                        log_internal_error("fridge_fish_process_error", e)
                    await asyncio.sleep(GAME_CLICK_RETRY_DELAY)

        except (ChatWriteForbiddenError, UserBannedInChannelError, ChannelPrivateError,
                UserNotParticipantError, ChatAdminRequiredError) as e:
            logging.warning(f"⚠️ یخچال میویی برای کاربر {user_id} به‌دلیل عدم دسترسی در گروه {chat_id} غیرفعال شد: {e}")
            log_internal_error("fridge_permission_lost", e)
            if user_id in user_data:
                user_data[user_id]["fridge_enabled"] = False
                save_user(user_id, user_data[user_id])
            try:
                await bot.send_message(user_id, "⛔ **یخچال میویی غیرفعال شد.** دیگر دسترسی لازم در گروه انتخاب‌شده وجود ندارد.")
            except Exception:
                pass
            break

        except Exception as e:
            logging.error(f"⚠️ خطا در چرخه‌ی یخچال میویی برای کاربر {user_id}: {e}")
            log_internal_error("fridge_cycle_error", e)

        interval = user_data.get(user_id, {}).get("fridge_interval_seconds", FRIDGE_INTERVAL_SECONDS)
        await asyncio.sleep(interval)

async def diamond_billing_worker(user_id, client):
    """
    هر BILLING_INTERVAL_SECONDS ثانیه، به نسبت مدت‌زمان سپری‌شده الماس کسر می‌کند
    (نرخ: DIAMOND_RATE_PER_HOUR الماس به ازای هر ساعت روشن بودن سلف).
    اگر موجودی تمام شود، سلف به‌صورت خودکار خاموش و به کاربر اطلاع داده می‌شود.
    """
    try:
        last_charge = datetime.now(pytz.UTC)

        while True:
            if user_id not in user_data or not user_data[user_id]["status"]:
                break

            await asyncio.sleep(BILLING_INTERVAL_SECONDS)

            if user_id not in user_data or not user_data[user_id]["status"]:
                break

            now = datetime.now(pytz.UTC)
            elapsed_hours = (now - last_charge).total_seconds() / 3600
            last_charge = now

            cost = elapsed_hours * DIAMOND_RATE_PER_HOUR
            if cost <= 0:
                continue

            success, new_balance = charge_diamonds_db(user_id, cost)

            if user_id in user_data and new_balance is not None:
                user_data[user_id]["diamonds"] = new_balance

            if not success:
                if user_id in user_data:
                    user_data[user_id]["status"] = False
                    save_user(user_id, user_data[user_id])

                await stop_self_client(user_id)

                try:
                    await bot.send_message(
                        user_id,
                        "⛔ **موجودی الماس شما به پایان رسید و سلف شما به‌صورت خودکار متوقف شد.**\n\n"
                        "برای فعال‌سازی مجدد، ابتدا از بخش «👤 حساب کاربری» موجودی خود را افزایش دهید."
                    )
                except Exception:
                    pass
                break

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logging.error(f"⚠️ خطای بیلینگ الماس کاربر {user_id}: {e}")

async def autostart_saved_users():
    await asyncio.sleep(5)

    for user_id, user in list(user_data.items()):
        try:
            if user["status"] and user["session"]:
                if float(user.get("diamonds", 0)) <= 0:
                    user["status"] = False
                    save_user(user_id, user)
                    logging.warning(f"⚠️ سلف کاربر {user_id} به‌دلیل موجودی صفر الماس غیرفعال ماند.")
                    continue

                client = await start_self_client(user_id, user["session"])
                if client:
                    logging.info(f"✅ سلف کاربر {user_id} راه‌اندازی شد.")
                else:
                    user["status"] = False
                    save_user(user_id, user)
                    logging.warning(f"⚠️ سلف کاربر {user_id} به‌دلیل نشست نامعتبر غیرفعال شد.")
        except Exception as e:
            # هر خطایی برای یک کاربر، فقط همان کاربر را تحت تأثیر قرار می‌دهد؛ بقیه‌ی
            # کاربران باید مستقل از این، در همین چرخه‌ی استارتاپ راه‌اندازی شوند.
            logging.error(f"❌ خطا در autostart برای کاربر {user_id}: {e}")
            log_internal_error("autostart_saved_users", e)

# ======================== هندلرهای ربات ========================
@bot.on(events.InlineQuery)
async def inline_panel_handler(event):
    """
    این هندلر فقط برای ساختن «پنل درون‌چتی» به کار می‌رود (بند ۸-۹): وقتی خودِ سلف
    (نه هیچ کاربر دیگری) از طریق Inline Mode به این بات کوئری می‌زند، یک نتیجه‌ی
    تکی حاوی همان منوی اصلیِ پنل خصوصی برمی‌گردانیم؛ خودِ سلف با .click() این نتیجه
    را در چتِ فعلی‌اش (گروه/پیوی/Saved Messages) درج می‌کند.
    """
    owner_id = event.query.user_id
    user = user_data.get(owner_id)

    if not user:
        builder = event.builder
        result = builder.article(
            "❌ ثبت‌نام نشده‌اید",
            text="ابتدا با /start در ربات ثبت‌نام کنید.",
        )
        await event.answer([result], cache_time=0)
        return

    builder = event.builder
    keyboard = wrap_panel_buttons(get_panel_root_keyboard(user), owner_id)
    result = builder.article(
        "🔗 پنل NovaSelf",
        text=PANEL_TEXT,
        buttons=keyboard,
    )
    await event.answer([result], cache_time=0)

@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    """هندلر دستور /start - کاملاً یکسان برای همه کاربران"""
    user_id = event.sender_id

    if user_id in generator_data:
        return

    if user_id not in user_data:
        sender = None
        try:
            sender = await event.get_sender()
        except Exception as e:
            log_internal_error("start_get_sender", e)

        user_data[user_id] = make_default_user(step="menu")
        if sender and getattr(sender, "username", None):
            user_data[user_id]["username"] = sender.username

        # طبق درخواست «تمام کاربرانی که ربات را استارت می‌کنند باید در دیتابیس ذخیره
        # شوند» — بلافاصله ذخیره می‌شود، نه فقط وقتی کاربر واقعاً سلف نصب می‌کند؛
        # این‌طوری در پنل ادمین/بکاپ هم از همان لحظه‌ی اول دیده می‌شود.
        save_user(user_id, user_data[user_id])

    user = user_data[user_id]

    # جوین اجباری: ادمین‌ها معاف هستند تا هیچ‌وقت خودشان از پنل قفل نشوند.
    if needs_join_check(user_id):
        all_joined, missing = await check_user_joined_all(user_id)
        if all_joined:
            _mark_user_verified(user_id)
        else:
            await _send_join_gate(event, user_id, missing)
            return

    await event.respond(
        get_start_root_text(),
        buttons=get_start_root_keyboard(user)
    )

@bot.on(events.NewMessage(pattern='/admin'))
async def admin_handler(event):
    """هندلر دستور /admin - فقط برای ادمین‌ها"""
    user_id = event.sender_id

    if not is_admin(user_id):
        await event.respond("❌ شما دسترسی ادمین ندارید!")
        return

    await event.respond(
        "👑 **پنل مدیریت NovaSelf**\n\n"
        "به پنل ادمین خوش آمدید! از طریق منوی زیر می‌توانید کاربران را مدیریت کنید:",
        buttons=get_admin_main_menu()
    )

@bot.on(events.CallbackQuery)
async def callback_handler(event):
    user_id = event.sender_id
    data = event.data
    panel_owner_id = None  # فقط وقتی پر می‌شود که این کلیک از یک پنل درون‌چتی آمده باشد

    if data == b"void":
        await event.answer()
        return

    # safe_edit را همین‌جا (بدون قید و شرط) به یک بسته‌بندی محلی تبدیل می‌کنیم تا هر
    # فراخوانی safe_edit در ادامه‌ی همین تابع، خودکار از این نسخه استفاده کند. وقتی
    # panel_owner_id (پایین‌تر) پر بشود، این نسخه خودش دکمه‌ها را با پیشوند مالک و
    # دکمه‌ی «✕ بستن پنل» بازسازی می‌کند؛ در غیر این صورت دقیقاً مثل قبل عمل می‌کند.
    # نکته‌ی مهم: چون خودِ همین تابع دوباره safe_edit را محلی تعریف می‌کند، نباید
    # مستقیم به نام safe_edit رجوع کرد (Python کل تابع را "لوکال" حساب می‌کند و قبل
    # از این خط با UnboundLocalError مواجه می‌شود)؛ برای همین از globals() می‌خوانیم.
    _module_safe_edit = globals()['safe_edit']

    async def safe_edit(ev, text, buttons=None):
        if panel_owner_id is not None and buttons:
            buttons = wrap_panel_buttons(buttons, panel_owner_id, add_close=True)
        return await _module_safe_edit(ev, text, buttons=buttons)

    # ====== پنل درون‌چتی (بندهای ۸-۱۲): بازکردن پیشوند مالکیت + کنترل دسترسی ======
    if data.startswith(b"ip_"):
        try:
            _, owner_id_str, real_action = data.decode().split("_", 2)
            owner_id = int(owner_id_str)
        except (ValueError, IndexError):
            await event.answer("❌ داده نامعتبر است.", alert=True)
            return

        if event.sender_id != owner_id:
            await event.answer("⛔ فقط صاحب این Self می‌تواند از این پنل استفاده کند.", alert=True)
            return

        if real_action == "panel_close":
            await _module_safe_edit(event, "✕ پنل بسته شد.", buttons=None)
            # برای شلوغ‌نشدنِ چت، خودِ پیامِ «پنل بسته شد» هم بعد از چند ثانیه
            # به‌صورت خودکار پاک می‌شود (در پس‌زمینه، بدون بلاک‌کردن هندلر).
            async def _auto_delete_closed_panel():
                await asyncio.sleep(3)
                try:
                    await event.delete()
                except Exception:
                    pass
            _spawn_background_task(_auto_delete_closed_panel())
            return

        user_id = owner_id
        data = real_action.encode()
        panel_owner_id = owner_id

    if not click_debouncer.should_process(user_id, data):
        await event.answer()  # کلیک تکراری/سریع؛ بی‌صدا نادیده گرفته می‌شود
        return

    if data == b"join_verify_check":
        all_joined, missing = await check_user_joined_all(user_id)
        if all_joined:
            _mark_user_verified(user_id)
            user = user_data.get(user_id) or make_default_user(step="menu")
            user_data[user_id] = user
            await safe_edit(event, get_start_root_text(), buttons=get_start_root_keyboard(user))
        else:
            await event.answer("برای استفاده از ربات، ابتدا باید در کانال‌های مشخص‌شده عضو شوید.", alert=True)
        return

    # ====== گیت جوین اجباری (بندِ بازسازی): فقط دکمه‌ی «تایید عضویت» بالا از این
    # گیت معاف است. این چک روی هر کلیکی اجرا می‌شود (نه فقط /start) تا کاربری که
    # مدت‌هاست /start نزده یا از کانال لفت داده، همچنان از استفاده باز نماند.
    # چون needs_join_check سبک است (lookup در حافظه)، تماس واقعاً سنگین با API
    # تلگرام (check_user_joined_all) فقط وقتی واقعاً لازم باشد اجرا می‌شود.
    if needs_join_check(user_id):
        all_joined, missing = await check_user_joined_all(user_id)
        if all_joined:
            _mark_user_verified(user_id)
        else:
            await event.answer("⛔ ابتدا باید در کانال‌های مشخص‌شده عضو شوید.", alert=True)
            await _send_join_gate(event, user_id, missing)
            return

    # ====== منوی ادمین ======
    if is_admin(user_id):
        # پنل ادمین
        if data == b"admin_panel":
            await safe_edit(event,
                "👑 **پنل مدیریت NovaSelf**\n\n"
                "از طریق منوی زیر می‌توانید کاربران را مدیریت کنید:",
                buttons=get_admin_main_menu()
            )
            return

        # آمار کاربران
        if data == b"admin_stats":
            total, active = get_user_stats()
            await safe_edit(event,
                f"📊 **آمار کاربران:**\n\n"
                f"👥 تعداد کل کاربران: {total}\n"
                f"🟢 کاربران فعال: {active}\n"
                f"🔴 کاربران غیرفعال: {total - active}\n\n"
                f"🕐 آخرین بروزرسانی: {tehran_now().strftime('%Y-%m-%d %H:%M:%S')}",
                buttons=[styled_button("➜ بازگشت", b"admin_panel", style=STYLE_OFF)]
            )
            return

        # ====================================================================
        # ============================ جوین اجباری ============================
        # ====================================================================
        if data == b"admin_joingate":
            await safe_edit(event, get_joingate_admin_text(), buttons=get_joingate_admin_keyboard())
            return

        if data == b"admin_joingate_add":
            admin_action_data[user_id] = {"type": "add_joingate", "step": "get_title"}
            await safe_edit(event,
                "➕ **افزودن کانال جوین اجباری**\n\n"
                "نام نمایشی کانال را ارسال کنید (همان چیزی که کنار 🔔 نشان داده می‌شود):",
                buttons=[[styled_button("➜ بازگشت", b"admin_joingate", style=STYLE_OFF)]]
            )
            return

        if data.startswith(b"admin_joingate_manage_"):
            cid = int(data.decode().split("admin_joingate_manage_", 1)[1])
            ch = get_join_channel_db(cid)
            if not ch:
                await event.answer("❌ این کانال پیدا نشد.", alert=True)
                await safe_edit(event, get_joingate_admin_text(), buttons=get_joingate_admin_keyboard())
                return
            await safe_edit(event, get_joingate_manage_text(ch), buttons=get_joingate_manage_keyboard(ch))
            return

        if data.startswith(b"admin_joingate_editlink_"):
            cid = int(data.decode().split("admin_joingate_editlink_", 1)[1])
            if not get_join_channel_db(cid):
                await event.answer("❌ این کانال پیدا نشد.", alert=True)
                return
            admin_action_data[user_id] = {"type": "edit_joingate_link", "channel_id": cid, "step": "get_link"}
            await safe_edit(event,
                "✏️ **تغییر لینک کانال**\n\n"
                "لینک عضویت جدید را ارسال کنید (مثال: `https://t.me/mychannel`):",
                buttons=[[styled_button("➜ بازگشت", f"admin_joingate_manage_{cid}".encode(), style=STYLE_OFF)]]
            )
            return

        if data.startswith(b"admin_joingate_toggle_"):
            cid = int(data.decode().split("admin_joingate_toggle_", 1)[1])
            ch = get_join_channel_db(cid)
            if not ch:
                await event.answer("❌ این کانال پیدا نشد.", alert=True)
                return
            new_state = not bool(ch["is_active"])
            set_join_channel_active_db(cid, new_state)
            reload_join_channels_cache()
            log_admin_action(user_id, 0, "toggle_joingate", f"id={cid} active={new_state}")
            ch = get_join_channel_db(cid)
            await safe_edit(event, get_joingate_manage_text(ch), buttons=get_joingate_manage_keyboard(ch))
            return

        if data.startswith(b"admin_joingate_delete_confirm_"):
            cid = int(data.decode().split("admin_joingate_delete_confirm_", 1)[1])
            success = delete_join_channel_db(cid)
            reload_join_channels_cache()
            if success:
                log_admin_action(user_id, 0, "delete_joingate", f"id={cid}")
                await event.answer("✅ کانال حذف شد.", alert=True)
            else:
                await event.answer("❌ این کانال پیدا نشد.", alert=True)
            await safe_edit(event, get_joingate_admin_text(), buttons=get_joingate_admin_keyboard())
            return

        if data.startswith(b"admin_joingate_delete_"):
            cid = int(data.decode().split("admin_joingate_delete_", 1)[1])
            ch = get_join_channel_db(cid)
            if not ch:
                await event.answer("❌ این کانال پیدا نشد.", alert=True)
                return
            await safe_edit(event,
                f"⚠️ حذف کانال «{ch['title']}»؟ این عملیات غیرقابل بازگشت است.",
                buttons=get_joingate_delete_confirm_keyboard(cid)
            )
            return

        # ====================================================================
        # ====================== قفل سراسری قابلیت‌ها =========================
        # ====================================================================
        if data == b"admin_globallock":
            await safe_edit(event, get_globallock_menu_text(), buttons=get_globallock_menu_keyboard())
            return

        if data.startswith(b"admin_globallock_toggle_"):
            key = data.decode().split("admin_globallock_toggle_", 1)[1]
            if key not in FEATURE_LOCK_LABELS:
                await event.answer("❌ قابلیت نامعتبر است.", alert=True)
                return
            if key in global_feature_locks:
                unlock_feature_globally_db(key)
                global_feature_locks.discard(key)
                log_admin_action(user_id, 0, "global_unlock", key)
            else:
                lock_feature_globally_db(key)
                global_feature_locks.add(key)
                log_admin_action(user_id, 0, "global_lock", key)
            await safe_edit(event, get_globallock_menu_text(), buttons=get_globallock_menu_keyboard())
            return

        # ====================================================================
        # ============================ سیستم بکاپ =============================
        # ====================================================================
        if data == b"admin_backup":
            await safe_edit(event, get_backup_menu_text(), buttons=get_backup_menu_keyboard())
            return

        if data == b"admin_backup_create":
            await safe_edit(event, "⏳ در حال ساخت بکاپ... (ممکن است چند ثانیه طول بکشد)")
            backup_id, size_bytes = create_backup_db(user_id, label="manual")
            if backup_id is None:
                await safe_edit(event, "❌ خطا در ساخت بکاپ. لاگ سرور را بررسی کنید.",
                                 buttons=get_backup_menu_keyboard())
                return
            log_admin_action(user_id, 0, "create_backup", f"id={backup_id} size={size_bytes}")
            await safe_edit(event,
                f"✅ بکاپ شماره {backup_id} با موفقیت ساخته شد. ({_format_bytes(size_bytes)})",
                buttons=get_backup_manage_keyboard(backup_id)
            )
            return

        if data == b"admin_backup_list":
            await safe_edit(event, get_backup_list_text(), buttons=get_backup_list_keyboard())
            return

        if data.startswith(b"admin_backup_manage_"):
            bid = int(data.decode().split("admin_backup_manage_", 1)[1])
            rows = {b["id"]: b for b in list_backups_db()}
            b = rows.get(bid)
            if not b:
                await event.answer("❌ این بکاپ پیدا نشد.", alert=True)
                await safe_edit(event, get_backup_list_text(), buttons=get_backup_list_keyboard())
                return
            await safe_edit(event, get_backup_manage_text(b), buttons=get_backup_manage_keyboard(bid))
            return

        if data.startswith(b"admin_backup_download_"):
            bid = int(data.decode().split("admin_backup_download_", 1)[1])
            raw = get_backup_data_db(bid)
            if not raw:
                await event.answer("❌ این بکاپ پیدا نشد.", alert=True)
                return
            file_obj = io.BytesIO(raw)
            file_obj.name = f"novaself_backup_{bid}.json"
            try:
                await safe_call(bot.send_file, user_id, file_obj,
                                 caption=f"💾 بکاپ شماره {bid}")
                await event.answer("✅ فایل بکاپ برایتان ارسال شد.", alert=True)
            except Exception as e:
                log_internal_error("backup_download", e)
                await event.answer("❌ خطا در ارسال فایل.", alert=True)
            return

        if data.startswith(b"admin_backup_delete_confirm_"):
            bid = int(data.decode().split("admin_backup_delete_confirm_", 1)[1])
            success = delete_backup_db(bid)
            if success:
                log_admin_action(user_id, 0, "delete_backup", f"id={bid}")
                await event.answer("✅ بکاپ حذف شد.", alert=True)
            else:
                await event.answer("❌ این بکاپ پیدا نشد.", alert=True)
            await safe_edit(event, get_backup_list_text(), buttons=get_backup_list_keyboard())
            return

        if data.startswith(b"admin_backup_delete_"):
            bid = int(data.decode().split("admin_backup_delete_", 1)[1])
            await safe_edit(event,
                f"⚠️ حذف بکاپ شماره {bid}؟ این عملیات غیرقابل بازگشت است.",
                buttons=get_backup_delete_confirm_keyboard(bid)
            )
            return

        if data.startswith(b"admin_backup_restore_confirm_"):
            token = data.decode().split("admin_backup_restore_confirm_", 1)[1]

            if token == "uploaded":
                dump = backup_upload_pending.get(user_id)
                source_label = "فایل آپلودشده"
            else:
                bid = int(token)
                raw = get_backup_data_db(bid)
                dump = json.loads(raw.decode("utf-8")) if raw else None
                source_label = f"بکاپ شماره {bid}"

            if not dump:
                await event.answer("❌ این بکاپ دیگر در دسترس نیست.", alert=True)
                return

            await safe_edit(event, "⏳ در حال گرفتن بکاپ ایمنی از وضعیت فعلی...")
            safety_id, _ = create_backup_db(user_id, label="pre_restore_auto")
            if safety_id is None:
                await safe_edit(event,
                    "❌ ساخت بکاپ ایمنیِ قبل از بازیابی ناموفق بود؛ برای احتیاط، بازیابی متوقف شد.",
                    buttons=get_backup_menu_keyboard()
                )
                return

            await safe_edit(event, "⏳ در حال بازیابی...")
            success, summary, error = restore_backup_payload(dump)
            backup_upload_pending.pop(user_id, None)

            if not success:
                await safe_edit(event,
                    f"❌ خطا در بازیابی: {error}\n\n"
                    f"می‌توانید از بکاپ ایمنیِ شماره {safety_id} (که همین الان گرفته شد) برای برگشت استفاده کنید.",
                    buttons=get_backup_menu_keyboard()
                )
                return

            log_admin_action(user_id, 0, "restore_backup", f"source={source_label} safety_id={safety_id}")

            # بعد از بازیابی، کش‌های درون‌حافظه‌ای که از دیتابیس خوانده می‌شوند تازه
            # می‌شوند تا وضعیت زنده‌ی ربات با دیتابیس هماهنگ بماند (بدون نیاز به Restart).
            try:
                reload_join_channels_cache()
                load_reactions_cache()
                load_autoreplies_cache()
                load_feature_locks_cache()
                load_global_locks_cache()
            except Exception as e:
                log_internal_error("post_restore_cache_reload", e)

            summary_lines = "\n".join(f"▫️ {t}: {c}" for t, c in summary.items() if c)
            await safe_edit(event,
                f"✅ **بازیابی «{source_label}» با موفقیت انجام شد.**\n\n"
                f"ردیف‌های بازیابی‌شده:\n{summary_lines or '(هیچ)'}\n\n"
                f"🛟 بکاپ ایمنیِ قبل از بازیابی: شماره {safety_id}\n\n"
                "⚠️ توجه: کاربرانی که همین الان با سلف روشن در حافظه فعال بودند تا "
                "ری‌استارت بعدی ربات با همان وضعیت قبلی کار می‌کنند؛ اطلاعات پروفایل/"
                "الماس/تنظیماتشان از دفعه‌ی بعدی که تغییری بدهند با نسخه‌ی بازیابی‌شده "
                "همگام می‌شود.",
                buttons=get_backup_menu_keyboard()
            )
            return

        if data.startswith(b"admin_backup_restore_"):
            bid = int(data.decode().split("admin_backup_restore_", 1)[1])
            rows = {b["id"]: b for b in list_backups_db()}
            if bid not in rows:
                await event.answer("❌ این بکاپ پیدا نشد.", alert=True)
                return
            await safe_edit(event,
                get_backup_restore_confirm_text(f"شماره {bid}"),
                buttons=get_backup_restore_confirm_keyboard(str(bid))
            )
            return

        if data == b"admin_backup_upload":
            admin_action_data[user_id] = {"type": "backup_upload", "step": "get_file"}
            await safe_edit(event,
                "⬆️ **بارگذاری بکاپ**\n\n"
                "فایل JSON بکاپ (که قبلاً از همین ربات دانلود کرده‌اید) را ارسال کنید:",
                buttons=[[styled_button("➜ بازگشت", b"admin_backup", style=STYLE_OFF)]]
            )
            return

        # مدیریت کدهای هدیه
        if data == b"admin_giftcodes":
            await safe_edit(event, get_giftcodes_admin_text(), buttons=get_giftcodes_admin_keyboard())
            return

        if data == b"admin_giftcode_create":
            admin_action_data[user_id] = {"type": "create_giftcode", "step": "get_code"}
            await safe_edit(event,
                "➕ **ساخت کد هدیه**\n\n"
                "لطفاً یک کد دلخواه وارد کنید (فقط حروف/اعداد انگلیسی، بدون فاصله، حداکثر ۲۰ کاراکتر):",
                buttons=[[styled_button("➜ بازگشت", b"admin_giftcodes", style=STYLE_OFF)]]
            )
            return

        # صفحه‌ی مدیریت یک کد هدیه‌ی خاص
        if data.startswith(b"admin_giftcode_manage_"):
            code = data.decode().split("admin_giftcode_manage_", 1)[1]
            detail = get_gift_code_detail_db(code)
            if not detail:
                await event.answer("❌ کد پیدا نشد.", alert=True)
                await safe_edit(event, get_giftcodes_admin_text(), buttons=get_giftcodes_admin_keyboard())
                return
            await safe_edit(event, get_giftcode_manage_text(detail), buttons=get_giftcode_manage_keyboard(detail))
            return

        if data.startswith(b"admin_giftcode_editamount_"):
            code = data.decode().split("admin_giftcode_editamount_", 1)[1]
            if not get_gift_code_detail_db(code):
                await event.answer("❌ کد پیدا نشد.", alert=True)
                return
            admin_action_data[user_id] = {"type": "giftcode_edit_amount", "code": code, "step": "get_value"}
            await safe_edit(event,
                f"💎 **تغییر مقدار الماس کد** `{code}`\n\nمقدار جدید الماس را وارد کنید (عدد بزرگ‌تر از صفر):",
                buttons=[[styled_button("➜ بازگشت", f"admin_giftcode_manage_{code}".encode(), style=STYLE_OFF)]]
            )
            return

        if data.startswith(b"admin_giftcode_editexpiry_"):
            code = data.decode().split("admin_giftcode_editexpiry_", 1)[1]
            if not get_gift_code_detail_db(code):
                await event.answer("❌ کد پیدا نشد.", alert=True)
                return
            admin_action_data[user_id] = {"type": "giftcode_edit_expiry", "code": code, "step": "get_value"}
            await safe_edit(event,
                f"⏱ **تغییر انقضای کد** `{code}`\n\n"
                "چند روز دیگر این کد منقضی شود؟ (برای بدون انقضا عدد ۰ را ارسال کنید):",
                buttons=[[styled_button("➜ بازگشت", f"admin_giftcode_manage_{code}".encode(), style=STYLE_OFF)]]
            )
            return

        if data.startswith(b"admin_giftcode_delete_confirm_"):
            code = data.decode().split("admin_giftcode_delete_confirm_", 1)[1]
            success = delete_gift_code_db(code)
            if success:
                log_admin_action(user_id, 0, "delete_giftcode", f"code={code}")
                await event.answer("✅ کد هدیه حذف شد.", alert=True)
            else:
                await event.answer("❌ کد پیدا نشد یا قبلاً حذف شده.", alert=True)
            await safe_edit(event, get_giftcodes_admin_text(), buttons=get_giftcodes_admin_keyboard())
            return

        if data.startswith(b"admin_giftcode_delete_"):
            code = data.decode().split("admin_giftcode_delete_", 1)[1]
            if not get_gift_code_detail_db(code):
                await event.answer("❌ کد پیدا نشد.", alert=True)
                return
            await safe_edit(event,
                f"⚠️ **حذف کد هدیه** `{code}`\n\n"
                "این عملیات غیرقابل بازگشت است. آیا مطمئن هستید؟",
                buttons=get_giftcode_delete_confirm_keyboard(code)
            )
            return

        if data.startswith(b"admin_giftcode_toggle_"):
            code = data.decode().split("admin_giftcode_toggle_", 1)[1]
            codes = {c["code"]: c for c in list_gift_codes_db()}
            current = codes.get(code)
            if not current:
                await event.answer("❌ کد پیدا نشد.", alert=True)
                return
            new_state = not bool(current["is_active"])
            set_gift_code_active_db(code, new_state)
            log_admin_action(user_id, 0, "toggle_giftcode", f"code={code} active={new_state}")
            detail = get_gift_code_detail_db(code)
            if detail:
                await safe_edit(event, get_giftcode_manage_text(detail), buttons=get_giftcode_manage_keyboard(detail))
            else:
                await safe_edit(event, get_giftcodes_admin_text(), buttons=get_giftcodes_admin_keyboard())
            return

        # ====================================================================
        # ================ تأیید/رد سفارش‌های خرید الماس (توسط ادمین) ========
        # ====================================================================
        if data.startswith(b"order_approve_"):
            order_id = data.decode().split("order_approve_", 1)[1]
            success, status_code, order = approve_order_db(order_id, user_id)

            if status_code == "not_found":
                await event.answer("❌ سفارش پیدا نشد.", alert=True)
                return
            if status_code == "already_processed":
                state = order.get("status") if order else "?"
                await event.answer(f"⚠️ این سفارش قبلاً پردازش شده است (وضعیت فعلی: {state}).", alert=True)
                return
            if status_code == "user_not_found":
                await event.answer("❌ کاربر مربوط به این سفارش پیدا نشد.", alert=True)
                return
            if not success:
                await event.answer("❌ خطای دیتابیس رخ داد. دوباره تلاش کنید.", alert=True)
                return

            buyer_id = order["user_id"]
            if buyer_id in user_data:
                user_data[buyer_id]["diamonds"] = order["_new_balance"]

            log_diamond_transfer("PURCHASE", buyer_id, order["amount_diamonds"])
            log_admin_action(user_id, buyer_id, "approve_order", f"order={order_id} amount={order['amount_diamonds']}")

            await event.answer("✅ سفارش تأیید شد و الماس به حساب کاربر اضافه شد.", alert=True)
            try:
                await event.reply(
                    f"✅ سفارش `{order_id}` توسط ادمین تأیید و {format_diamonds(order['amount_diamonds'])} 💎 به کاربر اضافه شد."
                )
            except Exception:
                pass

            try:
                await safe_call(bot.send_message, buyer_id,
                    "✅ **سفارش شما با موفقیت تأیید شد.**\n\n"
                    f"💎 الماس دریافت شده : {format_diamonds(order['amount_diamonds'])}\n"
                    f"🧾 کد سفارش : {order_id}\n"
                    f"💰 مبلغ : {order['amount_toman']:,.0f} تومان\n\n"
                    "موجودی الماس شما با موفقیت شارژ شد."
                )
            except Exception as e:
                log_internal_error("notify_order_approved", e)
            return

        if data.startswith(b"order_reject_cancel"):
            admin_action_data.pop(user_id, None)
            await event.answer("عملیات لغو‌کردن سفارش خودش لغو شد.", alert=True)
            return

        if data.startswith(b"order_reject_"):
            order_id = data.decode().split("order_reject_", 1)[1]
            order = get_order_db(order_id)
            if not order:
                await event.answer("❌ سفارش پیدا نشد.", alert=True)
                return
            if order["status"] != "pending_review":
                await event.answer(f"⚠️ این سفارش قبلاً پردازش شده است (وضعیت فعلی: {order['status']}).", alert=True)
                return

            admin_action_data[user_id] = {"type": "reject_order", "order_id": order_id, "step": "get_reason"}
            await event.respond(
                "❌ **لغو سفارش**\n\n"
                "لطفاً دلیل لغو سفارش را به‌صورت متن ارسال کنید:",
                buttons=[[styled_button("➜ بازگشت", b"order_reject_cancel", style=STYLE_OFF)]]
            )
            return

        # لیست کاربران
        if data == b"admin_users_list":
            buttons = get_users_list_page(0)
            await safe_edit(event,
                "📋 **لیست کاربران:**\n\n"
                "برای مشاهده جزئیات هر کاربر روی آن کلیک کنید:",
                buttons=buttons
            )
            return

        # صفحه‌بندی لیست کاربران
        if data.startswith(b"admin_users_page_"):
            page = int(data.decode().split("_")[3])
            buttons = get_users_list_page(page)
            await safe_edit(event,
                "📋 **لیست کاربران:**\n\n"
                "برای مشاهده جزئیات هر کاربر روی آن کلیک کنید:",
                buttons=buttons
            )
            return

        # مشاهده جزئیات کاربر
        if data.startswith(b"admin_view_user_"):
            target_id = int(data.decode().split("_")[3])
            if target_id in user_data:
                user = user_data[target_id]

                status_text = status_icon(user["status"])
                font_name = FONT_NAMES.get(user["font_id"], "نامشخص")
                action_name = ACTIONS.get(user["active_action"], ("هیچ",))[0] if user["active_action"] != "none" else "هیچ"
                date_text = (
                    f"{status_icon(True)} {DATE_TYPE_NAMES.get(user.get('date_type', 'shamsi'), '؟')}"
                    if user.get("date_enabled") else status_icon(False)
                )
                textmode_text = TEXTMODE_NAMES.get(user.get("text_mode", 0), "خاموش") if user.get("text_mode") else "خاموش"
                secretary_text = (
                    f"{status_icon(True)} ({user.get('secretary_delay', 60)} ثانیه)"
                    if user.get("secretary_enabled") else status_icon(False)
                )
                username_display = f"@{user.get('username')}" if user.get("username") else "ثبت نشده"

                await safe_edit(event,
                    f"👤 **جزئیات کاربر:**\n\n"
                    f"🆔 شناسه: `{target_id}`\n"
                    f"💡 یوزرنیم: {username_display}\n"
                    f"📊 وضعیت: {status_text}\n"
                    f"💎 موجودی الماس: {format_diamonds(user.get('diamonds', 0))} ({format_toman(user.get('diamonds', 0))} تومان)\n"
                    f"👥 تعداد رفرال: {user.get('referral_count', 0)}\n"
                    f"🔤 فونت: {font_name}\n"
                    f"⌚ ساعت نام: {status_icon(user['name_time'])}\n"
                    f"⌚ ساعت بیو: {status_icon(user['bio_time'])}\n"
                    f"📅 تاریخ: {date_text}\n"
                    f"🖊️ حالت متن: {textmode_text}\n"
                    f"🧑‍💼 منشی پیوی: {secretary_text}\n"
                    f"🎭 اکشن: {action_name}\n"
                    f"📅 تاریخ ثبت: {user.get('joined_at', 'نامشخص')}\n\n"
                    f"💡 برای مدیریت این کاربر از دکمه‌های زیر استفاده کنید:",
                    buttons=get_user_detail_buttons(target_id)
                )
            else:
                await event.answer("❌ کاربر پیدا نشد!", alert=True)
            return

        # تغییر وضعیت کاربر توسط ادمین
        # مدیریت قابلیت‌های یک کاربر توسط ادمین (بند ۷)
        if data.startswith(b"admin_features_"):
            target_id = int(data.decode().split("admin_features_", 1)[1])
            if target_id not in user_data:
                await event.answer("❌ کاربر پیدا نشد!", alert=True)
                return
            await safe_edit(event,
                get_user_features_text(target_id),
                buttons=get_user_features_keyboard(target_id, user_data[target_id])
            )
            return

        # ====================================================================
        # ================ قفل کردن قابلیت‌ها برای یک کاربر خاص ==============
        # ====================================================================
        if data.startswith(b"admin_lock_features_"):
            target_id = int(data.decode().split("admin_lock_features_", 1)[1])
            if target_id not in user_data:
                await event.answer("❌ کاربر پیدا نشد!", alert=True)
                return
            await safe_edit(event, get_lock_features_text(target_id), buttons=get_lock_features_keyboard(target_id))
            return

        if data.startswith(b"admin_togglelock_"):
            remainder = data.decode().split("admin_togglelock_", 1)[1]
            key, _, target_id_str = remainder.rpartition("_")

            try:
                target_id = int(target_id_str)
            except ValueError:
                await event.answer("❌ عملیات نامعتبر است.", alert=True)
                return

            if key not in FEATURE_LOCK_LABELS or target_id not in user_data:
                await event.answer("❌ عملیات نامعتبر است.", alert=True)
                return

            currently_locked = key in feature_locks.get(target_id, set())
            if currently_locked:
                unlock_feature_db(target_id, key)
                feature_locks.get(target_id, set()).discard(key)
                log_admin_action(user_id, target_id, "unlock_feature", key)
            else:
                lock_feature_db(target_id, key)
                feature_locks.setdefault(target_id, set()).add(key)
                log_admin_action(user_id, target_id, "lock_feature", key)

            await safe_edit(event, get_lock_features_text(target_id), buttons=get_lock_features_keyboard(target_id))
            return

        if data.startswith(b"admin_togglefeat_"):
            remainder = data.decode().split("admin_togglefeat_", 1)[1]
            field, _, target_id_str = remainder.rpartition("_")
            target_id = int(target_id_str)

            if target_id not in user_data or field not in dict(ADMIN_MANAGEABLE_FEATURES):
                await event.answer("❌ عملیات نامعتبر است.", alert=True)
                return

            target_user = user_data[target_id]
            target_user[field] = not target_user.get(field)
            save_user(target_id, target_user)
            log_admin_action(user_id, target_id, "toggle_feature", f"{field}={target_user[field]}")

            await safe_edit(event,
                get_user_features_text(target_id),
                buttons=get_user_features_keyboard(target_id, target_user)
            )
            return

        if data.startswith(b"admin_userfont_"):
            target_id = int(data.decode().split("admin_userfont_", 1)[1])
            if target_id not in user_data:
                await event.answer("❌ کاربر پیدا نشد!", alert=True)
                return
            await safe_edit(event, "🔤 **فونت ساعت این کاربر**",
                             buttons=get_admin_font_grid_keyboard(target_id, user_data[target_id].get("font_id", 1)))
            return

        if data.startswith(b"admin_setfont_"):
            parts = data.decode().split("_")
            target_id, font_id = int(parts[-2]), int(parts[-1])
            if target_id not in user_data:
                await event.answer("❌ کاربر پیدا نشد!", alert=True)
                return
            user_data[target_id]["font_id"] = font_id
            save_user(target_id, user_data[target_id])
            log_admin_action(user_id, target_id, "set_font", str(font_id))
            await safe_edit(event, "🔤 **فونت ساعت این کاربر**",
                             buttons=get_admin_font_grid_keyboard(target_id, font_id))
            return

        if data.startswith(b"admin_userdatefont_"):
            target_id = int(data.decode().split("admin_userdatefont_", 1)[1])
            if target_id not in user_data:
                await event.answer("❌ کاربر پیدا نشد!", alert=True)
                return
            await safe_edit(event, "🔤 **فونت تاریخ این کاربر**",
                             buttons=get_admin_datefont_grid_keyboard(target_id, user_data[target_id].get("date_font", 1)))
            return

        if data.startswith(b"admin_setdatefont_"):
            parts = data.decode().split("_")
            target_id, font_id = int(parts[-2]), int(parts[-1])
            if target_id not in user_data:
                await event.answer("❌ کاربر پیدا نشد!", alert=True)
                return
            user_data[target_id]["date_font"] = font_id
            save_user(target_id, user_data[target_id])
            log_admin_action(user_id, target_id, "set_date_font", str(font_id))
            await safe_edit(event, "🔤 **فونت تاریخ این کاربر**",
                             buttons=get_admin_datefont_grid_keyboard(target_id, font_id))
            return

        if data.startswith(b"admin_usertextmode_"):
            target_id = int(data.decode().split("admin_usertextmode_", 1)[1])
            if target_id not in user_data:
                await event.answer("❌ کاربر پیدا نشد!", alert=True)
                return
            await safe_edit(event, "🖊️ **حالت متن این کاربر**",
                             buttons=get_admin_textmode_grid_keyboard(target_id, user_data[target_id].get("text_mode", 0)))
            return

        if data.startswith(b"admin_settextmode_"):
            parts = data.decode().split("_")
            target_id, mode_id = int(parts[-2]), int(parts[-1])
            if target_id not in user_data:
                await event.answer("❌ کاربر پیدا نشد!", alert=True)
                return
            user_data[target_id]["text_mode"] = mode_id
            save_user(target_id, user_data[target_id])
            log_admin_action(user_id, target_id, "set_text_mode", str(mode_id))
            await safe_edit(event, "🖊️ **حالت متن این کاربر**",
                             buttons=get_admin_textmode_grid_keyboard(target_id, mode_id))
            return

        if data.startswith(b"admin_useractions_"):
            target_id = int(data.decode().split("admin_useractions_", 1)[1])
            if target_id not in user_data:
                await event.answer("❌ کاربر پیدا نشد!", alert=True)
                return
            await safe_edit(event, "🎭 **اکشن این کاربر**",
                             buttons=get_admin_actions_grid_keyboard(target_id, user_data[target_id].get("active_action", "none")))
            return

        if data.startswith(b"admin_setaction_"):
            raw = data.decode()[len("admin_setaction_"):]
            target_id_str, action_key = raw.rsplit("_", 1)
            target_id = int(target_id_str)
            if target_id not in user_data or action_key not in ACTIONS:
                await event.answer("❌ عملیات نامعتبر است.", alert=True)
                return
            user_data[target_id]["active_action"] = action_key
            save_user(target_id, user_data[target_id])
            log_admin_action(user_id, target_id, "set_action", action_key)
            await safe_edit(event, "🎭 **اکشن این کاربر**",
                             buttons=get_admin_actions_grid_keyboard(target_id, action_key))
            return

        if data.startswith(b"admin_toggle_user_"):
            target_id = int(data.decode().split("_")[3])
            if target_id in user_data:
                user = user_data[target_id]
                user["status"] = not user["status"]

                if user["status"]:
                    if float(user.get("diamonds", 0)) <= 0:
                        user["status"] = False
                        await event.answer("💎 موجودی الماس این کاربر کافی نیست.", alert=True)
                    else:
                        client = await start_self_client(target_id, user["session"])
                        if not client:
                            user["status"] = False
                            await event.answer("❌ خطا در راه‌اندازی (نشست نامعتبر است)", alert=True)
                        else:
                            await event.answer("✅ وضعیت کاربر تغییر کرد!", alert=True)
                else:
                    await stop_self_client(target_id)
                    await event.answer("✅ وضعیت کاربر تغییر کرد!", alert=True)

                save_user(target_id, user)
                log_admin_action(user_id, target_id, "toggle_status", f"new_status={user['status']}")

                await safe_edit(event,
                    f"👤 **جزئیات کاربر:**\n\n"
                    f"🆔 شناسه: `{target_id}`\n"
                    f"📊 وضعیت جدید: {status_icon(user['status'])}",
                    buttons=get_user_detail_buttons(target_id)
                )
            return

        # حذف کاربر توسط ادمین
        if data.startswith(b"admin_delete_user_"):
            target_id = int(data.decode().split("_")[3])
            if target_id in user_data:
                await stop_self_client(target_id)
                delete_user_db(target_id)
                del user_data[target_id]
                log_admin_action(user_id, target_id, "delete_user", "")

                await event.answer("✅ کاربر حذف شد!", alert=True)
                await safe_edit(event,
                    "🗑️ **کاربر با موفقیت حذف شد.**",
                    buttons=[styled_button("➜ بازگشت", b"admin_users_list", style=STYLE_OFF)]
                )
            return

        # ارسال پیام به کاربر خاص
        if data.startswith(b"admin_send_to_user_"):
            target_id = int(data.decode().split("_")[4])
            broadcast_data[user_id] = {
                "type": "single",
                "target_id": target_id,
                "step": "get_message"
            }
            await safe_edit(event,
                f"📨 **ارسال پیام به کاربر {target_id}**\n\n"
                "لطفاً پیام خود را ارسال کنید (متن، عکس، ویدیو، فایل، ویس، Video Note، استیکر، GIF، "
                "Poll، Contact، Location یا یک پیام Forward‌شده — همه پشتیبانی می‌شوند).\n"
                "برای لغو عملیات، /cancel را بفرستید."
            )
            return

        # ارسال پیام همگانی
        if data == b"admin_broadcast":
            broadcast_data[user_id] = {
                "type": "broadcast",
                "step": "get_message"
            }
            await safe_edit(event,
                "📨 **ارسال پیام همگانی**\n\n"
                "⚠️ این پیام برای **همه کاربران** ارسال خواهد شد!\n\n"
                "لطفاً پیام خود را ارسال کنید (متن، عکس، ویدیو، فایل، ویس، Video Note، استیکر، GIF، "
                "Poll، Contact، Location یا یک پیام Forward‌شده — همه پشتیبانی می‌شوند).\n"
                "برای لغو عملیات، /cancel را بفرستید."
            )
            return

        # جستجوی کاربر
        if data == b"admin_search_user":
            broadcast_data[user_id] = {
                "type": "search",
                "step": "get_user_id"
            }
            await safe_edit(event,
                "🔍 **جستجوی کاربر**\n\n"
                "لطفاً شناسه (ID) کاربر مورد نظر را وارد کنید:"
            )
            return

        # نمایش لاگ‌های مدیریتی اخیر
        if data == b"admin_logs":
            logs = get_recent_admin_logs(15)
            if not logs:
                log_text = "📜 **لاگ مدیریتی**\n\nهنوز هیچ عملیاتی ثبت نشده است."
            else:
                lines = ["📜 **۱۵ عملیات مدیریتی اخیر:**\n"]
                for admin_id_l, target_id_l, action_l, details_l, created_at_l in logs:
                    ts = created_at_l.strftime("%Y-%m-%d %H:%M") if created_at_l else "؟"
                    lines.append(f"▫️ [{ts}] ادمین {admin_id_l} ← کاربر {target_id_l} | {action_l} {details_l}")
                log_text = "\n".join(lines)
            await safe_edit(event, log_text, buttons=[styled_button("➜ بازگشت", b"admin_panel", style=STYLE_OFF)])
            return

        # ====================================================================
        # ============ مدیریت پیام‌های ارسال‌شده توسط ادمین (بخش دوازدهم) ====
        # ====================================================================
        if data == b"admin_messages_list":
            await safe_edit(event, get_broadcasts_admin_text(), buttons=get_broadcasts_admin_keyboard())
            return

        if data.startswith(b"admin_message_view_"):
            broadcast_id = data.decode().split("admin_message_view_", 1)[1]
            rows = {r["broadcast_id"]: r for r in list_broadcasts_db(limit=100)}
            record = rows.get(broadcast_id)
            if not record:
                await event.answer("❌ این پیام پیدا نشد (شاید قبلاً حذف شده).", alert=True)
                await safe_edit(event, get_broadcasts_admin_text(), buttons=get_broadcasts_admin_keyboard())
                return
            deliveries = get_broadcast_deliveries_db(broadcast_id)
            await safe_edit(event, get_broadcast_detail_text(record, len(deliveries)),
                             buttons=get_broadcast_detail_keyboard(broadcast_id))
            return

        if data.startswith(b"admin_message_delete_"):
            broadcast_id = data.decode().split("admin_message_delete_", 1)[1]
            deliveries = get_broadcast_deliveries_db(broadcast_id)

            if not deliveries:
                delete_broadcast_record_db(broadcast_id)
                await event.answer("این پیام دیگر گیرنده‌ای ندارد؛ رکورد حذف شد.", alert=True)
                await safe_edit(event, get_broadcasts_admin_text(), buttons=get_broadcasts_admin_keyboard())
                return

            await safe_edit(event, "⏳ در حال حذف پیام از چت کاربران...")

            deleted_count = 0
            failed_count = 0
            for d in deliveries:
                # هر خطا (کاربر پیام را قبلاً حذف کرده، بلاک کرده، ربات دسترسی حذف ندارد،
                # پیام قدیمی است و ...) فقط برای همان کاربر ثبت می‌شود و ادامه‌ی حذف بقیه
                # را متوقف نمی‌کند (بند ۲۷ آپدیت).
                try:
                    await bot.delete_messages(d["chat_id"], [d["message_id"]])
                    deleted_count += 1
                except Exception as e:
                    failed_count += 1
                    log_internal_error("delete_broadcast_message", f"broadcast={broadcast_id} chat={d['chat_id']} err={e}")

            delete_broadcast_record_db(broadcast_id)
            log_admin_action(user_id, 0, "delete_broadcast", f"broadcast={broadcast_id} deleted={deleted_count} failed={failed_count}")

            await safe_edit(event,
                "🗑 **حذف پیام کامل شد.**\n\n"
                f"✅ حذف‌شده از چت کاربران: {deleted_count}\n"
                f"❌ ناموفق (قبلاً حذف‌شده/بلاک/دسترسی نبود): {failed_count}",
                buttons=[styled_button("➜ بازگشت", b"admin_messages_list", style=STYLE_OFF)]
            )
            return

        # افزایش الماس
        if data.startswith(b"admin_add_diamond_"):
            target_id = int(data.decode().split("_")[3])
            admin_action_data[user_id] = {"type": "add_diamond", "target_id": target_id, "step": "get_amount"}
            await safe_edit(event,
                f"➕ **افزایش الماس کاربر {target_id}**\n\n"
                "لطفاً مقدار الماس موردنظر برای افزایش را وارد کنید (عدد مثبت):"
            )
            return

        # کاهش الماس
        if data.startswith(b"admin_sub_diamond_"):
            target_id = int(data.decode().split("_")[3])
            admin_action_data[user_id] = {"type": "sub_diamond", "target_id": target_id, "step": "get_amount"}
            await safe_edit(event,
                f"➖ **کاهش الماس کاربر {target_id}**\n\n"
                "لطفاً مقدار الماس موردنظر برای کاهش را وارد کنید (عدد مثبت):"
            )
            return

        # تغییر تعداد رفرال
        if data.startswith(b"admin_set_referral_"):
            target_id = int(data.decode().split("_")[3])
            admin_action_data[user_id] = {"type": "set_referral", "target_id": target_id, "step": "get_amount"}
            await safe_edit(event,
                f"👥 **تغییر تعداد رفرال کاربر {target_id}**\n\n"
                "لطفاً تعداد رفرال جدید را وارد کنید (عدد صفر یا مثبت):"
            )
            return

        # بروزرسانی همه کاربران
        if data == b"admin_refresh_all":
            await safe_edit(event, "⏳ در حال بروزرسانی اطلاعات همه کاربران...")

            for uid, user in list(user_data.items()):
                if user["status"] and user["session"]:
                    await stop_self_client(uid)
                    client = await start_self_client(uid, user["session"])
                    if not client:
                        user["status"] = False
                        save_user(uid, user)
                        logging.error(f"❌ خطا در بروزرسانی کاربر {uid}")

            await safe_edit(event,
                "✅ **همه کاربران با موفقیت بروزرسانی شدند!**",
                buttons=[styled_button("➜ بازگشت", b"admin_panel", style=STYLE_OFF)]
            )
            return

    # ====== منوی کاربر ======

    if data == b"start_gen_fast":
        generator_data[user_id] = {
            "step": "get_phone",
            "phone": None,
            "phone_code_hash": None,
            "code_buffer": "",
            "recovery": False
        }
        await safe_edit(event,
            "📞 **مرحله اول: وارد کردن شماره**\n\n"
            "لطفاً شماره تلفن خود را به همراه کد کشور وارد کنید.\n"
            "مثال: `+989123456789`",
            buttons=[[styled_button("❌ لغو نصب", b"install_cancel", style=STYLE_OFF)]]
        )
        return

    if data == b"install_cancel":
        if user_id in generator_data:
            del generator_data[user_id]
        if user_id in active_signins:
            try:
                await active_signins[user_id].disconnect()
            except Exception as e:
                log_internal_error("cancel_install_disconnect", e)
            del active_signins[user_id]
        await safe_edit(event, "❌ عملیات نصب/بازیابی نوا سلف لغو شد.", buttons=get_start_root_keyboard(user))
        return

    if data == b"account_recover_session":
        await safe_edit(event,
            "آیا مطمئن هستید که می‌خواهید نشست خود را بازیابی کنید؟\n\n"
            "⚠️ اطلاعات حساب حذف نمی‌شود اما نیاز به ورود دوباره دارید.",
            buttons=[
                [styled_button("🟢 تایید", b"account_recover_session_confirmed", style=STYLE_ON)],
                [styled_button("➜ بازگشت", b"start_account", style=STYLE_OFF)]
            ]
        )
        return

    if data == b"account_recover_session_confirmed":
        generator_data[user_id] = {
            "step": "get_phone",
            "phone": None,
            "phone_code_hash": None,
            "code_buffer": "",
            "recovery": True
        }
        await safe_edit(event,
            "🔄 **بازیابی نشست**\n\n"
            "موجودی، تنظیمات و رفرال شما دست‌نخورده باقی می‌ماند و فقط نشستِ اتصال حساب "
            "دوباره ساخته می‌شود.\n\n"
            "لطفاً شماره تلفن حساب خود را به همراه کد کشور وارد کنید.\n"
            "مثال: `+989123456789`",
            buttons=[[styled_button("❌ لغو نصب", b"install_cancel", style=STYLE_OFF)]]
        )
        return

    if user_id in generator_data and generator_data[user_id]["step"] == "get_code":
        generator = generator_data[user_id]

        if data.startswith(b"k_"):
            action = data.decode().split("_")[1]

            if action.isdigit():
                if len(generator["code_buffer"]) < 5:
                    generator["code_buffer"] += action

                await safe_edit(event,
                    "📩 **مرحله دوم: وارد کردن کد تایید**\n\n"
                    "کد ۵ رقمی ارسال شده به تلگرام خود را وارد کنید:",
                    buttons=get_code_keyboard(generator["code_buffer"])
                )

            elif action == "clear":
                generator["code_buffer"] = ""
                await safe_edit(event,
                    "📩 **مرحله دوم: وارد کردن کد تایید**\n\n"
                    "کد ۵ رقمی ارسال شده به تلگرام خود را وارد کنید:",
                    buttons=get_code_keyboard(generator["code_buffer"])
                )

            elif action == "submit":
                if len(generator["code_buffer"]) < 5:
                    await event.answer("⚠️ لطفاً کد ۵ رقمی را کامل وارد کنید!", alert=True)
                    return

                await safe_edit(event, "⏳ در حال بررسی کد و ورود به حساب...")
                await process_code_signin(event, user_id, generator["code_buffer"])

            return

    if user_id not in user_data:
        return

    user = user_data[user_id]

    if data == b"back_to_main":
        # نگه‌داشته شده برای سازگاری با هر پیام قدیمیِ باز، اما دیگر از هیچ دکمه‌ی
        # جدیدی صدا زده نمی‌شود؛ به ریشه‌ی مناسب بسته به بستر (پنل خصوصی/عمومی) می‌رود.
        if panel_owner_id is not None:
            await safe_edit(event, PANEL_TEXT, buttons=get_panel_root_keyboard(user))
        else:
            await safe_edit(event, get_start_root_text(), buttons=get_start_root_keyboard(user))
        return

    if data == b"panel_root":
        await safe_edit(event, PANEL_TEXT, buttons=get_panel_root_keyboard(user))
        return

    if data == b"settings_root":
        await safe_edit(event, PANEL_TEXT, buttons=get_settings_root_keyboard(user_id))
        return

    if data == b"panel_account":
        await safe_edit(event, get_panel_account_text(user_id, user), buttons=get_panel_account_keyboard(user_id, user))
        return

    if data == b"start_root":
        await safe_edit(event, get_start_root_text(), buttons=get_start_root_keyboard(user))
        return

    if data == b"start_manage_self":
        await safe_edit(event, get_start_manage_self_text(user), buttons=get_start_manage_self_keyboard(user))
        return

    if data == b"start_account":
        await safe_edit(event, get_start_account_text(user_id, user), buttons=get_start_account_keyboard())
        return

    if data == b"start_about":
        await safe_edit(event, get_start_about_text(), buttons=get_start_about_keyboard())
        return

    if data == b"menu_time":
        if is_feature_locked(user_id, "time"):
            await event.answer("این قابلیت برای شما قفل شده است.", alert=True)
            return
        await safe_edit(event,
            get_time_menu_text(user),
            buttons=get_time_menu_keyboard(user)
        )
        return

    if data == b"menu_fonts":
        await safe_edit(event,
            get_fonts_menu_text(user),
            buttons=get_fonts_menu_keyboard(user["font_id"])
        )
        return

    if data == b"menu_actions":
        if is_feature_locked(user_id, "actions"):
            await event.answer("این قابلیت برای شما قفل شده است.", alert=True)
            return
        await safe_edit(event,
            "🎭 **مدیریت اکشن‌های فیک**\n\n"
            "با انتخاب هر گزینه، وضعیت شما به‌صورت مداوم برای دیگران نمایش داده می‌شود:",
            buttons=get_actions_menu_keyboard(user["active_action"])
        )
        return

    if data == b"menu_date":
        if is_feature_locked(user_id, "date"):
            await event.answer("این قابلیت برای شما قفل شده است.", alert=True)
            return
        await safe_edit(event,
            get_date_menu_text(user),
            buttons=get_date_menu_keyboard(user)
        )
        return

    if data == b"toggle_date_enabled":
        user["date_enabled"] = not user.get("date_enabled", False)
        save_user(user_id, user)
        log_settings_change(user_id, "date_enabled", user["date_enabled"])
        await safe_edit(event,
            get_date_menu_text(user),
            buttons=get_date_menu_keyboard(user)
        )
        return

    if data.startswith(b"setdatetype_"):
        date_type = data.decode().split("_", 1)[1]
        if date_type in DATE_TYPE_NAMES:
            user["date_type"] = date_type
            save_user(user_id, user)
            log_settings_change(user_id, "date_type", date_type)
        await safe_edit(event,
            get_date_menu_text(user),
            buttons=get_date_menu_keyboard(user)
        )
        return

    if data == b"menu_date_fonts":
        await safe_edit(event,
            get_date_fonts_menu_text(user),
            buttons=get_date_fonts_menu_keyboard(user.get("date_font", 1))
        )
        return

    if data.startswith(b"setdatefont_"):
        font_id = int(data.decode().split("_")[1])
        user["date_font"] = font_id
        save_user(user_id, user)
        log_settings_change(user_id, "date_font", font_id)
        await safe_edit(event,
            get_date_fonts_menu_text(user),
            buttons=get_date_fonts_menu_keyboard(font_id)
        )
        return

    if data == b"menu_textmode":
        if is_feature_locked(user_id, "textmode"):
            await event.answer("این قابلیت برای شما قفل شده است.", alert=True)
            return
        await safe_edit(event,
            "🖊️ **حالت متن**\n\n"
            "با انتخاب یکی از حالت‌های زیر، تمام پیام‌های متنی شما بلافاصله پس از ارسال "
            "با همان قالب ویرایش می‌شوند. برای غیرفعال کردن، دوباره روی گزینه فعال بزنید.",
            buttons=get_textmode_menu_keyboard(user.get("text_mode", 0))
        )
        return

    if data.startswith(b"settextmode_"):
        mode_id = int(data.decode().split("_")[1])
        if user.get("text_mode") == mode_id:
            user["text_mode"] = 0
        else:
            user["text_mode"] = mode_id
        save_user(user_id, user)
        await safe_edit(event,
            "🖊️ **حالت متن**\n\n"
            "✅ حالت متن با موفقیت بروزرسانی شد.",
            buttons=get_textmode_menu_keyboard(user.get("text_mode", 0))
        )
        return

    if data.startswith(b"setfont_"):
        font_id = int(data.decode().split("_")[1])
        user["font_id"] = font_id
        save_user(user_id, user)
        log_settings_change(user_id, "font_id", font_id)

        await safe_edit(event,
            get_fonts_menu_text(user),
            buttons=get_fonts_menu_keyboard(font_id)
        )
        return

    if data.startswith(b"setact_"):
        action_key = data.decode().split("_")[1]

        if user["active_action"] == action_key:
            user["active_action"] = "none"
        else:
            user["active_action"] = action_key

        save_user(user_id, user)

        await safe_edit(event,
            "🎭 **مدیریت اکشن‌های فیک**\n\n"
            f"✅ وضعیت اکشن با موفقیت تغییر یافت.",
            buttons=get_actions_menu_keyboard(user["active_action"])
        )
        return

    if data == b"toggle_status":
        user["status"] = not user["status"]

        if user["status"]:
            if float(user.get("diamonds", 0)) <= 0:
                user["status"] = False
                await event.answer(
                    "💎 موجودی الماس شما کافی نیست.\n\nابتدا از بخش «حساب کاربری» موجودی خود را افزایش دهید.",
                    alert=True
                )
            else:
                client = await start_self_client(user_id, user["session"])
                if not client:
                    user["status"] = False
                    await event.answer("❌ نشست منقضی شده یا خطا در اتصال!", alert=True)
        else:
            await stop_self_client(user_id)

        save_user(user_id, user)
        log_self_toggle(user_id, user["status"])

        # دکمه‌ی «وضعیت سلف» هم در ریشه‌ی `.پنل` و هم در «مدیریت سلف» (/start) وجود
        # دارد؛ بسته به بستری که از آن کلیک شده (پنل خصوصی یا چت عادی بات)، همان
        # صفحه دوباره با وضعیت تازه رندر می‌شود.
        if panel_owner_id is not None:
            await safe_edit(event, PANEL_TEXT, buttons=get_panel_root_keyboard(user))
        else:
            await safe_edit(event, get_start_manage_self_text(user), buttons=get_start_manage_self_keyboard(user))
        return

    if data == b"toggle_name_time":
        user["name_time"] = not user["name_time"]
        save_user(user_id, user)
        log_settings_change(user_id, "name_time", user["name_time"])

        await safe_edit(event,
            get_time_menu_text(user),
            buttons=get_time_menu_keyboard(user)
        )
        return

    if data == b"toggle_bio_time":
        user["bio_time"] = not user["bio_time"]
        save_user(user_id, user)
        log_settings_change(user_id, "bio_time", user["bio_time"])

        await safe_edit(event,
            get_time_menu_text(user),
            buttons=get_time_menu_keyboard(user)
        )
        return

    # ====================================================================
    # ====================== سیستم خرید الماس (State Machine) ==========
    # ====================================================================
    if data == b"account_buy_diamond":
        purchase_data[user_id] = {"buffer": ""}
        user["step"] = "buy_amount"
        await safe_edit(event,
            "💎 **خرید الماس**\n\n"
            "تعداد الماسی که می‌خواهید خریداری کنید را با کیبورد زیر وارد کنید:",
            buttons=get_buy_amount_keyboard("")
        )
        return

    # این هندلر فقط باید وقتی که کاربر واقعاً در مرحله‌ی وارد کردن مقدار خرید است
    # به کلیک‌های کیپد واکنش نشان بدهد؛ در غیر این صورت (مثلاً اگر کاربر از یک پیام
    # قدیمی روی این دکمه‌ها بزند) بی‌صدا نادیده گرفته می‌شود تا با Stateهای دیگر تداخل نکند.
    if data.startswith(b"buy_k_") and user.get("step") == "buy_amount":
        pending = purchase_data.setdefault(user_id, {"buffer": ""})
        buffer_str = pending.get("buffer", "")
        action = data.decode().split("buy_k_", 1)[1]

        if action == "back":
            buffer_str = buffer_str[:-1]
        elif action == "submit":
            try:
                amount = int(buffer_str)
                if amount <= 0:
                    raise ValueError
            except ValueError:
                await event.answer("❌ لطفاً یک عدد معتبر و بزرگ‌تر از صفر وارد کنید.", alert=True)
                return

            pending["amount"] = amount
            pending["toman"] = amount * DIAMOND_PRICE_TOMAN
            user["step"] = "buy_confirm"
            await safe_edit(event, get_buy_confirm_text(amount), buttons=get_buy_confirm_keyboard())
            return
        elif action.isdigit() and len(buffer_str) < MAX_BUY_DIAMONDS_DIGITS:
            buffer_str += action

        pending["buffer"] = buffer_str
        await safe_edit(event, "💎 **خرید الماس**\n\nتعداد الماسی که می‌خواهید خریداری کنید را با کیبورد زیر وارد کنید:",
                         buttons=get_buy_amount_keyboard(buffer_str))
        return

    if data == b"buy_amount_back" and user.get("step") == "buy_confirm":
        pending = purchase_data.setdefault(user_id, {"buffer": ""})
        user["step"] = "buy_amount"
        await safe_edit(event, "💎 **خرید الماس**\n\nتعداد الماسی که می‌خواهید خریداری کنید را با کیبورد زیر وارد کنید:",
                         buttons=get_buy_amount_keyboard(pending.get("buffer", "")))
        return

    if data == b"buy_amount_confirm" and user.get("step") == "buy_confirm":
        pending = purchase_data.get(user_id)
        if not pending or "amount" not in pending:
            user["step"] = "managed"
            await safe_edit(event, "❌ عملیات منقضی شده. دوباره از منوی «خرید الماس» اقدام کنید.",
                             buttons=[[styled_button("➜ بازگشت", b"start_account", style=STYLE_OFF)]])
            return
        user["step"] = "buy_payment"
        await safe_edit(event, get_buy_payment_text(pending["amount"]), buttons=get_buy_payment_keyboard())
        return

    if data == b"buy_payment_back" and user.get("step") == "buy_payment":
        pending = purchase_data.get(user_id) or {}
        user["step"] = "buy_confirm"
        await safe_edit(event, get_buy_confirm_text(pending.get("amount", 0)), buttons=get_buy_confirm_keyboard())
        return

    if data == b"buy_pay_gateway" and user.get("step") == "buy_payment":
        await event.answer("🔒 درگاه پرداخت در حال حاضر فعال نیست. لطفاً از «کارت به کارت» استفاده کنید.", alert=True)
        return

    if data == b"buy_pay_card" and user.get("step") == "buy_payment":
        pending = purchase_data.get(user_id)
        if not pending or "amount" not in pending:
            user["step"] = "managed"
            await safe_edit(event, "❌ عملیات منقضی شده. دوباره از منوی «خرید الماس» اقدام کنید.",
                             buttons=[[styled_button("➜ بازگشت", b"start_account", style=STYLE_OFF)]])
            return
        pending["payment_method"] = "card_to_card"
        pending["invoice_created_at"] = tehran_now()
        user["step"] = "buy_invoice"
        await safe_edit(event,
            get_buy_invoice_text("(بعد از تأیید ساخته می‌شود)", user_id, user.get("username"),
                                  pending["amount"], pending["toman"], pending["invoice_created_at"]),
            buttons=get_buy_invoice_keyboard()
        )
        return

    if data == b"buy_invoice_back" and user.get("step") == "buy_invoice":
        pending = purchase_data.get(user_id) or {}
        user["step"] = "buy_payment"
        await safe_edit(event, get_buy_payment_text(pending.get("amount", 0)), buttons=get_buy_payment_keyboard())
        return

    if data == b"buy_invoice_confirm" and user.get("step") == "buy_invoice":
        pending = purchase_data.get(user_id)
        if not pending or "amount" not in pending:
            user["step"] = "managed"
            await safe_edit(event, "❌ عملیات منقضی شده. دوباره از منوی «خرید الماس» اقدام کنید.",
                             buttons=[[styled_button("➜ بازگشت", b"start_account", style=STYLE_OFF)]])
            return

        # اگر سفارش قبلاً ساخته شده (مثلاً کاربر چندبار روی تأیید زده)، دوباره ساخته نمی‌شود
        if not pending.get("order_id"):
            order_id = create_order_db(user_id, user.get("username"), pending["amount"], pending["toman"], "card_to_card")
            if not order_id:
                await event.answer("❌ خطا در ساخت سفارش. دوباره تلاش کنید.", alert=True)
                return
            pending["order_id"] = order_id
            logging.info(f"🧾 سفارش جدید {order_id} توسط کاربر {user_id} (مقدار: {pending['amount']} الماس)")

        user["step"] = "buy_receipt"
        await safe_edit(event, get_buy_waiting_receipt_text(pending["toman"]), buttons=get_buy_waiting_receipt_keyboard())
        return

    if data == b"buy_receipt_back" and user.get("step") == "buy_receipt":
        pending = purchase_data.get(user_id) or {}
        user["step"] = "buy_invoice"
        order = get_order_db(pending.get("order_id")) if pending.get("order_id") else None
        created_at = order["created_at"] if order else pending.get("invoice_created_at", tehran_now())
        await safe_edit(event,
            get_buy_invoice_text(pending.get("order_id", "—"), user_id, user.get("username"),
                                  pending.get("amount", 0), pending.get("toman", 0), created_at),
            buttons=get_buy_invoice_keyboard()
        )
        return

    if data == b"account_delete_confirm":
        await safe_edit(event,
            "⚠️ **هشدار**\n\n"
            "با حذف حساب کاربری، تمام اطلاعات شما شامل تنظیمات، سشن، داده‌های ذخیره‌شده و "
            "سایر اطلاعات (از جمله موجودی الماس و رفرال) به‌صورت دائمی از دیتابیس حذف خواهند شد.\n\n"
            "این عملیات غیرقابل بازگشت است.",
            buttons=get_account_delete_warning_keyboard()
        )
        return

    if data == b"account_delete_final":
        await stop_self_client(user_id)
        delete_user_db(user_id)
        del user_data[user_id]
        transfer_data.pop(user_id, None)

        await safe_edit(event,
            "🗑️ **حساب کاربری با موفقیت و به‌صورت کامل حذف شد.**\n\n"
            "برای شروع مجدد، دستور /start را ارسال کنید."
        )
        return

    if data == b"account_transfer_start":
        transfer_data[user_id] = {}
        user["step"] = "transfer_get_target"
        await safe_edit(event,
            "💸 **انتقال الماس**\n\n"
            "لطفاً آیدی عددی کاربر مقصد را ارسال کنید:",
            buttons=get_transfer_cancel_keyboard()
        )
        return

    if data == b"account_giftcode_start":
        user["step"] = "giftcode_get_code"
        await safe_edit(event,
            "🎁 **کد هدیه**\n\n"
            "لطفاً کد هدیه‌ی خود را ارسال کنید:",
            buttons=[[styled_button("➜ بازگشت", b"start_root", style=STYLE_OFF)]]
        )
        return

    if data == b"transfer_cancel":
        transfer_data.pop(user_id, None)
        user["step"] = "managed"
        await safe_edit(event, get_start_account_text(user_id, user), buttons=get_start_account_keyboard())
        return

    if data == b"transfer_confirm_execute":
        pending = transfer_data.get(user_id)
        if not pending or "target_id" not in pending or "amount" not in pending:
            await event.answer("❌ اطلاعات انتقال یافت نشد، دوباره تلاش کنید.", alert=True)
            return

        target_id = pending["target_id"]
        amount = pending["amount"]

        success, message, sender_balance, receiver_balance = transfer_diamonds_db(user_id, target_id, amount)

        if success:
            if user_id in user_data:
                user_data[user_id]["diamonds"] = sender_balance
            if target_id in user_data:
                user_data[target_id]["diamonds"] = receiver_balance

            transfer_data.pop(user_id, None)
            user["step"] = "managed"
            log_diamond_transfer(user_id, target_id, amount)

            when = tehran_now()
            sender_username = user.get("username")
            sender_label = f"@{sender_username}" if sender_username else f"`{user_id}`"
            receiver_user = user_data.get(target_id, {})
            receiver_username = receiver_user.get("username")
            receiver_label = f"@{receiver_username}" if receiver_username else f"`{target_id}`"
            amount_str = format_diamonds(amount)

            # --- رسید فرستنده (روی همین پیام) ---
            await safe_edit(event,
                build_sender_receipt(receiver_label, amount_str, format_diamonds(sender_balance), when),
                buttons=[[styled_button("➜ بازگشت", b"start_account", style=STYLE_OFF)]]
            )

            # --- رسید گیرنده (پیام جداگانه به خودش، اگر قبلاً با ربات استارت زده باشد) ---
            try:
                await safe_call(
                    bot.send_message, target_id,
                    build_receiver_receipt(sender_label, amount_str, format_diamonds(receiver_balance), when)
                )
            except Exception as e:
                log_internal_error("receiver_receipt_send", e)
        else:
            await safe_edit(event,
                f"{message}",
                buttons=[[styled_button("➜ بازگشت", b"start_account", style=STYLE_OFF)]]
            )
            transfer_data.pop(user_id, None)
            user["step"] = "managed"
        return

    if data == b"menu_tag":
        if is_feature_locked(user_id, "tag"):
            await event.answer("این قابلیت برای شما قفل شده است.", alert=True)
            return
        await safe_edit(event, get_tag_menu_text(), buttons=get_tag_menu_keyboard())
        return

    if data == b"menu_ping":
        if is_feature_locked(user_id, "ping"):
            await event.answer("این قابلیت برای شما قفل شده است.", alert=True)
            return
        await safe_edit(event, get_ping_menu_text(), buttons=get_ping_menu_keyboard())
        return

    if data == b"menu_whois":
        if is_feature_locked(user_id, "whois"):
            await event.answer("این قابلیت برای شما قفل شده است.", alert=True)
            return
        await safe_edit(event, get_whois_menu_text(), buttons=get_whois_menu_keyboard())
        return

    # ====================================================================
    # ============================== ریکت ================================
    # ====================================================================
    if data == b"menu_reaction":
        if is_feature_locked(user_id, "reaction"):
            await event.answer("این قابلیت برای شما قفل شده است.", alert=True)
            return
        await safe_edit(event, get_reaction_menu_text(user_id, user), buttons=get_reaction_menu_keyboard(user))
        return

    if data == b"reaction_toggle":
        user["reaction_enabled"] = not user.get("reaction_enabled", False)
        save_user(user_id, user)
        log_settings_change(user_id, "reaction_enabled", user["reaction_enabled"])
        await safe_edit(event, get_reaction_menu_text(user_id, user), buttons=get_reaction_menu_keyboard(user))
        return

    if data == b"reaction_list":
        await safe_edit(event, get_reaction_list_text(user_id), buttons=get_reaction_list_keyboard())
        return

    # ====================================================================
    # ========================== پاسخ خودکار ==============================
    # ====================================================================
    if data == b"menu_autoreply":
        if is_feature_locked(user_id, "autoreply"):
            await event.answer("این قابلیت برای شما قفل شده است.", alert=True)
            return
        await safe_edit(event, get_autoreply_menu_text(user_id, user), buttons=get_autoreply_menu_keyboard(user))
        return

    if data == b"autoreply_toggle":
        user["autoreply_enabled"] = not user.get("autoreply_enabled", False)
        save_user(user_id, user)
        log_settings_change(user_id, "autoreply_enabled", user["autoreply_enabled"])
        await safe_edit(event, get_autoreply_menu_text(user_id, user), buttons=get_autoreply_menu_keyboard(user))
        return

    if data == b"autoreply_matchtype":
        await safe_edit(event, get_autoreply_matchtype_text(),
                         buttons=get_autoreply_matchtype_keyboard(user.get("autoreply_match_type", "exact")))
        return

    if data.startswith(b"autoreply_setmatch_"):
        key = data.decode().split("autoreply_setmatch_", 1)[1]
        if key not in AUTOREPLY_MATCH_TYPES:
            await event.answer("❌ نوع تطبیق نامعتبر است.", alert=True)
            return
        user["autoreply_match_type"] = key
        save_user(user_id, user)
        log_settings_change(user_id, "autoreply_match_type", key)
        await safe_edit(event, get_autoreply_menu_text(user_id, user), buttons=get_autoreply_menu_keyboard(user))
        return

    if data == b"autoreply_add":
        autoreply_draft[user_id] = {}
        user["step"] = "autoreply_get_trigger"
        await safe_edit(event,
            "کلمه یا جمله‌ای که می‌خواهی به آن پاسخ داده شود را ارسال کن.",
            buttons=[[styled_button("➜ بازگشت", b"menu_autoreply", style=STYLE_OFF)]]
        )
        return

    if data == b"autoreply_remove":
        if not autoreply_cache.get(user_id):
            await event.answer("❌ هنوز هیچ پاسخ خودکاری اضافه نکرده‌اید.", alert=True)
            return
        user["step"] = "autoreply_get_delete_id"
        await safe_edit(event,
            "شماره پاسخ موردنظر را وارد کنید:",
            buttons=[[styled_button("➜ بازگشت", b"menu_autoreply", style=STYLE_OFF)]]
        )
        return

    if data == b"autoreply_list":
        await safe_edit(event, get_autoreply_list_text(user_id), buttons=get_autoreply_list_keyboard(user_id))
        return

    if data.startswith(b"autoreply_view_"):
        try:
            local_id = int(data.decode().split("autoreply_view_", 1)[1])
        except ValueError:
            await event.answer("❌ شناسه نامعتبر است.", alert=True)
            return
        item = next((i for i in autoreply_cache.get(user_id, []) if i["local_id"] == local_id), None)
        if not item:
            await event.answer("❌ این پاسخ پیدا نشد (شاید قبلاً حذف شده).", alert=True)
            await safe_edit(event, get_autoreply_list_text(user_id), buttons=get_autoreply_list_keyboard(user_id))
            return
        await safe_edit(event, get_autoreply_view_text(item), buttons=get_autoreply_view_keyboard(local_id))
        return

    if data.startswith(b"autoreply_delete_"):
        try:
            local_id = int(data.decode().split("autoreply_delete_", 1)[1])
        except ValueError:
            await event.answer("❌ شناسه نامعتبر است.", alert=True)
            return
        removed = delete_autoreply_db(user_id, local_id)
        if user_id in autoreply_cache:
            autoreply_cache[user_id] = [i for i in autoreply_cache[user_id] if i["local_id"] != local_id]
        if removed:
            log_settings_change(user_id, "autoreply_deleted", str(local_id))
            await event.answer("✅ پاسخ خودکار حذف شد.", alert=True)
        else:
            await event.answer("❌ این پاسخ پیدا نشد.", alert=True)
        await safe_edit(event, get_autoreply_list_text(user_id), buttons=get_autoreply_list_keyboard(user_id))
        return

    if data == b"menu_secretary":
        if is_feature_locked(user_id, "secretary"):
            await event.answer("این قابلیت برای شما قفل شده است.", alert=True)
            return
        await safe_edit(event, get_secretary_menu_text(user), buttons=get_secretary_menu_keyboard(user))
        return

    # ====== میو ======
    if data == b"menu_meow":
        if is_feature_locked(user_id, "meow"):
            await event.answer("این قابلیت برای شما قفل شده است.", alert=True)
            return
        await safe_edit(event, get_meow_menu_text(user), buttons=get_meow_menu_keyboard(user_id, user))
        return

    if data == b"meow_settings":
        await safe_edit(event, get_meow_settings_text(user), buttons=get_meow_settings_keyboard(user))
        return

    if data == b"fish_settings":
        if is_feature_locked(user_id, "fish"):
            await event.answer("این قابلیت برای شما قفل شده است.", alert=True)
            return
        await safe_edit(event, get_fish_settings_text(user), buttons=get_fish_settings_keyboard(user))
        return

    if data == b"meowpoint_settings":
        if is_feature_locked(user_id, "meowpoint"):
            await event.answer("این قابلیت برای شما قفل شده است.", alert=True)
            return
        await safe_edit(event, get_meowpoint_settings_text(user), buttons=get_meowpoint_settings_keyboard(user))
        return

    if data == b"streetcat_settings":
        if is_feature_locked(user_id, "streetcat"):
            await event.answer("این قابلیت برای شما قفل شده است.", alert=True)
            return
        await safe_edit(event, get_streetcat_settings_text(user), buttons=get_streetcat_settings_keyboard(user))
        return

    if data == b"fridge_settings":
        if is_feature_locked(user_id, "fridge"):
            await event.answer("این قابلیت برای شما قفل شده است.", alert=True)
            return
        await safe_edit(event, get_fridge_settings_text(user), buttons=get_fridge_settings_keyboard(user))
        return

    if data == b"fish_ops_menu":
        await safe_edit(event, get_fish_ops_menu_text(user), buttons=get_fish_ops_menu_keyboard(user))
        return

    if data.startswith(b"fishop_rarity_"):
        rarity_key = data.decode().split("fishop_rarity_", 1)[1]
        if rarity_key not in dict(FISH_OPS_RARITY_LABELS):
            await event.answer("❌ سطح نامعتبر است.", alert=True)
            return
        label = dict(FISH_OPS_RARITY_LABELS)[rarity_key]
        await safe_edit(event, f"⚙️ **عملیات ماهی — سطح {label}**", buttons=get_fish_op_rarity_keyboard(user, rarity_key))
        return

    if data.startswith(b"fishop_set_"):
        remainder = data.decode().split("fishop_set_", 1)[1]
        rarity_key, _, op_key = remainder.rpartition("_")
        if rarity_key not in dict(FISH_OPS_RARITY_LABELS) or op_key not in ("sell", "feed", "fridge"):
            await event.answer("❌ مقدار نامعتبر است.", alert=True)
            return
        user[f"fish_operation_{rarity_key}"] = op_key
        save_user(user_id, user)
        log_settings_change(user_id, f"fish_operation_{rarity_key}", op_key)
        label = dict(FISH_OPS_RARITY_LABELS)[rarity_key]
        await safe_edit(event, f"⚙️ **عملیات ماهی — سطح {label}**", buttons=get_fish_op_rarity_keyboard(user, rarity_key))
        return

    if data == b"meow_toggle":
        want_on = not user.get("meow_enabled", False)

        if want_on and not user.get("meow_chat_id"):
            await event.answer("❌ ابتدا یک گروه برای میو انتخاب کنید.", alert=True)
            return

        user["meow_enabled"] = want_on
        save_user(user_id, user)
        log_settings_change(user_id, "meow_enabled", want_on)

        # بلافاصله Task مربوطه را متوقف/شروع می‌کنیم (نه اینکه منتظر چرخه‌ی بعدی بمانیم)
        old_task = user.get("meow_task")
        if old_task and not old_task.done():
            old_task.cancel()
        user["meow_task"] = None

        if want_on:
            client = active_clients.get(user_id)
            if client:
                user["meow_task"] = asyncio.get_event_loop().create_task(meow_worker(user_id, client))
            else:
                user["meow_enabled"] = False
                save_user(user_id, user)
                await event.answer("❌ ابتدا Self را روشن کنید.", alert=True)

        await safe_edit(event, get_meow_settings_text(user), buttons=get_meow_settings_keyboard(user))
        return

    if data == b"meow_interval_inc":
        current = user.get("meow_interval_seconds", MEOW_INTERVAL_SECONDS)
        user["meow_interval_seconds"] = current + 5
        save_user(user_id, user)
        log_settings_change(user_id, "meow_interval_seconds", user["meow_interval_seconds"])
        await safe_edit(event, get_meow_settings_text(user), buttons=get_meow_settings_keyboard(user))
        return

    if data == b"meow_interval_dec":
        current = user.get("meow_interval_seconds", MEOW_INTERVAL_SECONDS)
        user["meow_interval_seconds"] = max(5, current - 5)
        save_user(user_id, user)
        log_settings_change(user_id, "meow_interval_seconds", user["meow_interval_seconds"])
        await safe_edit(event, get_meow_settings_text(user), buttons=get_meow_settings_keyboard(user))
        return

    if data == b"fish_toggle":
        want_on = not user.get("fish_enabled", False)

        if want_on and not user.get("meow_chat_id"):
            await event.answer("❌ ابتدا از بخش میو یک گروه انتخاب کنید.", alert=True)
            return

        user["fish_enabled"] = want_on
        save_user(user_id, user)
        log_settings_change(user_id, "fish_enabled", want_on)

        old_task = user.get("fish_task")
        if old_task and not old_task.done():
            old_task.cancel()
        user["fish_task"] = None

        if want_on:
            client = active_clients.get(user_id)
            if client:
                user["fish_task"] = asyncio.get_event_loop().create_task(fish_worker(user_id, client))
            else:
                user["fish_enabled"] = False
                save_user(user_id, user)
                await event.answer("❌ ابتدا Self را روشن کنید.", alert=True)

        await safe_edit(event, get_fish_settings_text(user), buttons=get_fish_settings_keyboard(user))
        return

    if data == b"fish_interval_inc":
        current = user.get("fish_interval_seconds", FISH_INTERVAL_SECONDS)
        user["fish_interval_seconds"] = current + INTERVAL_STEP_SECONDS
        save_user(user_id, user)
        log_settings_change(user_id, "fish_interval_seconds", user["fish_interval_seconds"])
        await safe_edit(event, get_fish_settings_text(user), buttons=get_fish_settings_keyboard(user))
        return

    if data == b"fish_interval_dec":
        current = user.get("fish_interval_seconds", FISH_INTERVAL_SECONDS)
        user["fish_interval_seconds"] = max(INTERVAL_STEP_SECONDS, current - INTERVAL_STEP_SECONDS)
        save_user(user_id, user)
        log_settings_change(user_id, "fish_interval_seconds", user["fish_interval_seconds"])
        await safe_edit(event, get_fish_settings_text(user), buttons=get_fish_settings_keyboard(user))
        return

    if data == b"meowpoint_toggle":
        want_on = not user.get("meowpoint_enabled", False)

        if want_on and not user.get("meow_chat_id"):
            await event.answer("❌ ابتدا از بخش میو یک گروه انتخاب کنید.", alert=True)
            return

        user["meowpoint_enabled"] = want_on
        save_user(user_id, user)
        log_settings_change(user_id, "meowpoint_enabled", want_on)

        old_task = user.get("meowpoint_task")
        if old_task and not old_task.done():
            old_task.cancel()
        user["meowpoint_task"] = None

        if want_on:
            client = active_clients.get(user_id)
            if client:
                user["meowpoint_task"] = asyncio.get_event_loop().create_task(meowpoint_worker(user_id, client))
            else:
                user["meowpoint_enabled"] = False
                save_user(user_id, user)
                await event.answer("❌ ابتدا Self را روشن کنید.", alert=True)

        await safe_edit(event, get_meowpoint_settings_text(user), buttons=get_meowpoint_settings_keyboard(user))
        return

    if data == b"meowpoint_interval_inc":
        current = user.get("meowpoint_interval_seconds", MEOWPOINT_INTERVAL_SECONDS)
        user["meowpoint_interval_seconds"] = current + INTERVAL_STEP_SECONDS
        save_user(user_id, user)
        log_settings_change(user_id, "meowpoint_interval_seconds", user["meowpoint_interval_seconds"])
        await safe_edit(event, get_meowpoint_settings_text(user), buttons=get_meowpoint_settings_keyboard(user))
        return

    if data == b"meowpoint_interval_dec":
        current = user.get("meowpoint_interval_seconds", MEOWPOINT_INTERVAL_SECONDS)
        user["meowpoint_interval_seconds"] = max(INTERVAL_STEP_SECONDS, current - INTERVAL_STEP_SECONDS)
        save_user(user_id, user)
        log_settings_change(user_id, "meowpoint_interval_seconds", user["meowpoint_interval_seconds"])
        await safe_edit(event, get_meowpoint_settings_text(user), buttons=get_meowpoint_settings_keyboard(user))
        return

    if data == b"streetcat_toggle":
        want_on = not user.get("streetcat_enabled", False)

        if want_on and not user.get("meow_chat_id"):
            await event.answer("❌ ابتدا از بخش میو یک گروه انتخاب کنید.", alert=True)
            return

        user["streetcat_enabled"] = want_on
        save_user(user_id, user)
        log_settings_change(user_id, "streetcat_enabled", want_on)
        # این قابلیت رویدادمحوره (بدون تایمر)؛ هندلرش همیشه ثبت‌شده‌ست و فقط این
        # فلگ رو چک می‌کنه، پس نیازی به استارت/استاپ Task نیست.
        await safe_edit(event, get_streetcat_settings_text(user), buttons=get_streetcat_settings_keyboard(user))
        return

    if data == b"fridge_toggle":
        want_on = not user.get("fridge_enabled", False)

        if want_on and not user.get("meow_chat_id"):
            await event.answer("❌ ابتدا از بخش میو یک گروه انتخاب کنید.", alert=True)
            return

        user["fridge_enabled"] = want_on
        save_user(user_id, user)
        log_settings_change(user_id, "fridge_enabled", want_on)

        old_task = user.get("fridge_task")
        if old_task and not old_task.done():
            old_task.cancel()
        user["fridge_task"] = None

        if want_on:
            client = active_clients.get(user_id)
            if client:
                user["fridge_task"] = asyncio.get_event_loop().create_task(fridge_worker(user_id, client))
            else:
                user["fridge_enabled"] = False
                save_user(user_id, user)
                await event.answer("❌ ابتدا Self را روشن کنید.", alert=True)

        await safe_edit(event, get_fridge_settings_text(user), buttons=get_fridge_settings_keyboard(user))
        return

    if data == b"fridge_interval_inc":
        current = user.get("fridge_interval_seconds", FRIDGE_INTERVAL_SECONDS)
        user["fridge_interval_seconds"] = current + INTERVAL_STEP_SECONDS
        save_user(user_id, user)
        log_settings_change(user_id, "fridge_interval_seconds", user["fridge_interval_seconds"])
        await safe_edit(event, get_fridge_settings_text(user), buttons=get_fridge_settings_keyboard(user))
        return

    if data == b"fridge_interval_dec":
        current = user.get("fridge_interval_seconds", FRIDGE_INTERVAL_SECONDS)
        user["fridge_interval_seconds"] = max(INTERVAL_STEP_SECONDS, current - INTERVAL_STEP_SECONDS)
        save_user(user_id, user)
        log_settings_change(user_id, "fridge_interval_seconds", user["fridge_interval_seconds"])
        await safe_edit(event, get_fridge_settings_text(user), buttons=get_fridge_settings_keyboard(user))
        return

    if data == b"meow_select_group":
        client = active_clients.get(user_id)
        if not client:
            await event.answer("❌ ابتدا Self را روشن کنید تا لیست گروه‌ها خوانده شود.", alert=True)
            return

        try:
            groups = []
            async for dialog in client.iter_dialogs(limit=200):
                if dialog.is_group:
                    groups.append((dialog.id, dialog.title or "بدون‌نام"))
        except Exception as e:
            log_internal_error("meow_fetch_groups", e)
            await event.answer("❌ خطا در دریافت لیست گروه‌ها.", alert=True)
            return

        if not groups:
            await event.answer("❌ هیچ گروهی پیدا نشد.", alert=True)
            return

        meow_group_cache[user_id] = groups
        await safe_edit(event,
            "📋 **انتخاب گروه برای میو**\n\nیکی از گروه‌های زیر را انتخاب کنید:",
            buttons=get_meow_group_list_keyboard(groups, 0, user.get("meow_chat_id"))
        )
        return

    if data.startswith(b"meow_grouppage_"):
        page = int(data.decode().split("meow_grouppage_", 1)[1])
        groups = meow_group_cache.get(user_id)

        if groups is None:
            await event.answer("❌ لیست منقضی شده، دوباره «انتخاب گروه» را بزنید.", alert=True)
            return

        await safe_edit(event,
            "📋 **انتخاب گروه برای میو**\n\nیکی از گروه‌های زیر را انتخاب کنید:",
            buttons=get_meow_group_list_keyboard(groups, page, user.get("meow_chat_id"))
        )
        return

    if data.startswith(b"meow_setgroup_"):
        chat_id = int(data.decode().split("meow_setgroup_", 1)[1])
        title = None
        for gid, gtitle in (meow_group_cache.get(user_id) or []):
            if gid == chat_id:
                title = gtitle
                break

        user["meow_chat_id"] = chat_id
        user["meow_chat_title"] = title
        save_user(user_id, user)
        log_settings_change(user_id, "meow_chat_id", chat_id)

        # این گروه برای همه‌ی قابلیت‌های میو (میو/ماهی/میو‌پوینت/یخچال) مشترک است؛
        # اگر هرکدام از قبل روشن بوده ولی هنوز گروهی نداشت (Task متوقف شده بود)، حالا
        # با گروه جدید دوباره راه‌اندازی می‌شود. Task‌های زنده خودشان با خواندن
        # meow_chat_id تازه از user_data در چرخه‌ی بعدی هماهنگ می‌شوند.
        client = active_clients.get(user_id)
        if client:
            for enabled_key, task_key, worker_fn in (
                ("meow_enabled", "meow_task", meow_worker),
                ("fish_enabled", "fish_task", fish_worker),
                ("meowpoint_enabled", "meowpoint_task", meowpoint_worker),
                ("fridge_enabled", "fridge_task", fridge_worker),
            ):
                if user.get(enabled_key):
                    old_task = user.get(task_key)
                    if not old_task or old_task.done():
                        user[task_key] = asyncio.get_event_loop().create_task(worker_fn(user_id, client))

        meow_group_cache.pop(user_id, None)
        await safe_edit(event, get_meow_menu_text(user), buttons=get_meow_menu_keyboard(user_id, user))
        return

    if data == b"secretary_toggle":
        user["secretary_enabled"] = not user.get("secretary_enabled", False)
        save_user(user_id, user)
        log_settings_change(user_id, "secretary_enabled", user["secretary_enabled"])
        await safe_edit(event, get_secretary_menu_text(user), buttons=get_secretary_menu_keyboard(user))
        return

    if data == b"secretary_set_text":
        user["step"] = "secretary_get_text"
        await safe_edit(event,
            "📝 متن موردنظر خود را ارسال کنید.\n\n"
            "این متن جایگزین پیام پیش‌فرض منشی می‌شود."
        )
        return

    if data == b"secretary_set_time":
        user["step"] = "secretary_get_time"
        await safe_edit(event,
            "⏱️ لطفاً زمان تأخیر پاسخ منشی را بر حسب **ثانیه** ارسال کنید.\n\n"
            "نمونه:\n"
            "▫️ ۱ دقیقه = 60\n"
            "▫️ ۵ دقیقه = 300\n"
            "▫️ ۱۰ دقیقه = 600"
        )
        return

# ======================== پردازش ورود با کد ========================
async def process_code_signin(event, user_id, code):
    generator = generator_data[user_id]
    client = active_signins.get(user_id)

    if not client:
        await event.respond("❌ نشست منقضی شده است. لطفاً مجدداً /start را بزنید.")
        del generator_data[user_id]
        return

    try:
        await client.sign_in(generator["phone"], code, phone_code_hash=generator["phone_code_hash"])
        session_string = client.session.save()

        if generator.get("recovery") and user_id in user_data:
            # بازیابی نشست: فقط Session و وضعیت آپدیت می‌شود، بقیه‌ی اطلاعات (الماس،
            # تنظیمات، رفرال و ...) دست‌نخورده باقی می‌ماند.
            user_data[user_id]["session"] = session_string
            user_data[user_id]["status"] = True
            user_data[user_id]["step"] = "managed"
        else:
            user_data[user_id] = make_default_user(session=session_string, status=True, step="managed")

        save_user(user_id, user_data[user_id])
        await _teardown_existing_client(user_id)
        register_active_client(user_id, client)

        await event.respond(
            "✅ **ورود با موفقیت انجام شد!**\n\n"
            "▫️ حساب شما به ربات متصل شد.\n"
            "▫️ اطلاعات در دیتابیس ابری ذخیره شد.\n"
            "▫️ سلف شما هم‌اکنون فعال است."
        )

        del generator_data[user_id]
        if user_id in active_signins:
            del active_signins[user_id]

        await event.respond(
            get_start_root_text(),
            buttons=get_start_root_keyboard(user_data[user_id])
        )

    except SessionPasswordNeededError:
        generator["step"] = "get_password"
        await event.respond(
            "🔐 **تایید دو مرحله‌ای فعال است!**\n\n"
            "لطفاً رمز عبور دو مرحله‌ای حساب خود را وارد کنید:"
        )
    except Exception as e:
        generator["code_buffer"] = ""
        await event.respond(
            f"❌ **خطا در ورود:**\n\n`{str(e)}`\n\n"
            "لطفاً مجدداً تلاش کنید:"
        )
        await event.respond(
            "📩 کد تایید را مجدداً وارد کنید:",
            buttons=get_code_keyboard("")
        )

# ======================== هندلر پیام‌های متنی ========================
@bot.on(events.NewMessage)
async def message_handler(event):
    user_id = event.sender_id
    text = event.text.strip() if event.text else ""

    # لغو عملیات
    _pending_steps = {
        "transfer_get_target", "transfer_get_amount", "transfer_confirm",
        "secretary_get_text", "secretary_get_time", "giftcode_get_code",
        "buy_amount", "buy_confirm", "buy_payment", "buy_invoice", "buy_receipt",
        "autoreply_get_trigger", "autoreply_get_response", "autoreply_get_delete_id",
    }
    _has_pending_step = user_id in user_data and user_data[user_id].get("step") in _pending_steps

    if text == "/cancel" and (
        user_id in broadcast_data or user_id in admin_action_data or user_id in generator_data or _has_pending_step
    ):
        # لغو یک خرید در حالِ انتظارِ رسید فقط State را ریست می‌کند؛ سفارشی که از قبل
        # در دیتابیس با وضعیت 'invoice' ثبت شده دست‌نخورده می‌ماند (کاربر می‌تواند بعداً
        # دوباره از حساب کاربری وارد بخش خرید شود، البته سفارش قدیمی دیگر از UI قابل
        # دسترسی نیست مگر مستقیماً توسط ادمین در دیتابیس بررسی شود).
        broadcast_data.pop(user_id, None)
        admin_action_data.pop(user_id, None)
        transfer_data.pop(user_id, None)
        purchase_data.pop(user_id, None)
        autoreply_draft.pop(user_id, None)
        backup_upload_pending.pop(user_id, None)

        if user_id in generator_data:
            del generator_data[user_id]
        if user_id in active_signins:
            try:
                await active_signins[user_id].disconnect()
            except Exception as e:
                log_internal_error("cancel_install_disconnect", e)
            del active_signins[user_id]

        if user_id in user_data:
            user_data[user_id]["step"] = "managed"
        await event.respond("❌ عملیات لغو شد.")
        if is_admin(user_id):
            await event.respond("👑 پنل ادمین:", buttons=get_admin_main_menu())
        return

    # ====== گیت جوین اجباری ======
    # این چک هم اینجا (نه فقط روی /start) تکرار می‌شود تا کاربرانی که مدت‌ها با
    # ربات کار کرده‌اند و دیگر /start نمی‌زنند هم از قلم نیفتند. عمداً وقتی کاربر
    # وسط فرآیند نصب سلف (وارد کردن شماره/کد/رمز دو مرحله‌ای) است این گیت اجرا
    # نمی‌شود؛ چون OTP تلگرام زمان محدودی دارد و متوقف‌کردنِ کاربر وسط آن فرآیند
    # برای اجبار به جوین، می‌تواند باعث از‌دست‌رفتن کدِ ورود شود.
    if user_id not in generator_data and user_id not in active_signins and needs_join_check(user_id):
        all_joined, missing = await check_user_joined_all(user_id)
        if all_joined:
            _mark_user_verified(user_id)
        else:
            await _send_join_gate(event, user_id, missing)
            return

    # ====== افزودن پاسخ خودکار (دو مرحله‌ای: Trigger سپس Response) ======
    if user_id in user_data and user_data[user_id].get("step") == "autoreply_get_trigger":
        trigger_text = text.strip()
        if not trigger_text:
            await event.respond("❌ لطفاً یک متن معتبر ارسال کنید.",
                                 buttons=[[styled_button("➜ بازگشت", b"menu_autoreply", style=STYLE_OFF)]])
            return
        autoreply_draft[user_id] = {"trigger_text": trigger_text}
        user_data[user_id]["step"] = "autoreply_get_response"
        await event.respond(
            "حالا پیام پاسخ خودکار را ارسال کن.\n\n"
            "می‌تواند متن، عکس، GIF، استیکر، ویدیو، فایل یا Voice باشد؛ با همان Formatting ذخیره می‌شود."
        )
        return

    if user_id in user_data and user_data[user_id].get("step") == "autoreply_get_response":
        draft = autoreply_draft.get(user_id)
        if not draft:
            user_data[user_id]["step"] = "managed"
            await event.respond("❌ عملیات منقضی شده. دوباره از «افزودن پاسخ خودکار» اقدام کنید.")
            return

        msg = event.message
        media_kind = _media_kind_key(msg)
        media_bytes = None
        media_filename = None
        media_mime = None

        if media_kind:
            size = getattr(event.file, "size", None) if event.file else None
            if size and size > MAX_AUTOREPLY_MEDIA_BYTES:
                await event.respond(
                    f"❌ حجم این فایل بیش از حد مجاز است (حداکثر {MAX_AUTOREPLY_MEDIA_MB} مگابایت). "
                    "فایل کوچک‌تری بفرست یا پیام دیگری ارسال کن."
                )
                return
            try:
                media_bytes = await event.download_media(file=bytes)
            except Exception as e:
                log_internal_error("autoreply_download_media", e)
                await event.respond("❌ خطا در دریافت فایل. دوباره تلاش کنید.")
                return
            media_filename = getattr(event.file, "name", None) if event.file else None
            media_mime = getattr(event.file, "mime_type", None) if event.file else None

        response_text = text if text else None
        if not response_text and not media_bytes:
            await event.respond("❌ پیام خالی قابل ذخیره نیست. یک متن یا رسانه ارسال کن.")
            return

        entities = msg.entities

        local_id = add_autoreply_db(
            user_id, draft["trigger_text"], response_text, entities,
            media_kind, media_bytes, media_filename, media_mime
        )
        autoreply_draft.pop(user_id, None)
        user_data[user_id]["step"] = "managed"

        if local_id is None:
            await event.respond("❌ خطا در ذخیره‌سازی پاسخ خودکار. دوباره تلاش کنید.")
            return

        autoreply_cache.setdefault(user_id, []).append({
            "local_id": local_id,
            "trigger_text": draft["trigger_text"],
            "response_text": response_text,
            "entities": entities,
            "media_kind": media_kind,
            "media_bytes": media_bytes,
            "media_filename": media_filename,
            "media_mime": media_mime,
        })

        await event.respond(
            f"✅ پاسخ خودکار شماره {local_id} با موفقیت ذخیره شد.",
            buttons=get_autoreply_menu_keyboard(user_data[user_id])
        )
        return

    # ====== حذف پاسخ خودکار (دریافت شماره) ======
    if user_id in user_data and user_data[user_id].get("step") == "autoreply_get_delete_id":
        try:
            local_id = int(text.strip())
        except ValueError:
            await event.respond("❌ لطفاً فقط شماره‌ی پاسخ را ارسال کنید (مثلاً 2).")
            return

        exists = any(i["local_id"] == local_id for i in autoreply_cache.get(user_id, []))
        if not exists:
            await event.respond(f"❌ پاسخ خودکار شماره {local_id} پیدا نشد.")
            return

        removed = delete_autoreply_db(user_id, local_id)
        if user_id in autoreply_cache:
            autoreply_cache[user_id] = [i for i in autoreply_cache[user_id] if i["local_id"] != local_id]
        user_data[user_id]["step"] = "managed"

        if removed:
            log_settings_change(user_id, "autoreply_deleted", str(local_id))
            await event.respond(f"✅ پاسخ خودکار شماره {local_id} حذف شد.",
                                 buttons=get_autoreply_menu_keyboard(user_data[user_id]))
        else:
            await event.respond("❌ خطا در حذف. دوباره تلاش کنید.")
        return

    # ====== مرحله‌ی انتظار برای عکس رسید خرید الماس ======
    # این بلوک عمداً خیلی زودتر از هندلر عمومی متن قرار گرفته تا با هیچ قابلیت دیگری
    # (منشی خودکار، حالت متن و ...) تداخل نکند و روی این State قفل بماند.
    if user_id in user_data and user_data[user_id].get("step") == "buy_receipt":
        pending = purchase_data.get(user_id)
        order_id = pending.get("order_id") if pending else None
        order = get_order_db(order_id) if order_id else None

        if not order:
            user_data[user_id]["step"] = "managed"
            purchase_data.pop(user_id, None)
            await event.respond("❌ سفارش پیدا نشد یا منقضی شده. دوباره از «حساب کاربری ← خرید الماس» اقدام کنید.")
            return

        if not event.photo:
            await event.respond(
                "📸 فقط **عکس رسید پرداخت** پذیرفته می‌شود.\n\n"
                "لطفاً فقط تصویر رسید را ارسال کنید (نه متن، فایل، ویس، ویدیو یا استیکر).",
                buttons=get_buy_waiting_receipt_keyboard()
            )
            return

        success, updated_order = set_order_receipt_db(order_id, event.chat_id, event.id, str(event.photo.id))
        if not success:
            if updated_order and updated_order.get("status") != "invoice":
                await event.respond("❌ برای این سفارش قبلاً رسید ارسال شده و در حال بررسی است.")
            else:
                await event.respond("❌ خطا در ثبت رسید. دوباره تلاش کنید.")
            return

        user_data[user_id]["step"] = "managed"
        username = user_data[user_id].get("username")

        await event.respond(
            "✅ **رسید شما دریافت شد.**\n\n"
            f"🧾 کد سفارش: `{order_id}`\n"
            "📌 وضعیت: در انتظار بررسی ادمین\n\n"
            "نتیجه‌ی بررسی به‌محض تأیید یا رد توسط ادمین برای شما ارسال می‌شود.",
            buttons=[[styled_button("➜ بازگشت به منو", b"start_account", style=STYLE_OFF)]]
        )

        # ارسال سفارش کامل + عکس رسید برای همه‌ی ادمین‌ها
        admin_caption = (
            "🧾 **سفارش جدید خرید الماس**\n\n"
            f"👤 نام : {username or '—'}\n"
            f"🆔 آیدی عددی : {user_id}\n"
            f"🔹 Username : {('@' + username) if username else 'ندارد'}\n"
            f"💎 تعداد الماس : {format_diamonds(order['amount_diamonds'])}\n"
            f"💰 مبلغ : {order['amount_toman']:,.0f} تومان\n"
            f"🧾 کد سفارش : {order_id}\n"
            f"⏱ زمان ثبت سفارش : {order['created_at'].strftime('%Y/%m/%d %H:%M')}\n"
            "📌 وضعیت : در انتظار بررسی\n"
            "📱 روش پرداخت : کارت به کارت"
        )
        admin_buttons = [
            [
                styled_button("✅ تأیید", f"order_approve_{order_id}".encode(), style=STYLE_ON),
                styled_button("❌ لغو", f"order_reject_{order_id}".encode(), style=STYLE_OFF),
            ]
        ]
        for admin_id in ADMIN_IDS:
            try:
                await safe_call(bot.send_file, admin_id, event.photo, caption=admin_caption, buttons=admin_buttons)
            except Exception as e:
                log_internal_error("send_order_to_admin", e)
        return

    # ====== ساخت کد هدیه توسط ادمین (چندمرحله‌ای، قبل از هندلر عمومی عددی) ======
    # ====== افزودن کانال جوین اجباری (سه‌مرحله‌ای: نام، شناسه، لینک) ======
    if user_id in admin_action_data and is_admin(user_id) and admin_action_data[user_id].get("type") == "add_joingate":
        action = admin_action_data[user_id]
        cancel_kb = [[styled_button("➜ بازگشت", b"admin_joingate", style=STYLE_OFF)]]

        if action["step"] == "get_title":
            title = text.strip()
            if not title:
                await event.respond("❌ لطفاً یک نام معتبر ارسال کنید.", buttons=cancel_kb)
                return
            action["title"] = title[:64]
            action["step"] = "get_link"
            await event.respond(
                "حالا **لینک عضویت کانال** را ارسال کنید (نه شناسه یا فوروارد پیام):\n\n"
                "• کانال عمومی: `https://t.me/channel_username`\n"
                "• کانال خصوصی: `https://t.me/+xxxxxxxxxx`\n\n"
                "⚠️ ربات باید از قبل واقعاً در این کانال عضو باشد (ترجیحاً با دسترسی ادمین)؛ "
                "همین لینک هم برای شناسایی دقیق کانال استفاده می‌شود و هم به‌عنوان دکمه‌ی "
                "«عضویت» به کاربران نشان داده خواهد شد.",
                buttons=cancel_kb
            )
            return

        if action["step"] == "get_link":
            # رفعِ باگِ واقعی («ربات از قبل ادمین بود ولی حتی با فوروارد هم گفت
            # ادمین نیست»): دو تلاش قبلی هیچ‌کدام برای اکانت بات قابل‌اعتماد نبودند:
            #   ۱) fwd.chat / fwd.get_chat فقط وقتی چیزی برمی‌گردانند که Telegram
            #      از قبل entity کامل را در کش/همان پیام گنجانده باشد؛ برای اولین
            #      برخورد بات با یک کانال خصوصی، معمولاً یک نسخه‌ی ناقص/min
            #      (بدون access_hash معتبر) برمی‌گردد که چک عضویت رویش شکست می‌خورد.
            #   ۲) bot.iter_dialogs() اصلاً برای اکانت بات کار نمی‌کند (طبق مستندات
            #      رسمی Telethon: «bot accounts do not have dialogs»)، پس آن fallback
            #      همیشه شکست می‌خورد، فارغ از عضویت واقعی بات.
            # راه‌حل قابل‌اعتماد: از روی همین لینک دعوت، با CheckChatInviteRequest
            # چک می‌کنیم. طبق مستندات تلگرام، اگر بات از قبل واقعاً عضو آن چت باشد،
            # پاسخ از نوع ChatInviteAlready است که entity کامل (با access_hash درست)
            # را همراه خودش دارد — بدون هیچ وابستگی به کش/دیالوگ/فوروارد.
            link = text.strip()
            if not link.startswith("http"):
                await event.respond("❌ لینک باید با http یا https شروع شود.", buttons=cancel_kb)
                return

            resolved_entity, resolution_error = await _resolve_channel_from_link(link)

            if resolved_entity is None:
                await event.respond(
                    "❌ **این کانال پیدا نشد.**\n\n"
                    f"جزئیات: `{resolution_error}`\n\n"
                    "مطمئن شوید لینک درست است و ربات از قبل واقعاً در این کانال عضو است "
                    "(نه اکانت سلف — خودِ ربات).",
                    buttons=cancel_kb
                )
                return

            # اعتبارسنجی نهایی: بات باید حداقل عضو (ترجیحاً ادمین) این کانال باشد.
            #
            # باگِ واقعیِ همین چک (که بارها هرچه درست بود باز «ادمین نیست» نشان
            # می‌داد): get_permissions(entity) بدون مشخص‌کردنِ کاربر، اصلاً وضعیتِ
            # خودِ بات را چک نمی‌کند — طبق مستندات رسمی Telethon، این حالت
            # «مجوزهای پیش‌فرضِ کلیِ چت» (default banned rights) را برمی‌گرداند که
            # هیچ ربطی به ادمین‌بودنِ بات ندارد. برای همین همیشه is_admin/is_creator/
            # is_member همه False بودند و خودِ همین کد (نه تلگرام) خطای مصنوعیِ
            # ChatAdminRequiredError صادر می‌کرد. برای چک‌کردنِ وضعیتِ خودِ بات، باید
            # صریحاً 'me' را به‌عنوان کاربر پاس بدهیم.
            try:
                my_perms = await bot.get_permissions(resolved_entity, 'me')
                if not my_perms or not (my_perms.is_admin or getattr(my_perms, "is_creator", False) or my_perms.is_member):
                    raise ChatAdminRequiredError(request=None)
            except Exception as e:
                bot_mention = f"@{BOT_USERNAME}" if BOT_USERNAME else "ربات"
                await event.respond(
                    f"❌ **{bot_mention} هنوز عضو/ادمین این کانال نیست.**\n\n"
                    f"جزئیات: `{e}`\n\n"
                    f"باید خودِ ربات ({bot_mention}) را (نه اکانت سلف) در کانال عضو کنید — "
                    "ترجیحاً با دسترسی ادمین — سپس همین لینک را دوباره ارسال کنید.",
                    buttons=cancel_kb
                )
                return

            identifier = str(resolved_entity.id)
            resolved_title = getattr(resolved_entity, "title", None) or getattr(resolved_entity, "username", None)

            new_id = create_join_channel_db(action["title"], identifier, link)
            del admin_action_data[user_id]

            if new_id is None:
                await event.respond("❌ خطا در ذخیره‌سازی کانال.", buttons=get_joingate_admin_keyboard())
                return

            reload_join_channels_cache()
            log_admin_action(user_id, 0, "add_joingate", f"id={new_id} title={action['title']}")
            await event.respond(
                f"✅ کانال «{action['title']}» (شناسایی‌شده به‌عنوان «{resolved_title or identifier}») "
                "با موفقیت اضافه شد و بررسی شد که ربات به آن دسترسی دارد.",
                buttons=get_joingate_admin_keyboard()
            )
            return

    # ====== تغییر لینک یک کانال جوین اجباری موجود ======
    if user_id in admin_action_data and is_admin(user_id) and admin_action_data[user_id].get("type") == "edit_joingate_link":
        action = admin_action_data[user_id]
        cid = action["channel_id"]
        cancel_kb = [[styled_button("➜ بازگشت", f"admin_joingate_manage_{cid}".encode(), style=STYLE_OFF)]]

        link = text.strip()
        if not link.startswith("http"):
            await event.respond("❌ لینک باید با http یا https شروع شود.", buttons=cancel_kb)
            return

        success = update_join_channel_link_db(cid, link)
        del admin_action_data[user_id]

        if not success:
            await event.respond("❌ این کانال پیدا نشد.", buttons=get_joingate_admin_keyboard())
            return

        reload_join_channels_cache()
        log_admin_action(user_id, 0, "edit_joingate_link", f"id={cid}")
        ch = get_join_channel_db(cid)
        await event.respond(
            "✅ لینک کانال بروزرسانی شد.",
            buttons=get_joingate_manage_keyboard(ch) if ch else get_joingate_admin_keyboard()
        )
        return

    # ====== دریافت فایل بکاپ آپلودشده برای بازیابی ======
    if user_id in admin_action_data and is_admin(user_id) and admin_action_data[user_id].get("type") == "backup_upload":
        cancel_kb = [[styled_button("➜ بازگشت", b"admin_backup", style=STYLE_OFF)]]

        if not event.document:
            await event.respond("❌ لطفاً فایل JSON بکاپ را به‌صورت Document ارسال کنید (نه متن).", buttons=cancel_kb)
            return

        size = getattr(event.file, "size", None) if event.file else None
        if size and size > 30 * 1024 * 1024:
            await event.respond("❌ حجم فایل بیش از حد مجاز است (حداکثر ۳۰ مگابایت).", buttons=cancel_kb)
            return

        try:
            raw = await event.download_media(file=bytes)
            dump = json.loads(raw.decode("utf-8"))
        except Exception as e:
            log_internal_error("backup_upload_parse", e)
            await event.respond("❌ فایل ارسالی یک بکاپ معتبر JSON نیست یا خراب است.", buttons=cancel_kb)
            return

        if not isinstance(dump, dict) or "meta" not in dump:
            await event.respond("❌ ساختار فایل با فرمت بکاپ NovaSelf مطابقت ندارد.", buttons=cancel_kb)
            return

        backup_upload_pending[user_id] = dump
        del admin_action_data[user_id]

        meta = dump.get("meta", {})
        created_at = meta.get("created_at", "نامشخص")
        await event.respond(
            get_backup_restore_confirm_text(f"فایل آپلودشده (ساخته‌شده در {created_at})"),
            buttons=get_backup_restore_confirm_keyboard("uploaded")
        )
        return

    if user_id in admin_action_data and is_admin(user_id) and admin_action_data[user_id].get("type") == "create_giftcode":
        action = admin_action_data[user_id]
        cancel_kb = [[styled_button("➜ بازگشت", b"admin_giftcodes", style=STYLE_OFF)]]

        if action["step"] == "get_code":
            code = text.strip()
            if not code.isalnum() or not code.isascii() or len(code) > 20:
                await event.respond("❌ کد باید فقط شامل حروف/اعداد انگلیسی و حداکثر ۲۰ کاراکتر باشد.", buttons=cancel_kb)
                return
            action["code"] = code.upper()
            action["step"] = "get_diamonds"
            await event.respond(f"✅ کد: `{action['code']}`\n\nحالا مقدار الماس این کد را وارد کنید:", buttons=cancel_kb)
            return

        if action["step"] == "get_diamonds":
            try:
                diamonds = float(text)
                if diamonds <= 0:
                    raise ValueError
            except ValueError:
                await event.respond("❌ لطفاً یک عدد معتبر و بزرگ‌تر از صفر ارسال کنید.", buttons=cancel_kb)
                return
            action["diamonds"] = diamonds
            action["step"] = "get_expiry"
            await event.respond("📅 چند روز دیگر این کد منقضی شود؟ (برای بدون انقضا عدد ۰ را ارسال کنید)", buttons=cancel_kb)
            return

        if action["step"] == "get_expiry":
            try:
                days = int(text)
                if days < 0:
                    raise ValueError
            except ValueError:
                await event.respond("❌ لطفاً یک عدد صحیح و غیرمنفی ارسال کنید.", buttons=cancel_kb)
                return

            expires_at = (tehran_now() + timedelta(days=days)) if days > 0 else None
            success, error = create_gift_code_db(action["code"], action["diamonds"], expires_at, user_id)
            del admin_action_data[user_id]

            if not success:
                await event.respond(f"❌ خطا در ساخت کد: {error}", buttons=get_giftcodes_admin_keyboard())
                return

            log_admin_action(user_id, 0, "create_giftcode", f"code={action['code']} diamonds={action['diamonds']}")
            await event.respond(
                f"✅ کد هدیه `{action['code']}` با موفقیت ساخته شد.",
                buttons=get_giftcodes_admin_keyboard()
            )
            return

    # ====== ویرایش مقدار الماس / انقضای یک کد هدیه‌ی موجود ======
    if user_id in admin_action_data and is_admin(user_id) and admin_action_data[user_id].get("type") in (
        "giftcode_edit_amount", "giftcode_edit_expiry"
    ):
        action = admin_action_data[user_id]
        code = action["code"]
        cancel_kb = [[styled_button("➜ بازگشت", f"admin_giftcode_manage_{code}".encode(), style=STYLE_OFF)]]

        if action["type"] == "giftcode_edit_amount":
            try:
                new_amount = float(text)
                if new_amount <= 0:
                    raise ValueError
            except ValueError:
                await event.respond("❌ لطفاً یک عدد معتبر و بزرگ‌تر از صفر ارسال کنید.", buttons=cancel_kb)
                return
            success = update_gift_code_amount_db(code, new_amount)
            del admin_action_data[user_id]
            if not success:
                await event.respond("❌ کد پیدا نشد یا خطایی رخ داد.", buttons=get_giftcodes_admin_keyboard())
                return
            log_admin_action(user_id, 0, "edit_giftcode_amount", f"code={code} new_amount={new_amount}")
            detail = get_gift_code_detail_db(code)
            await event.respond(
                f"✅ مقدار الماس کد `{code}` به {format_diamonds(new_amount)} تغییر یافت.",
                buttons=get_giftcode_manage_keyboard(detail) if detail else get_giftcodes_admin_keyboard()
            )
            return

        if action["type"] == "giftcode_edit_expiry":
            try:
                days = int(text)
                if days < 0:
                    raise ValueError
            except ValueError:
                await event.respond("❌ لطفاً یک عدد صحیح و غیرمنفی ارسال کنید.", buttons=cancel_kb)
                return
            new_expiry = (tehran_now() + timedelta(days=days)) if days > 0 else None
            success = update_gift_code_expiry_db(code, new_expiry)
            del admin_action_data[user_id]
            if not success:
                await event.respond("❌ کد پیدا نشد یا خطایی رخ داد.", buttons=get_giftcodes_admin_keyboard())
                return
            log_admin_action(user_id, 0, "edit_giftcode_expiry", f"code={code} days={days}")
            detail = get_gift_code_detail_db(code)
            await event.respond(
                f"✅ انقضای کد `{code}` بروزرسانی شد.",
                buttons=get_giftcode_manage_keyboard(detail) if detail else get_giftcodes_admin_keyboard()
            )
            return

    # ====== دریافت دلیل لغو سفارش خرید الماس ======
    if user_id in admin_action_data and is_admin(user_id) and admin_action_data[user_id].get("type") == "reject_order":
        action = admin_action_data[user_id]
        order_id = action["order_id"]
        reason = text.strip()

        if not reason:
            await event.respond("❌ لطفاً دلیل لغو را به‌صورت متن ارسال کنید.",
                                 buttons=[[styled_button("➜ بازگشت", b"order_reject_cancel", style=STYLE_OFF)]])
            return

        success, status_code, order = reject_order_db(order_id, user_id, reason)
        del admin_action_data[user_id]

        if not success:
            if status_code == "already_processed":
                state = order.get("status") if order else "?"
                await event.respond(f"⚠️ این سفارش قبلاً پردازش شده است (وضعیت فعلی: {state}).")
            else:
                await event.respond("❌ سفارش پیدا نشد یا خطایی رخ داد.")
            return

        log_admin_action(user_id, order["user_id"], "reject_order", f"order={order_id} reason={reason}")
        await event.respond(f"✅ سفارش `{order_id}` رد شد و دلیل برای کاربر ارسال شد.")

        try:
            await safe_call(bot.send_message, order["user_id"],
                "❌ **سفارش شما رد شد.**\n\n"
                f"🧾 کد سفارش : {order_id}\n"
                f"💎 تعداد الماس : {format_diamonds(order['amount_diamonds'])}\n"
                f"💰 مبلغ : {order['amount_toman']:,.0f} تومان\n\n"
                f"دلیل : {reason}"
            )
        except Exception as e:
            log_internal_error("notify_order_rejected", e)
        return

    # ====== پردازش عملیات مدیریتی الماس/رفرال ======
    if user_id in admin_action_data and is_admin(user_id):
        action = admin_action_data[user_id]
        target_id = action["target_id"]

        try:
            amount = float(text)
        except (TypeError, ValueError):
            await event.respond("❌ لطفاً یک عدد معتبر ارسال کنید.")
            return

        if action["type"] in ("add_diamond", "sub_diamond"):
            if amount <= 0:
                await event.respond("❌ مقدار باید بیشتر از صفر باشد.")
                return

            signed_amount = amount if action["type"] == "add_diamond" else -amount
            success, new_balance = admin_adjust_diamonds_db(target_id, signed_amount)

            if not success:
                await event.respond("❌ کاربر پیدا نشد یا خطایی در دیتابیس رخ داد.")
                del admin_action_data[user_id]
                return

            if target_id in user_data:
                user_data[target_id]["diamonds"] = new_balance

            action_label = "افزایش" if action["type"] == "add_diamond" else "کاهش"
            log_admin_action(user_id, target_id, f"{action_label} الماس", f"مقدار: {amount}")

            await event.respond(
                f"✅ موجودی الماس کاربر {target_id} با موفقیت {action_label} یافت.\n"
                f"💎 موجودی جدید: {format_diamonds(new_balance)}"
            )

        elif action["type"] == "set_referral":
            if amount < 0:
                await event.respond("❌ تعداد رفرال نمی‌تواند منفی باشد.")
                return

            success, new_count = admin_set_referral_db(target_id, int(amount))
            if not success:
                await event.respond("❌ کاربر پیدا نشد یا خطایی در دیتابیس رخ داد.")
                del admin_action_data[user_id]
                return

            if target_id in user_data:
                user_data[target_id]["referral_count"] = new_count

            log_admin_action(user_id, target_id, "تغییر تعداد رفرال", f"مقدار جدید: {new_count}")

            await event.respond(f"✅ تعداد رفرال کاربر {target_id} به {new_count} تغییر یافت.")

        del admin_action_data[user_id]

        if target_id in user_data:
            await event.respond(
                "👤 برای مشاهده جزئیات بروزرسانی‌شده:",
                buttons=get_user_detail_buttons(target_id)
            )
        return

    # ====== پردازش پیام همگانی ======
    if user_id in broadcast_data and is_admin(user_id):
        broadcast = broadcast_data[user_id]

        if broadcast.get("type") == "search" and broadcast.get("step") == "get_user_id":
            try:
                target_id = int(text)
                if target_id in user_data:
                    await event.respond(
                        f"✅ کاربر {target_id} پیدا شد!",
                        buttons=get_user_detail_buttons(target_id)
                    )
                else:
                    await event.respond("❌ کاربر پیدا نشد!")
                del broadcast_data[user_id]
            except ValueError:
                await event.respond("❌ شناسه معتبر نیست. لطفاً یک عدد وارد کنید.")
            return

        if broadcast.get("step") == "get_message":
            broadcast["src_chat_id"] = event.chat_id
            broadcast["src_message_id"] = event.id
            preview = text if text else _describe_message_kind(event.message)
            broadcast["summary"] = preview
            broadcast["step"] = "confirm"

            if broadcast["type"] == "single":
                target_id = broadcast["target_id"]
                await event.respond(
                    f"📨 **تایید ارسال پیام به کاربر {target_id}**\n\n"
                    f"📝 پیش‌نمایش:\n---\n{preview}\n---\n\n"
                    "آیا از ارسال این پیام مطمئن هستید؟",
                    buttons=[
                        [styled_button("✅ بله، ارسال کن", b"broadcast_confirm", style=STYLE_ON)],
                        [styled_button("➜ بازگشت", b"broadcast_cancel", style=STYLE_OFF)]
                    ]
                )
            else:
                total_users, _ = get_user_stats()
                await event.respond(
                    f"📨 **تایید ارسال پیام همگانی**\n\n"
                    f"⚠️ این پیام برای **{total_users} نفر** ارسال خواهد شد!\n\n"
                    f"📝 پیش‌نمایش:\n---\n{preview}\n---\n\n"
                    "آیا از ارسال این پیام مطمئن هستید؟",
                    buttons=[
                        [styled_button("✅ بله، ارسال کن", b"broadcast_confirm", style=STYLE_ON)],
                        [styled_button("➜ بازگشت", b"broadcast_cancel", style=STYLE_OFF)]
                    ]
                )
            return

    # ====== پردازش ساخت خودکار حساب ======
    if user_id in generator_data:
        generator = generator_data[user_id]

        if generator["step"] == "get_phone":
            # جلوگیری از اسپم: اگر کاربر قبلاً شماره‌ی اشتباه فرستاده (چه به‌خاطر
            # فرمت نامعتبر، چه رد شدن توسط خود تلگرام)، تا پایان زمان انتظار
            # (۳۰ ثانیه بار اول، ۶۰ ثانیه از بار دوم به بعد) اجازه‌ی تلاش مجدد
            # داده نمی‌شود. هر دو مسیر خطا از یک شمارنده‌ی مشترک استفاده می‌کنند.
            wait_until = generator.get("phone_wait_until")
            if wait_until and tehran_now() < wait_until:
                remaining = int((wait_until - tehran_now()).total_seconds()) + 1
                await event.respond(f"⏳ لطفاً {remaining} ثانیه دیگر صبر کنید و دوباره شماره را ارسال کنید.")
                return

            def _apply_phone_penalty():
                attempts = generator.get("phone_attempts", 0) + 1
                generator["phone_attempts"] = attempts
                wait_seconds = 30 if attempts == 1 else 60
                generator["phone_wait_until"] = tehran_now() + timedelta(seconds=wait_seconds)
                return wait_seconds

            normalized_phone, phone_error = normalize_phone_number(text)
            if phone_error:
                wait_seconds = _apply_phone_penalty()
                await event.respond(
                    f"{phone_error}\n\n"
                    "نمونه‌های قابل قبول: `0912xxxxxxx`، `912xxxxxxx`، `+98912xxxxxxx`\n\n"
                    f"⏳ لطفاً {wait_seconds} ثانیه صبر کنید و دوباره امتحان کنید."
                )
                return  # در همان مرحله می‌ماند تا کاربر دوباره امتحان کند (بدون کرش)

            generator["phone"] = normalized_phone

            await event.respond("⏳ در حال اتصال به سرورهای تلگرام...")

            client = None
            try:
                client = TelegramClient(StringSession(), API_ID, API_HASH)
                await client.connect()

                send_code_result = await client.send_code_request(generator["phone"])
                active_signins[user_id] = client
                generator["phone_code_hash"] = send_code_result.phone_code_hash
                generator["step"] = "get_code"
                generator.pop("phone_attempts", None)
                generator.pop("phone_wait_until", None)

                await event.respond(
                    "📩 **کد تایید ارسال شد!**\n\n"
                    "یک کد ۵ رقمی به تلگرام شما ارسال شده است.\n"
                    "لطفاً آن را از طریق دکمه‌های زیر وارد کنید:",
                    buttons=get_code_keyboard("")
                )
            except FloodWaitError as e:
                # خود تلگرام محدودیت گذاشته؛ دقیقاً به همان مدت صبر تحمیل می‌شود
                generator["phone_wait_until"] = tehran_now() + timedelta(seconds=e.seconds)
                await event.respond(
                    f"⏳ تلگرام درخواست شما را موقتاً محدود کرده است.\n"
                    f"لطفاً {e.seconds} ثانیه دیگر دوباره شماره را ارسال کنید."
                )
                if client:
                    try:
                        await client.disconnect()
                    except Exception:
                        pass
                if user_id in active_signins:
                    del active_signins[user_id]
            except Exception as e:
                wait_seconds = _apply_phone_penalty()

                await event.respond(
                    f"❌ **خطا در ارسال کد:**\n\n`{str(e)}`\n\n"
                    f"لطفاً {wait_seconds} ثانیه صبر کنید و دوباره شماره را ارسال کنید."
                )
                # generator_data عمداً حذف نمی‌شود تا کاربر مجبور به /start دوباره
                # نشود؛ فقط در همین مرحله با محدودیت زمانی می‌ماند.
                if client:
                    try:
                        await client.disconnect()
                    except Exception:
                        pass
                if user_id in active_signins:
                    del active_signins[user_id]

            return

        if generator["step"] == "get_password":
            client = active_signins.get(user_id)

            if not client:
                await event.respond("❌ نشست منقضی شده است. لطفاً مجدداً /start را بزنید.")
                del generator_data[user_id]
                return

            try:
                await client.sign_in(password=text)
                session_string = client.session.save()

                if generator.get("recovery") and user_id in user_data:
                    user_data[user_id]["session"] = session_string
                    user_data[user_id]["status"] = True
                    user_data[user_id]["step"] = "managed"
                else:
                    user_data[user_id] = make_default_user(session=session_string, status=True, step="managed")

                save_user(user_id, user_data[user_id])
                await _teardown_existing_client(user_id)
                register_active_client(user_id, client)

                await event.respond(
                    "✅ **ورود با رمز دو مرحله‌ای موفقیت‌آمیز بود!**\n\n"
                    "حساب شما با موفقیت به ربات متصل شد."
                )

                del generator_data[user_id]
                if user_id in active_signins:
                    del active_signins[user_id]

                await event.respond(
                    get_start_root_text(),
                    buttons=get_start_root_keyboard(user_data[user_id])
                )
            except Exception as e:
                await event.respond(
                    f"❌ **رمز دو مرحله‌ای اشتباه است:**\n\n`{str(e)}`\n\n"
                    "لطفاً مجدداً رمز صحیح را وارد کنید:"
                )

            return

    # ====== دریافت سشن آماده ======
    # ====== تنظیم متن منشی ======
    if user_id in user_data and user_data[user_id].get("step") == "secretary_get_text":
        new_text = text if text else "مشغولم، بعداً پاسخ می‌دهم ✅"
        user_data[user_id]["secretary_text"] = new_text
        user_data[user_id]["step"] = "managed"
        save_user(user_id, user_data[user_id])

        await event.respond("✅ متن منشی با موفقیت ذخیره شد.")
        await event.respond(
            get_secretary_menu_text(user_data[user_id]),
            buttons=get_secretary_menu_keyboard(user_data[user_id])
        )
        return

    # ====== تنظیم تایم منشی ======
    if user_id in user_data and user_data[user_id].get("step") == "secretary_get_time":
        try:
            seconds = int(text)
            if seconds < 1 or seconds > 86400:
                raise ValueError
        except (ValueError, TypeError):
            await event.respond("❌ لطفاً یک عدد معتبر (بین 1 تا 86400) بر حسب ثانیه ارسال کنید.")
            return

        user_data[user_id]["secretary_delay"] = seconds
        user_data[user_id]["step"] = "managed"
        save_user(user_id, user_data[user_id])

        await event.respond(f"✅ زمان تأخیر منشی روی {seconds} ثانیه تنظیم شد.")
        await event.respond(
            get_secretary_menu_text(user_data[user_id]),
            buttons=get_secretary_menu_keyboard(user_data[user_id])
        )
        return

    # ====== انتقال الماس: مرحله اول (آیدی مقصد) ======
    # ====== کد هدیه: دریافت و اعتبارسنجی کد از کاربر ======
    if user_id in user_data and user_data[user_id].get("step") == "giftcode_get_code":
        code = text.strip()
        user_data[user_id]["step"] = "managed"

        success, message, new_balance = redeem_gift_code_db(code, user_id)
        if success and new_balance is not None:
            user_data[user_id]["diamonds"] = new_balance
            log_settings_change(user_id, "giftcode_redeemed", code)

        await event.respond(
            message,
            buttons=[[styled_button("➜ بازگشت", b"start_root", style=STYLE_OFF)]]
        )
        return

    if user_id in user_data and user_data[user_id].get("step") == "transfer_get_target":
        try:
            target_id = int(text)
        except ValueError:
            await event.respond("❌ آیدی عددی معتبر نیست. لطفاً فقط عدد ارسال کنید.", buttons=get_transfer_cancel_keyboard())
            return

        if target_id == user_id:
            await event.respond("❌ انتقال به خودتان امکان‌پذیر نیست.", buttons=get_transfer_cancel_keyboard())
            return

        if target_id not in user_data or not user_data[target_id].get("session"):
            await event.respond("❌ کاربری با این آیدی در سیستم ثبت‌نام نکرده است.", buttons=get_transfer_cancel_keyboard())
            return

        transfer_data[user_id] = {"target_id": target_id}
        user_data[user_id]["step"] = "transfer_get_amount"

        await event.respond(
            f"✅ کاربر مقصد یافت شد: `{target_id}`\n\n"
            "💎 حالا مقدار الماس موردنظر برای انتقال را وارد کنید:",
            buttons=get_transfer_cancel_keyboard()
        )
        return

    # ====== انتقال الماس: مرحله دوم (مقدار) ======
    if user_id in user_data and user_data[user_id].get("step") == "transfer_get_amount":
        pending = transfer_data.get(user_id)
        if not pending or "target_id" not in pending:
            user_data[user_id]["step"] = "managed"
            await event.respond("❌ عملیات منقضی شده. دوباره از منوی حساب کاربری اقدام کنید.")
            return

        try:
            amount = float(text)
        except ValueError:
            await event.respond("❌ لطفاً فقط عدد ارسال کنید.", buttons=get_transfer_cancel_keyboard())
            return

        if amount <= 0:
            await event.respond("❌ مقدار انتقال باید بیشتر از صفر باشد.", buttons=get_transfer_cancel_keyboard())
            return

        current_balance = user_data[user_id].get("diamonds", 0)
        if current_balance < amount:
            await event.respond(
                f"❌ موجودی شما کافی نیست.\n💎 موجودی فعلی: {format_diamonds(current_balance)}",
                buttons=get_transfer_cancel_keyboard()
            )
            return

        target_id = pending["target_id"]
        transfer_data[user_id]["amount"] = amount
        user_data[user_id]["step"] = "transfer_confirm"

        new_sender_balance = current_balance - amount
        target_balance = user_data.get(target_id, {}).get("diamonds", 0)
        new_receiver_balance = target_balance + amount

        await event.respond(
            "🧾 **تایید انتقال الماس**\n\n"
            f"👤 فرستنده: `{user_id}`\n"
            f"👤 گیرنده: `{target_id}`\n\n"
            f"💎 تعداد الماس: {format_diamonds(amount)}\n\n"
            f"موجودی فعلی شما: {format_diamonds(current_balance)}\n"
            f"موجودی شما پس از انتقال: {format_diamonds(new_sender_balance)}\n\n"
            "آیا از انجام این انتقال مطمئن هستید؟",
            buttons=get_transfer_confirm_keyboard()
        )
        return

    if user_id in user_data and user_data[user_id].get("step") == "get_session":
        # روش قدیمی «ثبت با سشن آماده» به‌طور کامل حذف شده است.
        return

# ======================== هندلر دکمه‌های تایید ارسال پیام ========================
@bot.on(events.CallbackQuery)
async def broadcast_callback_handler(event):
    data = event.data

    # این هندلر فقط باید به دکمه‌های تایید/لغو ارسال همگانی واکنش نشان دهد؛
    # بدون این فیلتر، روی هر کلیکی در کل ربات هم اجرا می‌شد و برای ادمین‌ها
    # پیام «عملیات فعالی وجود ندارد» را حتی روی دکمه‌های بی‌ربط نشان می‌داد.
    if data not in (b"broadcast_confirm", b"broadcast_cancel"):
        return

    user_id = event.sender_id

    if not is_admin(user_id):
        await event.answer("❌ شما دسترسی ادمین ندارید!", alert=True)
        return

    if user_id not in broadcast_data:
        await event.answer("❌ عملیات فعالی وجود ندارد!", alert=True)
        return

    broadcast = broadcast_data[user_id]

    if data == b"broadcast_confirm":
        await safe_edit(event, "⏳ در حال ارسال پیام...")

        src_chat_id = broadcast.get("src_chat_id")
        src_message_id = broadcast.get("src_message_id")
        try:
            src_msg = await bot.get_messages(src_chat_id, ids=src_message_id)
        except Exception as e:
            log_internal_error("broadcast_fetch_src_message", e)
            src_msg = None

        if not src_msg:
            await safe_edit(event,
                "❌ **پیام مبدا دیگر در دسترس نیست (شاید حذف شده).**\n\nعملیات لغو شد.",
                buttons=[styled_button("➜ بازگشت", b"admin_panel", style=STYLE_OFF)]
            )
            del broadcast_data[user_id]
            return

        if broadcast["type"] == "single":
            target_id = broadcast["target_id"]
            broadcast_id = create_broadcast_record_db(user_id, "single", target_id, broadcast.get("summary", ""))
            try:
                sent = await _copy_message_to(bot, target_id, src_msg)
                if broadcast_id and sent:
                    add_broadcast_delivery_db(broadcast_id, target_id, target_id, sent.id)
                await safe_edit(event,
                    f"✅ **پیام با موفقیت به کاربر {target_id} ارسال شد!**",
                    buttons=[styled_button("➜ بازگشت", b"admin_panel", style=STYLE_OFF)]
                )
            except Exception as e:
                await safe_edit(event,
                    f"❌ **خطا در ارسال پیام:**\n\n`{str(e)}`",
                    buttons=[styled_button("➜ بازگشت", b"admin_panel", style=STYLE_OFF)]
                )

        else:
            total_users = len(user_data)
            success_count = 0
            fail_count = 0
            broadcast_id = create_broadcast_record_db(user_id, "broadcast", None, broadcast.get("summary", ""))

            for uid in list(user_data.keys()):
                try:
                    sent = await _copy_message_to(bot, uid, src_msg)
                    success_count += 1
                    if broadcast_id and sent:
                        add_broadcast_delivery_db(broadcast_id, uid, uid, sent.id)
                    await asyncio.sleep(0.1)
                except Exception as e:
                    fail_count += 1
                    logging.error(f"❌ خطا در ارسال به {uid}: {e}")

            await safe_edit(event,
                f"✅ **ارسال پیام همگانی کامل شد!**\n\n"
                f"📨 تعداد کل: {total_users}\n"
                f"✅ موفق: {success_count}\n"
                f"❌ ناموفق: {fail_count}",
                buttons=[styled_button("➜ بازگشت", b"admin_panel", style=STYLE_OFF)]
            )

        del broadcast_data[user_id]
        return

    elif data == b"broadcast_cancel":
        del broadcast_data[user_id]
        await safe_edit(event,
            "❌ **ارسال پیام لغو شد.**",
            buttons=[styled_button("➜ بازگشت", b"admin_panel", style=STYLE_OFF)]
        )
        return

# ======================== اجرای اصلی ========================
if __name__ == "__main__":
    logging.info("🚀 راه‌اندازی ربات NovaSelf...")

    init_db()
    user_data = get_all_users()
    logging.info(f"📊 تعداد کاربران بارگذاری شده: {len(user_data)}")
    load_reactions_cache()
    load_autoreplies_cache()
    load_feature_locks_cache()
    load_global_locks_cache()
    load_join_gate_cache()

    loop = asyncio.get_event_loop()

    async def _load_bot_username():
        global BOT_USERNAME
        me = await bot.get_me()
        BOT_USERNAME = me.username
        logging.info(f"🤖 نام‌کاربری ربات برای پنل درون‌چتی ذخیره شد: @{BOT_USERNAME}")

    loop.run_until_complete(_load_bot_username())
    loop.create_task(autostart_saved_users())

    webapp_app = create_webapp_app(
        bot_token=BOT_TOKEN,
        user_data=user_data,
        save_user=save_user,
        start_self_client=start_self_client,
        stop_self_client=stop_self_client,
        format_diamonds=format_diamonds,
        diamond_rate_per_hour=DIAMOND_RATE_PER_HOUR,
        allowed_origin=MINIAPP_ORIGIN,
        is_feature_locked=is_feature_locked,
        is_feature_globally_locked=is_feature_globally_locked,
    )
    loop.create_task(run_webapp_server(webapp_app, host="0.0.0.0", port=PORT))

    logging.info("✅ ربات با موفقیت راه‌اندازی شد!")
    logging.info(f"👑 تعداد ادمین‌ها: {len(ADMIN_IDS)}")

    bot.run_until_disconnected()
