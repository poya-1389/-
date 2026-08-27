# -*- coding: utf-8 -*-
"""
nova_self_features.py
====================================================================
تمام منطق «سلف» NovaSelf: دستورات متنیِ خودِ کاربر (.تگ، .پینگ، .آیدی،
.ریکت، .حذف، .بلاک/.آن‌بلاک، .ویدیو مسیج)، هندلرهای پس‌زمینه‌ی کلاینت
سلف (منشی پیوی، ریکت خودکار، سین خودکار، پاسخ خودکار، نجات پیشی)،
Workerهای زمان‌بندی‌شده (میو/ماهی/میوپوینت/یخچال میویی/اکشن/صورتحساب)،
و مدیریت طول‌عمرِ کلاینتِ Telethon هر کاربر (استارت/استاپ/ثبت Handler).

این فایل هیچ Handlerِ سطحِ بات (`@bot.on`) ندارد - آن‌ها (و ورودی‌های
جریانِ لاگین/کد/رمز که یک‌بار مصرف‌اند) در main.py می‌مانند؛ اینجا فقط
Handlerهایی هستند که روی کلاینتِ اختصاصیِ هر Self ثبت می‌شوند.
====================================================================
"""

import asyncio
import os
import re
import io
import time
import logging
import tempfile
import shutil
from datetime import datetime
import pytz
from telethon import TelegramClient, events, helpers
from telethon.sessions import StringSession
from telethon.errors import (
    FloodWaitError, MessageNotModifiedError, RPCError,
    ChatWriteForbiddenError, UserBannedInChannelError,
    UserNotParticipantError, ChannelPrivateError, ChatAdminRequiredError,
)
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.messages import GetFullChatRequest, SetTypingRequest, SendReactionRequest
from telethon.tl.functions.account import UpdateProfileRequest, UpdateStatusRequest
from telethon.tl.functions.contacts import BlockRequest, UnblockRequest
from telethon.tl.types import (
    ChannelParticipantsAdmins, InputMessageEntityMentionName,
    DocumentAttributeVideo, DocumentAttributeAnimated, ReactionEmoji,
)
try:
    import imageio_ffmpeg
    _FFMPEG_AVAILABLE = True
except ImportError:
    _FFMPEG_AVAILABLE = False

import nova_state
from nova_utils import safe_call, log_internal_error, log_settings_change
from nova_state import (
    bot, API_ID, API_HASH, ACTIONS,
    user_data, active_clients, generator_data, secretary_state,
    reaction_targets, autoreply_cache, feature_locks, _auto_sent_marks,
    DIAMOND_RATE_PER_HOUR,
    MEOW_INTERVAL_SECONDS, FISH_INTERVAL_SECONDS,
    MEOWPOINT_INTERVAL_SECONDS, FRIDGE_INTERVAL_SECONDS, BILLING_INTERVAL_SECONDS,
    FISH_RESPONSE_TIMEOUT, FISH_EDIT_WAIT_SECONDS, FISH_NUTRITION_BY_RARITY,
    FISH_RARITY_TO_FIELD, FISH_OPERATION_LABELS, FISH_OPERATION_FALLBACK_MARKERS,
    MEOWPOINT_RESPONSE_TIMEOUT,
    REACTION_APPLY_DELAY, TAG_ADMIN_TRIGGERS, TAG_MEMBERS_TRIGGERS,
    PANEL_TRIGGERS, PING_TRIGGERS, WHOIS_TRIGGERS, BALANCE_TRIGGERS,
    REACTION_SET_PREFIXES, REACTION_REMOVE_TRIGGERS,
    BLOCK_TRIGGERS_NORMALIZED, UNBLOCK_TRIGGERS_NORMALIZED, VIDEOMESSAGE_TRIGGERS,
    CLEANUP_COMMAND_RE, CLEANUP_MAX_COUNT, _PHONE_DIGIT_TRANSLATION,
    GAME_CLICK_MAX_ATTEMPTS, GAME_CLICK_RETRY_DELAY,
    tehran_now, apply_font, format_date, build_format_entities,
    make_blockquote_entity, is_admin, _spawn_background_task, _normalize_block_cmd,
    format_diamonds,
)
from nova_db import (
    save_user, update_username_db, charge_diamonds_db,
    set_user_reaction_db, remove_user_reaction_db, is_feature_locked,
)

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

    # نکته: BOT_USERNAME عمداً با نامِ کامل‌شده (nova_state.BOT_USERNAME) خوانده
    # می‌شود، نه با from-import؛ چون این مقدار در main.py موقع استارت پر می‌شود
    # (بعد از این‌که این ماژول Import شده) و from-import مقدارِ اولیه (None) را
    # برای همیشه منجمد می‌کرد.
    if not nova_state.BOT_USERNAME:
        return

    try:
        results = await event.client.inline_query(nova_state.BOT_USERNAME, "")
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

