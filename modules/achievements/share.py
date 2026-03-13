import io
import os
import random
import textwrap

from PIL import Image, ImageDraw, ImageFont
from flask import current_app

FORMATS = {
    '1:1': (1080, 1080),
    '9:16': (1080, 1920),
    '3:4': (1080, 1440),
}

DESIGN = {
    'common': {
        'bg': (14, 11, 20),
        'glow_color': (160, 160, 160),
        'glow_strength': 0.12,
        'card_top_tint': (120, 180, 120),
        'card_top_alpha': 0.08,
        'card_bottom': (20, 10, 35),
        'border_color': (160, 160, 160),
        'border_alpha': 0.15,
        'accent': (156, 163, 175),
        'pill_bg_alpha': 0.15,
        'pill_color': (170, 170, 170),
    },
    'rare': {
        'bg': (8, 14, 30),
        'glow_color': (59, 130, 246),
        'glow_strength': 0.35,
        'card_top_tint': (59, 130, 246),
        'card_top_alpha': 0.1,
        'card_bottom': (10, 12, 35),
        'border_color': (59, 130, 246),
        'border_alpha': 0.25,
        'accent': (59, 130, 246),
        'pill_bg_alpha': 0.12,
        'pill_color': (124, 196, 255),
    },
    'epic': {
        'bg': (12, 6, 22),
        'glow_color': (139, 92, 246),
        'glow_strength': 0.4,
        'card_top_tint': (139, 92, 246),
        'card_top_alpha': 0.12,
        'card_bottom': (15, 8, 35),
        'border_color': (179, 136, 255),
        'border_alpha': 0.3,
        'accent': (139, 92, 246),
        'pill_bg_alpha': 0.12,
        'pill_color': (208, 160, 255),
    },
    'legendary': {
        'bg': (17, 13, 2),
        'glow_color': (255, 200, 50),
        'glow_strength': 0.4,
        'card_top_tint': (232, 163, 8),
        'card_top_alpha': 0.14,
        'card_bottom': (25, 18, 10),
        'border_color': (255, 200, 50),
        'border_alpha': 0.35,
        'accent': (232, 163, 8),
        'pill_bg_alpha': 0.14,
        'pill_color': (255, 217, 102),
    },
}

RARITY_LABELS = {
    'common': 'Pospolite',
    'rare': 'Rzadkie',
    'epic': 'Epickie',
    'legendary': 'Legendarne',
}

PAD = 100
CARD_W = 1080 - 2 * PAD  # 880


def _blend(bg, fg, alpha):
    return tuple(int(bg[i] * (1 - alpha) + fg[i] * alpha) for i in range(3))


def _card_bg_at_y(d, y, card_h):
    t = y / max(card_h, 1)
    a = d['card_top_alpha'] * (1 - t)
    return _blend(d['card_bottom'], d['card_top_tint'], a)


def _load_fonts(static_folder):
    path = os.path.join(static_folder, 'fonts', 'Inter-Bold.ttf')
    try:
        return {
            'name': ImageFont.truetype(path, 52),
            'desc': ImageFont.truetype(path, 36),
            'pill': ImageFont.truetype(path, 28),
            'stat': ImageFont.truetype(path, 28),
            'date': ImageFont.truetype(path, 24),
            'footer': ImageFont.truetype(path, 22),
        }
    except (OSError, IOError):
        df = ImageFont.load_default()
        return {k: df for k in ('name', 'desc', 'pill', 'stat', 'date', 'footer')}


