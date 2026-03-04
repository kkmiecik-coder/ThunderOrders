"""
Generate PWA icons from logo.png (1024x1024).
Run once: python scripts/generate_pwa_icons.py
"""

import os
from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGO_PATH = os.path.join(BASE_DIR, 'logo.png')
OUTPUT_DIR = os.path.join(BASE_DIR, 'static', 'img', 'pwa')

STANDARD_SIZES = [72, 96, 128, 144, 152, 192, 384, 512]
MASKABLE_SIZES = [192, 512]
BADGE_SIZE = 96


def generate_standard_icons(img):
    for size in STANDARD_SIZES:
        resized = img.resize((size, size), Image.LANCZOS)
        resized.save(os.path.join(OUTPUT_DIR, f'icon-{size}x{size}.png'), 'PNG')
        print(f'  icon-{size}x{size}.png')


def generate_maskable_icons(img):
    for size in MASKABLE_SIZES:
        # 10% padding safe zone
        padding = int(size * 0.1)
        inner_size = size - 2 * padding
        resized = img.resize((inner_size, inner_size), Image.LANCZOS)
        canvas = Image.new('RGBA', (size, size), (36, 0, 70, 255))  # #240046
        canvas.paste(resized, (padding, padding), resized)
        canvas.save(os.path.join(OUTPUT_DIR, f'maskable-{size}x{size}.png'), 'PNG')
        print(f'  maskable-{size}x{size}.png')


def generate_badge_icon(img):
    size = BADGE_SIZE
    resized = img.resize((size, size), Image.LANCZOS).convert('RGBA')
    # Create white silhouette on transparent background
    pixels = resized.load()
    for y in range(size):
        for x in range(size):
            r, g, b, a = pixels[x, y]
            if a > 30:
                pixels[x, y] = (255, 255, 255, a)
            else:
                pixels[x, y] = (0, 0, 0, 0)
    resized.save(os.path.join(OUTPUT_DIR, f'badge-{size}x{size}.png'), 'PNG')
    print(f'  badge-{size}x{size}.png')


if __name__ == '__main__':
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    img = Image.open(LOGO_PATH).convert('RGBA')
    print(f'Source: {LOGO_PATH} ({img.size[0]}x{img.size[1]})')
    print(f'Output: {OUTPUT_DIR}\n')

    print('Standard icons:')
    generate_standard_icons(img)

    print('\nMaskable icons:')
    generate_maskable_icons(img)

    print('\nBadge icon:')
    generate_badge_icon(img)

    print('\nDone!')