# ======================== دستور .موجودی ========================
async def handle_balance_command(event, user_id):
    """همان پیامِ دستور ویرایش و موجودیِ الماسِ کاربر به‌صورت نقل‌قول نمایش داده می‌شود."""
    try:
        client = event.client
        current_user = user_data.get(user_id, {})
        balance_text = format_diamonds(current_user.get("diamonds", 0))
        result_text = f"💎 موجودی الماس شما: {balance_text}"
        surrogated = helpers.add_surrogate(result_text)
        entities = [make_blockquote_entity(0, len(surrogated))]

        await safe_call(client.edit_message, event.chat_id, event.id, result_text, formatting_entities=entities)
    except MessageNotModifiedError:
        pass
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
    except Exception as e:
        log_internal_error("balance_command", e)

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

        # طبق درخواست صریح: به‌جای ارسال یک پیامِ تازه، خودِ پیامِ دستور ویرایش
        # می‌شود و به‌صورت نقل‌قول (Blockquote) نمایش داده می‌شود.
        result_text = f"✅ از این به بعد پیام‌های این کاربر به‌صورت خودکار با {emoji} ریکت می‌شوند.{note}"
        surrogated = helpers.add_surrogate(result_text)
        entities = [make_blockquote_entity(0, len(surrogated))]
        client = event.client
        await safe_call(client.edit_message, event.chat_id, event.id, result_text, formatting_entities=entities)
    except MessageNotModifiedError:
        pass
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
            # طبق درخواست صریح: ویرایشِ خودِ پیامِ دستور به‌جای ارسال پیامِ تازه،
            # به‌صورت نقل‌قول.
            result_text = "✅ ریکت این کاربر حذف شد."
            surrogated = helpers.add_surrogate(result_text)
            entities = [make_blockquote_entity(0, len(surrogated))]
            client = event.client
            await safe_call(client.edit_message, event.chat_id, event.id, result_text, formatting_entities=entities)
        else:
            await event.reply("❌ این کاربر در لیست ریکت شما نبود.")
    except MessageNotModifiedError:
        pass
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
    except Exception as e:
        log_internal_error("remove_reaction_command", e)

# ======================== دستور .حذف (پاکسازی پیام‌ها) ========================
async def handle_cleanup_command(event, user_id, raw_count_text):
    """
    اجرای `.حذف N` (یا `.delete N`): عدد را (فارسی یا انگلیسی) تشخیص می‌دهد، خودِ
    پیامِ دستور را حذف می‌کند و به‌علاوه N پیامِ اخیرِ ماقبلِ آن در همان چت را نیز
    حذف می‌کند. اگر عدد نامعتبر/صفر/منفی بود، به‌جای حذف، فقط همان پیامِ دستور
    با توضیح خطا ویرایش می‌شود (چیزی حذف نمی‌شود) تا کاربر متوجهِ ایرادِ کار شود.
    """
    try:
        client = event.client
        chat_id = event.chat_id

        normalized = raw_count_text.translate(_PHONE_DIGIT_TRANSLATION)
        try:
            count = int(normalized)
        except ValueError:
            await safe_call(client.edit_message, chat_id, event.id,
                             "❌ عدد نامعتبر است. مثال صحیح: `.حذف 10`")
            return

        if count <= 0:
            await safe_call(client.edit_message, chat_id, event.id,
                             "❌ تعداد باید بزرگ‌تر از صفر باشد.")
            return

        capped_note = ""
        if count > CLEANUP_MAX_COUNT:
            count = CLEANUP_MAX_COUNT
            capped_note = f" (برای جلوگیری از محدودیت تلگرام، حداکثر {CLEANUP_MAX_COUNT} پیام در هر اجرا حذف می‌شود)"

        # پیام‌های اخیرِ همین چت را (بدون خودِ پیامِ دستور) واکشی می‌کنیم
        ids_to_delete = [event.id]
        try:
            older_msgs = await client.get_messages(chat_id, limit=count, offset_id=event.id)
            ids_to_delete.extend(m.id for m in older_msgs)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            try:
                older_msgs = await client.get_messages(chat_id, limit=count, offset_id=event.id)
                ids_to_delete.extend(m.id for m in older_msgs)
            except Exception as e2:
                log_internal_error("cleanup_fetch_retry", f"user={user_id} err={e2}")
        except Exception as e:
            log_internal_error("cleanup_fetch", f"user={user_id} err={e}")

        try:
            await safe_call(client.delete_messages, chat_id, ids_to_delete)
        except FloodWaitError:
            raise  # خودِ safe_call قبلاً صبر و تلاش مجدد کرده؛ اگر بازم نشد بگذار به except بیرونی برسد
        except Exception as e:
            log_internal_error("cleanup_delete", f"user={user_id} chat={chat_id} err={e}")
            # عدم موفقیت در حذف (مثلاً Permission در گروه) نباید کرش کند؛ فقط لاگ می‌شود.
            if capped_note:
                logging.info(f"🧹 پاکسازی{capped_note} برای کاربر {user_id} در چت {chat_id}")
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
    except Exception as e:
        log_internal_error("cleanup_command", e)

