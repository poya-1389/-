# -*- coding: utf-8 -*-
"""
nova_menus.py
====================================================================
تمام تابع‌های ساخت متن/دکمه (UI) پنل کاربر و پنل ادمین NovaSelf، به‌علاوه
ساخت تصویر دیجیتالیِ کارتِ `.پنل`. این توابع خالص‌اند: فقط از روی
User/آرگومان‌های ورودی و کش‌های خواندنیِ nova_state رشته/دکمه می‌سازند -
هیچ Handlerِ تلگرامی (`@bot.on`) اینجا نیست.

جهتِ وابستگی: این فایل از nova_state و nova_db وارد می‌کند، اما هرگز
برعکس - nova_db از این فایل چیزی وارد نمی‌کند (تا از Import حلقوی
جلوگیری شود).
====================================================================
"""

import io
import logging
from telethon import Button
try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

import nova_state
from nova_utils import (
    styled_button, toggle_button, toggle_label, status_icon,
    STYLE_ON, STYLE_OFF, STYLE_INFO, wrap_panel_buttons,
    build_clock_preview, build_date_preview, log_internal_error,
)
from nova_state import (
    bot, feature_locks, reaction_targets, autoreply_cache,
    ACTIONS, FONT_NAMES, DATE_TYPE_NAMES, TEXTMODE_NAMES, AUTOREPLY_MATCH_TYPES,
    DIAMOND_RATE_PER_HOUR, DIAMOND_PRICE_TOMAN,
    MEOW_INTERVAL_SECONDS, FISH_INTERVAL_SECONDS,
    MEOWPOINT_INTERVAL_SECONDS, FRIDGE_INTERVAL_SECONDS,
    CLEANUP_MAX_COUNT, FISH_OPERATION_NAMES_FA,
    format_diamonds, format_toman, format_expiry,
    format_interval, apply_font, format_date, tehran_now,
)
from nova_db import (
    get_db_connection, list_backups_db, list_broadcasts_db,
    list_gift_codes_db, list_join_channels_db, get_user_stats,
    get_referral_reward_db, is_referral_enabled_db, get_referral_stats_db,
)

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
    ("cleanup", "🧹 حذف و پاکسازی"),
    ("blockmgmt", "🚫 بلاک و آن‌بلاک"),
    ("autoseen", "👁️ سین خودکار"),
    ("videomessage", "🎥 ویدیو مسیج"),
    ("balance", "💎 موجودی"),
]
FEATURE_LOCK_LABELS = dict(FEATURE_LOCK_DEFS)

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
    lines = [
        "🔔 **مدیریت جوین اجباری**\n",
        f"تعداد کانال‌ها: {len(channels)}",
        "(عضویت هر بار زنده از تلگرام چک می‌شود؛ آماری از «تأییدشده‌ها» ذخیره نمی‌شود)\n",
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

def get_settings_root_keyboard(user_id, page=1):
    """
    صفحه‌ی «⚙ تنظیمات سلف» — دسترسی به تمام قابلیت‌های سلف، طبق چیدمان درخواستی،
    حالا در ۲ صفحه. وقتی قابلیتی برای کاربر قفل باشد: به‌جای ایموجی مخصوص همان
    قابلیت، ایموجی 🔒 نمایش داده می‌شود و رنگ دکمه هم قرمز (STYLE_OFF) می‌شود.
    """
    locks = feature_locks.get(user_id, set())

    def btn(key, emoji, text, cb_data):
        locked = key in locks
        icon = "🔒" if locked else emoji
        style = STYLE_OFF if locked else STYLE_INFO
        return styled_button(f"{icon} {text}", cb_data, style=style)

    # دکمه‌های شماره‌ی صفحه: بدون رنگ، فقط صفحه‌ی فعلی سبز می‌شود. از چپ «１»
    # (صفحه‌ی اول) و از راست «２» (صفحه‌ی دوم) - ترتیب هرگز عوض نمی‌شود.
    page_row = [
        styled_button("１", b"settings_root", style=(STYLE_ON if page == 1 else None)),
        styled_button("２", b"settings_page2", style=(STYLE_ON if page == 2 else None)),
    ]

    if page == 2:
        return [
            [btn("balance", "💎", "موجودی", b"menu_balance")],
            page_row,
            [styled_button("➜ بازگشت", b"panel_root", style=STYLE_OFF)]
        ]

    return [
        [
            btn("date", "📅", "تاریخ", b"menu_date"),
            btn("actions", "🎭", "اکشن", b"menu_actions"),
            btn("time", "⌚", "ساعت", b"menu_time"),
        ],
        [
            btn("textmode", "🖊️", "حالت متن", b"menu_textmode"),
            btn("secretary", "🧑‍💼", "منشی پیوی", b"menu_secretary"),
        ],
        [
            btn("tag", "🏷️", "تگ", b"menu_tag"),
            btn("meow", "🐱", "میو", b"menu_meow"),
            btn("ping", "🏓", "پینگ", b"menu_ping"),
        ],
        [
            btn("autoreply", "🤖", "پاسخ خودکار", b"menu_autoreply"),
            btn("reaction", "👍", "ریکت", b"menu_reaction"),
            btn("whois", "🪪", "اطلاعات", b"menu_whois"),
        ],
        [
            btn("cleanup", "🧹", "حذف و پاکسازی", b"menu_cleanup"),
            btn("blockmgmt", "🚫", "بلاک و آن‌بلاک", b"menu_blockmgmt"),
        ],
        [
            btn("videomessage", "🎥", "ویدیو مسیج", b"menu_videomessage"),
            btn("autoseen", "👁️", "سین خودکار", b"menu_autoseen"),
        ],
        page_row,
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
    """
    شبکه‌ی انتخابِ اکشن‌ها؛ همه از ACTIONS خوانده می‌شوند (شامل «همیشه آنلاین»)،
    پس فقط یکی می‌تواند هم‌زمان فعال باشد - دقیقاً مثل بقیه‌ی اکشن‌ها.
    """
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

# ======================== منوی موجودی ========================
def get_balance_menu_text():
    return (
        "💎 **قابلیت موجودی**\n\n"
        "▫️ `.موجودی` — نمایش موجودی الماس سلف شما"
    )

def get_balance_menu_keyboard():
    return [[styled_button("➜ بازگشت", b"settings_page2", style=STYLE_OFF)]]

# ======================== منوی حذف و پاکسازی ========================
def get_cleanup_menu_text():
    return (
        "🧹 **حذف و پاکسازی**\n\n"
        "این قابلیت با ارسال دستور زیر (توسط خودتان) در هر چتی فعال می‌شود:\n\n"
        "▫️ `.حذف` + تعداد پیام\n"
        "— حذف تعداد مشخصی از پیام‌های اخیر همان چت\n\n"
        "مثال:\n"
        "`.حذف 10`\n"
        "یا:\n"
        "`.حذف ۱۰`\n\n"
        f"حداکثر {CLEANUP_MAX_COUNT} پیام در هر اجرا (برای جلوگیری از محدودیت تلگرام)."
    )

def get_cleanup_menu_keyboard():
    return [[styled_button("➜ بازگشت", b"settings_root", style=STYLE_OFF)]]

# ======================== منوی بلاک و آن‌بلاک ========================
def get_blockmgmt_menu_text():
    return (
        "🚫 **بلاک و آن‌بلاک**\n\n"
        "این قابلیت با Reply روی پیام شخص موردنظر و ارسال یکی از دستورات زیر (توسط خودتان) کار می‌کند:\n\n"
        "▫️ `.بلاک` — بلاک‌کردن همان کاربر\n"
        "▫️ `.آن بلاک` — آن‌بلاک‌کردن همان کاربر\n\n"
        "نکته: حتماً باید روی پیام همان شخص Reply کرده باشید."
    )

def get_blockmgmt_menu_keyboard():
    return [[styled_button("➜ بازگشت", b"settings_root", style=STYLE_OFF)]]

# ======================== منوی سین خودکار ========================
def get_autoseen_menu_text(user):
    return f"👁️ **قابلیت سین خودکار**\n\nوضعیت: {status_icon(user.get('autoseen_enabled', False))}"

def get_autoseen_menu_keyboard(user):
    return [
        [toggle_button("سین خودکار", user.get("autoseen_enabled", False), b"autoseen_toggle")],
        [styled_button("➜ بازگشت", b"settings_root", style=STYLE_OFF)]
    ]

# ======================== منوی ویدیو مسیج ========================
def get_videomessage_menu_text():
    return (
        "🎥 **قابلیت ویدیو مسیج**\n\n"
        "▫️ `.ویدیو مسیج` + ریپلای\n\n"
        "روی یک ویدیو ریپلای کنید و خروجی را به‌صورت ویدیو مسیج یا ویدیو گرد دریافت کنید"
    )

def get_videomessage_menu_keyboard():
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
        if key in locks:
            text += " 🔒"
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
        [styled_button("👥 الماس رایگان", b"account_referral", style=STYLE_INFO)],
        [styled_button("➜ بازگشت", b"start_root", style=STYLE_OFF)]
    ]

# ======================== صفحه‌ی الماس رایگان (Referral) ========================
def get_referral_page_text(user_id, user):
    if not is_referral_enabled_db():
        return (
            "💎 **الماس رایگان**\n\n"
            "❌ قابلیتِ رفرال در حال حاضر توسط مدیریت غیرفعال است."
        )

    bot_username = nova_state.BOT_USERNAME
    link = f"https://t.me/{bot_username}?start={user_id}" if bot_username else "(در حال آماده‌سازی...)"
    reward = get_referral_reward_db()
    return (
        "💎 **الماس رایگان**\n\n"
        f"🔗 لینک دعوت شما:\n`{link}`\n\n"
        f"🎁 جایزه هر رفرال:\n{format_diamonds(reward)} الماس\n\n"
        f"👥 تعداد رفرال شما:\n{user.get('referral_count', 0)}"
    )

def get_referral_page_keyboard():
    return [[styled_button("➜ بازگشت", b"start_account", style=STYLE_OFF)]]

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
        ]
    ]

