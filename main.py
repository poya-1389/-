# -*- coding: utf-8 -*-
"""
main.py
====================================================================
ارکستراسیونِ NovaSelf: ثبت Handlerهای سطح‌بالای بات (پنل درون‌چتی،
/start، /admin، کالبک‌های اینلاین، پیام‌های عمومی، جریانِ ثبت‌نام/کد/
رمزِ ورود)، و اجرای اصلی برنامه.

منطقِ این پروژه بین ۵ فایل تقسیم شده:
  - nova_utils.py            ابزارهای مستقل بدون وابستگی (دکمه‌ی رنگی، Debounce، safe_call)
  - nova_state.py            تنظیمات، کلاینت بات، تمام کش/دیکشنری‌های سراسری، توابع کمکیِ پرکاربرد
  - nova_db.py                لایه‌ی دیتابیس، اقتصاد الماس، بکاپ، بررسیِ زنده‌ی جوین اجباری
  - nova_menus.py             تمام تابع‌های متن/دکمه‌ی پنل (UI) + ساخت تصویر کارتِ پنل
  - nova_self_features.py    دستورات متنیِ سلف + Workerهای پس‌زمینه + مدیریت کلاینت هر کاربر
  - main.py (همین فایل)      فقط Handlerهای سطح‌بالای بات + اجرای اصلی
====================================================================
"""

import json
import io
import logging
import asyncio
from datetime import timedelta
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, SessionPasswordNeededError, MessageNotModifiedError