# ======================== دستورات .بلاک و .آن بلاک ========================
def _display_name_of(entity):
    name = " ".join(filter(None, [getattr(entity, "first_name", None), getattr(entity, "last_name", None)]))
    if name:
        return name
    username = getattr(entity, "username", None)
    if username:
        return f"@{username}"
    return str(getattr(entity, "id", "کاربر"))

async def handle_block_command(event, user_id):
    try:
        if not event.is_reply:
            await event.reply("❌ برای بلاک کردن باید روی پیام همان کاربر Reply کنید.")
            return

        reply = await event.get_reply_message()
        if not reply or not reply.sender_id:
            await event.reply("❌ اطلاعات این کاربر در دسترس نیست.")
            return

        client = event.client
        try:
            target = await reply.get_sender()
        except Exception as e:
            log_internal_error("block_get_sender", e)
            await event.reply("❌ اطلاعات این کاربر در دسترس نیست.")
            return

        if not target:
            await event.reply("❌ اطلاعات این کاربر در دسترس نیست.")
            return

        name = _display_name_of(target)

        try:
            await safe_call(client, BlockRequest(id=target))
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            return
        except Exception as e:
            log_internal_error("block_command", f"user={user_id} target={getattr(target,'id',None)} err={e}")
            await event.reply(f"❌ بلاک کردن {name} با خطا مواجه شد.")
            return

        await asyncio.sleep(0.2)
        try:
            result_text = f"کاربر {name} بلاک شد."
            surrogated = helpers.add_surrogate(result_text)
            entities = [make_blockquote_entity(0, len(surrogated))]
            await safe_call(client.edit_message, event.chat_id, event.id, result_text, formatting_entities=entities)
        except MessageNotModifiedError:
            pass
        except Exception as e:
            log_internal_error("block_edit_message", e)

        log_settings_change(user_id, "blocked_user", str(getattr(target, "id", "")))
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
    except Exception as e:
        log_internal_error("block_command_unexpected", e)

async def handle_unblock_command(event, user_id):
    try:
        if not event.is_reply:
            await event.reply("❌ برای آن‌بلاک کردن باید روی پیام همان کاربر Reply کنید.")
            return

        reply = await event.get_reply_message()
        if not reply or not reply.sender_id:
            await event.reply("❌ اطلاعات این کاربر در دسترس نیست.")
            return

        client = event.client
        try:
            target = await reply.get_sender()
        except Exception as e:
            log_internal_error("unblock_get_sender", e)
            await event.reply("❌ اطلاعات این کاربر در دسترس نیست.")
            return

        if not target:
            await event.reply("❌ اطلاعات این کاربر در دسترس نیست.")
            return

        name = _display_name_of(target)

        try:
            await safe_call(client, UnblockRequest(id=target))
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            return
        except Exception as e:
            log_internal_error("unblock_command", f"user={user_id} target={getattr(target,'id',None)} err={e}")
            await event.reply(f"❌ آن‌بلاک کردن {name} با خطا مواجه شد.")
            return

        await asyncio.sleep(0.2)
        try:
            result_text = f"کاربر {name} آن بلاک شد."
            surrogated = helpers.add_surrogate(result_text)
            entities = [make_blockquote_entity(0, len(surrogated))]
            await safe_call(client.edit_message, event.chat_id, event.id, result_text, formatting_entities=entities)
        except MessageNotModifiedError:
            pass
        except Exception as e:
            log_internal_error("unblock_edit_message", e)

        log_settings_change(user_id, "unblocked_user", str(getattr(target, "id", "")))
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
    except Exception as e:
        log_internal_error("unblock_command_unexpected", e)

