# -*- coding: utf-8 -*-
"""
nova_utils.py
====================================================================
ماژول کمکی مستقل NovaSelf.

این فایل عمداً هیچ وابستگی‌ای به main.py ندارد (نه user_data، نه bot،
نه هیچ متغیر سراسری دیگری import نمی‌کند) تا کاملاً ماژولار، قابل تست
و بدون ریسک تداخل با بقیه‌ی پروژه باشد. هر تابع فقط از روی ورودی‌هایی
که بهش داده می‌شه کار می‌کنه.

شامل:
  1) آیکون یکپارچه‌ی وضعیت (✓ / ✕)
  2) پیش‌نمایش فونت ساعت و تاریخ
  3) متن رسید دوطرفه‌ی انتقال الماس
  4) جلوگیری از پردازش کلیک‌های تکراری (Debounce)
  5) اجرای امن عملیات تلگرام با مدیریت خودکار FloodWait
  6) لاگ داخلی عملیات مهم (فایل جدا: nova_internal.log)
  7) دکمه‌های شیشه‌ای رنگی (Bot API 9.4، با Fallback امن)
====================================================================
"""

import time
import logging
import asyncio
from datetime import datetime

from telethon.errors import FloodWaitError
from telethon.tl.custom import Button

# ==================== ۷. دکمه‌ی شیشه‌ای رنگی (با Fallback) ====================
# تلگرام از Bot API 9.4 (۹ فوریه ۲۰۲۶) فیلد style را به دکمه‌ها اضافه کرد که
# فقط ۳ مقدار دارد: primary (آبی), success (سبز), danger (قرمز).
# این ویژگی فقط روی نسخه‌های تازه‌ی Telethon (>=1.44.0) و کلاینت‌های تلگرامِ
# بعد از فوریه ۲۰۲۶ نمایش داده می‌شود؛ روی بقیه، دکمه بدون رنگ (حالت عادی) دیده می‌شود.
STYLE_ON = "success"    # سبز — برای وضعیت فعال/روشن
STYLE_OFF = "danger"    # قرمز — برای وضعیت غیرفعال/خاموش
STYLE_INFO = "primary"  # آبی — برای دکمه‌های اطلاعاتی/خنثی مثل «حساب کاربری»

_style_supported = True  # اگر نسخه‌ی Telethon قدیمی باشد و اولین‌بار خطا بدهد، خودکار False می‌شود


def styled_button(text: str, data: bytes, style: str = None):
    """
    معادل امنِ Button.inline که در صورت پشتیبانی، رنگ می‌گیرد.
    اگر نسخه‌ی نصب‌شده‌ی Telethon از پارامتر style پشتیبانی نکند (کتابخانه‌ی
    قدیمی‌تر)، خودش خاموش‌شان می‌کند و به‌جای کرش‌کردن، دکمه‌ی بدون رنگ برمی‌گرداند.
    """
    global _style_supported

    if style and _style_supported:
        try:
            return Button.inline(text, data, style=style)
        except TypeError:
            _style_supported = False
            logging.warning("⚠️ این نسخه از Telethon از دکمه‌های رنگی (style) پشتیبانی نمی‌کند؛ نسخه را به‌روزرسانی کنید.")

    return Button.inline(text, data)


def toggle_button(label: str, flag: bool, data: bytes):
    """دکمه‌ی روشن/خاموش با آیکون یکپارچه و رنگ متناظر (سبز=فعال، قرمز=غیرفعال)."""
    text = toggle_label(label, flag)
    style = STYLE_ON if flag else STYLE_OFF
    return styled_button(text, data, style=style)


ICON_OFF = "✕"


def status_icon(flag: bool) -> str:
    """آیکون یکسان برای همه‌ی منوها: فعال=✓ ، غیرفعال=✕."""
    return ICON_ON if flag else ICON_OFF


def toggle_label(label: str, flag: bool) -> str:
    """برچسب یکدست برای دکمه‌های روشن/خاموش، مثل: 'ساعت نام (✓)'."""
    return f"{label} ({status_icon(flag)})"


# ==================== ۲. پیش‌نمایش فونت‌ها ====================
def build_clock_preview(apply_font_fn, font_id: int, now: datetime = None) -> str:
    """نمونه‌ی ساعت با فونت انتخابی، مثل: ۱۲:۰۰ با فونت مدنظر."""
    now = now or datetime.now()
    raw = now.strftime("%H:%M")
    return apply_font_fn(raw, font_id)


