import io
import os
import re
import qrcode
import qrcode.image.svg
from PIL import Image, ImageDraw


LOGO_SVG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'static', 'img', 'icons', 'logo-icon.svg')


def _get_logo_for_png(qr_size):
    """Laduje logo SVG i konwertuje na PNG przez cairosvg (~25% rozmiaru QR)."""
    if not os.path.exists(LOGO_SVG_PATH):
        return None

    logo_size = int(qr_size * 0.25)
    try:
        import cairosvg
        with open(LOGO_SVG_PATH, 'rb') as f:
            svg_data = f.read()
        png_data = cairosvg.svg2png(
            bytestring=svg_data,
            output_width=logo_size,
            output_height=logo_size,
        )
        return Image.open(io.BytesIO(png_data)).convert('RGBA')
    except Exception:
        return None


def _read_logo_svg_parts():
    """Czyta logo SVG i zwraca (defs, visual_content, vb_width, vb_height)."""
    if not os.path.exists(LOGO_SVG_PATH):
        return None, None, None, None

    with open(LOGO_SVG_PATH, 'r', encoding='utf-8') as f:
        svg_content = f.read()

    vb_match = re.search(r'viewBox="([^"]*)"', svg_content)
    if not vb_match:
        return None, None, None, None

    vb = vb_match.group(1).split()
    vb_width = float(vb[2])
    vb_height = float(vb[3])

    inner_match = re.search(r'<svg[^>]*>(.*)</svg>', svg_content, re.DOTALL)
    if not inner_match:
        return None, None, None, None

    inner = inner_match.group(1)

    defs_match = re.search(r'(<defs>.*?</defs>)', inner, re.DOTALL)
    defs = defs_match.group(1) if defs_match else ''
    visual = inner.replace(defs, '').strip() if defs else inner.strip()

    return defs, visual, vb_width, vb_height


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
    """Generuje QR kod jako SVG z przezroczystym tlem i osadzonym logo."""
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

    # Osadz logo bezposrednio w SVG (nie jako <image href>)
    defs, visual, logo_vb_w, logo_vb_h = _read_logo_svg_parts()
    if visual:
        viewbox_match = re.search(r'viewBox="([^"]*)"', svg_content)
        if viewbox_match:
            vb = viewbox_match.group(1).split()
            vb_width = float(vb[2])
            vb_height = float(vb[3])

            logo_target = vb_width * 0.25
            scale = min(logo_target / logo_vb_w, logo_target / logo_vb_h)
            scaled_w = logo_vb_w * scale
            scaled_h = logo_vb_h * scale

            logo_x = (vb_width - scaled_w) / 2
            logo_y = (vb_height - scaled_h) / 2

            circle_r = max(scaled_w, scaled_h) * 0.6
            circle_cx = vb_width / 2
            circle_cy = vb_height / 2

            logo_elements = f'''
    {defs}
    <circle cx="{circle_cx}" cy="{circle_cy}" r="{circle_r}" fill="white"/>
    <g transform="translate({logo_x}, {logo_y}) scale({scale})">
        {visual}
    </g>
'''
            svg_content = svg_content.replace('</svg>', f'{logo_elements}</svg>')

    return svg_content