# ======================== خرید الماس (کیبورد عددی + State Machine) ========================
MAX_BUY_DIAMONDS_DIGITS = 7  # جلوگیری از وارد کردن اعداد نجومی/بی‌معنی

def _calc_buy_days(amount):
    """
    تعداد روزی که مقدار الماسِ واردشده برای «روشن ماندنِ» سلف کافی است - واقعی و
    بر اساس همان نرخِ مصرفِ ساعتیِ پروژه (DIAMOND_RATE_PER_HOUR) محاسبه می‌شود،
    نه یک عدد ثابت/Hard-code.
    """
    try:
        amount = float(amount or 0)
    except (TypeError, ValueError):
        return 0
    if amount <= 0 or not DIAMOND_RATE_PER_HOUR:
        return 0
    total_hours = amount / DIAMOND_RATE_PER_HOUR
    return int(total_hours // 24)

def get_buy_amount_text(buffer_str):
    """
    طبق درخواست: نمایش مقدار الماس/تومان/روز از روی دکمه‌ی شیشه‌ای به متنِ خودِ
    پیام منتقل شده است.
    """
    try:
        amount = int(buffer_str) if buffer_str else 0
    except ValueError:
        amount = 0
    toman = amount * DIAMOND_PRICE_TOMAN
    days = _calc_buy_days(amount)
    return (
        "💎 **خرید الماس**\n\n"
        "تعداد الماسی که می‌خواهید خریداری کنید را با کیبورد زیر وارد کنید:\n\n"
        f"💎 • الماس: {format_diamonds(amount)}\n"
        f"💰 • تومان: {toman:,.0f} تومان\n"
        f"📆 • روز: {days} روز"
    )

def get_buy_amount_keyboard(buffer_str):
    # طبق درخواست صریح: ردیفِ پیش‌نمایش (دکمه‌ی بی‌رنگِ «تعداد/تومان») حذف شده
    # (این اطلاعات الان در متنِ پیام است)، و تمام دکمه‌های عددی آبی شدند.
    return [
        [
            styled_button("1", b"buy_k_1", style=STYLE_INFO),
            styled_button("2", b"buy_k_2", style=STYLE_INFO),
            styled_button("3", b"buy_k_3", style=STYLE_INFO),
        ],
        [
            styled_button("4", b"buy_k_4", style=STYLE_INFO),
            styled_button("5", b"buy_k_5", style=STYLE_INFO),
            styled_button("6", b"buy_k_6", style=STYLE_INFO),
        ],
        [
            styled_button("7", b"buy_k_7", style=STYLE_INFO),
            styled_button("8", b"buy_k_8", style=STYLE_INFO),
            styled_button("9", b"buy_k_9", style=STYLE_INFO),
        ],
        [
            styled_button("⌫", b"buy_k_back", style=STYLE_OFF),
            styled_button("0", b"buy_k_0", style=STYLE_INFO),
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
        [styled_button("👥 مدیریت رفرال", b"admin_referral", style=STYLE_INFO)],
        [styled_button("💾 سیستم بکاپ", b"admin_backup", style=STYLE_INFO)],
        [styled_button("📜 لاگ‌های مدیریتی اخیر", b"admin_logs", style=STYLE_INFO)],
        [styled_button("🔄 بروزرسانی همه کاربران", b"admin_refresh_all", style=STYLE_INFO)]
    ]

def get_admin_referral_text():
    stats = get_referral_stats_db()
    reward = get_referral_reward_db()
    enabled = is_referral_enabled_db()
    return (
        "👥 **مدیریت رفرال**\n\n"
        f"🎁 مقدار جایزه‌ی فعلی: {format_diamonds(reward)} الماس\n"
        f"⚙️ وضعیت سراسری: {status_icon(enabled)}\n\n"
        f"📊 تعداد کل رفرال‌های ثبت‌شده: {stats['total']}\n"
        f"✅ تعداد رفرال‌هایی که جایزه گرفته‌اند: {stats['credited']}"
    )

def get_admin_referral_keyboard(enabled):
    return [
        [toggle_button("رفرال سراسری", enabled, b"admin_referral_toggle")],
        [styled_button("✏️ تغییر مقدار جایزه", b"admin_referral_set_reward", style=STYLE_INFO)],
        [styled_button("0️⃣ صفر کردن جایزه", b"admin_referral_zero_reward", style=STYLE_OFF)],
        [styled_button("➜ بازگشت", b"admin_panel", style=STYLE_OFF)]
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
    ("reaction_enabled", "ریکت"),
    ("autoreply_enabled", "پاسخ خودکار"),
    ("autoseen_enabled", "سین خودکار"),
    ("meow_enabled", "میو"),
    ("fish_enabled", "ماهی"),
    ("meowpoint_enabled", "میو پوینت"),
    ("streetcat_enabled", "نجات پیشی"),
    ("fridge_enabled", "یخچال میویی"),
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

def _load_card_font(size, bold=True):
    """فونت لاتین برای کارت پنل؛ روی چند مسیر رایج امتحان می‌شود و در نبودشان
    به فونت پیش‌فرض Pillow برمی‌گردد (بدون کرش)."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()

def _card_text_width(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]

async def build_panel_card_image(owner_id, user):
    """
    ساخت تصویر «کارت پنل» با ظاهر دیجیتالی برای دستور `.پنل` (افقی، 960×560):
    سمت چپ عکسِ پروفایلِ کاربر در دایره‌ای بزرگ با حلقه‌ی نئونی، سمت راست عنوان
    NOVA SELF و زیرش یوزرنیم و آیدی عددی‌اش.

    اگر Pillow نصب نباشد، یا دانلود عکس پروفایل/هر بخش دیگر با خطا مواجه شود،
    None برمی‌گرداند تا پنل بدون تصویر (دقیقاً مثل قبل، فقط متنی) کار کند و
    قابلیت اصلیِ باز شدنِ پنل هرگز به‌خاطر این افزوده به‌هم نریزد.
    """
    if not _PIL_AVAILABLE:
        return None
    try:
        W, H = 960, 560
        bg_top, bg_bottom = (6, 8, 24), (24, 8, 48)
        img = Image.new("RGB", (W, H), bg_top)
        draw = ImageDraw.Draw(img)
        for y in range(H):
            t = y / H
            r = int(bg_top[0] + (bg_bottom[0] - bg_top[0]) * t)
            g = int(bg_top[1] + (bg_bottom[1] - bg_top[1]) * t)
            b = int(bg_top[2] + (bg_bottom[2] - bg_top[2]) * t)
            draw.line([(0, y), (W, y)], fill=(r, g, b))

        grid_color = (34, 52, 82)
        for x in range(0, W, 46):
            draw.line([(x, 0), (x, H)], fill=grid_color, width=1)
        for y in range(0, H, 46):
            draw.line([(0, y), (W, y)], fill=grid_color, width=1)

        accent = (0, 220, 255)
        bl, pad, lw = 50, 30, 5
        for (cx, cy, dx, dy) in [(pad, pad, 1, 1), (W - pad, pad, -1, 1),
                                  (pad, H - pad, 1, -1), (W - pad, H - pad, -1, -1)]:
            draw.line([(cx, cy), (cx + dx * bl, cy)], fill=accent, width=lw)
            draw.line([(cx, cy), (cx, cy + dy * bl)], fill=accent, width=lw)

        # ---- آواتار سمت چپ ----
        avatar_size = 300
        avatar_x = 70
        avatar_y = (H - avatar_size) // 2

        avatar_img = None
        try:
            photo_bytes = await bot.download_profile_photo(owner_id, file=bytes)
            if photo_bytes:
                avatar_img = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
        except Exception as e:
            log_internal_error("panel_card_avatar_download", f"user={owner_id} err={e}")
            avatar_img = None

        if avatar_img is None:
            avatar_img = Image.new("RGB", (avatar_size, avatar_size), (26, 30, 54))
            ad = ImageDraw.Draw(avatar_img)
            initial_source = user.get("username") or str(owner_id)
            initial = initial_source[0].upper()
            init_font = _load_card_font(140)
            iw = _card_text_width(ad, initial, init_font)
            ad.text(((avatar_size - iw) / 2, avatar_size / 2 - 70), initial, font=init_font, fill=(0, 220, 255))
        else:
            # مربعی‌کردن (Crop از وسط) قبل از دایره‌ای‌کردن، تا عکس‌های غیرمربعی کش نیایند
            w0, h0 = avatar_img.size
            side = min(w0, h0)
            left, top = (w0 - side) // 2, (h0 - side) // 2
            avatar_img = avatar_img.crop((left, top, left + side, top + side)).resize((avatar_size, avatar_size))

        mask = Image.new("L", (avatar_size, avatar_size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, avatar_size, avatar_size), fill=255)

        ring_pad = 16
        ring_size = avatar_size + ring_pad * 2
        ring_layer = Image.new("RGBA", (ring_size, ring_size), (0, 0, 0, 0))
        ring_draw = ImageDraw.Draw(ring_layer)
        ring_draw.ellipse((3, 3, ring_size - 3, ring_size - 3), outline=(0, 220, 255, 255), width=7)
        ring_blur = ring_layer.filter(ImageFilter.GaussianBlur(7))
        img.paste(ring_blur, (avatar_x - ring_pad, avatar_y - ring_pad), ring_blur)
        img.paste(ring_layer, (avatar_x - ring_pad, avatar_y - ring_pad), ring_layer)
        img.paste(avatar_img, (avatar_x, avatar_y), mask)

        # ---- بلوکِ متنیِ سمت راست ----
        right_x = avatar_x + avatar_size + 50
        right_margin = 26
        max_text_width = W - right_x - right_margin

        # طبق گزارش «متن‌ها هنوز کوچیکن»، این نسخه فونت‌ها را به‌طور محسوس بزرگ‌تر
        # کرده (نه فقط چند پیکسل) - چون تلگرام تصویرِ اینلاین را در حبابِ چت با
        # عرضِ فیزیکیِ محدود نمایش می‌دهد، اندازه‌ی مؤثرِ فونت روی صفحه از نسبتِ
        # «اندازه‌ی فونت به عرضِ کل تصویر» می‌آید، نه از رزولوشنِ خام؛ پس برای
        # واقعاً بزرگ‌تر دیده‌شدن، این نسبت باید افزایش پیدا کند.
        title_font = _load_card_font(104, bold=True)
        sub_font_small = _load_card_font(30, bold=False)
        title_text = "NOVA SELF"
        title_y = 60

        # اگر به هر دلیلی (مثلاً فونتِ Fallback) عنوان از عرضِ باقیمانده رد بشود،
        # فونتش را تا حدی کوچک می‌کنیم که کامل جا شود (به‌جای بریده‌شدن).
        tw_title = _card_text_width(ImageDraw.Draw(img), title_text, title_font)
        while tw_title > max_text_width and title_font.size > 50:
            title_font = _load_card_font(title_font.size - 2, bold=True)
            tw_title = _card_text_width(ImageDraw.Draw(img), title_text, title_font)

        glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_layer)
        glow_draw.text((right_x, title_y), title_text, font=title_font, fill=(0, 220, 255, 255))
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(16))
        img = Image.alpha_composite(img.convert("RGBA"), glow_layer).convert("RGB")
        draw = ImageDraw.Draw(img)
        draw.text((right_x, title_y), title_text, font=title_font, fill=(255, 255, 255))

        sub_text = "SELF MANAGEMENT PANEL"
        draw.text((right_x + 4, title_y + 130), sub_text, font=sub_font_small, fill=(120, 170, 220))
        draw.line([(right_x, title_y + 185), (right_x + 380, title_y + 185)], fill=(0, 150, 190), width=3)

        info_font = _load_card_font(70, bold=True)
        sub_font = _load_card_font(48, bold=False)
        # نکته: فونت لاتین (DejaVu/Liberation) شکل‌دهیِ درستِ حروف فارسی/عربی را
        # پشتیبانی نمی‌کند، پس عمداً همه‌ی متن‌های داخل خودِ تصویر انگلیسی هستند.
        username_text = f"@{user.get('username')}" if user.get("username") else "No Username"
        id_text = f"ID: {owner_id}"

        # اگر یوزرنیم طولانی بود (تلگرام حداکثر ۳۲ کاراکتر مجاز می‌داند)، فونت را
        # تا حدی کوچک می‌کنیم که در عرضِ باقیمانده جا شود.
        uw = _card_text_width(draw, username_text, info_font)
        while uw > max_text_width and info_font.size > 24:
            info_font = _load_card_font(info_font.size - 2, bold=True)
            uw = _card_text_width(draw, username_text, info_font)

        draw.text((right_x, title_y + 228), username_text, font=info_font, fill=(255, 255, 255))
        draw.text((right_x, title_y + 312), id_text, font=sub_font, fill=(150, 205, 255))

        tag_font = _load_card_font(22, bold=False)
        tag_text = "NOVASELF  •  DIGITAL IDENTITY CARD"
        tgw = _card_text_width(draw, tag_text, tag_font)
        draw.text(((W - tgw) / 2, H - 44), tag_text, font=tag_font, fill=(85, 115, 155))

        out = io.BytesIO()
        out.name = "novaself_panel.png"
        img.save(out, "PNG")
        out.seek(0)
        return out
    except Exception as e:
        log_internal_error("panel_card_image", e)
        return None