from webapp_api import create_webapp_app, run_webapp_server
import nova_state
from nova_utils import (
    STYLE_OFF, STYLE_ON, build_receiver_receipt, build_sender_receipt,
    log_diamond_transfer, log_internal_error, log_self_toggle, log_settings_change,
    safe_call, status_icon, styled_button, wrap_panel_buttons,
)
from nova_state import (
    ACTIONS, ADMIN_IDS, API_HASH, API_ID, AUTOREPLY_MATCH_TYPES,
    BOT_TOKEN, DATE_TYPE_NAMES, DIAMOND_PRICE_TOMAN, DIAMOND_RATE_PER_HOUR,
    FISH_INTERVAL_SECONDS, FONT_NAMES, FRIDGE_INTERVAL_SECONDS,
    INTERVAL_STEP_SECONDS, MAX_AUTOREPLY_MEDIA_BYTES, MAX_AUTOREPLY_MEDIA_MB,
    MEOWPOINT_INTERVAL_SECONDS, MEOW_INTERVAL_SECONDS, MINIAPP_ORIGIN, PORT,
    TEXTMODE_NAMES, _copy_message_to, _describe_message_kind, _media_kind_key,
    active_clients, active_signins, admin_action_data, autoreply_cache,
    autoreply_draft, backup_upload_pending, bot, broadcast_data, click_debouncer,
    feature_locks, format_diamonds, format_expiry, format_toman, generator_data,
    is_admin, make_default_user, meow_group_cache, normalize_phone_number,
    _spawn_background_task,
    purchase_data, safe_edit, tehran_now, transfer_data, user_data,
)
from nova_db import (
    add_autoreply_db, add_broadcast_delivery_db, admin_adjust_diamonds_db,
    admin_set_referral_db, approve_order_db, check_user_joined_all,
    create_pending_referral_db, credit_referral_db, get_pending_referral_db,
    get_referral_reward_db, get_referral_stats_db, increment_referral_count_db,
    is_referral_enabled_db, set_referral_enabled_db, set_referral_reward_db,
    create_backup_db, create_broadcast_record_db, create_gift_code_db,
    create_join_channel_db, create_order_db, delete_autoreply_db,
    delete_backup_db, delete_broadcast_record_db, delete_gift_code_db,
    delete_join_channel_db, delete_user_db, enforce_join_gate, get_all_users,
    get_backup_data_db, get_broadcast_deliveries_db, get_gift_code_detail_db,
    get_join_channel_db, get_order_db, get_recent_admin_logs, get_user_stats,
    init_db, is_feature_locked, list_backups_db, list_broadcasts_db,
    list_gift_codes_db, load_autoreplies_cache, load_feature_locks_cache,
    load_join_gate_cache, load_reactions_cache, lock_feature_db, log_admin_action,
    redeem_gift_code_db, reject_order_db, reload_join_channels_cache,
    restore_backup_payload, save_user, set_gift_code_active_db,
    set_join_channel_active_db, set_order_receipt_db, transfer_diamonds_db,
    unlock_feature_db, update_gift_code_amount_db, update_gift_code_expiry_db,
    update_join_channel_link_db,
)
from nova_menus import (
    ADMIN_MANAGEABLE_FEATURES, FEATURE_LOCK_LABELS, FISH_OPS_RARITY_LABELS,
    JOIN_REQUIRED_TEXT, MAX_BUY_DIAMONDS_DIGITS, PANEL_TEXT, _format_bytes,
    _send_join_gate, build_panel_card_image, get_account_delete_warning_keyboard,
    get_actions_menu_keyboard, get_admin_actions_grid_keyboard,
    get_admin_datefont_grid_keyboard, get_admin_font_grid_keyboard,
    get_admin_main_menu, get_admin_textmode_grid_keyboard,
    get_admin_referral_text, get_admin_referral_keyboard,
    get_autoreply_list_keyboard, get_autoreply_list_text,
    get_autoreply_matchtype_keyboard, get_autoreply_matchtype_text,
    get_autoreply_menu_keyboard, get_autoreply_menu_text,
    get_autoreply_view_keyboard, get_autoreply_view_text,
    get_autoseen_menu_keyboard, get_autoseen_menu_text,
    get_backup_delete_confirm_keyboard, get_backup_list_keyboard,
    get_balance_menu_keyboard, get_balance_menu_text,
    get_backup_list_text, get_backup_manage_keyboard, get_backup_manage_text,
    get_backup_menu_keyboard, get_backup_menu_text,
    get_backup_restore_confirm_keyboard, get_backup_restore_confirm_text,
    get_blockmgmt_menu_keyboard, get_blockmgmt_menu_text,
    get_broadcast_detail_keyboard, get_broadcast_detail_text,
    get_broadcasts_admin_keyboard, get_broadcasts_admin_text,
    get_buy_amount_keyboard, get_buy_amount_text, get_buy_confirm_keyboard, get_buy_confirm_text,
    get_buy_invoice_keyboard, get_buy_invoice_text, get_buy_payment_keyboard,
    get_buy_payment_text, get_buy_waiting_receipt_keyboard,
    get_buy_waiting_receipt_text, get_cleanup_menu_keyboard, get_cleanup_menu_text,
    get_code_keyboard, get_date_fonts_menu_keyboard, get_date_fonts_menu_text,
    get_date_menu_keyboard, get_date_menu_text, get_fish_op_rarity_keyboard,
    get_fish_ops_menu_keyboard, get_fish_ops_menu_text, get_fish_settings_keyboard,
    get_fish_settings_text, get_fonts_menu_keyboard, get_fonts_menu_text,
    get_fridge_settings_keyboard, get_fridge_settings_text,
    get_giftcode_delete_confirm_keyboard, get_giftcode_manage_keyboard,
    get_giftcode_manage_text, get_giftcodes_admin_keyboard,
    get_giftcodes_admin_text, get_join_required_keyboard,
    get_joingate_admin_keyboard, get_joingate_admin_text,
    get_joingate_delete_confirm_keyboard, get_joingate_manage_keyboard,
    get_joingate_manage_text, get_lock_features_keyboard, get_lock_features_text,
    get_meow_group_list_keyboard, get_meow_menu_keyboard, get_meow_menu_text,
    get_meow_settings_keyboard, get_meow_settings_text,
    get_meowpoint_settings_keyboard, get_meowpoint_settings_text,
    get_panel_account_keyboard, get_panel_account_text, get_panel_root_keyboard,
    get_ping_menu_keyboard, get_ping_menu_text, get_reaction_list_keyboard,
    get_reaction_list_text, get_reaction_menu_keyboard, get_reaction_menu_text,
    get_secretary_menu_keyboard, get_secretary_menu_text, get_settings_root_keyboard,
    get_start_about_keyboard, get_start_about_text, get_start_account_keyboard,
    get_start_account_text, get_start_manage_self_keyboard,
    get_referral_page_text, get_referral_page_keyboard,
    get_start_manage_self_text, get_start_root_keyboard, get_start_root_text,
    get_streetcat_settings_keyboard, get_streetcat_settings_text,
    get_tag_menu_keyboard, get_tag_menu_text, get_textmode_menu_keyboard,
    get_time_menu_keyboard, get_time_menu_text, get_transfer_cancel_keyboard,
    get_transfer_confirm_keyboard, get_user_detail_buttons,
    get_user_features_keyboard, get_user_features_text, get_users_list_page,
    get_videomessage_menu_keyboard, get_videomessage_menu_text,
    get_whois_menu_keyboard, get_whois_menu_text,
)
from nova_self_features import (
    _teardown_existing_client, autostart_saved_users, fish_worker, fridge_worker,
    meow_worker, meowpoint_worker, register_active_client, start_self_client,
    stop_self_client,
)

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

    # جوین اجباری: پنل درون‌چتی هم نباید برای کاربری که الان (زنده) عضو همه‌ی
    # کانال‌ها نیست ساخته شود.
    blocked, missing = await enforce_join_gate(owner_id)
    if blocked:
        builder = event.builder
        result = builder.article(
            "🔔 عضویت لازم است",
            text=JOIN_REQUIRED_TEXT,
            buttons=get_join_required_keyboard(missing),
        )
        await event.answer([result], cache_time=0)
        return

    builder = event.builder
    keyboard = wrap_panel_buttons(get_panel_root_keyboard(user), owner_id)

    card_image = await build_panel_card_image(owner_id, user)
    if card_image is not None:
        try:
            result = builder.photo(card_image, text=PANEL_TEXT, buttons=keyboard)
            await event.answer([result], cache_time=0)
            return
        except Exception as e:
            # اگر آپلود تصویر هر دلیلی شکست خورد، به حالت متنیِ قبلی برمی‌گردیم
            # (کاربر هیچ‌وقت نباید به‌خاطر این افزوده اصلاً پنلی دریافت نکند).
            log_internal_error("panel_card_photo_result", e)

    result = builder.article(
        "پـنـل مـدیـریـت نـوا سـلـف",
        text=PANEL_TEXT,
        buttons=keyboard,
    )
    await event.answer([result], cache_time=0)


