# -*- coding: utf-8 -*-
"""
nova_card.py
====================================================================
رندرِ «کارت پنل» (تصویرِ بالای `.پنل`) با Pillow. این فایل عمداً مستقل است
(هیچ وابستگی‌ای به تلگرام/دیتابیس ندارد) و فقط از روی یک dict داده‌ی آماده، تصویر
می‌سازد؛ جمع‌کردن داده‌های واقعی (پینگ، موجودی، ...) کارِ nova_menus است.

شکل‌دهی متن فارسی (به ترتیب اولویت):
  1) Pillow با Raqm (در صورت وجود)  2) arabic-reshaper + python-bidi
  3) اگر هیچ‌کدام نبود، برچسب‌ها انگلیسی می‌شوند (تا متن شکسته نمایش داده نشود).
فونت‌ها از پوشه‌ی fonts/ کنار پروژه خوانده می‌شوند (DejaVu برای فارسی، Poppins برای عنوان).
====================================================================
"""

import io
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont, features

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    _HAS_RESHAPER = True
except Exception:  # کتابخانه‌ها نصب نیستند
    _HAS_RESHAPER = False

W, H = 1280, 853      # اندازه‌ی نهایی
S = 2                 # ابَرنمونه‌برداری برای لبه‌های نرم
_DIR = os.path.dirname(os.path.abspath(__file__))
_FONT_DIRS = [os.path.join(_DIR, "fonts"), "/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype/liberation"]

CYAN, GREEN, PURPLE, PINK, BLUE = (0, 205, 255), (0, 230, 150), (175, 85, 255), (255, 80, 190), (45, 120, 255)

LABELS_FA = {
    "online": "آنلاین", "offline": "آفلاین",
    "online_sub": "ربات شما فعال است", "offline_sub": "ربات شما غیرفعال است",
    "ping": "پینگ", "features": "امکانات فعال", "duration": "مدت فعالیت", "account": "شناسه اکانت",
    "subtitle": "مدیریت اکانت تلگرام", "location": "تهران • IRST",
}
LABELS_EN = {
    "online": "Online", "offline": "Offline",
    "online_sub": "Your self is active", "offline_sub": "Your self is inactive",
    "ping": "Ping", "features": "Active features", "duration": "Uptime", "account": "Account ID",
    "subtitle": "Telegram account manager", "location": "Tehran • IRST",
}


def _shaping_mode():
    try:
        if features.check("raqm"):
            return "raqm"
    except Exception:
        pass
    return "reshape" if _HAS_RESHAPER else None


def _load_font(names, size):
    for d in _FONT_DIRS:
        for n in names:
            path = os.path.join(d, n)
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, int(size * S))
                except Exception:
                    continue
    return ImageFont.load_default()


def _fa_font(size, bold=False):
    return _load_font(["DejaVuSans-Bold.ttf"] if bold else ["DejaVuSans.ttf"], size)


def _latin_bold(size):
    return _load_font(["Poppins-Bold.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"], size)


def _shape(text, mode):
    if mode == "reshape":
        return get_display(arabic_reshaper.reshape(text))
    return text


def _text(layer, xy, text, font, fill, mode, anchor="mm"):
    ImageDraw.Draw(layer).text((xy[0] * S, xy[1] * S), _shape(text, mode), font=font, fill=fill, anchor=anchor)


def _fit(text, make_font, size, max_w, mode, min_size=14):
    """فونت را تا جایی کوچک می‌کند که متن در max_w (پیکسل نهایی) جا شود."""
    probe = ImageDraw.Draw(Image.new("L", (4, 4)))
    while True:
        font = make_font(size)
        width = probe.textlength(_shape(text, mode), font=font) / S
        if width <= max_w or size <= min_size:
            return font
        size -= 2