# ======================== دستور .ویدیو مسیج ========================
VIDEO_NOTE_MAX_SIDE = 640       # حداکثر ابعاد استانداردِ ویدیو مسیج تلگرام
VIDEO_NOTE_MAX_DURATION = 60    # ثانیه؛ محدودیت رایج طول ویدیو مسیج

async def _convert_to_video_note(input_path, output_path):
    """
    با ffmpeg (باینریِ مستقلِ بسته‌شده در imageio-ffmpeg، بدون نیاز به نصب سیستمی
    روی هاست) ویدیو را واقعاً مربعی (Crop از مرکز)، حداکثر ۶۴۰ پیکسل، و حداکثر
    ۶۰ ثانیه می‌کند تا تلگرام واقعاً آن را به‌صورت گرد/دایره‌ای نمایش دهد - برخلاف
    فقط علامت‌زدن video_note=True روی ویدیوی نامربعِ اصلی که تلگرام آن را به‌صورت
    ویدیوی معمولی نشان می‌دهد، نه گرد.
    خروجی: (success: bool, duration_seconds: float, error_message: str|None)
    """
    if not _FFMPEG_AVAILABLE:
        return False, 0.0, "imageio-ffmpeg نصب نیست"

    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    vf = f"crop='min(iw,ih)':'min(iw,ih)',scale={VIDEO_NOTE_MAX_SIDE}:{VIDEO_NOTE_MAX_SIDE}"
    cmd = [
        ffmpeg_path, "-y", "-i", input_path,
        "-t", str(VIDEO_NOTE_MAX_DURATION),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
        "-c:a", "aac", "-b:a", "96k",
        "-movflags", "+faststart",
        output_path,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()
    except Exception as e:
        return False, 0.0, str(e)

    stderr_text = stderr.decode(errors="ignore") if stderr else ""
    duration = 0.0
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", stderr_text)
    if match:
        h, m, s = match.groups()
        duration = min(int(h) * 3600 + int(m) * 60 + float(s), VIDEO_NOTE_MAX_DURATION)

    if proc.returncode != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        return False, 0.0, (stderr_text[-500:] if stderr_text else f"ffmpeg exit={proc.returncode}")

    return True, duration, None

async def handle_videomessage_command(event, user_id):
    """
    اجرای `.ویدیو مسیج` روی یک پیامِ ویدیوییِ Reply‌شده: ویدیو دانلود، با ffmpeg
    واقعاً مربعی/کوتاه‌شده می‌شود و به‌صورت ویدیو مسیج/ویدیو گردِ واقعیِ تلگرام
    (round_message + ابعاد مربعیِ صریح، طبق نیازِ مستندِ تلگرام برای این نوع
    پیام) در همان چت ارسال می‌شود. تمام خطاهای احتمالی (فرمت نامعتبر، حجم/طول
    زیاد، FloodWait) بدون کرش مدیریت می‌شوند و فایل‌های موقت همیشه پاک می‌شوند.
    """
    tmp_dir = None
    status_msg = None
    try:
        if not event.is_reply:
            await event.reply("❌ برای این قابلیت باید روی یک ویدیو Reply کنید.")
            return

        reply = await event.get_reply_message()
        if not reply or not getattr(reply, "video", None):
            await event.reply("❌ باید روی یک پیامِ ویدیویی Reply کنید.")
            return

        if not _FFMPEG_AVAILABLE:
            await event.reply("❌ این قابلیت روی سرور فعال نیست (imageio-ffmpeg نصب نشده است).")
            return

        client = event.client
        tmp_dir = tempfile.mkdtemp(prefix="novaself_vnote_")
        input_path = os.path.join(tmp_dir, "input.mp4")
        output_path = os.path.join(tmp_dir, "output.mp4")

        try:
            status_msg = await event.reply("⏳ در حال تبدیل به ویدیو مسیج...")
        except Exception:
            status_msg = None

        try:
            await safe_call(client.download_media, reply, input_path)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            return
        except Exception as e:
            log_internal_error("videomessage_download", f"user={user_id} err={e}")
            err_text = "❌ دانلود ویدیو ناموفق بود."
            if status_msg:
                try:
                    await status_msg.edit(err_text)
                except Exception:
                    pass
            else:
                await event.reply(err_text)
            return

        success, duration, err = await _convert_to_video_note(input_path, output_path)
        if not success:
            log_internal_error("videomessage_convert", f"user={user_id} err={err}")
            err_text = "❌ تبدیل ویدیو به ویدیو مسیج ناموفق بود؛ فرمت ویدیو پشتیبانی نمی‌شود."
            if status_msg:
                try:
                    await status_msg.edit(err_text)
                except Exception:
                    pass
            else:
                await event.reply(err_text)
            return

        attributes = [DocumentAttributeVideo(
            duration=int(duration) if duration else 1,
            w=VIDEO_NOTE_MAX_SIDE, h=VIDEO_NOTE_MAX_SIDE,
            round_message=True,
            supports_streaming=True,
        )]

        try:
            await safe_call(client.send_file, event.chat_id, output_path, attributes=attributes)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            return
        except Exception as e:
            log_internal_error("videomessage_send", f"user={user_id} err={e}")
            err_text = "❌ ارسال ویدیو مسیج ناموفق بود."
            if status_msg:
                try:
                    await status_msg.edit(err_text)
                except Exception:
                    pass
            else:
                await event.reply(err_text)
            return

        if status_msg:
            try:
                await status_msg.delete()
            except Exception:
                pass
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
    except Exception as e:
        log_internal_error("videomessage_command_unexpected", e)
    finally:
        if tmp_dir:
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

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

            # --- موجودی (در هر نوع چتی) ---
            if text_stripped and text_stripped.lower() in BALANCE_TRIGGERS:
                if is_feature_locked(user_id, "balance"):
                    await event.reply("این قابلیت برای شما قفل شده است.")
                    return
                await handle_balance_command(event, user_id)
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

            # --- حذف/پاکسازی پیام‌ها (.حذف N / .delete N — در هر نوع چتی) ---
            if text_stripped:
                cleanup_match = CLEANUP_COMMAND_RE.match(text_stripped)
                if cleanup_match:
                    if is_feature_locked(user_id, "cleanup"):
                        await event.reply("این قابلیت برای شما قفل شده است.")
                        return
                    await handle_cleanup_command(event, user_id, cleanup_match.group(1))
                    return

            # --- بلاک / آن‌بلاک (.بلاک / .آن بلاک — در هر نوع چتی، فقط با Reply) ---
            if text_stripped:
                normalized_cmd = _normalize_block_cmd(text_stripped.lower())
                is_block_cmd = normalized_cmd in BLOCK_TRIGGERS_NORMALIZED or normalized_cmd in UNBLOCK_TRIGGERS_NORMALIZED
                if is_block_cmd and is_feature_locked(user_id, "blockmgmt"):
                    await event.reply("این قابلیت برای شما قفل شده است.")
                    return
                if normalized_cmd in BLOCK_TRIGGERS_NORMALIZED:
                    await handle_block_command(event, user_id)
                    return
                if normalized_cmd in UNBLOCK_TRIGGERS_NORMALIZED:
                    await handle_unblock_command(event, user_id)
                    return

            # --- ویدیو مسیج (.ویدیو مسیج — در هر نوع چتی، فقط با Reply روی ویدیو) ---
            if text_stripped and text_stripped.lower() in VIDEOMESSAGE_TRIGGERS:
                if is_feature_locked(user_id, "videomessage"):
                    await event.reply("این قابلیت برای شما قفل شده است.")
                    return
                await handle_videomessage_command(event, user_id)
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
    وقتی یکی از کاربران داخل «لیست ریکت» پیام جدیدی بفرستد، بعد از ~۱ ثانیه Delay،
    همان ایموجی روی پیامش ریکت زده می‌شود. طبق آپدیت جدید، این قابلیت هم در
    گروه/سوپرگروه مشترک و هم در چت خصوصی (وقتی همان کاربر مستقیماً به صاحب سلف
    پیام بدهد) کار می‌کند. هر کاربر مستقل مدیریت می‌شود؛ چون Delay فقط ۱ ثانیه
    است، برای هر پیام یک Task کوتاه‌مدت جدید ساخته می‌شود (نه یک Task دائمی) تا
    با پیام‌های پی‌درپی تداخل/تجمع پیدا نکند.
    """
    async def handler(event):
        try:
            if event.out:
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
            message_id = event.id

            # نکته‌ی مهم (باگ گزارش‌شده: «بعد از ثبت تازه‌ی سلف، ریکت روی کاربرِ
            # ثبت‌شده اعمال نمی‌شود»): بلافاصله بعد از لاگین، کلاینتِ تازه‌ساخته‌شده
            # هنوز هیچ کشِ Entity ندارد (چون get_dialogs یا مشابه آن اجرا نشده).
            # send_reaction با یک chat_id خامِ int سعی می‌کند خودش Entity را از کش
            # Resolve کند و همان لحظه (روی چت‌هایی که کلاینت تازه اولین پیامشان را
            # می‌بیند) با خطای «entity پیدا نشد» شکست می‌خورد. اینجا به‌جای chat_id،
            # از خودِ input_chat که مستقیماً از همین Update فعلی ساخته می‌شود
            # استفاده می‌کنیم؛ این یکی از قبل Access Hash کامل دارد و نیازی به کش
            # قدیمی ندارد.
            try:
                input_chat = await event.get_input_chat()
            except Exception:
                input_chat = event.chat_id  # فallback؛ بهتر از هیچ

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
                    # به‌جای متد میان‌راهیِ client.send_reaction (که وجودش/امضایش
                    # بین نسخه‌های مختلف Telethon یکسان نیست و همین منبعِ اصلیِ باگِ
                    # «ثبت می‌شود ولی ریکت اعمال نمی‌شود» بود)، مستقیماً از خودِ
                    # درخواست خام تلگرام (messages.sendReaction) استفاده می‌کنیم که
                    # امضای ثابت و تضمین‌شده دارد.
                    await safe_call(
                        client,
                        SendReactionRequest(
                            peer=input_chat,
                            msg_id=message_id,
                            reaction=[ReactionEmoji(emoticon=emoji)],
                            add_to_recent=True,
                        )
                    )
                except asyncio.CancelledError:
                    pass
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    logging.warning(f"⚠️ ریکت روی کاربر {sender_id} برای Self {user_id} اعمال نشد: {e}")
                    log_internal_error("apply_reaction", f"user={user_id} target={sender_id} err={e}")

            _spawn_background_task(_delayed_react())
        except Exception as e:
            logging.error(f"⚠️ خطای هندلر ریکت برای کاربر {user_id}: {e}")
            log_internal_error("reaction_handler_unexpected", e)

    return handler

# ======================== قابلیت سین خودکار ========================
def make_autoseen_handler(user_id):
    """
    وقتی قابلیت روشن است، هر پیام خصوصیِ دریافتی از یک کاربرِ واقعی (نه بات)
    بلافاصله Seen/Read می‌شود. طبق درخواست صریح، برای بات‌ها اجرا نمی‌شود و
    محدود به یک چت خاص نیست — روی همه‌ی چت‌های خصوصی صاحب سلف فعال است.
    """
    async def handler(event):
        try:
            if event.out or not event.is_private:
                return

            user = user_data.get(user_id)
            if not user or not user.get("status") or not user.get("autoseen_enabled"):
                return

            if is_feature_locked(user_id, "autoseen"):
                return

            try:
                chat = await event.get_chat()
            except Exception as e:
                log_internal_error("autoseen_get_chat", f"user={user_id} err={e}")
                return

            if not chat or getattr(chat, "bot", False):
                return  # طبق درخواست صریح: فقط Userهای واقعی، نه Botها

            client = event.client
            await safe_call(client.send_read_acknowledge, event.chat_id)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
        except Exception as e:
            log_internal_error("autoseen_handler", f"user={user_id} err={e}")

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
    client.add_event_handler(make_autoseen_handler(user_id), events.NewMessage(incoming=True))

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

            # «همیشه آنلاین» حالا دقیقاً مثل بقیه‌ی اکشن‌ها، فقط یکی از آن‌ها به‌طور
            # هم‌زمان قابل انتخاب است (از طریق همون active_action)؛ فقط مکانیزم اجرایش
            # با بقیه فرق دارد: به‌جای SetTypingRequest، هر ۴ ثانیه UpdateStatusRequest
            # می‌فرستد تا تلگرام کاربر را واقعاً آنلاین نشان دهد.
            if action_key == "online":
                try:
                    await client(UpdateStatusRequest(offline=False))
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    log_internal_error("always_online", f"user={user_id} err={e}")
                await asyncio.sleep(4)
                continue

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