async def _try_credit_referral(referred_id):
    """
    اگر این کاربر یک رفرالِ «در انتظار» دارد (با لینکِ دعوت آمده ولی هنوز جایزه
    داده نشده) و همین الان (این تابع فقط بعد از تأییدِ Join اجباری صدا زده
    می‌شود) شرایط تکمیل شده، جایزه را نهایی می‌کند و به دعوت‌کننده اطلاع می‌دهد.

    کاملاً Idempotent و امن برای صدازدنِ مکرر: credit_referral_db فقط دقیقاً
    یک‌بار می‌تواند موفق شود (شرطِ reward_credited=FALSE در خودِ UPDATE)، پس
    هیچ‌وقت یک نفر دو بار جایزه نمی‌گیرد، حتی اگر این تابع هم‌زمان چند بار
    فراخوانی شود.
    """
    try:
        pending_referrer = get_pending_referral_db(referred_id)
        if not pending_referrer:
            return

        reward = get_referral_reward_db()
        referrer_id = credit_referral_db(referred_id, reward)
        if not referrer_id:
            return  # قبلاً اعتبار داده شده یا اصلاً رفرالی در انتظار نبود

        if reward > 0:
            success, new_balance = admin_adjust_diamonds_db(referrer_id, reward)
            if success and referrer_id in user_data and new_balance is not None:
                # مقدار دقیقِ بازگشتی از دیتابیس (نه جمعِ دستیِ حافظه) منبعِ حقیقت است
                user_data[referrer_id]["diamonds"] = new_balance

        new_count = increment_referral_count_db(referrer_id)
        if referrer_id in user_data and new_count is not None:
            user_data[referrer_id]["referral_count"] = new_count

        referred_user = user_data.get(referred_id, {})
        referred_username = referred_user.get("username")
        referred_label = f"@{referred_username}" if referred_username else "بدون یوزرنیم"

        try:
            await bot.send_message(
                referrer_id,
                f"🎉 کاربر `{referred_id}` ({referred_label})\n"
                "با لینک دعوت شما به NoVA SeLF پیوست.\n\n"
                f"🎁 جایزه رفرال: {format_diamonds(reward)} 💎"
            )
        except Exception as e:
            log_internal_error("referral_notify", e)
    except Exception as e:
        log_internal_error("try_credit_referral", e)

@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    """هندلر دستور /start - کاملاً یکسان برای همه کاربران"""
    user_id = event.sender_id

    if user_id in generator_data:
        return

    # پارسِ پارامترِ Referral از لینکِ دعوت (اگر /start با یک payload آمده باشد،
    # مثلِ https://t.me/BotUsername?start=123456789 که تلگرام آن را به‌صورتِ
    # پیامِ متنیِ «/start 123456789» تحویل می‌دهد).
    referrer_id = None
    _start_parts = (event.raw_text or "").split(maxsplit=1)
    if len(_start_parts) > 1 and _start_parts[1].strip().isdigit():
        try:
            referrer_id = int(_start_parts[1].strip())
        except ValueError:
            referrer_id = None

    is_new_user = user_id not in user_data

    if is_new_user:
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

        # ثبتِ رفرالِ «در انتظار» - طبق بندهای امنیتی: فقط برای کاربرِ واقعاً تازه
        # (نه هر باری که /start می‌زند)، فقط اگر دعوت‌کننده واقعاً در ربات ثبت‌نام
        # کرده باشد، و هرگز خودِ کاربر (Self Referral؛ create_pending_referral_db
        # خودش هم این حالت را رد می‌کند). جایزه اینجا هنوز داده نمی‌شود - فقط
        # پایین همین تابع، بعد از Join واقعیِ کانال‌های اجباری، اعتبار داده می‌شود.
        if referrer_id and is_referral_enabled_db() and referrer_id in user_data:
            create_pending_referral_db(user_id, referrer_id)
    else:
        # کاربرِ قبلاً ثبت‌شده: یوزرنیمش را هم همین‌جا تازه می‌کنیم (نه فقط بار
        # اول)، چون این فیلد پایه‌ی جستجوی «انتقال الماس با یوزرنیم» است و اگر
        # کاربر یوزرنیمش را عوض کرده باشد یا موقع اولین /start اصلاً یوزرنیم
        # نداشته، بدون این بازتازه‌سازی برای همیشه قدیمی/خالی می‌ماند.
        try:
            sender = await event.get_sender()
            current_username = getattr(sender, "username", None) if sender else None
            if current_username and user_data[user_id].get("username") != current_username:
                user_data[user_id]["username"] = current_username
                save_user(user_id, user_data[user_id])
        except Exception as e:
            log_internal_error("start_refresh_username", e)

    user = user_data[user_id]

    # جوین اجباری: هر بار زنده چک می‌شود (بدون کش/دیتابیس)؛ ادمین‌ها معاف هستند
    # تا هیچ‌وقت خودشان از پنل قفل نشوند.
    blocked, missing = await enforce_join_gate(user_id)
    if blocked:
        await _send_join_gate(event, user_id, missing)
        return

    # طبق «سیستم Referral»: رفرال فقط بعد از تکمیل Join اجباری (همین بالا) نهایی
    # می‌شود - این تابع خودش Idempotent است (اگر رفرالی در انتظار نبود یا قبلاً
    # جایزه داده شده بود، هیچ کاری نمی‌کند)، پس امن است که هر بار /start صدا زده شود.
    await _try_credit_referral(user_id)

    await event.respond(
        get_start_root_text(),
        buttons=get_start_root_keyboard(user)
    )

