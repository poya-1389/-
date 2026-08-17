# -*- coding: utf-8 -*-
"""
webapp_api.py
====================================================================
ماژول بک‌اند Mini App برای NovaSelf.

این فایل را کنار main.py قرار بده و طبق راهنمای پایین همین فایل، آن را
داخل main.py وصل کن. این ماژول یک سرور aiohttp کوچک بالا می‌آورد که
فقط دو مسیر دارد:

  GET  /api/me      -> برگرداندن اطلاعات و تنظیمات فعلی کاربر
  POST /api/update  -> تغییر یک تنظیم (فونت، حالت متن، وضعیت سلف، منشی و ...)

اعتبارسنجی درخواست‌ها دقیقاً طبق الگوریتم رسمی تلگرام برای Web App
انجام می‌شود (بر پایه‌ی هش HMAC ساخته‌شده از initData و توکن ربات)،
پس هیچ‌کس جز خودِ کاربرِ واقعیِ صاحب سشن نمی‌تواند تنظیمات را تغییر دهد.
====================================================================
"""

import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qsl

from aiohttp import web

# فیلدهای بولی که به‌سادگی toggle می‌شوند (فقط true/false از فرانت می‌آید)
TOGGLE_FIELDS = {
    "date_enabled", "name_time", "bio_time", "secretary_enabled",
}
# فیلدهای عددی/متنی ساده که با یک مقدار مشخص جایگزین می‌شوند
SIMPLE_FIELDS = {
    "font_id": int,
    "text_mode": int,
    "date_type": str,
    "date_font": int,
}

# محدوده‌ی مجاز برای فیلدهای عددی/متنی ساده (برای همسان‌ماندن با محدودیت‌های
# همان فیلدها در منوهای خودِ ربات؛ قبلاً این محدودیت‌ها فقط سمت ربات چک می‌شد
# و از طریق Mini App هر عددی قابل ارسال بود).
FONT_ID_RANGE = range(0, 21)          # با تعداد فونت‌های واقعی FONTS در main.py هماهنگ کنید
TEXT_MODE_RANGE = range(0, 9)         # 0 (خاموش) تا 8 طبق build_format_entities
DATE_FONT_ID_RANGE = FONT_ID_RANGE
DATE_TYPE_VALUES = {"shamsi", "qamari", "gregorian"}

# نگاشت هر فیلد به کلید قفلِ قابلیتِ متناظرش (طبق همان کلیدهایی که در منوهای
# خودِ ربات با is_feature_locked/is_feature_globally_locked چک می‌شوند). این
# نگاشت برای جلوگیری از دورزدنِ قفل ادمین از طریق Mini App استفاده می‌شود.
FIELD_TO_FEATURE_KEY = {
    "font_id": "time",
    "text_mode": "textmode",
    "date_type": "date",
    "date_font": "date",
    "date_enabled": "date",
    "name_time": "time",
    "bio_time": "time",
    "secretary_enabled": "secretary",
    "secretary_bulk": "secretary",
}


def _validate_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86400):
    """
    اعتبارسنجی initData ارسالی از Telegram WebApp طبق مستندات رسمی تلگرام.
    در صورت معتبر بودن، دیکشنری پارس‌شده (شامل فیلد user) را برمی‌گرداند،
    در غیر این صورت None.
    """
    if not init_data:
        return None
    try:
        pairs = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None

    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        return None

    auth_date = pairs.get("auth_date")
    if auth_date and max_age_seconds:
        if time.time() - int(auth_date) > max_age_seconds:
            return None  # initData خیلی قدیمی است -> رد می‌شود

    if "user" in pairs:
        try:
            pairs["user"] = json.loads(pairs["user"])
        except json.JSONDecodeError:
            pairs["user"] = None

    return pairs