def _grad(size, c1, c2, vertical=False, diagonal=False):
    w, h = size
    img = Image.new("RGBA", size)
    d = ImageDraw.Draw(img)
    if diagonal:
        # گرادیان قطری: روی تصویر کوچک‌تر ساخته و کش می‌آید
        small = _grad((256, 1), c1, c2).resize((256, 1))
        strip = small.resize((w + h, 1)).crop((0, 0, w + h, 1))
        for y in range(h):
            img.paste(strip.crop((y, 0, y + w, 1)).resize((w, 1)), (0, y))
        return img
    n = h if vertical else w
    for i in range(n):
        t = i / max(1, n - 1)
        col = tuple(int(c1[k] + (c2[k] - c1[k]) * t) for k in range(3)) + (255,)
        d.line([(0, i), (w, i)] if vertical else [(i, 0), (i, h)], fill=col)
    return img


def _glow(base, draw_fn, radius, strength=1.0):
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw_fn(layer)
    blurred = layer.filter(ImageFilter.GaussianBlur(radius * S))
    if strength != 1.0:
        a = blurred.getchannel("A").point(lambda v: min(255, int(v * strength)))
        blurred.putalpha(a)
    base.alpha_composite(blurred)


def _rrect(layer, box, radius, fill=None, outline=None, width=2):
    ImageDraw.Draw(layer).rounded_rectangle(
        [box[0] * S, box[1] * S, box[2] * S, box[3] * S], radius=radius * S,
        fill=fill, outline=outline, width=int(width * S))


# ------------------------------- آیکون‌ها -------------------------------
def _ic_bars(layer, cx, cy, size, color):
    d = ImageDraw.Draw(layer)
    bw, gap = size * 0.2, size * 0.12
    for i, hh in enumerate((0.4, 0.7, 1.0)):
        x0 = cx - size / 2 + i * (bw + gap)
        d.rounded_rectangle([x0 * S, (cy + size / 2 - size * hh) * S, (x0 + bw) * S, (cy + size / 2) * S],
                            radius=bw * S / 2, fill=color)


def _ic_chip(layer, cx, cy, size, color):
    d = ImageDraw.Draw(layer)
    r = size / 2
    d.rounded_rectangle([(cx - r * .7) * S, (cy - r * .7) * S, (cx + r * .7) * S, (cy + r * .7) * S],
                        radius=5 * S, outline=color, width=3 * S)
    d.rectangle([(cx - r * .3) * S, (cy - r * .3) * S, (cx + r * .3) * S, (cy + r * .3) * S], fill=color)
    for k in (-.4, 0, .4):
        d.line([((cx + k * r) * S, (cy - r) * S), ((cx + k * r) * S, (cy - r * .7) * S)], fill=color, width=3 * S)
        d.line([((cx + k * r) * S, (cy + r * .7) * S), ((cx + k * r) * S, (cy + r) * S)], fill=color, width=3 * S)
        d.line([((cx - r) * S, (cy + k * r) * S), ((cx - r * .7) * S, (cy + k * r) * S)], fill=color, width=3 * S)
        d.line([((cx + r * .7) * S, (cy + k * r) * S), ((cx + r) * S, (cy + k * r) * S)], fill=color, width=3 * S)