@bot.on(events.NewMessage(pattern='/admin'))
async def admin_handler(event):
    """هندلر دستور /admin - فقط برای ادمین‌ها"""
    user_id = event.sender_id

    if not is_admin(user_id):
        # طبق درخواست صریح: کاربران غیرِادمین دیگر هیچ پاسخی دریافت نمی‌کنند
        # (قبلاً پیام «❌ شما دسترسی ادمین ندارید!» نمایش داده می‌شد).
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
            if not click_debouncer.should_process(event.sender_id, data):
                await event.answer()  # کلیک تکراری/سریع روی «بستن پنل»؛ تسکِ دوم ساخته نمی‌شود
                return
            await _module_safe_edit(event, "✕ پنل بسته شد.", buttons=None)
            # طبق درخواست: بعد از ۳ ثانیه خودِ پیامِ «پنل بسته شد» هم پاک شود.
            # نکته‌ی حیاتی: Task باید حتماً با _spawn_background_task ساخته شود
            # (نه asyncio.create_task خام)؛ وگرنه چون هیچ‌جا رفرنسی از Task نگه
            # داشته نمی‌شود، Garbage Collector پایتون ممکن است پیش از تمام‌شدنِ
            # ۳ ثانیه، خودِ Task را جمع‌آوری/لغو کند و پیام هرگز پاک نشود - دقیقاً
            # همان باگی که گزارش شده بود.
            async def _delete_after_delay():
                try:
                    await asyncio.sleep(3)
                    await event.delete()
                except Exception as e:
                    log_internal_error("panel_close_auto_delete", e)
            _spawn_background_task(_delete_after_delay())
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
            user = user_data.get(user_id) or make_default_user(step="menu")
            user_data[user_id] = user
            await _try_credit_referral(user_id)
            await safe_edit(event, get_start_root_text(), buttons=get_start_root_keyboard(user))
        else:
            await event.answer("برای استفاده از ربات، ابتدا باید در کانال‌های مشخص‌شده عضو شوید.", alert=True)
        return

    # ====== نگهبانِ جوین اجباری (روی همه‌ی کلیک‌های دیگر، هر بار زنده) ======
    # بدون این چک، کاربری که یک‌بار وارد پنل شده ولی الان از یکی از کانال‌ها
    # لفت داده، همچنان می‌توانست با کلیک روی دکمه‌های داخل پنل به همه‌ی قابلیت‌ها
    # دسترسی داشته باشد. اینجا (نه فقط توی /start) دوباره زنده چک می‌شود.
    blocked, missing = await enforce_join_gate(user_id)
    if blocked:
        await safe_edit(event, JOIN_REQUIRED_TEXT, buttons=get_join_required_keyboard(missing))
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

        # ====================================================================
        # ============================ مدیریت رفرال ============================
        # ====================================================================
        if data == b"admin_referral":
            await safe_edit(event, get_admin_referral_text(), buttons=get_admin_referral_keyboard(is_referral_enabled_db()))
            return

        if data == b"admin_referral_toggle":
            set_referral_enabled_db(not is_referral_enabled_db())
            log_admin_action(user_id, 0, "referral_toggle", str(is_referral_enabled_db()))
            await safe_edit(event, get_admin_referral_text(), buttons=get_admin_referral_keyboard(is_referral_enabled_db()))
            return

        if data == b"admin_referral_zero_reward":
            set_referral_reward_db(0)
            log_admin_action(user_id, 0, "referral_reward_zeroed", "0")
            await safe_edit(event, get_admin_referral_text(), buttons=get_admin_referral_keyboard(is_referral_enabled_db()))
            return

        if data == b"admin_referral_set_reward":
            admin_action_data[user_id] = {"type": "admin_referral_reward", "step": "get_amount"}
            await safe_edit(event,
                "✏️ **تغییر مقدار جایزه‌ی رفرال**\n\n"
                "مقدار جدید جایزه (به الماس) را ارسال کنید:",
                buttons=[[styled_button("➜ بازگشت", b"admin_referral", style=STYLE_OFF)]]
            )
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
                expiry_text = format_expiry(user.get("diamonds", 0))

                await safe_edit(event,
                    f"👤 **جزئیات کاربر:**\n\n"
                    f"🆔 شناسه: `{target_id}`\n"
                    f"💡 یوزرنیم: {username_display}\n"
                    f"📊 وضعیت: {status_text}\n"
                    f"💎 موجودی الماس: {format_diamonds(user.get('diamonds', 0))} ({format_toman(user.get('diamonds', 0))} تومان)\n"
                    f"⏳ انقضا: {expiry_text}\n"
                    f"👥 تعداد رفرال: {user.get('referral_count', 0)}\n"
                    f"🔤 فونت: {font_name}\n"
                    f"⌚ ساعت نام: {status_icon(user['name_time'])}\n"
                    f"⌚ ساعت بیو: {status_icon(user['bio_time'])}\n"
                    f"📅 تاریخ: {date_text}\n"
                    f"🖊️ حالت متن: {textmode_text}\n"
                    f"🧑‍💼 منشی پیوی: {secretary_text}\n"
                    f"🎭 اکشن: {action_name}\n"
                    f"👍 ریکت: {status_icon(user.get('reaction_enabled', False))}\n"
                    f"🤖 پاسخ خودکار: {status_icon(user.get('autoreply_enabled', False))}\n"
                    f"👁️ سین خودکار: {status_icon(user.get('autoseen_enabled', False))}\n"
                    f"🐱 میو: {status_icon(user.get('meow_enabled', False))}\n"
                    f"🐟 ماهی: {status_icon(user.get('fish_enabled', False))}\n"
                    f"🪙 میو پوینت: {status_icon(user.get('meowpoint_enabled', False))}\n"
                    f"🐈 نجات پیشی: {status_icon(user.get('streetcat_enabled', False))}\n"
                    f"❄️ یخچال میویی: {status_icon(user.get('fridge_enabled', False))}\n"
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
        await safe_edit(event, "📞 در حال آماده‌سازی مرحله‌ی ارسال شماره...")
        await bot.send_message(
            user_id,
            "📞 مرحله اول: ارسال شماره\n\n"
            "برای استفاده از نوا سلف لازم است ابتدا شماره خود را از طریق دکمه زیر ارسال کنید\n\n"
            "⚠️ روی دکمه‌ی «📞 ارسال شماره تلفن» بزنید و در پنجره باز شده «Share My Phone Number» "
            "یا «اشتراک گذاری شماره تلفن من» را کلیک کنید.\n\n"
            "⁉️ توجه داشته باشید نوا سلف تنها پیش نیاز های لازم برای اجرا سلف را از شما دریافت می کند "
            "و تمامی اطلاعات شما پیش ما محفوظ است!",
            buttons=[[Button.request_phone("📞 ارسال شماره تلفن", resize=True)]]
        )
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
        await safe_edit(event, "🔄 در حال آماده‌سازی بازیابی نشست...")
        await bot.send_message(
            user_id,
            "📞 مرحله اول: ارسال شماره\n\n"
            "موجودی، تنظیمات و رفرال شما دست‌نخورده باقی می‌ماند و فقط نشستِ اتصال حساب دوباره "
            "ساخته می‌شود؛ برای ادامه لازم است شماره‌ی حساب خود را از طریق دکمه زیر ارسال کنید\n\n"
            "⚠️ روی دکمه‌ی «📞 ارسال شماره تلفن» بزنید و در پنجره باز شده «Share My Phone Number» "
            "یا «اشتراک گذاری شماره تلفن من» را کلیک کنید.\n\n"
            "⁉️ توجه داشته باشید نوا سلف تنها پیش نیاز های لازم برای اجرا سلف را از شما دریافت می کند "
            "و تمامی اطلاعات شما پیش ما محفوظ است!",
            buttons=[[Button.request_phone("📞 ارسال شماره تلفن", resize=True)]]
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
        await safe_edit(event, PANEL_TEXT, buttons=get_settings_root_keyboard(user_id, page=1))
        return

    if data == b"settings_page2":
        await safe_edit(event, PANEL_TEXT, buttons=get_settings_root_keyboard(user_id, page=2))
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

    if data == b"account_referral":
        await safe_edit(event, get_referral_page_text(user_id, user), buttons=get_referral_page_keyboard())
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
            get_buy_amount_text(""),
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
        await safe_edit(event, get_buy_amount_text(buffer_str),
                         buttons=get_buy_amount_keyboard(buffer_str))
        return

    if data == b"buy_amount_back" and user.get("step") == "buy_confirm":
        pending = purchase_data.setdefault(user_id, {"buffer": ""})
        user["step"] = "buy_amount"
        await safe_edit(event, get_buy_amount_text(pending.get("buffer", "")),
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
            "لطفاً آیدی عددی یا یوزرنیمِ کاربر مقصد را ارسال کنید:",
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

    if data == b"menu_cleanup":
        if is_feature_locked(user_id, "cleanup"):
            await event.answer("این قابلیت برای شما قفل شده است.", alert=True)
            return
        await safe_edit(event, get_cleanup_menu_text(), buttons=get_cleanup_menu_keyboard())
        return

    if data == b"menu_blockmgmt":
        if is_feature_locked(user_id, "blockmgmt"):
            await event.answer("این قابلیت برای شما قفل شده است.", alert=True)
            return
        await safe_edit(event, get_blockmgmt_menu_text(), buttons=get_blockmgmt_menu_keyboard())
        return

    if data == b"menu_autoseen":
        if is_feature_locked(user_id, "autoseen"):
            await event.answer("این قابلیت برای شما قفل شده است.", alert=True)
            return
        await safe_edit(event, get_autoseen_menu_text(user), buttons=get_autoseen_menu_keyboard(user))
        return

    if data == b"menu_videomessage":
        if is_feature_locked(user_id, "videomessage"):
            await event.answer("این قابلیت برای شما قفل شده است.", alert=True)
            return
        await safe_edit(event, get_videomessage_menu_text(), buttons=get_videomessage_menu_keyboard())
        return

    if data == b"menu_balance":
        if is_feature_locked(user_id, "balance"):
            await event.answer("این قابلیت برای شما قفل شده است.", alert=True)
            return
        await safe_edit(event, get_balance_menu_text(), buttons=get_balance_menu_keyboard())
        return

    if data == b"autoseen_toggle":
        user["autoseen_enabled"] = not user.get("autoseen_enabled", False)
        save_user(user_id, user)
        log_settings_change(user_id, "autoseen_enabled", user["autoseen_enabled"])
        await safe_edit(event, get_autoseen_menu_text(user), buttons=get_autoseen_menu_keyboard(user))
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
        try:
            panel_msg = await event.get_message()
            user["secretary_panel_msg_id"] = panel_msg.id if panel_msg else None
        except Exception as e:
            log_internal_error("secretary_panel_ref", e)
            user["secretary_panel_msg_id"] = None
        user["secretary_panel_chat_id"] = event.chat_id
        user["step"] = "secretary_get_text"
        await safe_edit(event,
            "📝 هر نوع محتوایی که می‌خواهید منشی به‌جای شما بفرستد را ارسال کنید:\n\n"
            "متن ساده، متنِ استایل‌دار (Bold/Italic/Underline/Strike/Spoiler/Quote/لینک)، "
            "عکس (+توضیح)، ویدیو (+توضیح)، GIF، استیکر، فایل، ویس، Video Note، موزیک، "
            "یا حتی یک پیامِ Forward‌شده - همان محتوا عیناً به‌عنوان پاسخ منشی ذخیره می‌شود."
        )
        return

    if data == b"secretary_set_time":
        try:
            panel_msg = await event.get_message()
            user["secretary_panel_msg_id"] = panel_msg.id if panel_msg else None
        except Exception as e:
            log_internal_error("secretary_panel_ref", e)
            user["secretary_panel_msg_id"] = None
        user["secretary_panel_chat_id"] = event.chat_id
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
    # مراحل ساخت خودکار حساب (شماره/کد تایید/رمز دو مرحله‌ای) هم باید با /cancel
    # قابل خروج باشند؛ قبلاً /cancel این حالت‌ها را نمی‌شناخت و کاربری که مثلاً
    # وسط وارد کردن کد تایید گیر می‌کرد، هیچ راهی برای خروج نداشت.
    _has_pending_login = user_id in generator_data

    if text == "/cancel" and (user_id in broadcast_data or user_id in admin_action_data
                               or _has_pending_step or _has_pending_login or user_id in purchase_data):
        # لغو یک خرید در حالِ انتظارِ رسید فقط State را ریست می‌کند؛ سفارشی که از قبل
        # در دیتابیس با وضعیت 'invoice' ثبت شده دست‌نخورده می‌ماند (کاربر می‌تواند بعداً
        # دوباره از حساب کاربری وارد بخش خرید شود، البته سفارش قدیمی دیگر از UI قابل
        # دسترسی نیست مگر مستقیماً توسط ادمین در دیتابیس بررسی شود).

        # اگر وسط مراحل ورود (شماره/کد/رمز دو مرحله‌ای) گیر کرده، کلاینتِ موقتِ
        # لاگین باید درست قطع شود؛ وگرنه یک اتصال باز و بی‌مصرف به تلگرام می‌ماند.
        pending_client = active_signins.pop(user_id, None)
        if pending_client:
            try:
                await pending_client.disconnect()
            except Exception:
                pass
        generator_data.pop(user_id, None)

        broadcast_data.pop(user_id, None)
        admin_action_data.pop(user_id, None)
        transfer_data.pop(user_id, None)
        purchase_data.pop(user_id, None)
        autoreply_draft.pop(user_id, None)
        backup_upload_pending.pop(user_id, None)
        if user_id in user_data:
            user_data[user_id]["step"] = "managed"
            user_data[user_id].pop("secretary_panel_chat_id", None)
            user_data[user_id].pop("secretary_panel_msg_id", None)
        # buttons=Button.clear() هم چون ممکن است هنگام لغو، دکمه‌ی «ارسال شماره
        # تلفن» (کیبورد پایین صفحه) هنوز باز باشد.
        await event.respond("❌ عملیات لغو شد.", buttons=Button.clear())
        if is_admin(user_id):
            await event.respond("👑 پنل ادمین:", buttons=get_admin_main_menu())
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
            action["step"] = "get_identifier"
            await event.respond(
                "حالا شناسه‌ی کانال را ارسال کنید:\n"
                "برای کانال عمومی: `@channel_username`\n"
                "برای کانال خصوصی: آیدی عددی کانال (باید ربات از قبل ادمین آن کانال باشد)",
                buttons=cancel_kb
            )
            return

        if action["step"] == "get_identifier":
            identifier = text.strip().lstrip("@")
            if not identifier:
                await event.respond("❌ شناسه نامعتبر است.", buttons=cancel_kb)
                return
            action["identifier"] = identifier
            action["step"] = "get_link"
            await event.respond(
                "حالا لینک عضویت کانال را ارسال کنید (مثال: `https://t.me/channel_username`):",
                buttons=cancel_kb
            )
            return

        if action["step"] == "get_link":
            link = text.strip()
            if not link.startswith("http"):
                await event.respond("❌ لینک باید با http یا https شروع شود.", buttons=cancel_kb)
                return

            new_id = create_join_channel_db(action["title"], action["identifier"], link)
            del admin_action_data[user_id]

            if new_id is None:
                await event.respond("❌ خطا در ذخیره‌سازی کانال.", buttons=get_joingate_admin_keyboard())
                return

            reload_join_channels_cache()
            log_admin_action(user_id, 0, "add_joingate", f"id={new_id} title={action['title']}")
            await event.respond(
                f"✅ کانال «{action['title']}» با موفقیت اضافه شد.\n\n"
                "⚠️ یادت باشه که ربات باید از قبل عضو/ادمین این کانال باشه تا بتونه عضویت کاربرا رو چک کنه.",
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

    # ====== تغییر مقدار جایزه‌ی رفرال توسط ادمین ======
    if user_id in admin_action_data and is_admin(user_id) and admin_action_data[user_id].get("type") == "admin_referral_reward":
        cancel_kb = [[styled_button("➜ بازگشت", b"admin_referral", style=STYLE_OFF)]]
        try:
            new_reward = float(text)
            if new_reward < 0:
                raise ValueError
        except (ValueError, TypeError):
            await event.respond("❌ لطفاً یک عدد معتبر و غیرمنفی ارسال کنید.", buttons=cancel_kb)
            return

        set_referral_reward_db(new_reward)
        del admin_action_data[user_id]
        log_admin_action(user_id, 0, "referral_reward_changed", f"new_reward={new_reward}")
        await event.respond(
            get_admin_referral_text(),
            buttons=get_admin_referral_keyboard(is_referral_enabled_db())
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
            # جلوگیری از اسپم: اگر کاربر قبلاً شماره‌ی اشتباه فرستاده، تا پایان
            # زمان انتظار (۳۰ ثانیه بار اول، ۶۰ ثانیه بار دوم به بعد) اجازه‌ی
            # تلاش مجدد داده نمی‌شود.
            wait_until = generator.get("phone_wait_until")
            if wait_until and tehran_now() < wait_until:
                remaining = int((wait_until - tehran_now()).total_seconds()) + 1
                await event.respond(f"⏳ لطفاً {remaining} ثانیه دیگر صبر کنید و دوباره شماره را ارسال کنید.")
                return

            # شماره فقط از طریق دکمه‌ی «ارسال شماره تلفن» (Request Contact) پذیرفته
            # می‌شود، نه با تایپ دستی. این‌طور تلگرام خودش تأیید می‌گیرد و همیشه
            # شماره‌ی واقعیِ خودِ همین اکانت ارسال می‌شود؛ جلوی وارد کردن شماره‌های
            # فیک/الکی که باعث درخواست کد اسپم به یک شماره‌ی نامرتبط می‌شد گرفته
            # می‌شود. contact.user_id باید دقیقاً همان فرستنده باشد تا کسی نتواند
            # با فوروارد کردن یک مخاطبِ دیگر این چک را دور بزند.
            contact = getattr(event.message, "contact", None)
            if not contact or not getattr(contact, "phone_number", None):
                await event.respond(
                    "❌ لطفاً شماره را فقط با دکمه‌ی «📞 ارسال شماره تلفن» (پایین صفحه) ارسال کنید؛ "
                    "تایپ دستیِ شماره دیگر پذیرفته نمی‌شود.",
                    buttons=[[Button.request_phone("📞 ارسال شماره تلفن", resize=True)]]
                )
                return

            if getattr(contact, "user_id", None) != user_id:
                await event.respond(
                    "❌ فقط شماره‌ی خودتان قابل قبول است. لطفاً از دکمه‌ی «📞 ارسال شماره تلفن» "
                    "استفاده کنید (نه فوروارد کردن مخاطب دیگری).",
                    buttons=[[Button.request_phone("📞 ارسال شماره تلفن", resize=True)]]
                )
                return

            normalized_phone, phone_error = normalize_phone_number(contact.phone_number)
            if phone_error:
                await event.respond(
                    f"{phone_error}\n\n"
                    "لطفاً دوباره با دکمه‌ی «📞 ارسال شماره تلفن» اقدام کنید.",
                    buttons=[[Button.request_phone("📞 ارسال شماره تلفن", resize=True)]]
                )
                return  # در همان مرحله می‌ماند تا کاربر دوباره امتحان کند (بدون کرش)

            generator["phone"] = normalized_phone

            await event.respond("⏳ در حال اتصال به سرورهای تلگرام...", buttons=Button.clear())

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
                    f"لطفاً {e.seconds} ثانیه دیگر دوباره شماره را ارسال کنید.",
                    buttons=[[Button.request_phone("📞 ارسال شماره تلفن", resize=True)]]
                )
                if client:
                    try:
                        await client.disconnect()
                    except Exception:
                        pass
                if user_id in active_signins:
                    del active_signins[user_id]
            except Exception as e:
                attempts = generator.get("phone_attempts", 0) + 1
                generator["phone_attempts"] = attempts
                wait_seconds = 30 if attempts == 1 else 60
                generator["phone_wait_until"] = tehran_now() + timedelta(seconds=wait_seconds)

                await event.respond(
                    f"❌ **خطا در ارسال کد:**\n\n`{str(e)}`\n\n"
                    f"لطفاً {wait_seconds} ثانیه صبر کنید و دوباره شماره را ارسال کنید.",
                    buttons=[[Button.request_phone("📞 ارسال شماره تلفن", resize=True)]]
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
    # ====== تنظیم متن/محتوای منشی (پشتیبانی کامل از هر نوع پیام تلگرام) ======
    if user_id in user_data and user_data[user_id].get("step") == "secretary_get_text":
        panel_chat_id = user_data[user_id].get("secretary_panel_chat_id")
        panel_msg_id = user_data[user_id].get("secretary_panel_msg_id")

        async def _update_secretary_panel(panel_text, buttons=None):
            """
            طبق «تغییر مکانیزم تنظیمات منشی»: به‌جای ارسال پیامِ تازه، همان پیامِ
            پنلی که قبلاً باز شده بود Edit می‌شود. اگر آن پیام به هر دلیلی در
            دسترس نبود (مثلاً پاک شده)، به‌عنوان تنها راهِ باقی‌مانده یک پیامِ
            تازه فرستاده می‌شود (Fallback امن، نه رفتار پیش‌فرض).
            """
            if panel_chat_id and panel_msg_id:
                try:
                    await event.client.edit_message(panel_chat_id, panel_msg_id, panel_text, buttons=buttons)
                    return
                except MessageNotModifiedError:
                    return
                except Exception as e:
                    log_internal_error("secretary_panel_edit", e)
            await event.respond(panel_text, buttons=buttons)

        msg = event.message
        media_kind = _media_kind_key(msg)
        media_bytes = None
        media_filename = None
        media_mime = None

        if media_kind:
            size = getattr(event.file, "size", None) if event.file else None
            if size and size > MAX_AUTOREPLY_MEDIA_BYTES:
                await _update_secretary_panel(
                    f"❌ حجم این فایل بیش از حد مجاز است (حداکثر {MAX_AUTOREPLY_MEDIA_MB} مگابایت).\n\n"
                    "فایل کوچک‌تری بفرست یا پیام دیگری ارسال کن."
                )
                return
            try:
                media_bytes = await event.download_media(file=bytes)
            except Exception as e:
                log_internal_error("secretary_download_media", e)
                await _update_secretary_panel("❌ خطا در دریافت فایل. دوباره تلاش کنید.")
                return
            media_filename = getattr(event.file, "name", None) if event.file else None
            media_mime = getattr(event.file, "mime_type", None) if event.file else None

        new_text = text if text else None
        if not new_text and not media_bytes:
            await _update_secretary_panel("❌ پیام خالی قابل ذخیره نیست. یک متن یا رسانه ارسال کن.")
            return

        user_data[user_id]["secretary_text"] = new_text or "مشغولم، بعداً پاسخ می‌دهم ✅"
        user_data[user_id]["secretary_entities"] = msg.entities
        user_data[user_id]["secretary_media_kind"] = media_kind
        user_data[user_id]["secretary_media_bytes"] = media_bytes
        user_data[user_id]["secretary_media_filename"] = media_filename
        user_data[user_id]["secretary_media_mime"] = media_mime
        user_data[user_id]["step"] = "managed"
        user_data[user_id].pop("secretary_panel_chat_id", None)
        user_data[user_id].pop("secretary_panel_msg_id", None)
        save_user(user_id, user_data[user_id])

        await _update_secretary_panel(
            get_secretary_menu_text(user_data[user_id]),
            buttons=get_secretary_menu_keyboard(user_data[user_id])
        )
        return

    # ====== تنظیم تایم منشی ======
    if user_id in user_data and user_data[user_id].get("step") == "secretary_get_time":
        panel_chat_id = user_data[user_id].get("secretary_panel_chat_id")
        panel_msg_id = user_data[user_id].get("secretary_panel_msg_id")

        async def _update_secretary_panel_time(panel_text, buttons=None):
            if panel_chat_id and panel_msg_id:
                try:
                    await event.client.edit_message(panel_chat_id, panel_msg_id, panel_text, buttons=buttons)
                    return
                except MessageNotModifiedError:
                    return
                except Exception as e:
                    log_internal_error("secretary_panel_edit", e)
            await event.respond(panel_text, buttons=buttons)

        try:
            seconds = int(text)
            if seconds < 1 or seconds > 86400:
                raise ValueError
        except (ValueError, TypeError):
            await _update_secretary_panel_time("❌ لطفاً یک عدد معتبر (بین 1 تا 86400) بر حسب ثانیه ارسال کنید.")
            return

        user_data[user_id]["secretary_delay"] = seconds
        user_data[user_id]["step"] = "managed"
        user_data[user_id].pop("secretary_panel_chat_id", None)
        user_data[user_id].pop("secretary_panel_msg_id", None)
        save_user(user_id, user_data[user_id])

        await _update_secretary_panel_time(
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
        raw_target = text.strip()
        target_id = None

        if raw_target.lstrip("+-").isdigit():
            try:
                target_id = int(raw_target)
            except ValueError:
                target_id = None
        else:
            # نکته‌ی مهم (علتِ اصلیِ باگِ گزارش‌شده): جستجوی فقط در کشِ محلیِ
            # user_data کافی نیست، چون آن فیلد فقط یک‌بار (موقع اولین /start)
            # پر می‌شود و اگر کاربر بعداً یوزرنیمش را عوض کند یا موقع اولین
            # /start اصلاً یوزرنیم نداشته، برای همیشه خالی/قدیمی می‌ماند. برای
            # همین اول زنده از خودِ تلگرام Resolve می‌کنیم و فقط اگر آن هم جواب
            # نداد (مثلاً به‌خاطر تنظیمات حریم خصوصی)، به کشِ محلی برمی‌گردیم.
            uname = raw_target.lstrip("@").strip()
            if uname:
                try:
                    entity = await bot.get_entity(uname)
                    resolved_id = getattr(entity, "id", None)
                    if resolved_id and resolved_id in user_data:
                        target_id = resolved_id
                        live_username = getattr(entity, "username", None)
                        if live_username:
                            user_data[resolved_id]["username"] = live_username
                except Exception as e:
                    log_internal_error("transfer_username_resolve", f"uname={uname} err={e}")

                if target_id is None:
                    uname_lower = uname.lower()
                    for uid, udata in user_data.items():
                        stored_uname = (udata.get("username") or "").lower()
                        if stored_uname and stored_uname == uname_lower:
                            target_id = uid
                            break

        if target_id is None:
            await event.respond(
                "❌ کاربر پیدا نشد. لطفاً آیدی عددی یا یوزرنیمِ معتبر ارسال کنید.",
                buttons=get_transfer_cancel_keyboard()
            )
            return

        if target_id == user_id:
            await event.respond("❌ انتقال به خودتان امکان‌پذیر نیست.", buttons=get_transfer_cancel_keyboard())
            return

        if target_id not in user_data or not user_data[target_id].get("session"):
            await event.respond("❌ کاربری با این مشخصات در سیستم ثبت‌نام نکرده است.", buttons=get_transfer_cancel_keyboard())
            return

        transfer_data[user_id] = {"target_id": target_id}
        user_data[user_id]["step"] = "transfer_get_amount"

        target_username = user_data[target_id].get("username")
        target_label = f"`{target_id}`" + (f" (@{target_username})" if target_username else "")

        await event.respond(
            f"✅ کاربر مقصد یافت شد: {target_label}\n\n"
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
    # نکته‌ی حیاتی: user_data.update(...) به‌جای بازتخصیصِ کامل (=)؛ چون سایر
    # ماژول‌ها (nova_db، nova_menus، nova_self_features) با from-import همین
    # دیکشنری را از nova_state گرفته‌اند. بازتخصیصِ کامل اینجا فقط نسخه‌ی محلیِ
    # main.py را عوض می‌کرد و همه‌ی جاهای دیگر برای همیشه دیکشنریِ خالیِ اولیه
    # را می‌دیدند.
    user_data.update(get_all_users())
    logging.info(f"📊 تعداد کاربران بارگذاری شده: {len(user_data)}")
    load_reactions_cache()
    load_autoreplies_cache()
    load_feature_locks_cache()
    load_join_gate_cache()

    loop = asyncio.get_event_loop()

    async def _load_bot_username():
        # نکته: BOT_USERNAME یک رشته‌ی معمولی است (نه دیکشنری/لیست)، پس نمی‌شود
        # در جا Mutate‌اش کرد؛ باید حتماً روی خودِ ماژول nova_state نوشته شود
        # (nova_state.BOT_USERNAME = ...)، نه با `global BOT_USERNAME` که فقط
        # یک نامِ تازه و بی‌ربط در فضای نامِ خودِ main.py می‌ساخت و nova_self_features
        # (که nova_state.BOT_USERNAME را می‌خواند) هیچ‌وقت مقدار واقعی را نمی‌دید.
        me = await bot.get_me()
        nova_state.BOT_USERNAME = me.username
        logging.info(f"🤖 نام‌کاربری ربات برای پنل درون‌چتی ذخیره شد: @{nova_state.BOT_USERNAME}")

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
    )
    loop.create_task(run_webapp_server(webapp_app, host="0.0.0.0", port=PORT))

    logging.info("✅ ربات با موفقیت راه‌اندازی شد!")
    logging.info(f"👑 تعداد ادمین‌ها: {len(ADMIN_IDS)}")

    bot.run_until_disconnected()