def build_date_preview(apply_font_fn, format_date_fn, font_id: int, date_type: str, now: datetime = None) -> str:
    """نمونه‌ی تاریخ با فونت و نوع تقویم انتخابی."""
    now = now or datetime.now()
    raw = format_date_fn(now, date_type)
    return apply_font_fn(raw, font_id)


# ==================== ۳. رسید دوطرفه‌ی انتقال الماس ====================
def build_sender_receipt(receiver_label: str, amount_str: str, new_balance_str: str, when: datetime = None) -> str:
    when = when or datetime.now()
    return (
        "🧾 **رسید انتقال الماس**\n\n"
        f"↩️ گیرنده: {receiver_label}\n"
        f"💎 مقدار انتقال: {amount_str}\n"
        f"💰 موجودی جدید شما: {new_balance_str}\n"
        f"🕒 تاریخ و ساعت: {when.strftime('%Y-%m-%d %H:%M:%S')}"
    )


def build_receiver_receipt(sender_label: str, amount_str: str, new_balance_str: str, when: datetime = None) -> str:
    when = when or datetime.now()
    return (
        "🧾 **رسید دریافت الماس**\n\n"
        f"↪️ فرستنده: {sender_label}\n"
        f"💎 مقدار دریافتی: {amount_str}\n"
        f"💰 موجودی جدید شما: {new_balance_str}\n"
        f"🕒 تاریخ و ساعت: {when.strftime('%Y-%m-%d %H:%M:%S')}"
    )


# ==================== ۴. جلوگیری از کلیک تکراری (Debounce) ====================
class ClickDebouncer:
    """
    جلوی پردازش چندباره‌ی یک کلیک سریع/تکراری روی همون دکمه رو می‌گیره.
    کلید تشخیص: (user_id, callback_data) + بازه‌ی زمانی کوتاه.
    حافظه‌ش با گذشت زمان به‌صورت تنبل (lazy) پاک‌سازی می‌شه تا رشد نامحدود نداشته باشه.
    """

    def __init__(self, window_seconds: float = 1.2, max_entries: int = 5000):
        self._window = window_seconds
        self._max_entries = max_entries
        self._last = {}

    def should_process(self, user_id, data: bytes) -> bool:
        key = (user_id, data)
        now = time.monotonic()
        last = self._last.get(key)

        if last is not None and (now - last) < self._window:
            return False

        self._last[key] = now

        if len(self._last) > self._max_entries:
            cutoff = now - (self._window * 10)
            stale = [k for k, t in self._last.items() if t < cutoff]
            for k in stale:
                self._last.pop(k, None)

        return True


# ==================== ۵. اجرای امن عملیات تلگرام (مدیریت خودکار FloodWait) ====================
async def safe_call(coro_func, *args, max_retries: int = 3, **kwargs):
    """
    coro_func (مثل client.send_message، client.edit_message و ...) رو با
    آرگومان‌های داده‌شده صدا می‌زنه؛ اگر FloodWaitError بگیره، خودش به‌اندازه‌ی
    لازم صبر می‌کنه و دوباره تلاش می‌کنه (بدون نیاز به تکرار این منطق در همه‌جا).
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            return await coro_func(*args, **kwargs)
        except FloodWaitError as e:
            last_error = e
            wait_for = e.seconds + 1
            logging.warning(f"⏳ FloodWait: {wait_for} ثانیه صبر (تلاش {attempt + 1}/{max_retries})")
            await asyncio.sleep(wait_for)
    if last_error:
        raise last_error


# ==================== ۶. لاگ داخلی عملیات مهم ====================
internal_logger = logging.getLogger("nova_internal")
if not internal_logger.handlers:
    _handler = logging.FileHandler("nova_internal.log", encoding="utf-8")
    _handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
    internal_logger.addHandler(_handler)
    internal_logger.setLevel(logging.INFO)
    internal_logger.propagate = False  # روی لاگ اصلی ربات تکرار/شلوغی ایجاد نکنه


def log_diamond_transfer(sender_id, receiver_id, amount):
    internal_logger.info(f"TRANSFER | from={sender_id} to={receiver_id} amount={amount}")


def log_self_toggle(user_id, new_status: bool):
    internal_logger.info(f"SELF_TOGGLE | user={user_id} status={'ON' if new_status else 'OFF'}")


def log_settings_change(user_id, field, value):
    internal_logger.info(f"SETTING_CHANGE | user={user_id} field={field} value={value}")


def log_internal_error(context, error):
    internal_logger.info(f"ERROR | context={context} error={error}")
