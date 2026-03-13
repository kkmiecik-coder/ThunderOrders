import os
from PIL import Image, ImageDraw, ImageFont
from flask import url_for, current_app

FORMATS = {
    'story': (1080, 1920),   # 9:16
    'post': (1080, 1080),    # 1:1
    'banner': (1920, 1080),  # 16:9
}

RARITY_COLORS = {
    'common': (176, 176, 176),
    'rare': (96, 176, 255),
    'epic': (192, 128, 255),
    'legendary': (255, 204, 68),
}

RARITY_LABELS = {
    'common': 'Pospolite',
    'rare': 'Rzadkie',
    'epic': 'Epickie',
    'legendary': 'Legendarne',
}


def generate_share_image(user, achievement, fmt='post'):
    """
    Generate share image and return URL.
    Caches in static/cache/achievements/.
    """
    cache_dir = os.path.join(current_app.static_folder, 'cache', 'achievements')
    os.makedirs(cache_dir, exist_ok=True)

    filename = f'{user.id}_{achievement.slug}_{fmt}.png'
    filepath = os.path.join(cache_dir, filename)

    # Check cache
    if os.path.exists(filepath):
        return f'/static/cache/achievements/{filename}'

    width, height = FORMATS.get(fmt, FORMATS['post'])
    rarity_color = RARITY_COLORS.get(achievement.rarity, RARITY_COLORS['common'])
    rarity_label = RARITY_LABELS.get(achievement.rarity, 'Pospolite')

    # Create dark background
    img = Image.new('RGB', (width, height), (26, 10, 46))
    draw = ImageDraw.Draw(img)

    # Draw radial gradient glow in center
    cx, cy = width // 2, height // 2 - 60
    glow_radius = min(width, height) // 2
    for i in range(glow_radius, 0, -3):
        ratio = i / glow_radius
        r = int(26 + (90 - 26) * (1 - ratio) * 0.4)
        g = int(10 + (24 - 10) * (1 - ratio) * 0.4)
        b = int(46 + (154 - 46) * (1 - ratio) * 0.4)
        alpha_factor = ratio * 0.6
        r = int(r * alpha_factor + 26 * (1 - alpha_factor))
        g = int(g * alpha_factor + 10 * (1 - alpha_factor))
        b = int(b * alpha_factor + 46 * (1 - alpha_factor))
        draw.ellipse(
            [cx - i, cy - i, cx + i, cy + i],
            fill=(r, g, b)
        )

    # Load fonts
    font_path = os.path.join(current_app.static_folder, 'fonts', 'Inter-Bold.ttf')
    try:
        font_title = ImageFont.truetype(font_path, 48)
        font_desc = ImageFont.truetype(font_path, 24)
        font_small = ImageFont.truetype(font_path, 20)
        font_logo = ImageFont.truetype(font_path, 18)
    except (OSError, IOError):
        font_title = ImageFont.load_default()
        font_desc = font_title
        font_small = font_title
        font_logo = font_title

    # Load badge icon — use @512 version for share images
    icon_filename = f'{achievement.slug}@512.png'
    icon_path = os.path.join(current_app.static_folder, 'uploads', 'achievements', icon_filename)
    icon_size = 180
    icon_y = cy - 120

    if icon_filename and os.path.exists(icon_path):
        try:
            icon = Image.open(icon_path).convert('RGBA')
            icon = icon.resize((icon_size, icon_size), Image.LANCZOS)

            # Draw circular border behind icon
            border_r = icon_size // 2 + 8
            draw.ellipse(
                [cx - border_r, icon_y - border_r + icon_size // 2,
                 cx + border_r, icon_y + border_r + icon_size // 2],
                outline=rarity_color, width=3
            )

            # Paste icon centered
            icon_pos = (cx - icon_size // 2, icon_y)
            img.paste(icon, icon_pos, icon)
        except Exception:
            pass

    # Text positioning
    name_y = icon_y + icon_size + 40

    # Logo at top
    draw.text((width // 2, 60), 'THUNDERORDERS', fill=(240, 147, 251), font=font_logo, anchor='mm')

    # Badge name
    draw.text((width // 2, name_y), achievement.name, fill='white', font=font_title, anchor='mm')

    # Description
    draw.text(
        (width // 2, name_y + 55),
        achievement.description,
        fill=(255, 255, 255, 180),
        font=font_desc,
        anchor='mm'
    )

    # Rarity label
    draw.text(
        (width // 2, name_y + 105),
        f'\u2726 {rarity_label}',
        fill=rarity_color,
        font=font_desc,
        anchor='mm'
    )

    # Stat percentage
    stat_text = ''
    if achievement.stat and achievement.stat.percentage:
        stat_text = f'Posiada {achievement.stat.percentage}% uzytkownikow'
    if stat_text:
        draw.text(
            (width // 2, name_y + 145),
            stat_text,
            fill=(255, 255, 255, 100),
            font=font_small,
            anchor='mm'
        )

    # Username
    username = user.first_name or user.email.split('@')[0]
    draw.text(
        (width // 2, name_y + 200),
        f'Zdobyte przez @{username}',
        fill=(180, 130, 220),
        font=font_small,
        anchor='mm'
    )

    # Footer
    draw.text(
        (width // 2, height - 50),
        'thunderorders.cloud',
        fill=(240, 147, 251, 120),
        font=font_logo,
        anchor='mm'
    )

    img.save(filepath, 'PNG', optimize=True)
    return f'/static/cache/achievements/{filename}'


def invalidate_share_cache():
    """Delete all cached share images. Called after stats recalculation."""
    cache_dir = os.path.join(current_app.static_folder, 'cache', 'achievements')
    if os.path.exists(cache_dir):
        for f in os.listdir(cache_dir):
            if f.endswith('.png'):
                try:
                    os.remove(os.path.join(cache_dir, f))
                except OSError:
                    pass