def generate_share_image(achievement, fmt='1:1', unlocked_at=None, stat_percentage=0):
    """Generate a share image as PNG bytes in memory. No file caching."""
    width, height = FORMATS.get(fmt, FORMATS['1:1'])
    d = DESIGN.get(achievement.rarity, DESIGN['common'])
    label = RARITY_LABELS.get(achievement.rarity, 'Pospolite')
    fonts = _load_fonts(current_app.static_folder)

    img = Image.new('RGB', (width, height), d['bg'])
    draw = ImageDraw.Draw(img)
    cx = width // 2
    cy = height // 2

    # --- Radial glow ---
    glow_r = int(max(width, height) * 0.375)
    for i in range(glow_r, 0, -2):
        ratio = i / glow_r
        alpha = (1 - ratio) ** 2 * d['glow_strength']
        c = _blend(d['bg'], d['glow_color'], alpha)
        draw.ellipse([cx - i, cy - i, cx + i, cy + i], fill=c)

    # --- Legendary particles ---
    if achievement.rarity == 'legendary':
        for _ in range(80):
            px = random.randint(0, width - 1)
            py = random.randint(0, height - 1)
            ps = random.randint(1, 4)
            po = 0.15 + random.random() * 0.55
            try:
                bg_px = img.getpixel((px, py))
                c = _blend(bg_px, (255, 210, 60), po)
                draw.ellipse([px, py, px + ps, py + ps], fill=c)
            except Exception:
                pass

    # --- Card (gradient, rounded corners) ---
    card_h = CARD_W  # square card
    # Fast gradient: 1px-wide strip then resize
    strip = Image.new('RGB', (1, card_h))
    for y in range(card_h):
        strip.putpixel((0, y), _card_bg_at_y(d, y, card_h))
    card = strip.resize((CARD_W, card_h), Image.NEAREST)

    mask = Image.new('L', (CARD_W, card_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, CARD_W - 1, card_h - 1], radius=28, fill=255
    )

    card_x = PAD
    card_y = (height - card_h) // 2
    img.paste(card, (card_x, card_y), mask)

    # Card border
    bc = _blend(d['bg'], d['border_color'], d['border_alpha'])
    draw.rounded_rectangle(
        [card_x, card_y, card_x + CARD_W - 1, card_y + card_h - 1],
        radius=28, outline=bc, width=2
    )

    # --- Logo (PNG) ---
    logo_path = os.path.join(
        current_app.static_folder, 'img', 'icons', 'logo-full-white.png'
    )
    if os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert('RGBA')
            lh = 44
            lw = int(logo.width * lh / logo.height)
            logo = logo.resize((lw, lh), Image.LANCZOS)
            img.paste(logo, (cx - lw // 2, card_y + 50), logo)
        except Exception:
            pass

    # --- Measure content block height first, then center it ---
    ring_r = 110
    gap_icon_name = 40
    gap_name_desc = 16
    gap_desc_pill = 24
    gap_pill_stat = 24
    gap_stat_date = 12

    # Measure text heights
    name_bbox = draw.textbbox((0, 0), achievement.name, font=fonts['name'])
    name_h = name_bbox[3] - name_bbox[1]

    wrapped = textwrap.fill(achievement.description, width=28)
    desc_lines = wrapped.split('\n')
    desc_h = 0
    for dl in desc_lines:
        lb = draw.textbbox((0, 0), dl, font=fonts['desc'])
        desc_h += (lb[3] - lb[1]) + 8
    desc_h -= 8  # remove last line gap

    pill_label = label
    pill_bbox = draw.textbbox((0, 0), pill_label, font=fonts['pill'])
    pill_tw = pill_bbox[2] - pill_bbox[0]
    pill_th = pill_bbox[3] - pill_bbox[1]
    diamond_size = 10
    diamond_gap = 10
    pw = diamond_size * 2 + diamond_gap + pill_tw + 64
    ph = pill_th + 24

    stat_h = 0
    if stat_percentage and stat_percentage > 0:
        sb = draw.textbbox((0, 0), f'Posiada {stat_percentage}% użytkowników', font=fonts['stat'])
        stat_h = (sb[3] - sb[1]) + gap_pill_stat

    date_h = 0
    if unlocked_at:
        db = draw.textbbox((0, 0), f'Zdobyte: 13.03.2026', font=fonts['date'])
        date_h = (db[3] - db[1]) + gap_stat_date

    total_h = (ring_r * 2 + gap_icon_name + name_h + gap_name_desc
               + desc_h + gap_desc_pill + ph + stat_h + date_h)

    # Available vertical space: between logo bottom and footer top
    logo_bottom = card_y + 50 + 44 + 20  # logo at card_y+50, h=44, +20 margin
    footer_top = card_y + card_h - 50     # leave 50px for footer
    avail_h = footer_top - logo_bottom
    content_top = logo_bottom + (avail_h - total_h) // 2

    # --- Draw icon with rings ---
    icon_cy = content_top + ring_r
    icon_rel_y = icon_cy - card_y
    cbg = _card_bg_at_y(d, icon_rel_y, card_h)

    draw.ellipse(
        [cx - ring_r, icon_cy - ring_r, cx + ring_r, icon_cy + ring_r],
        outline=_blend(cbg, d['accent'], 0.3), width=3
    )
    ir = ring_r - 8
    draw.ellipse(
        [cx - ir, icon_cy - ir, cx + ir, icon_cy + ir],
        outline=_blend(cbg, d['accent'], 0.6), width=3
    )
    icr = ring_r - 16
    circle_fill = _blend(cbg, (255, 255, 255), 0.05)
    draw.ellipse(
        [cx - icr, icon_cy - icr, cx + icr, icon_cy + icr],
        fill=circle_fill, outline=d['accent'], width=3
    )

    # Icon image
    icon_file = f'{achievement.slug}@512.png'
    icon_path = os.path.join(
        current_app.static_folder, 'uploads', 'achievements', icon_file
    )
    if os.path.exists(icon_path):
        try:
            icon = Image.open(icon_path).convert('RGBA')
            icon = icon.resize((120, 120), Image.LANCZOS)
            img.paste(icon, (cx - 60, icon_cy - 60), icon)
        except Exception:
            pass

    # --- Text content (positioned from centered block) ---
    text_y = icon_cy + ring_r + gap_icon_name

    # Name
    draw.text(
        (cx, text_y), achievement.name,
        fill=(245, 245, 245), font=fonts['name'], anchor='mt'
    )
    text_y += name_h + gap_name_desc

    # Description
    desc_color = _blend(
        _card_bg_at_y(d, text_y - card_y, card_h), (255, 255, 255), 0.5
    )
    for dl in desc_lines:
        draw.text(
            (cx, text_y), dl,
            fill=desc_color, font=fonts['desc'], anchor='mt'
        )
        lb = draw.textbbox((0, 0), dl, font=fonts['desc'])
        text_y += (lb[3] - lb[1]) + 8
    text_y += gap_desc_pill - 8  # compensate last line gap

    # Rarity pill
    px1 = cx - pw // 2
    py1 = text_y
    pill_cbg = _card_bg_at_y(d, text_y - card_y, card_h)
    pill_fill = _blend(pill_cbg, d['accent'], d['pill_bg_alpha'])
    draw.rounded_rectangle(
        [px1, py1, px1 + pw, py1 + ph],
        radius=ph // 2, fill=pill_fill
    )
    pill_cy = py1 + ph // 2
    star_cx = px1 + 32 + diamond_size
    draw.polygon(
        [(star_cx, pill_cy - diamond_size),
         (star_cx + diamond_size, pill_cy),
         (star_cx, pill_cy + diamond_size),
         (star_cx - diamond_size, pill_cy)],
        fill=d['pill_color']
    )
    text_start_x = star_cx + diamond_size + diamond_gap
    draw.text(
        (text_start_x, pill_cy), pill_label,
        fill=d['pill_color'], font=fonts['pill'], anchor='lm'
    )
    text_y += ph + gap_pill_stat

    # Stat percentage
    if stat_percentage and stat_percentage > 0:
        stat_cbg = _card_bg_at_y(d, text_y - card_y, card_h)
        stat_color = _blend(stat_cbg, (255, 255, 255), 0.4)
        draw.text(
            (cx, text_y), f'Posiada {stat_percentage}% użytkowników',
            fill=stat_color, font=fonts['stat'], anchor='mt'
        )
        sb = draw.textbbox((0, 0), f'Posiada {stat_percentage}% użytkowników', font=fonts['stat'])
        text_y += (sb[3] - sb[1]) + gap_stat_date

    # Unlock date
    if unlocked_at:
        date_cbg = _card_bg_at_y(d, text_y - card_y, card_h)
        date_color = _blend(date_cbg, (255, 255, 255), 0.35)
        date_str = unlocked_at.strftime('%d.%m.%Y')
        draw.text(
            (cx, text_y), f'Zdobyte: {date_str}',
            fill=date_color, font=fonts['date'], anchor='mt'
        )

    # Footer
    footer_y = card_y + card_h - 40
    footer_cbg = _card_bg_at_y(d, card_h - 40, card_h)
    footer_color = _blend(footer_cbg, (255, 255, 255), 0.5)
    draw.text(
        (cx, footer_y), 'thunderorders.cloud',
        fill=footer_color, font=fonts['footer'], anchor='mb'
    )

    # --- Output as bytes ---
    buf = io.BytesIO()
    img.save(buf, 'PNG', optimize=True)
    buf.seek(0)
    return buf


def invalidate_share_cache():
    """No longer needed — images are generated on demand."""
    pass
