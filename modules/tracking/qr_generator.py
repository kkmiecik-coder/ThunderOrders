import io
import os
import re
import qrcode
import qrcode.image.svg
from PIL import Image, ImageDraw


LOGO_SVG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'static', 'img', 'icons', 'logo-icon.svg')
LOGO_PNG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'static', 'img', 'icons', 'logo-icon.png')


def _get_logo_for_png(qr_size):
    """Laduje i skaluje logo do ~25% rozmiaru QR kodu (PNG)"""
    logo_size = int(qr_size * 0.25)

    logo_path = LOGO_PNG_PATH
    if not os.path.exists(logo_path):
        try:
            import cairosvg
            svg_path = LOGO_SVG_PATH
            if os.path.exists(svg_path):
                png_data = cairosvg.svg2png(url=svg_path, output_width=logo_size, output_height=logo_size)
                return Image.open(io.BytesIO(png_data)).convert('RGBA')
        except ImportError:
            pass
        return None

    logo = Image.open(logo_path).convert('RGBA')
    logo = logo.resize((logo_size, logo_size), Image.LANCZOS)
    return logo


def generate_qr_png(url, size=1024):
    """Generuje QR kod jako PNG z przezroczystym tlem i logo."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=20,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)

    img = qr.make_image(fill_color='black', back_color='white').convert('RGBA')

    # Zamien biale piksele na przezroczyste
    data = img.getdata()
    new_data = []
    for item in data:
        if item[0] > 200 and item[1] > 200 and item[2] > 200:
            new_data.append((255, 255, 255, 0))
        else:
            new_data.append(item)
    img.putdata(new_data)

    img = img.resize((size, size), Image.NEAREST)

    # Dodaj logo na srodku
    logo = _get_logo_for_png(size)
    if logo:
        logo_pos = ((size - logo.size[0]) // 2, (size - logo.size[1]) // 2)
        circle_size = int(logo.size[0] * 1.15)
        circle_img = Image.new('RGBA', (circle_size, circle_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(circle_img)
        draw.ellipse([0, 0, circle_size - 1, circle_size - 1], fill=(255, 255, 255, 255))
        circle_pos = ((size - circle_size) // 2, (size - circle_size) // 2)
        img.paste(circle_img, circle_pos, circle_img)
        img.paste(logo, logo_pos, logo)

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer.getvalue()


def generate_qr_svg(url):
    """Generuje QR kod jako SVG z przezroczystym tlem i logo."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)

    factory = qrcode.image.svg.SvgPathImage
    img = qr.make_image(image_factory=factory)

    buffer = io.BytesIO()
    img.save(buffer)
    svg_content = buffer.getvalue().decode('utf-8')

    # Usun biale tlo
    svg_content = svg_content.replace('fill="#ffffff"', 'fill="none"')
    svg_content = svg_content.replace("fill='#ffffff'", "fill='none'")

    # Dodaj logo na srodku SVG
    if os.path.exists(LOGO_SVG_PATH):
        viewbox_match = re.search(r'viewBox="([^"]*)"', svg_content)
        if viewbox_match:
            vb = viewbox_match.group(1).split()
            vb_width = float(vb[2])
            vb_height = float(vb[3])

            logo_size = vb_width * 0.25
            logo_x = (vb_width - logo_size) / 2
            logo_y = (vb_height - logo_size) / 2

            circle_r = logo_size * 0.6
            circle_cx = vb_width / 2
            circle_cy = vb_height / 2

            logo_elements = f'''
    <circle cx="{circle_cx}" cy="{circle_cy}" r="{circle_r}" fill="white"/>
    <image href="/static/img/icons/logo-icon.svg" x="{logo_x}" y="{logo_y}" width="{logo_size}" height="{logo_size}"/>
'''
            svg_content = svg_content.replace('</svg>', f'{logo_elements}</svg>')

    return svg_content