def create_webapp_app(*, bot_token, user_data, save_user, start_self_client,
                       stop_self_client, format_diamonds, diamond_rate_per_hour=5,
                       allowed_origin="*", is_feature_locked=None,
                       is_feature_globally_locked=None):
    """
    این تابع را از main.py صدا بزن و خروجی‌اش را با run_webapp_server اجرا کن.
    توجه: user_data باید همان دیکشنری سراسری main.py باشد (پاس دادن با رفرنس)
    تا تغییرات این ماژول همان لحظه در حافظه‌ی ربات هم دیده شود.
    """

    async def _authed_user(request):
        init_data = request.headers.get("X-Init-Data", "")
        parsed = _validate_init_data(init_data, bot_token)
        if not parsed or not parsed.get("user"):
            return None, None
        tg_user = parsed["user"]
        user_id = tg_user.get("id")
        user = user_data.get(user_id)
        if not user:
            return None, None
        return user_id, user

    async def handle_me(request):
        user_id, user = await _authed_user(request)
        if user is None:
            return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
        return web.json_response({"ok": True, **_serialize_user(user)})

    async def handle_update(request):
        user_id, user = await _authed_user(request)
        if user is None:
            return web.json_response({"ok": False, "error": "unauthorized"}, status=401)

        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "invalid-json"}, status=400)

        field = body.get("field")

        # جلوگیری از دورزدنِ قفلِ قابلیت (که در منوهای خودِ ربات رعایت می‌شود)
        # از طریق فراخوانی مستقیمِ Mini App API. قبلاً این‌جا هیچ‌کدام از این دو
        # چک انجام نمی‌شد و یک کاربرِ قفل‌شده می‌توانست تنظیمات را از طریق
        # Mini App تغییر دهد حتی اگر ادمین آن قابلیت را برایش قفل کرده باشد.
        feature_key = FIELD_TO_FEATURE_KEY.get(field)
        if feature_key:
            if callable(is_feature_globally_locked) and is_feature_globally_locked(feature_key):
                return web.json_response({"ok": False, "error": "feature-locked"}, status=403)
            if callable(is_feature_locked) and is_feature_locked(user_id, feature_key):
                return web.json_response({"ok": False, "error": "feature-locked"}, status=403)

        try:
            if field == "status":
                try:
                    await _handle_status_toggle(user_id, user, bool(body.get("value")),
                                                 start_self_client, stop_self_client)
                except ValueError as e:
                    # دلیل دقیقِ شکست (موجودی ناکافی / نشست نامعتبر) را حفظ می‌کنیم
                    # تا فرانت بتواند پیام درست را نشان دهد؛ قبلاً این دلیل با یک
                    # پیام عمومی «invalid-value» گم می‌شد و کاربر متوجه علت
                    # واقعی نمی‌شد (برخلاف رفتار خودِ ربات که پیام دقیق می‌دهد).
                    save_user(user_id, user)
                    return web.json_response({"ok": False, "error": str(e), **_serialize_user(user)}, status=409)

            elif field in TOGGLE_FIELDS:
                user[field] = bool(body.get("value"))

            elif field in SIMPLE_FIELDS:
                caster = SIMPLE_FIELDS[field]
                value = caster(body.get("value"))
                if field == "font_id" and value not in FONT_ID_RANGE:
                    return web.json_response({"ok": False, "error": "invalid-value"}, status=400)
                if field == "text_mode" and value not in TEXT_MODE_RANGE:
                    return web.json_response({"ok": False, "error": "invalid-value"}, status=400)
                if field == "date_font" and value not in DATE_FONT_ID_RANGE:
                    return web.json_response({"ok": False, "error": "invalid-value"}, status=400)
                if field == "date_type" and value not in DATE_TYPE_VALUES:
                    return web.json_response({"ok": False, "error": "invalid-value"}, status=400)
                user[field] = value

            elif field == "secretary_bulk":
                text = str(body.get("secretary_text", "") or "")[:500]
                delay = int(body.get("secretary_delay", 60))
                # محدوده را با محدوده‌ی واقعیِ همین فیلد در منوی خودِ ربات
                # (۱ تا ۸۶۴۰۰ ثانیه) یکسان کردیم؛ قبلاً این‌جا ۵ تا ۳۶۰۰ بود که
                # با چیزی که در ربات مجاز است هم‌خوانی نداشت.
                delay = max(1, min(delay, 86400))
                user["secretary_text"] = text
                user["secretary_delay"] = delay

            else:
                return web.json_response({"ok": False, "error": "unknown-field"}, status=400)

        except (TypeError, ValueError):
            return web.json_response({"ok": False, "error": "invalid-value"}, status=400)

        save_user(user_id, user)
        return web.json_response({"ok": True, **_serialize_user(user)})

    def _format_expiry(diamonds_val):
        if diamonds_val <= 0 or not diamond_rate_per_hour:
            return "منقضی شده"
        total_hours = diamonds_val / diamond_rate_per_hour
        days = int(total_hours // 24)
        hours = int(total_hours % 24)
        if days > 0:
            return f"{days} روز و {hours} ساعت"
        return f"{hours} ساعت"

    def _serialize_user(user):
        diamonds_val = float(user.get("diamonds", 0) or 0)
        return {
            "status": bool(user.get("status")),
            "font_id": user.get("font_id", 1),
            "text_mode": user.get("text_mode", 0),
            "date_enabled": bool(user.get("date_enabled")),
            "date_type": user.get("date_type", "shamsi"),
            "date_font": user.get("date_font", 1),
            "name_time": bool(user.get("name_time")),
            "bio_time": bool(user.get("bio_time")),
            "secretary_enabled": bool(user.get("secretary_enabled")),
            "secretary_text": user.get("secretary_text", ""),
            "secretary_delay": user.get("secretary_delay", 60),
            "diamonds_formatted": format_diamonds(diamonds_val),
            "diamonds_rounded": round(diamonds_val),
            "expiry_text": _format_expiry(diamonds_val),
            "referral_count": user.get("referral_count", 0),
            "joined_at": str(user.get("joined_at", "") or ""),
        }

    @web.middleware
    async def cors_middleware(request, handler):
        if request.method == "OPTIONS":
            resp = web.Response()
        else:
            try:
                resp = await handler(request)
            except web.HTTPException as exc:
                resp = exc
        resp.headers["Access-Control-Allow-Origin"] = allowed_origin
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Init-Data"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return resp

    app = web.Application(middlewares=[cors_middleware])
    app.router.add_get("/api/me", handle_me)
    app.router.add_post("/api/update", handle_update)
    app.router.add_route("OPTIONS", "/{tail:.*}", lambda r: web.Response())
    return app


async def _handle_status_toggle(user_id, user, want_on, start_self_client, stop_self_client):
    """دقیقاً همان منطقِ toggle_status موجود در main.py (برای یکسان‌ماندن رفتار)."""
    if want_on == user.get("status"):
        return  # چیزی تغییر نکرده

    if want_on:
        if float(user.get("diamonds", 0)) <= 0:
            user["status"] = False
            raise ValueError("insufficient-diamonds")
        client = await start_self_client(user_id, user.get("session"))
        if not client:
            user["status"] = False
            raise ValueError("session-invalid")
        user["status"] = True
    else:
        await stop_self_client(user_id)
        user["status"] = False


async def run_webapp_server(app, host="0.0.0.0", port=8080):
    """اجرای سرور به‌صورت هم‌زمان با ربات (در همان event loop)."""
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logging.info(f"🌐 Mini App API روی {host}:{port} در حال اجراست.")