def _ic_clock(layer, cx, cy, size, color, ring=True):
    d = ImageDraw.Draw(layer)
    r = size / 2
    if ring:
        d.ellipse([(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S], outline=color, width=int(3 * S))
    d.line([(cx * S, (cy - r * .55) * S), (cx * S, cy * S), ((cx + r * .4) * S, (cy + r * .25) * S)],
           fill=color, width=int(3 * S), joint="curve")


def _ic_calendar(layer, cx, cy, size, color):
    d = ImageDraw.Draw(layer)
    r = size / 2
    d.rounded_rectangle([(cx - r) * S, (cy - r * .8) * S, (cx + r) * S, (cy + r) * S], radius=7 * S,
                        outline=color, width=int(3 * S))
    d.line([((cx - r) * S, (cy - r * .25) * S), ((cx + r) * S, (cy - r * .25) * S)], fill=color, width=int(3 * S))
    for x in (-.5, .5):
        d.line([((cx + x * r) * S, (cy - r * 1.1) * S), ((cx + x * r) * S, (cy - r * .6) * S)], fill=color, width=int(3 * S))
    for gx in (-.5, 0, .5):
        for gy in (.15, .6):
            d.rectangle([(cx + gx * r - 2) * S, (cy + gy * r - 2) * S, (cx + gx * r + 2) * S, (cy + gy * r + 2) * S], fill=color)


def _ic_pin(layer, cx, cy, size, color):
    d = ImageDraw.Draw(layer)
    r = size / 2
    d.ellipse([(cx - r * .8) * S, (cy - r) * S, (cx + r * .8) * S, (cy + r * .6) * S], fill=color)
    d.polygon([((cx - r * .62) * S, (cy + r * .25) * S), ((cx + r * .62) * S, (cy + r * .25) * S), (cx * S, (cy + r * 1.1) * S)], fill=color)
    d.ellipse([(cx - r * .3) * S, (cy - r * .5) * S, (cx + r * .3) * S, (cy + r * .1) * S], fill=(8, 12, 30, 255))


def _ic_person(layer, cx, cy, size, color):
    d = ImageDraw.Draw(layer)
    r = size / 2
    d.ellipse([(cx - r * .35) * S, (cy - r * .7) * S, (cx + r * .35) * S, (cy) * S], fill=color)
    d.pieslice([(cx - r * .75) * S, (cy + r * .05) * S, (cx + r * .75) * S, (cy + r * 1.35) * S], 180, 360, fill=color)


def _ic_grid(layer, cx, cy, size, color):
    d = ImageDraw.Draw(layer)
    r = size / 2
    s = r * .8
    for gx in (-1, 0):
        for gy in (-1, 0):
            x0, y0 = cx + gx * s * 1.1 + s * .05, cy + gy * s * 1.1 + s * .05
            d.rounded_rectangle([x0 * S, y0 * S, (x0 + s) * S, (y0 + s) * S], radius=5 * S, fill=color)


def _background():
    base = Image.new("RGBA", (W * S, H * S), (5, 7, 18, 255))
    glows = [((-230, -190, 380, 170), (20, 70, 255, 120)), ((-260, 640, 240, 980), (20, 60, 255, 115)),
             ((1020, 700, 1520, 1020), (40, 80, 255, 100)), ((1060, -200, 1500, 120), (90, 60, 255, 95))]
    for box, col in glows:
        _glow(base, lambda l, b=box, c=col: ImageDraw.Draw(l).ellipse([v * S for v in b], fill=c), 70, 1.0)
    # خطوط موجیِ نرم گوشه‌ها
    def waves(layer):
        d = ImageDraw.Draw(layer)
        for off, a in ((0, 90), (26, 55), (52, 30)):
            d.arc([(-420 + off) * S, (-300 + off) * S, (520 + off) * S, (330 + off) * S], 0, 90, fill=(70, 150, 255, a), width=3 * S)
            d.arc([(900 - off) * S, (600 - off) * S, (1700 - off) * S, (1300 - off) * S], 180, 270, fill=(100, 120, 255, a), width=3 * S)
    _glow(base, waves, 3)
    waves(base)
    return base


def render_panel_card(data):
    """
    data: online(bool), time, date, ping, features, duration_fa, duration_en,
          account_id, avatar_bytes (اختیاری), initial (اختیاری)
    خروجی: BytesIO (JPEG).
    """
    mode = _shaping_mode()
    L = LABELS_FA if mode else LABELS_EN
    duration = data.get("duration_fa") if mode else data.get("duration_en")

    img = _background()

    # ---------- حلقه‌ی گرادیانی + آواتار ----------
    cx, cy, ro = 640, 205, 150
    ring_w = 8
    ring_mask = Image.new("L", img.size, 0)
    md = ImageDraw.Draw(ring_mask)
    md.ellipse([(cx - ro) * S, (cy - ro) * S, (cx + ro) * S, (cy + ro) * S], fill=255)
    md.ellipse([(cx - ro + ring_w) * S, (cy - ro + ring_w) * S, (cx + ro - ring_w) * S, (cy + ro - ring_w) * S], fill=0)
    ring_grad = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gbox = ((cx - ro) * S, (cy - ro) * S, (cx + ro) * S, (cy + ro) * S)
    ring_grad.paste(_grad((gbox[2] - gbox[0], gbox[3] - gbox[1]), CYAN, PURPLE, diagonal=True), (gbox[0], gbox[1]))
    ring_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ring_layer.paste(ring_grad, (0, 0), ring_mask)
    glow = ring_layer.filter(ImageFilter.GaussianBlur(14 * S))
    img.alpha_composite(glow)
    img.alpha_composite(ring_layer)

    inner = ro - ring_w - 6
    disc = Image.new("RGBA", ((2 * inner) * S, (2 * inner) * S), (8, 12, 30, 255))
    avatar_bytes = data.get("avatar_bytes")
    if avatar_bytes:
        try:
            av = Image.open(io.BytesIO(avatar_bytes)).convert("RGB")
            side = min(av.size)
            left, top = (av.width - side) // 2, (av.height - side) // 2
            disc = av.crop((left, top, left + side, top + side)).resize(disc.size, Image.LANCZOS).convert("RGBA")
        except Exception:
            avatar_bytes = None
    if not avatar_bytes:
        ImageDraw.Draw(disc).text((disc.width / 2, disc.height / 2), data.get("initial") or "N",
                                  font=_latin_bold(120), fill=CYAN + (255,), anchor="mm")
    dmask = Image.new("L", disc.size, 0)
    ImageDraw.Draw(dmask).ellipse([0, 0, disc.width - 1, disc.height - 1], fill=255)
    img.paste(disc, ((cx - inner) * S, (cy - inner) * S), dmask)

    # ---------- عنوان ----------
    title_font = _latin_bold(74)
    t_mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(t_mask).text((cx * S, 398 * S), "NoVASeLFBot", font=title_font, fill=255, anchor="mm")
    glow_src = Image.new("RGBA", img.size, (0, 0, 0, 0))
    tb = t_mask.getbbox()
    glow_src.paste(_grad((tb[2] - tb[0], tb[3] - tb[1]), CYAN, PURPLE), (tb[0], tb[1]), t_mask.crop(tb))
    img.alpha_composite(glow_src.filter(ImageFilter.GaussianBlur(10 * S)))
    img.alpha_composite(glow_src)
    _text(img, (cx, 460), L["subtitle"], _fa_font(27), (175, 190, 235, 255), mode)
    sub_w = ImageDraw.Draw(img).textlength(_shape(L["subtitle"], mode), font=_fa_font(27)) / S
    for x0, x1, col in ((cx - sub_w / 2 - 20 - 62, cx - sub_w / 2 - 20, CYAN), (cx + sub_w / 2 + 20, cx + sub_w / 2 + 20 + 62, PURPLE)):
        _rrect(img, (x0, 458, x1, 461), 2, fill=col + (255,))

    # ---------- وضعیت (بالا-چپ) ----------
    st_col = GREEN if data.get("online") else (255, 85, 95)
    _rrect(img, (72, 112, 257, 167), 28, fill=(10, 30, 38, 210), outline=st_col + (255,), width=2)
    _glow(img, lambda l: ImageDraw.Draw(l).ellipse([(95) * S, (127) * S, (121) * S, (153) * S], fill=st_col + (255,)), 6)
    ImageDraw.Draw(img).ellipse([95 * S, 127 * S, 121 * S, 153 * S], fill=st_col + (255,))
    _text(img, (192, 140), L["online"] if data.get("online") else L["offline"], _fa_font(25, True), (255, 255, 255, 255), mode)
    _text(img, (164, 193), L["online_sub"] if data.get("online") else L["offline_sub"], _fa_font(19), (150, 168, 215, 255), mode)

    # ---------- باکس پینگ / امکانات (چپ) ----------
    _rrect(img, (67, 238, 419, 342), 24, fill=(10, 18, 48, 200), outline=(40, 70, 170, 255), width=2)
    ImageDraw.Draw(img).line([(231 * S, 258 * S), (231 * S, 322 * S)], fill=(45, 60, 130, 255), width=2 * S)
    _ic_bars(img, 100, 280, 36, CYAN)
    _text(img, (175, 268), L["ping"], _fa_font(18), (190, 200, 232, 255), mode)
    _text(img, (165, 306), data.get("ping", "—"), _fit(data.get("ping", "—"), lambda s: _latin_bold(s), 26, 100, None), CYAN + (255,), None)
    _ic_chip(img, 268, 282, 34, PURPLE)
    _text(img, (352, 268), L["features"], _fa_font(18), (190, 200, 232, 255), mode)
    _text(img, (335, 306), str(data.get("features", 0)), _latin_bold(28), PURPLE + (255,), None)

    # ---------- ساعت / تاریخ / موقعیت (راست) ----------
    _ic_clock(img, 1186, 143, 44, BLUE)
    _text(img, (1118, 143), data.get("time", "--:--"), _latin_bold(40), (255, 255, 255, 255), None, anchor="rm")
    _ic_calendar(img, 1186, 225, 40, PURPLE)
    _text(img, (1118, 225), data.get("date", ""), _latin_bold(34), (255, 255, 255, 255), None, anchor="rm")
    _ic_pin(img, 1186, 303, 34, (35, 175, 255))
    _text(img, (1148, 303), L["location"], _fa_font(21), (170, 190, 240, 255), mode, anchor="rm")

    # ---------- چهار کارت پایین ----------
    _rrect(img, (60, 500, 1222, 772), 30, fill=(8, 14, 44, 140), outline=(40, 75, 215, 255), width=2)
    cards = [
        ((86, 527, 356, 749), CYAN, _ic_person, L["account"], str(data.get("account_id", "")), False),
        ((377, 527, 633, 749), GREEN, _ic_bars, L["ping"], data.get("ping", "—"), False),
        ((654, 527, 909, 749), PURPLE, _ic_clock, L["duration"], duration or "—", True),
        ((930, 527, 1196, 749), PINK, _ic_grid, L["features"], str(data.get("features", 0)), False),
    ]
    for box, col, icon, label, value, value_is_fa in cards:
        mx = (box[0] + box[2]) / 2
        _glow(img, lambda l, b=box, c=col: _rrect(l, b, 26, fill=c + (70,)), 14, 0.8)
        _rrect(img, box, 26, fill=(14, 22, 56, 150), outline=col + (200,), width=2)
        # دایره‌ی آیکون
        ImageDraw.Draw(img).ellipse([(mx - 37) * S, (582 - 37) * S, (mx + 37) * S, (582 + 37) * S], outline=col + (255,), width=3 * S)
        if icon is _ic_clock:
            icon(img, mx, 582, 52, col, ring=False)
        else:
            icon(img, mx, 582, 34, col)
        vmode = mode if value_is_fa else None
        vfont = _fit(value, (lambda s: _fa_font(s, True)) if value_is_fa else (lambda s: _latin_bold(s)), 40, (box[2] - box[0]) - 36, vmode)
        _text(img, (mx, 660), value, vfont, (255, 255, 255, 255), vmode)
        _text(img, (mx, 702), label, _fa_font(21), (195, 205, 235, 255), mode)
        _rrect(img, (mx - 65, 727, mx + 65, 733), 3, fill=col + (255,))

    out = io.BytesIO()
    out.name = "novaself_panel.jpg"
    img.convert("RGB").resize((W, H), Image.LANCZOS).save(out, "JPEG", quality=92)
    out.seek(0)
    return out
