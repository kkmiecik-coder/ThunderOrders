# QR Code Tracking System — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an internal QR code tracking system that lets admins create QR campaigns, generate branded QR codes (with ThunderOrders logo), and view detailed visit analytics in the admin panel.

**Architecture:** New Flask blueprint `tracking_bp` registered without url_prefix. Public endpoint `/qr/<slug>` handles redirect + visit recording. Admin routes under `/admin/qr-tracking/` for CRUD and statistics. Chart.js for analytics dashboard. GeoLite2 for IP geolocation.

**Tech Stack:** Flask, SQLAlchemy, Flask-Migrate, Chart.js v4.4.7, qrcode[pil], user-agents, geoip2, openpyxl (already installed)

**Spec:** `docs/superpowers/specs/2026-03-12-qr-tracking-design.md`

---

## File Structure

```
modules/tracking/
├── __init__.py          # Blueprint: tracking_bp
├── models.py            # QRCampaign, QRVisit
├── routes.py            # Admin routes (CRUD, stats API, export, QR download)
├── qr_routes.py         # Public endpoint /qr/<slug>
├── qr_generator.py      # QR code generation (SVG/PNG with logo)
├── utils.py             # UA parsing, fingerprint, geolocation helpers
└── export.py            # XLSX export

templates/admin/tracking/
├── index.html           # Campaign list
├── detail.html          # Campaign statistics (charts + visit table)
├── form.html            # Create/edit campaign form
└── qr_code.html         # QR code preview + download

static/css/pages/admin/
└── qr-tracking.css      # Styles (light + dark mode)

static/js/pages/admin/
└── qr-tracking.js       # Charts, AJAX, filtering, dark mode
```

**Files to modify:**
- `app.py` — register `tracking_bp`
- `config.py` — add `GEOIP_DB_PATH`
- `requirements.txt` — add `user-agents`, `geoip2`
- `templates/components/sidebar_admin.html` — create "Komunikacja" accordion
- `.gitignore` — add `data/*.mmdb`

---

## Chunk 1: Foundation — Models, Blueprint, Dependencies

### Task 1: Install dependencies and update config

**Files:**
- Modify: `requirements.txt`
- Modify: `config.py`
- Modify: `.gitignore`

- [ ] **Step 1: Install new Python packages**

Run:
```bash
pip install user-agents geoip2
```

- [ ] **Step 2: Update requirements.txt**

Run:
```bash
pip freeze > requirements.txt
```

Verify `user-agents` and `geoip2` appear in the file.

- [ ] **Step 3: Add GEOIP_DB_PATH to config.py**

In `config.py`, inside the `Config` class, add:

```python
GEOIP_DB_PATH = os.environ.get('GEOIP_DB_PATH') or os.path.join(basedir, 'data', 'GeoLite2-City.mmdb')
```

- [ ] **Step 4: Add data/*.mmdb to .gitignore**

Append to `.gitignore`:

```
# GeoIP database
data/*.mmdb
```

- [ ] **Step 5: Create data directory if missing**

Run:
```bash
mkdir -p data
```

- [ ] **Step 6: Commit**

```bash
git add requirements.txt config.py .gitignore
git commit -m "chore: add user-agents, geoip2 dependencies and GEOIP_DB_PATH config"
```

---

### Task 2: Create models (QRCampaign + QRVisit)

**Files:**
- Create: `modules/tracking/__init__.py`
- Create: `modules/tracking/models.py`

- [ ] **Step 1: Create blueprint __init__.py**

Create `modules/tracking/__init__.py`:

```python
"""
Tracking Module
System sledzenia wizyt z kodow QR
"""

from flask import Blueprint

tracking_bp = Blueprint('tracking', __name__)

from . import routes
from . import qr_routes
```

- [ ] **Step 2: Create models.py with QRCampaign and QRVisit**

Create `modules/tracking/models.py`:

```python
from extensions import db
from datetime import datetime, timezone, timedelta


def get_local_now():
    """Zwraca aktualny czas polski (Europe/Warsaw)"""
    utc_now = datetime.now(timezone.utc)
    year = utc_now.year
    # Ostatnia niedziela marca (przejscie na czas letni)
    march_last_sunday = 31 - ((datetime(year, 3, 31).weekday() + 1) % 7)
    dst_start = datetime(year, 3, march_last_sunday, 1, tzinfo=timezone.utc)
    # Ostatnia niedziela pazdziernika (przejscie na czas zimowy)
    october_last_sunday = 31 - ((datetime(year, 10, 31).weekday() + 1) % 7)
    dst_end = datetime(year, 10, october_last_sunday, 1, tzinfo=timezone.utc)

    if dst_start <= utc_now < dst_end:
        offset = timedelta(hours=2)  # CEST
    else:
        offset = timedelta(hours=1)  # CET

    return (utc_now + offset).replace(tzinfo=None)


class QRCampaign(db.Model):
    __tablename__ = 'qr_campaigns'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False, index=True)
    target_url = db.Column(db.String(500), nullable=False, default='https://thunderorders.cloud')
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=get_local_now)
    updated_at = db.Column(db.DateTime, default=get_local_now, onupdate=get_local_now)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    creator = db.relationship('User', backref='qr_campaigns', foreign_keys=[created_by])
    visits = db.relationship(
        'QRVisit',
        back_populates='campaign',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f'<QRCampaign {self.name}>'

    @property
    def total_visits(self):
        return self.visits.count()

    @property
    def unique_visits(self):
        return self.visits.filter_by(is_unique=True).count()

    @property
    def last_visit(self):
        visit = self.visits.order_by(QRVisit.visited_at.desc()).first()
        return visit.visited_at if visit else None

    @property
    def full_url(self):
        return f'/qr/{self.slug}'


class QRVisit(db.Model):
    __tablename__ = 'qr_visits'

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('qr_campaigns.id'), nullable=False, index=True)
    visitor_id = db.Column(db.String(64), nullable=False)
    is_unique = db.Column(db.Boolean, nullable=False, default=True)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    device_type = db.Column(db.String(20))
    browser = db.Column(db.String(50))
    os = db.Column(db.String(50))
    country = db.Column(db.String(100))
    city = db.Column(db.String(100))
    referer = db.Column(db.String(500))
    visited_at = db.Column(db.DateTime, default=get_local_now, nullable=False, index=True)

    campaign = db.relationship('QRCampaign', back_populates='visits')

    __table_args__ = (
        db.Index('ix_qr_visits_visitor_campaign', 'visitor_id', 'campaign_id'),
    )

    def __repr__(self):
        return f'<QRVisit campaign={self.campaign_id} visitor={self.visitor_id[:8]}>'
```

- [ ] **Step 3: Create placeholder route files to avoid import errors**

Create `modules/tracking/routes.py`:

```python
from . import tracking_bp
```

Create `modules/tracking/qr_routes.py`:

```python
from . import tracking_bp
```

- [ ] **Step 4: Register blueprint in app.py**

In `app.py`, in the `register_blueprints()` function, add after the last blueprint registration:

```python
from modules.tracking import tracking_bp
app.register_blueprint(tracking_bp)
```

- [ ] **Step 5: Generate and apply migration**

Run:
```bash
flask db migrate -m "Add QR tracking tables (qr_campaigns, qr_visits)"
flask db upgrade
```

Verify: Check `migrations/versions/` for the new migration file. Confirm both tables exist in the database.

- [ ] **Step 6: Commit**

```bash
git add modules/tracking/ migrations/versions/ app.py
git commit -m "feat: add QR tracking models and blueprint registration"
```

---

## Chunk 2: Public QR Tracking Endpoint + Utilities

### Task 3: Create utility helpers (UA parsing, fingerprint, geolocation)

**Files:**
- Create: `modules/tracking/utils.py`

- [ ] **Step 1: Create utils.py with all helper functions**

Create `modules/tracking/utils.py`:

```python
import hashlib
import uuid
import os
from user_agents import parse as parse_ua
from flask import current_app


def generate_visitor_id():
    """Generuje losowy UUID v4 jako visitor_id dla cookie"""
    return uuid.uuid4().hex


def generate_fingerprint(user_agent, ip_address, accept_language):
    """Generuje SHA-256 fingerprint jako fallback gdy brak cookie"""
    raw = f'{user_agent}|{ip_address}|{accept_language}'
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def parse_user_agent(ua_string):
    """Parsuje User-Agent string i zwraca dict z device_type, browser, os"""
    if not ua_string:
        return {'device_type': 'unknown', 'browser': 'unknown', 'os': 'unknown'}

    ua = parse_ua(ua_string)

    if ua.is_mobile:
        device_type = 'mobile'
    elif ua.is_tablet:
        device_type = 'tablet'
    else:
        device_type = 'desktop'

    browser = ua.browser.family or 'unknown'
    os_name = ua.os.family or 'unknown'

    return {
        'device_type': device_type,
        'browser': browser,
        'os': os_name,
    }


def get_geolocation(ip_address):
    """Geolokalizacja IP z bazy GeoLite2. Zwraca dict z country, city."""
    result = {'country': None, 'city': None}

    if not ip_address or ip_address in ('127.0.0.1', '::1'):
        return result

    db_path = current_app.config.get('GEOIP_DB_PATH')
    if not db_path or not os.path.exists(db_path):
        return result

    try:
        import geoip2.database
        with geoip2.database.Reader(db_path) as reader:
            response = reader.city(ip_address)
            result['country'] = response.country.name
            result['city'] = response.city.name
    except Exception:
        pass

    return result


def get_client_ip(request):
    """Pobiera prawdziwy IP klienta (uwzglednia proxy/nginx)"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers['X-Forwarded-For'].split(',')[0].strip()
    if request.headers.get('X-Real-Ip'):
        return request.headers['X-Real-Ip']
    return request.remote_addr
```

- [ ] **Step 2: Commit**

```bash
git add modules/tracking/utils.py
git commit -m "feat: add QR tracking utility helpers (UA parsing, fingerprint, geolocation)"
```

---

### Task 4: Implement public QR tracking endpoint

**Files:**
- Modify: `modules/tracking/qr_routes.py`

- [ ] **Step 1: Implement /qr/<slug> endpoint**

Replace contents of `modules/tracking/qr_routes.py`:

```python
from flask import redirect, abort, request, make_response
from . import tracking_bp
from .models import QRCampaign, QRVisit, db, get_local_now
from .utils import (
    generate_visitor_id,
    generate_fingerprint,
    parse_user_agent,
    get_geolocation,
    get_client_ip,
)

COOKIE_NAME = 'thunderorders_qr_visitor'
COOKIE_MAX_AGE = 365 * 24 * 60 * 60  # 1 year


@tracking_bp.route('/qr/<slug>')
def qr_redirect(slug):
    """Publiczny endpoint QR - rejestruje wizyte i przekierowuje"""
    campaign = QRCampaign.query.filter_by(slug=slug, is_deleted=False).first()
    if not campaign:
        abort(404)

    # Redirect bez trackingu jesli kampania nieaktywna
    if not campaign.is_active:
        return redirect(campaign.target_url, code=302)

    # Identyfikacja odwiedzajacego
    visitor_id = request.cookies.get(COOKIE_NAME)
    set_cookie = False

    if not visitor_id:
        # Fallback: fingerprint
        ip = get_client_ip(request)
        ua = request.headers.get('User-Agent', '')
        lang = request.headers.get('Accept-Language', '')
        visitor_id = generate_fingerprint(ua, ip, lang)
        set_cookie = True
        cookie_value = generate_visitor_id()
    else:
        cookie_value = visitor_id
        ip = get_client_ip(request)

    # Sprawdz unikalnosc
    is_unique = not QRVisit.query.filter_by(
        campaign_id=campaign.id,
        visitor_id=visitor_id
    ).first()

    # Parsuj User-Agent
    ua_string = request.headers.get('User-Agent', '')
    ua_info = parse_user_agent(ua_string)

    # Geolokalizacja
    client_ip = get_client_ip(request)
    geo = get_geolocation(client_ip)

    # Zapisz wizyte
    visit = QRVisit(
        campaign_id=campaign.id,
        visitor_id=visitor_id,
        is_unique=is_unique,
        ip_address=client_ip,
        user_agent=ua_string[:500] if ua_string else None,
        device_type=ua_info['device_type'],
        browser=ua_info['browser'],
        os=ua_info['os'],
        country=geo['country'],
        city=geo['city'],
        referer=request.headers.get('Referer', '')[:500] or None,
    )
    db.session.add(visit)
    db.session.commit()

    # Redirect z ustawieniem cookie
    response = make_response(redirect(campaign.target_url, code=302))
    if set_cookie:
        response.set_cookie(
            COOKIE_NAME,
            cookie_value,
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            samesite='Lax',
            secure=True,
        )

    return response
```

- [ ] **Step 2: Test manually**

Start the dev server and test:
1. Create a test campaign directly in the database (or wait for Task 5 admin UI)
2. Visit `http://localhost:5001/qr/<test-slug>`
3. Verify: redirect happens, cookie is set, QRVisit record exists in DB

- [ ] **Step 3: Commit**

```bash
git add modules/tracking/qr_routes.py
git commit -m "feat: implement public QR redirect endpoint with visit tracking"
```

---

## Chunk 3: QR Code Generator

### Task 5: QR code generator with logo

**Files:**
- Create: `modules/tracking/qr_generator.py`

- [ ] **Step 1: Create qr_generator.py**

Create `modules/tracking/qr_generator.py`:

```python
import io
import os
import qrcode
import qrcode.image.svg
from PIL import Image
from flask import current_app


LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'static', 'img', 'icons', 'logo-icon.svg')
LOGO_PNG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'static', 'img', 'icons', 'logo-icon.png')


def _get_logo_for_png(qr_size):
    """Laduje i skaluje logo do ~25% rozmiaru QR kodu (PNG)"""
    logo_size = int(qr_size * 0.25)

    # Probuj PNG najpierw (lepsze do kompozycji)
    logo_path = LOGO_PNG_PATH
    if not os.path.exists(logo_path):
        # Fallback - sprobuj SVG przez cairosvg jesli dostepny
        try:
            import cairosvg
            svg_path = LOGO_PATH
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
    """Generuje QR kod jako PNG z przezroczystym tlem i logo.

    Args:
        url: URL do zakodowania w QR
        size: Rozmiar obrazu w pikselach (domyslnie 1024x1024)

    Returns:
        bytes: PNG image data
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=20,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)

    # Generuj z bialym tlem, potem zamien na przezroczyste
    img = qr.make_image(fill_color='black', back_color='white').convert('RGBA')

    # Zamien biale piksele na przezroczyste
    data = img.getdata()
    new_data = []
    for item in data:
        if item[0] > 200 and item[1] > 200 and item[2] > 200:
            new_data.append((255, 255, 255, 0))  # Przezroczyste
        else:
            new_data.append(item)
    img.putdata(new_data)

    # Skaluj do docelowego rozmiaru
    img = img.resize((size, size), Image.NEAREST)

    # Dodaj logo na srodku
    logo = _get_logo_for_png(size)
    if logo:
        logo_pos = ((size - logo.size[0]) // 2, (size - logo.size[1]) // 2)
        # Biale kolko pod logo (zeby QR nie przeszkadzal)
        circle_size = int(logo.size[0] * 1.15)
        circle_img = Image.new('RGBA', (circle_size, circle_size), (0, 0, 0, 0))
        from PIL import ImageDraw
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
    """Generuje QR kod jako SVG z przezroczystym tlem i logo.

    Args:
        url: URL do zakodowania w QR

    Returns:
        str: SVG markup
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)

    # Generuj SVG
    factory = qrcode.image.svg.SvgPathImage
    img = qr.make_image(image_factory=factory)

    buffer = io.BytesIO()
    img.save(buffer)
    svg_content = buffer.getvalue().decode('utf-8')

    # Usun biale tlo (zamien na przezroczyste)
    svg_content = svg_content.replace('fill="#ffffff"', 'fill="none"')
    svg_content = svg_content.replace("fill='#ffffff'", "fill='none'")

    # Dodaj logo na srodku SVG
    logo_svg_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        '..', '..', 'static', 'img', 'icons', 'logo-icon.svg'
    )

    if os.path.exists(logo_svg_path):
        # Pobierz wymiary SVG
        import re
        viewbox_match = re.search(r'viewBox="([^"]*)"', svg_content)
        if viewbox_match:
            vb = viewbox_match.group(1).split()
            vb_width = float(vb[2])
            vb_height = float(vb[3])

            # Logo zajmuje ~25% QR
            logo_size = vb_width * 0.25
            logo_x = (vb_width - logo_size) / 2
            logo_y = (vb_height - logo_size) / 2

            # Biale kolko pod logo
            circle_r = logo_size * 0.6
            circle_cx = vb_width / 2
            circle_cy = vb_height / 2

            logo_elements = f'''
    <circle cx="{circle_cx}" cy="{circle_cy}" r="{circle_r}" fill="white"/>
    <image href="/static/img/icons/logo-icon.svg" x="{logo_x}" y="{logo_y}" width="{logo_size}" height="{logo_size}"/>
'''
            # Wstaw przed zamknieciem </svg>
            svg_content = svg_content.replace('</svg>', f'{logo_elements}</svg>')

    return svg_content
```

- [ ] **Step 2: Create PNG version of logo (if not exists)**

Check if `static/img/icons/logo-icon.png` exists. If not, create it from the SVG:

```bash
# Jesli cairosvg jest zainstalowany:
python -c "
import cairosvg
cairosvg.svg2png(url='static/img/icons/logo-icon.svg', write_to='static/img/icons/logo-icon.png', output_width=512, output_height=512)
print('Logo PNG created')
"
```

If `cairosvg` is not available, create the PNG manually (e.g., open SVG in browser, screenshot, save as PNG). The PNG fallback is optional — SVG `<image>` element works for the SVG output regardless.

- [ ] **Step 3: Commit**

```bash
git add modules/tracking/qr_generator.py
git commit -m "feat: add QR code generator with transparent background and logo overlay"
```

---

## Chunk 4: Admin Routes — CRUD + QR Download

### Task 6: Admin routes — campaign list, create, edit, delete

**Files:**
- Modify: `modules/tracking/routes.py`

- [ ] **Step 1: Implement admin routes**

Replace contents of `modules/tracking/routes.py`:

```python
import re
from flask import (
    render_template, redirect, url_for, request,
    jsonify, flash, abort, send_file
)
from flask_login import login_required, current_user
from utils.decorators import role_required
from . import tracking_bp
from .models import QRCampaign, QRVisit, db, get_local_now
from .qr_generator import generate_qr_png, generate_qr_svg
import io


def slugify(text):
    """Konwertuje tekst na slug (lowercase, bez spacji, tylko a-z0-9-)"""
    text = text.lower().strip()
    # Zamien polskie znaki
    replacements = {
        'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n',
        'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z',
    }
    for pl, en in replacements.items():
        text = text.replace(pl, en)
    # Zamien spacje i inne znaki na myslniki
    text = re.sub(r'[^a-z0-9]+', '-', text)
    # Usun podwojne myslniki i myslniki na poczatku/koncu
    text = re.sub(r'-+', '-', text).strip('-')
    return text[:50]


# ==========================================
#  Lista kampanii
# ==========================================

@tracking_bp.route('/admin/qr-tracking')
@login_required
@role_required('admin', 'mod')
def qr_tracking_list():
    """Lista kampanii QR"""
    campaigns = QRCampaign.query.filter_by(is_deleted=False)\
        .order_by(QRCampaign.created_at.desc()).all()
    return render_template('admin/tracking/index.html', campaigns=campaigns)


# ==========================================
#  Tworzenie kampanii
# ==========================================

@tracking_bp.route('/admin/qr-tracking/new', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'mod')
def qr_tracking_create():
    """Tworzenie nowej kampanii QR"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        slug = request.form.get('slug', '').strip()
        target_url = request.form.get('target_url', '').strip()
        is_active = request.form.get('is_active') == 'on'

        # Walidacja
        if not name:
            flash('Nazwa kampanii jest wymagana.', 'error')
            return render_template('admin/tracking/form.html', campaign=None)

        if not slug:
            slug = slugify(name)

        # Walidacja sluga
        if len(slug) < 2:
            flash('Slug musi miec minimum 2 znaki.', 'error')
            return render_template('admin/tracking/form.html', campaign=None)

        if not re.match(r'^[a-z0-9-]+$', slug):
            flash('Slug moze zawierac tylko male litery, cyfry i myslniki.', 'error')
            return render_template('admin/tracking/form.html', campaign=None)

        # Sprawdz unikalnosc sluga
        existing = QRCampaign.query.filter_by(slug=slug).first()
        if existing:
            flash(f'Slug "{slug}" jest juz zajety.', 'error')
            return render_template('admin/tracking/form.html', campaign=None)

        if not target_url:
            target_url = 'https://thunderorders.cloud'

        campaign = QRCampaign(
            name=name,
            slug=slug,
            target_url=target_url,
            is_active=is_active,
            created_by=current_user.id,
        )
        db.session.add(campaign)
        db.session.commit()

        flash(f'Kampania "{name}" zostala utworzona.', 'success')
        return redirect(url_for('tracking.qr_tracking_detail', id=campaign.id))

    return render_template('admin/tracking/form.html', campaign=None)


# ==========================================
#  Edycja kampanii
# ==========================================

@tracking_bp.route('/admin/qr-tracking/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'mod')
def qr_tracking_edit(id):
    """Edycja kampanii QR"""
    campaign = QRCampaign.query.filter_by(id=id, is_deleted=False).first_or_404()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        slug = request.form.get('slug', '').strip()
        target_url = request.form.get('target_url', '').strip()
        is_active = request.form.get('is_active') == 'on'

        if not name:
            flash('Nazwa kampanii jest wymagana.', 'error')
            return render_template('admin/tracking/form.html', campaign=campaign)

        if not slug:
            slug = slugify(name)

        if len(slug) < 2:
            flash('Slug musi miec minimum 2 znaki.', 'error')
            return render_template('admin/tracking/form.html', campaign=campaign)

        if not re.match(r'^[a-z0-9-]+$', slug):
            flash('Slug moze zawierac tylko male litery, cyfry i myslniki.', 'error')
            return render_template('admin/tracking/form.html', campaign=campaign)

        # Sprawdz unikalnosc sluga (pomijajac biezaca kampanie)
        existing = QRCampaign.query.filter(
            QRCampaign.slug == slug,
            QRCampaign.id != campaign.id
        ).first()
        if existing:
            flash(f'Slug "{slug}" jest juz zajety.', 'error')
            return render_template('admin/tracking/form.html', campaign=campaign)

        if not target_url:
            target_url = 'https://thunderorders.cloud'

        campaign.name = name
        campaign.slug = slug
        campaign.target_url = target_url
        campaign.is_active = is_active
        db.session.commit()

        flash(f'Kampania "{name}" zostala zaktualizowana.', 'success')
        return redirect(url_for('tracking.qr_tracking_detail', id=campaign.id))

    return render_template('admin/tracking/form.html', campaign=campaign)


# ==========================================
#  Soft-delete kampanii
# ==========================================

@tracking_bp.route('/admin/qr-tracking/<int:id>/delete', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def qr_tracking_delete(id):
    """Soft-delete kampanii QR"""
    campaign = QRCampaign.query.filter_by(id=id, is_deleted=False).first_or_404()
    campaign.is_deleted = True
    db.session.commit()
    flash(f'Kampania "{campaign.name}" zostala usunieta.', 'success')
    return redirect(url_for('tracking.qr_tracking_list'))


# ==========================================
#  Toggle aktywnosci kampanii (AJAX)
# ==========================================

@tracking_bp.route('/admin/qr-tracking/<int:id>/toggle', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def qr_tracking_toggle(id):
    """Toggle aktywnosci kampanii (AJAX)"""
    campaign = QRCampaign.query.filter_by(id=id, is_deleted=False).first_or_404()
    campaign.is_active = not campaign.is_active
    db.session.commit()
    return jsonify({'success': True, 'is_active': campaign.is_active})


# ==========================================
#  Szczegoly kampanii (statystyki)
# ==========================================

@tracking_bp.route('/admin/qr-tracking/<int:id>')
@login_required
@role_required('admin', 'mod')
def qr_tracking_detail(id):
    """Szczegolowe statystyki kampanii"""
    campaign = QRCampaign.query.filter_by(id=id, is_deleted=False).first_or_404()
    return render_template('admin/tracking/detail.html', campaign=campaign)


# ==========================================
#  Podglad QR kodu
# ==========================================

@tracking_bp.route('/admin/qr-tracking/<int:id>/qr-code')
@login_required
@role_required('admin', 'mod')
def qr_tracking_qr_code(id):
    """Podglad kodu QR kampanii"""
    campaign = QRCampaign.query.filter_by(id=id, is_deleted=False).first_or_404()

    # Generuj SVG do podgladu inline
    full_url = f'https://thunderorders.cloud/qr/{campaign.slug}'
    svg_preview = generate_qr_svg(full_url)

    return render_template(
        'admin/tracking/qr_code.html',
        campaign=campaign,
        svg_preview=svg_preview,
        full_url=full_url,
    )


# ==========================================
#  Pobieranie QR kodu (SVG/PNG)
# ==========================================

@tracking_bp.route('/admin/qr-tracking/<int:id>/download/<format>')
@login_required
@role_required('admin', 'mod')
def qr_tracking_download(id, format):
    """Pobieranie kodu QR w formacie SVG lub PNG"""
    campaign = QRCampaign.query.filter_by(id=id, is_deleted=False).first_or_404()
    full_url = f'https://thunderorders.cloud/qr/{campaign.slug}'

    if format == 'svg':
        svg_data = generate_qr_svg(full_url)
        return send_file(
            io.BytesIO(svg_data.encode('utf-8')),
            mimetype='image/svg+xml',
            as_attachment=True,
            download_name=f'qr-{campaign.slug}.svg',
        )
    elif format == 'png':
        png_data = generate_qr_png(full_url)
        return send_file(
            io.BytesIO(png_data),
            mimetype='image/png',
            as_attachment=True,
            download_name=f'qr-{campaign.slug}.png',
        )
    else:
        abort(400)


# ==========================================
#  API statystyk (AJAX dla wykresow)
# ==========================================

@tracking_bp.route('/admin/qr-tracking/<int:id>/api/stats')
@login_required
@role_required('admin', 'mod')
def qr_tracking_api_stats(id):
    """JSON ze statystykami kampanii dla Chart.js"""
    campaign = QRCampaign.query.filter_by(id=id, is_deleted=False).first_or_404()

    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    granularity = request.args.get('granularity', 'daily')  # daily, weekly, monthly

    query = QRVisit.query.filter_by(campaign_id=campaign.id)

    if date_from:
        from datetime import datetime
        try:
            query = query.filter(QRVisit.visited_at >= datetime.strptime(date_from, '%Y-%m-%d'))
        except ValueError:
            pass

    if date_to:
        from datetime import datetime
        try:
            dt_to = datetime.strptime(date_to, '%Y-%m-%d')
            dt_to = dt_to.replace(hour=23, minute=59, second=59)
            query = query.filter(QRVisit.visited_at <= dt_to)
        except ValueError:
            pass

    visits = query.order_by(QRVisit.visited_at.asc()).all()

    # Agregacja po czasie
    from collections import defaultdict, Counter
    timeline = defaultdict(lambda: {'total': 0, 'unique': 0})
    devices = Counter()
    browsers = Counter()
    countries = Counter()

    for v in visits:
        if granularity == 'daily':
            key = v.visited_at.strftime('%Y-%m-%d')
        elif granularity == 'weekly':
            # Poczatek tygodnia (poniedzialek)
            weekday = v.visited_at.weekday()
            week_start = v.visited_at - __import__('datetime').timedelta(days=weekday)
            key = week_start.strftime('%Y-%m-%d')
        else:  # monthly
            key = v.visited_at.strftime('%Y-%m')

        timeline[key]['total'] += 1
        if v.is_unique:
            timeline[key]['unique'] += 1

        devices[v.device_type or 'unknown'] += 1
        browsers[v.browser or 'unknown'] += 1
        if v.country:
            countries[v.country] += 1

    # Sortuj timeline
    sorted_timeline = sorted(timeline.items())

    # Statystyki ogolne
    from datetime import datetime, timedelta
    now = get_local_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = today_start - timedelta(days=7)

    total_all = campaign.total_visits
    unique_all = campaign.unique_visits
    today_count = QRVisit.query.filter(
        QRVisit.campaign_id == campaign.id,
        QRVisit.visited_at >= today_start
    ).count()
    week_count = QRVisit.query.filter(
        QRVisit.campaign_id == campaign.id,
        QRVisit.visited_at >= week_ago
    ).count()

    return jsonify({
        'summary': {
            'total': total_all,
            'unique': unique_all,
            'today': today_count,
            'last_7_days': week_count,
        },
        'timeline': {
            'labels': [t[0] for t in sorted_timeline],
            'total': [t[1]['total'] for t in sorted_timeline],
            'unique': [t[1]['unique'] for t in sorted_timeline],
        },
        'devices': {
            'labels': [d[0] for d in devices.most_common(10)],
            'data': [d[1] for d in devices.most_common(10)],
        },
        'browsers': {
            'labels': [b[0] for b in browsers.most_common(10)],
            'data': [b[1] for b in browsers.most_common(10)],
        },
        'countries': {
            'labels': [c[0] for c in countries.most_common(10)],
            'data': [c[1] for c in countries.most_common(10)],
        },
    })
```

- [ ] **Step 2: Commit**

```bash
git add modules/tracking/routes.py
git commit -m "feat: add admin QR tracking routes (CRUD, stats API, QR download)"
```

---

### Task 7: XLSX export

**Files:**
- Create: `modules/tracking/export.py`
- Modify: `modules/tracking/routes.py` (add export route)

- [ ] **Step 1: Create export.py**

Create `modules/tracking/export.py`:

```python
import io
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side


def export_visits_xlsx(campaign, visits):
    """Generuje plik XLSX z wizytami kampanii.

    Args:
        campaign: QRCampaign object
        visits: list of QRVisit objects

    Returns:
        bytes: XLSX file data
    """
    wb = Workbook()
    ws = wb.active
    ws.title = 'Wizyty QR'

    # Style
    header_font = Font(bold=True, color='FFFFFF', size=11)
    header_fill = PatternFill(start_color='462C1A', end_color='462C1A', fill_type='solid')
    header_alignment = Alignment(horizontal='center', vertical='center')
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin'),
    )

    # Naglowek kampanii
    ws.merge_cells('A1:I1')
    ws['A1'] = f'Kampania: {campaign.name}'
    ws['A1'].font = Font(bold=True, size=14)

    ws.merge_cells('A2:I2')
    ws['A2'] = f'URL: https://thunderorders.cloud/qr/{campaign.slug}'

    ws.merge_cells('A3:I3')
    ws['A3'] = f'Eksport: {__import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M")}'

    # Naglowki kolumn
    headers = [
        'Data/Godzina', 'Typ urz.', 'Przegladarka', 'System',
        'Kraj', 'Miasto', 'IP', 'Unikalny', 'Referer'
    ]

    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=5, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = thin_border

    # Dane
    for row_idx, visit in enumerate(visits, 6):
        ws.cell(row=row_idx, column=1, value=visit.visited_at.strftime('%Y-%m-%d %H:%M:%S') if visit.visited_at else '')
        ws.cell(row=row_idx, column=2, value=visit.device_type or '')
        ws.cell(row=row_idx, column=3, value=visit.browser or '')
        ws.cell(row=row_idx, column=4, value=visit.os or '')
        ws.cell(row=row_idx, column=5, value=visit.country or '')
        ws.cell(row=row_idx, column=6, value=visit.city or '')
        ws.cell(row=row_idx, column=7, value=visit.ip_address or '')
        ws.cell(row=row_idx, column=8, value='Tak' if visit.is_unique else 'Nie')
        ws.cell(row=row_idx, column=9, value=visit.referer or '')

        for col in range(1, 10):
            ws.cell(row=row_idx, column=col).border = thin_border

    # Szerokosc kolumn
    column_widths = [20, 10, 15, 15, 15, 15, 18, 10, 30]
    for i, width in enumerate(column_widths, 1):
        ws.column_dimensions[chr(64 + i)].width = width

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()
```

- [ ] **Step 2: Add export route to routes.py**

Add at the end of `modules/tracking/routes.py`, before the last line:

```python
# ==========================================
#  Export XLSX
# ==========================================

@tracking_bp.route('/admin/qr-tracking/<int:id>/export')
@login_required
@role_required('admin', 'mod')
def qr_tracking_export(id):
    """Export wizyt do XLSX"""
    campaign = QRCampaign.query.filter_by(id=id, is_deleted=False).first_or_404()

    query = QRVisit.query.filter_by(campaign_id=campaign.id)

    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    if date_from:
        from datetime import datetime
        try:
            query = query.filter(QRVisit.visited_at >= datetime.strptime(date_from, '%Y-%m-%d'))
        except ValueError:
            pass

    if date_to:
        from datetime import datetime
        try:
            dt_to = datetime.strptime(date_to, '%Y-%m-%d')
            dt_to = dt_to.replace(hour=23, minute=59, second=59)
            query = query.filter(QRVisit.visited_at <= dt_to)
        except ValueError:
            pass

    visits = query.order_by(QRVisit.visited_at.desc()).all()

    from .export import export_visits_xlsx
    xlsx_data = export_visits_xlsx(campaign, visits)

    return send_file(
        io.BytesIO(xlsx_data),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'qr-visits-{campaign.slug}.xlsx',
    )
```

- [ ] **Step 3: Commit**

```bash
git add modules/tracking/export.py modules/tracking/routes.py
git commit -m "feat: add XLSX export for QR tracking visits"
```

---

## Chunk 5: Templates + CSS + JS

### Task 8: Admin templates

**Files:**
- Create: `templates/admin/tracking/index.html`
- Create: `templates/admin/tracking/form.html`
- Create: `templates/admin/tracking/detail.html`
- Create: `templates/admin/tracking/qr_code.html`

- [ ] **Step 1: Create campaign list template (index.html)**

Create `templates/admin/tracking/index.html`:

```html
{% extends "admin/base_admin.html" %}

{% block title %}QR Tracking{% endblock %}

{% block extra_css %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/admin/qr-tracking.css') }}">
{% endblock %}

{% block content %}
<div class="qr-tracking-page">
    <div class="page-header">
        <div class="header-left">
            <h1>QR Tracking</h1>
            <p class="header-subtitle">Zarzadzaj kampaniami QR i sledz statystyki</p>
        </div>
        <div class="header-right">
            <a href="{{ url_for('tracking.qr_tracking_create') }}" class="btn btn-primary">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M8 2a.5.5 0 01.5.5v5h5a.5.5 0 010 1h-5v5a.5.5 0 01-1 0v-5h-5a.5.5 0 010-1h5v-5A.5.5 0 018 2z"/>
                </svg>
                <span>Nowa kampania</span>
            </a>
        </div>
    </div>

    {% if campaigns %}
    <div class="table-container">
        <div class="table-responsive">
            <table class="data-table qr-table">
                <thead>
                    <tr>
                        <th>Nazwa</th>
                        <th>Slug</th>
                        <th>Status</th>
                        <th>Wizyty</th>
                        <th>Unikalne</th>
                        <th>Ostatnia wizyta</th>
                        <th>Akcje</th>
                    </tr>
                </thead>
                <tbody>
                    {% for c in campaigns %}
                    <tr>
                        <td class="campaign-name">{{ c.name }}</td>
                        <td>
                            <code class="slug-code">/qr/{{ c.slug }}</code>
                        </td>
                        <td>
                            <label class="toggle-switch" title="{% if c.is_active %}Aktywna{% else %}Nieaktywna{% endif %}">
                                <input type="checkbox" {% if c.is_active %}checked{% endif %}
                                       onchange="toggleCampaign({{ c.id }}, this)">
                                <span class="toggle-slider"></span>
                            </label>
                        </td>
                        <td class="text-center">{{ c.total_visits }}</td>
                        <td class="text-center">{{ c.unique_visits }}</td>
                        <td>
                            {% if c.last_visit %}
                                {{ c.last_visit.strftime('%d.%m.%Y %H:%M') }}
                            {% else %}
                                <span class="text-muted">Brak</span>
                            {% endif %}
                        </td>
                        <td class="actions-cell">
                            <a href="{{ url_for('tracking.qr_tracking_detail', id=c.id) }}" class="btn btn-sm btn-outline" title="Statystyki">
                                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M4 11H2v3h2v-3zm5-4H7v7h2V7zm5-5h-2v12h2V2z"/></svg>
                            </a>
                            <a href="{{ url_for('tracking.qr_tracking_qr_code', id=c.id) }}" class="btn btn-sm btn-outline" title="Kod QR">
                                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M0 2h2V0H0v2zm4 0h2V0H4v2zM0 6h2V4H0v2zm8-6v2h2V0H8zM4 4H2v2h2V4zm8 0h2V2h-2v2zm-4 2h2V4H8v2zM0 8h6V2H0v6zm2-4h2v2H2V4zm8 10h2v-2h-2v2zm-4 0h2v-2H6v2zm4-4h2V8h-2v2zm0-6v6h6V4h-6zm4 4h-2V6h2v2zm0 4h2v-2h-2v2zm-8 2h2v-2H6v2zm-6 0h6v-6H0v6zm2-4h2v2H2v-2z"/></svg>
                            </a>
                            <a href="{{ url_for('tracking.qr_tracking_edit', id=c.id) }}" class="btn btn-sm btn-outline" title="Edytuj">
                                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M12.146.146a.5.5 0 01.708 0l3 3a.5.5 0 010 .708l-10 10a.5.5 0 01-.168.11l-5 2a.5.5 0 01-.65-.65l2-5a.5.5 0 01.11-.168l10-10z"/></svg>
                            </a>
                            <button type="button" class="btn btn-sm btn-outline btn-danger" title="Usun" onclick="deleteCampaign({{ c.id }}, '{{ c.name }}')">
                                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M5.5 5.5A.5.5 0 016 6v6a.5.5 0 01-1 0V6a.5.5 0 01.5-.5zm2.5 0a.5.5 0 01.5.5v6a.5.5 0 01-1 0V6a.5.5 0 01.5-.5zm3 .5a.5.5 0 00-1 0v6a.5.5 0 001 0V6z"/><path fill-rule="evenodd" d="M14.5 3a1 1 0 01-1 1H13v9a2 2 0 01-2 2H5a2 2 0 01-2-2V4h-.5a1 1 0 01-1-1V2a1 1 0 011-1H5.5l1-1h3l1 1H13.5a1 1 0 011 1v1z"/></svg>
                            </button>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
    {% else %}
    <div class="empty-state">
        <svg width="64" height="64" viewBox="0 0 16 16" fill="currentColor" opacity="0.3">
            <path d="M0 2h2V0H0v2zm4 0h2V0H4v2zM0 6h2V4H0v2zm8-6v2h2V0H8zM4 4H2v2h2V4zm8 0h2V2h-2v2zm-4 2h2V4H8v2zM0 8h6V2H0v6zm2-4h2v2H2V4zm8 10h2v-2h-2v2zm-4 0h2v-2H6v2zm4-4h2V8h-2v2zm0-6v6h6V4h-6zm4 4h-2V6h2v2zm0 4h2v-2h-2v2zm-8 2h2v-2H6v2zm-6 0h6v-6H0v6zm2-4h2v2H2v-2z"/>
        </svg>
        <h3>Brak kampanii QR</h3>
        <p>Utworz pierwsza kampanie, aby zaczac sledzic skany kodow QR.</p>
        <a href="{{ url_for('tracking.qr_tracking_create') }}" class="btn btn-primary">Utworz kampanie</a>
    </div>
    {% endif %}
</div>

<!-- Delete confirmation form (hidden) -->
<form id="delete-form" method="POST" style="display: none;">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
</form>

{% endblock %}

{% block extra_js %}
<script src="{{ url_for('static', filename='js/pages/admin/qr-tracking.js') }}"></script>
{% endblock %}
```

- [ ] **Step 2: Create campaign form template (form.html)**

Create `templates/admin/tracking/form.html`:

```html
{% extends "admin/base_admin.html" %}

{% block title %}{% if campaign %}Edytuj kampanie{% else %}Nowa kampania{% endif %} — QR Tracking{% endblock %}

{% block extra_css %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/admin/qr-tracking.css') }}">
{% endblock %}

{% block content %}
<div class="qr-tracking-page">
    <div class="page-header">
        <div class="header-left">
            <a href="{{ url_for('tracking.qr_tracking_list') }}" class="btn btn-outline btn-back">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                    <path fill-rule="evenodd" d="M11.354 1.646a.5.5 0 010 .708L5.707 8l5.647 5.646a.5.5 0 01-.708.708l-6-6a.5.5 0 010-.708l6-6a.5.5 0 01.708 0z"/>
                </svg>
                Powrot
            </a>
            <h1>{% if campaign %}Edytuj kampanie{% else %}Nowa kampania QR{% endif %}</h1>
        </div>
    </div>

    <div class="form-card">
        <form method="POST" class="campaign-form">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

            <div class="form-group">
                <label for="name">Nazwa kampanii <span class="required">*</span></label>
                <input type="text" id="name" name="name" class="form-control"
                       value="{{ campaign.name if campaign else '' }}"
                       placeholder="np. Wizytowki marzec 2026" required
                       oninput="autoSlug(this.value)">
            </div>

            <div class="form-group">
                <label for="slug">Slug (identyfikator URL)</label>
                <div class="input-with-prefix">
                    <span class="input-prefix">thunderorders.cloud/qr/</span>
                    <input type="text" id="slug" name="slug" class="form-control"
                           value="{{ campaign.slug if campaign else '' }}"
                           placeholder="wizytowki-marzec-2026"
                           pattern="[a-z0-9\-]+" minlength="2" maxlength="50">
                </div>
                <small class="form-hint">Male litery, cyfry i myslniki. Min. 2 znaki.</small>
            </div>

            <div class="form-group">
                <label for="target_url">Docelowy URL</label>
                <input type="url" id="target_url" name="target_url" class="form-control"
                       value="{{ campaign.target_url if campaign else 'https://thunderorders.cloud' }}"
                       placeholder="https://thunderorders.cloud">
                <small class="form-hint">Gdzie zostanie przekierowany uzytkownik po zeskanowaniu QR.</small>
            </div>

            <div class="form-group form-check">
                <label class="checkbox-label">
                    <input type="checkbox" name="is_active" id="is_active"
                           {% if not campaign or campaign.is_active %}checked{% endif %}>
                    <span>Kampania aktywna</span>
                </label>
                <small class="form-hint">Nieaktywna kampania nadal przekierowuje, ale nie rejestruje wizyt.</small>
            </div>

            <div class="form-actions">
                <a href="{{ url_for('tracking.qr_tracking_list') }}" class="btn btn-outline">Anuluj</a>
                <button type="submit" class="btn btn-primary">
                    {% if campaign %}Zapisz zmiany{% else %}Utworz kampanie{% endif %}
                </button>
            </div>
        </form>
    </div>
</div>
{% endblock %}

{% block extra_js %}
<script src="{{ url_for('static', filename='js/pages/admin/qr-tracking.js') }}"></script>
{% endblock %}
```

- [ ] **Step 3: Create campaign detail/stats template (detail.html)**

Create `templates/admin/tracking/detail.html`:

```html
{% extends "admin/base_admin.html" %}

{% block title %}{{ campaign.name }} — QR Tracking{% endblock %}

{% block extra_css %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/admin/qr-tracking.css') }}">
{% endblock %}

{% block content %}
<div class="qr-tracking-page">
    <div class="page-header">
        <div class="header-left">
            <a href="{{ url_for('tracking.qr_tracking_list') }}" class="btn btn-outline btn-back">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                    <path fill-rule="evenodd" d="M11.354 1.646a.5.5 0 010 .708L5.707 8l5.647 5.646a.5.5 0 01-.708.708l-6-6a.5.5 0 010-.708l6-6a.5.5 0 01.708 0z"/>
                </svg>
                Powrot
            </a>
            <h1>{{ campaign.name }}</h1>
            <span class="status-badge {% if campaign.is_active %}badge-active{% else %}badge-inactive{% endif %}">
                {% if campaign.is_active %}Aktywna{% else %}Nieaktywna{% endif %}
            </span>
        </div>
        <div class="header-right">
            <a href="{{ url_for('tracking.qr_tracking_qr_code', id=campaign.id) }}" class="btn btn-outline">Kod QR</a>
            <a href="{{ url_for('tracking.qr_tracking_edit', id=campaign.id) }}" class="btn btn-outline">Edytuj</a>
            <a href="{{ url_for('tracking.qr_tracking_export', id=campaign.id) }}" class="btn btn-outline">Eksport XLSX</a>
        </div>
    </div>

    <!-- Summary Cards -->
    <div class="stats-row" id="stats-cards">
        <div class="stat-card">
            <span class="stat-value" id="stat-total">-</span>
            <span class="stat-label">Wszystkie skany</span>
        </div>
        <div class="stat-card">
            <span class="stat-value" id="stat-unique">-</span>
            <span class="stat-label">Unikalne wizyty</span>
        </div>
        <div class="stat-card">
            <span class="stat-value" id="stat-today">-</span>
            <span class="stat-label">Dzisiaj</span>
        </div>
        <div class="stat-card">
            <span class="stat-value" id="stat-week">-</span>
            <span class="stat-label">Ostatnie 7 dni</span>
        </div>
    </div>

    <!-- Filters -->
    <div class="filters-row">
        <div class="filter-group">
            <label>Od:</label>
            <input type="date" id="filter-date-from" class="form-control">
        </div>
        <div class="filter-group">
            <label>Do:</label>
            <input type="date" id="filter-date-to" class="form-control">
        </div>
        <div class="filter-group">
            <label>Granularnosc:</label>
            <select id="filter-granularity" class="form-control">
                <option value="daily">Dziennie</option>
                <option value="weekly">Tygodniowo</option>
                <option value="monthly">Miesiecznie</option>
            </select>
        </div>
        <button class="btn btn-primary btn-sm" onclick="loadStats()">Filtruj</button>
    </div>

    <!-- Charts -->
    <div class="charts-grid">
        <div class="chart-card chart-card-wide">
            <h3>Wizyty w czasie</h3>
            <canvas id="timeline-chart"></canvas>
        </div>
        <div class="chart-card">
            <h3>Urzadzenia</h3>
            <canvas id="devices-chart"></canvas>
        </div>
        <div class="chart-card">
            <h3>Przegladarki</h3>
            <canvas id="browsers-chart"></canvas>
        </div>
        <div class="chart-card chart-card-wide">
            <h3>Top 10 krajow</h3>
            <canvas id="countries-chart"></canvas>
        </div>
    </div>

    <!-- Recent Visits Table -->
    <div class="table-container">
        <h3>Ostatnie wizyty</h3>
        <div class="table-responsive">
            <table class="data-table visits-table">
                <thead>
                    <tr>
                        <th>Data/Godzina</th>
                        <th>Urzadzenie</th>
                        <th>Przegladarka</th>
                        <th class="hide-mobile">System</th>
                        <th>Kraj</th>
                        <th class="hide-mobile">Miasto</th>
                        <th>Unikalny</th>
                    </tr>
                </thead>
                <tbody id="visits-tbody">
                    <tr><td colspan="7" class="text-center text-muted">Ladowanie...</td></tr>
                </tbody>
            </table>
        </div>
    </div>
</div>

<!-- Campaign ID for JS -->
<input type="hidden" id="campaign-id" value="{{ campaign.id }}">
{% endblock %}

{% block extra_js %}
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
<script src="{{ url_for('static', filename='js/pages/admin/qr-tracking.js') }}"></script>
{% endblock %}
```

- [ ] **Step 4: Create QR code preview template (qr_code.html)**

Create `templates/admin/tracking/qr_code.html`:

```html
{% extends "admin/base_admin.html" %}

{% block title %}Kod QR — {{ campaign.name }}{% endblock %}

{% block extra_css %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/admin/qr-tracking.css') }}">
{% endblock %}

{% block content %}
<div class="qr-tracking-page">
    <div class="page-header">
        <div class="header-left">
            <a href="{{ url_for('tracking.qr_tracking_detail', id=campaign.id) }}" class="btn btn-outline btn-back">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                    <path fill-rule="evenodd" d="M11.354 1.646a.5.5 0 010 .708L5.707 8l5.647 5.646a.5.5 0 01-.708.708l-6-6a.5.5 0 010-.708l6-6a.5.5 0 01.708 0z"/>
                </svg>
                Powrot
            </a>
            <h1>Kod QR — {{ campaign.name }}</h1>
        </div>
    </div>

    <div class="qr-preview-card">
        <div class="qr-preview">
            {{ svg_preview|safe }}
        </div>

        <div class="qr-info">
            <p class="qr-url">
                <strong>URL:</strong>
                <code>{{ full_url }}</code>
            </p>
            <p class="qr-target">
                <strong>Przekierowanie na:</strong>
                <code>{{ campaign.target_url }}</code>
            </p>
        </div>

        <div class="qr-download-buttons">
            <a href="{{ url_for('tracking.qr_tracking_download', id=campaign.id, format='svg') }}"
               class="btn btn-primary">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M.5 9.9a.5.5 0 01.5.5v2.5a1 1 0 001 1h12a1 1 0 001-1v-2.5a.5.5 0 011 0v2.5a2 2 0 01-2 2H2a2 2 0 01-2-2v-2.5a.5.5 0 01.5-.5z"/>
                    <path d="M7.646 11.854a.5.5 0 00.708 0l3-3a.5.5 0 00-.708-.708L8.5 10.293V1.5a.5.5 0 00-1 0v8.793L5.354 8.146a.5.5 0 10-.708.708l3 3z"/>
                </svg>
                Pobierz SVG
            </a>
            <a href="{{ url_for('tracking.qr_tracking_download', id=campaign.id, format='png') }}"
               class="btn btn-primary">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M.5 9.9a.5.5 0 01.5.5v2.5a1 1 0 001 1h12a1 1 0 001-1v-2.5a.5.5 0 011 0v2.5a2 2 0 01-2 2H2a2 2 0 01-2-2v-2.5a.5.5 0 01.5-.5z"/>
                    <path d="M7.646 11.854a.5.5 0 00.708 0l3-3a.5.5 0 00-.708-.708L8.5 10.293V1.5a.5.5 0 00-1 0v8.793L5.354 8.146a.5.5 0 10-.708.708l3 3z"/>
                </svg>
                Pobierz PNG
            </a>
        </div>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 5: Commit**

```bash
git add templates/admin/tracking/
git commit -m "feat: add QR tracking admin templates (list, form, detail, QR preview)"
```

---

### Task 9: CSS styles (light + dark mode)

**Files:**
- Create: `static/css/pages/admin/qr-tracking.css`

- [ ] **Step 1: Create qr-tracking.css**

Create `static/css/pages/admin/qr-tracking.css` with full light + dark mode styles. This file should include styles for:

- `.qr-tracking-page` — page wrapper
- `.page-header` — flex header with title + buttons (responsive)
- `.stats-row` / `.stat-card` — summary cards grid (4 cols desktop, 2 cols mobile)
- `.filters-row` — date filters row (wrap on mobile)
- `.charts-grid` — chart cards grid (2 cols desktop, 1 col mobile)
- `.chart-card` / `.chart-card-wide` — chart containers
- `.qr-table` / `.visits-table` — table styles
- `.toggle-switch` / `.toggle-slider` — active/inactive toggle
- `.slug-code` — monospace slug display
- `.status-badge` / `.badge-active` / `.badge-inactive` — status pills
- `.form-card` / `.campaign-form` — form styling
- `.input-with-prefix` / `.input-prefix` — slug input with prefix label
- `.qr-preview-card` / `.qr-preview` / `.qr-download-buttons` — QR code page
- `.empty-state` — empty campaign list
- `.btn-back` — back button styling

**Reference files for patterns:**
- `static/css/pages/admin/feedback-list.css` — page layout, table styles, buttons
- `static/css/pages/admin/statistics.css` — chart card layout, stat cards
- `static/css/core/variables.css` — color variables

**Key styles to implement:**

```css
/* === LIGHT MODE === */

.qr-tracking-page { padding: 20px; }

.stats-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 24px;
}

.stat-card {
    background: #fff;
    border: 1px solid #e0e0e0;
    border-radius: 12px;
    padding: 20px;
    text-align: center;
}

.stat-value { font-size: 2rem; font-weight: 700; display: block; }
.stat-label { font-size: 0.85rem; color: #666; }

.charts-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 16px;
    margin-bottom: 24px;
}

.chart-card {
    background: #fff;
    border: 1px solid #e0e0e0;
    border-radius: 12px;
    padding: 20px;
}

.chart-card-wide { grid-column: 1 / -1; }

.filters-row {
    display: flex;
    gap: 12px;
    align-items: end;
    margin-bottom: 24px;
    flex-wrap: wrap;
}

.toggle-switch { position: relative; display: inline-block; width: 44px; height: 24px; }
.toggle-switch input { opacity: 0; width: 0; height: 0; }
.toggle-slider {
    position: absolute; inset: 0; background: #ccc;
    border-radius: 24px; cursor: pointer; transition: 0.3s;
}
.toggle-slider::before {
    content: ''; position: absolute; height: 18px; width: 18px;
    left: 3px; bottom: 3px; background: white;
    border-radius: 50%; transition: 0.3s;
}
.toggle-switch input:checked + .toggle-slider { background: #8338EC; }
.toggle-switch input:checked + .toggle-slider::before { transform: translateX(20px); }

.slug-code {
    background: #f5f5f5; padding: 2px 8px;
    border-radius: 4px; font-size: 0.85rem;
}

.status-badge {
    padding: 4px 12px; border-radius: 20px;
    font-size: 0.8rem; font-weight: 600;
}
.badge-active { background: #d4edda; color: #155724; }
.badge-inactive { background: #f8d7da; color: #721c24; }
.badge-unique { background: #d4edda; color: #155724; padding: 2px 8px; border-radius: 10px; font-size: 0.8rem; }

.form-card {
    background: #fff; border: 1px solid #e0e0e0;
    border-radius: 12px; padding: 24px; max-width: 600px;
}

.input-with-prefix { display: flex; align-items: center; }
.input-prefix {
    background: #f5f5f5; border: 1px solid #e0e0e0;
    border-right: none; padding: 8px 12px;
    border-radius: 8px 0 0 8px; font-size: 0.85rem; color: #666;
    white-space: nowrap;
}
.input-with-prefix .form-control { border-radius: 0 8px 8px 0; }

.qr-preview-card {
    background: #fff; border: 1px solid #e0e0e0;
    border-radius: 12px; padding: 32px; text-align: center;
    max-width: 600px;
}
.qr-preview svg { max-width: 300px; height: auto; margin-bottom: 24px; }
.qr-download-buttons { display: flex; gap: 12px; justify-content: center; margin-top: 24px; }

.empty-state { text-align: center; padding: 60px 20px; }
.empty-state h3 { margin: 16px 0 8px; }
.empty-state p { color: #666; margin-bottom: 24px; }

.hide-mobile { /* visible by default */ }

/* === DARK MODE === */

[data-theme="dark"] .stat-card,
[data-theme="dark"] .chart-card,
[data-theme="dark"] .form-card,
[data-theme="dark"] .qr-preview-card {
    background: rgba(255, 255, 255, 0.05);
    border-color: rgba(240, 147, 251, 0.15);
    backdrop-filter: blur(10px);
}

[data-theme="dark"] .stat-value { color: #fff; }
[data-theme="dark"] .stat-label { color: rgba(255, 255, 255, 0.6); }

[data-theme="dark"] .slug-code {
    background: rgba(255, 255, 255, 0.1);
    color: #f093fb;
}

[data-theme="dark"] .badge-active { background: rgba(16, 185, 129, 0.2); color: #6bcb77; }
[data-theme="dark"] .badge-inactive { background: rgba(239, 68, 68, 0.2); color: #ff6b6b; }
[data-theme="dark"] .badge-unique { background: rgba(16, 185, 129, 0.2); color: #6bcb77; }

[data-theme="dark"] .toggle-switch input:checked + .toggle-slider { background: #f093fb; }

[data-theme="dark"] .input-prefix {
    background: rgba(255, 255, 255, 0.05);
    border-color: rgba(240, 147, 251, 0.15);
    color: rgba(255, 255, 255, 0.6);
}

[data-theme="dark"] .empty-state p { color: rgba(255, 255, 255, 0.6); }

/* === RESPONSIVE === */

@media (max-width: 768px) {
    .stats-row { grid-template-columns: repeat(2, 1fr); }
    .charts-grid { grid-template-columns: 1fr; }
    .filters-row { flex-direction: column; }
    .qr-download-buttons { flex-direction: column; }
    .qr-download-buttons .btn { width: 100%; }
    .hide-mobile { display: none; }
    .header-right { flex-wrap: wrap; }
    .header-right .btn { width: 100%; }
    .page-header { flex-direction: column; gap: 12px; }
}
```

Extend this with any additional styles needed, following existing patterns in the project.

- [ ] **Step 2: Commit**

```bash
git add static/css/pages/admin/qr-tracking.css
git commit -m "feat: add QR tracking CSS styles with light and dark mode"
```

---

### Task 10: JavaScript (Charts, AJAX, interactions)

**Files:**
- Create: `static/js/pages/admin/qr-tracking.js`

- [ ] **Step 1: Create qr-tracking.js**

Create `static/js/pages/admin/qr-tracking.js` with the following functionality:

```javascript
/**
 * QR Tracking - Admin Dashboard
 * Chart.js charts, AJAX stats loading, campaign interactions
 */

document.addEventListener('DOMContentLoaded', function() {
    // Detail page - load charts
    var campaignId = document.getElementById('campaign-id');
    if (campaignId) {
        loadStats();
    }
});


// ==========================================
//  Auto-slug generation (form page)
// ==========================================

function autoSlug(name) {
    var slugInput = document.getElementById('slug');
    if (!slugInput || slugInput.dataset.manual === 'true') return;

    var slug = name.toLowerCase().trim();
    // Polish characters
    var replacements = {
        'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n',
        'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z',
    };
    Object.keys(replacements).forEach(function(pl) {
        slug = slug.replace(new RegExp(pl, 'g'), replacements[pl]);
    });
    slug = slug.replace(/[^a-z0-9]+/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');
    slugInput.value = slug.substring(0, 50);
}


// ==========================================
//  Toggle campaign active/inactive
// ==========================================

function toggleCampaign(id, checkbox) {
    var csrfToken = document.querySelector('meta[name="csrf-token"]');
    var token = csrfToken ? csrfToken.getAttribute('content') : '';

    fetch('/admin/qr-tracking/' + id + '/toggle', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': token,
        },
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.success) {
            if (window.Toast) {
                window.Toast.show(
                    data.is_active ? 'Kampania aktywowana' : 'Kampania dezaktywowana',
                    'success'
                );
            }
        }
    })
    .catch(function() {
        checkbox.checked = !checkbox.checked;
        if (window.Toast) {
            window.Toast.show('Blad podczas zmiany statusu', 'error');
        }
    });
}


// ==========================================
//  Delete campaign
// ==========================================

function deleteCampaign(id, name) {
    if (!confirm('Czy na pewno chcesz usunac kampanie "' + name + '"?')) return;

    var form = document.getElementById('delete-form');
    form.action = '/admin/qr-tracking/' + id + '/delete';
    form.submit();
}


// ==========================================
//  Load statistics (AJAX)
// ==========================================

var charts = {};

function loadStats() {
    var campaignId = document.getElementById('campaign-id').value;
    var dateFrom = document.getElementById('filter-date-from').value;
    var dateTo = document.getElementById('filter-date-to').value;
    var granularity = document.getElementById('filter-granularity').value;

    var params = new URLSearchParams();
    if (dateFrom) params.append('date_from', dateFrom);
    if (dateTo) params.append('date_to', dateTo);
    params.append('granularity', granularity);

    fetch('/admin/qr-tracking/' + campaignId + '/api/stats?' + params.toString())
        .then(function(r) { return r.json(); })
        .then(function(data) {
            updateSummaryCards(data.summary);
            renderTimelineChart(data.timeline);
            renderDoughnutChart('devices-chart', 'devices', data.devices);
            renderDoughnutChart('browsers-chart', 'browsers', data.browsers);
            renderBarChart(data.countries);
            loadRecentVisits(campaignId);
        })
        .catch(function(err) {
            console.error('Error loading stats:', err);
        });
}

function updateSummaryCards(summary) {
    document.getElementById('stat-total').textContent = summary.total;
    document.getElementById('stat-unique').textContent = summary.unique;
    document.getElementById('stat-today').textContent = summary.today;
    document.getElementById('stat-week').textContent = summary.last_7_days;
}


// ==========================================
//  Chart rendering
// ==========================================

function isDarkMode() {
    return document.documentElement.getAttribute('data-theme') === 'dark';
}

function getChartColors() {
    var dark = isDarkMode();
    return {
        primary: dark ? '#f093fb' : '#8338EC',
        secondary: dark ? '#4facfe' : '#3A86FF',
        text: dark ? '#ffffff' : '#333333',
        grid: dark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)',
        tooltip_bg: dark ? 'rgba(0,0,0,0.8)' : 'rgba(0,0,0,0.7)',
        palette: dark
            ? ['#f093fb', '#4facfe', '#ff6b6b', '#ffd93d', '#6bcb77', '#4d96ff', '#ff922b', '#cc5de8', '#20c997', '#ff6b81']
            : ['#8338EC', '#3A86FF', '#FF006E', '#FB5607', '#FFBE0B', '#06D6A0', '#118AB2', '#EF476F', '#073B4C', '#FFD166'],
    };
}

function renderTimelineChart(data) {
    var ctx = document.getElementById('timeline-chart');
    if (!ctx) return;

    if (charts.timeline) charts.timeline.destroy();

    var colors = getChartColors();

    charts.timeline = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.labels,
            datasets: [
                {
                    label: 'Wszystkie wizyty',
                    data: data.total,
                    borderColor: colors.primary,
                    backgroundColor: colors.primary + '33',
                    fill: true,
                    tension: 0.3,
                },
                {
                    label: 'Unikalne wizyty',
                    data: data.unique,
                    borderColor: colors.secondary,
                    backgroundColor: colors.secondary + '33',
                    fill: true,
                    tension: 0.3,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { labels: { color: colors.text } },
                tooltip: { backgroundColor: colors.tooltip_bg },
            },
            scales: {
                x: {
                    ticks: { color: colors.text },
                    grid: { color: colors.grid },
                },
                y: {
                    beginAtZero: true,
                    ticks: { color: colors.text, stepSize: 1 },
                    grid: { color: colors.grid },
                },
            },
        },
    });
}

function renderDoughnutChart(canvasId, chartKey, data) {
    var ctx = document.getElementById(canvasId);
    if (!ctx) return;

    if (charts[chartKey]) charts[chartKey].destroy();

    var colors = getChartColors();

    charts[chartKey] = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: data.labels,
            datasets: [{
                data: data.data,
                backgroundColor: colors.palette.slice(0, data.labels.length),
                borderWidth: 0,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: colors.text, padding: 12 },
                },
                tooltip: { backgroundColor: colors.tooltip_bg },
            },
        },
    });
}

function renderBarChart(data) {
    var ctx = document.getElementById('countries-chart');
    if (!ctx) return;

    if (charts.countries) charts.countries.destroy();

    var colors = getChartColors();

    charts.countries = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.labels,
            datasets: [{
                label: 'Wizyty',
                data: data.data,
                backgroundColor: colors.primary + '88',
                borderColor: colors.primary,
                borderWidth: 1,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            indexAxis: 'y',
            plugins: {
                legend: { display: false },
                tooltip: { backgroundColor: colors.tooltip_bg },
            },
            scales: {
                x: {
                    beginAtZero: true,
                    ticks: { color: colors.text, stepSize: 1 },
                    grid: { color: colors.grid },
                },
                y: {
                    ticks: { color: colors.text },
                    grid: { display: false },
                },
            },
        },
    });
}


// ==========================================
//  Recent visits table (loaded from stats)
// ==========================================

function loadRecentVisits(campaignId) {
    var tbody = document.getElementById('visits-tbody');
    if (!tbody) return;

    var dateFrom = document.getElementById('filter-date-from').value;
    var dateTo = document.getElementById('filter-date-to').value;

    var params = new URLSearchParams();
    if (dateFrom) params.append('date_from', dateFrom);
    if (dateTo) params.append('date_to', dateTo);

    fetch('/admin/qr-tracking/' + campaignId + '/api/visits?' + params.toString())
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.visits.length === 0) {
                tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">Brak wizyt</td></tr>';
                return;
            }

            var html = '';
            data.visits.forEach(function(v) {
                html += '<tr>';
                html += '<td>' + v.visited_at + '</td>';
                html += '<td>' + v.device_type + '</td>';
                html += '<td>' + v.browser + '</td>';
                html += '<td class="hide-mobile">' + v.os + '</td>';
                html += '<td>' + (v.country || '-') + '</td>';
                html += '<td class="hide-mobile">' + (v.city || '-') + '</td>';
                html += '<td>' + (v.is_unique ? '<span class="badge-unique">Tak</span>' : 'Nie') + '</td>';
                html += '</tr>';
            });
            tbody.innerHTML = html;
        })
        .catch(function() {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">Blad ladowania</td></tr>';
        });
}


// ==========================================
//  Dark mode observer (update charts)
// ==========================================

var themeObserver = new MutationObserver(function(mutations) {
    mutations.forEach(function(mutation) {
        if (mutation.attributeName === 'data-theme') {
            // Re-render all charts with new colors
            var campaignId = document.getElementById('campaign-id');
            if (campaignId) {
                loadStats();
            }
        }
    });
});

themeObserver.observe(document.documentElement, { attributes: true });
```

**Note:** The recent visits table will need an additional API endpoint that returns individual visit records. Add this to `routes.py`:

```python
@tracking_bp.route('/admin/qr-tracking/<int:id>/api/visits')
@login_required
@role_required('admin', 'mod')
def qr_tracking_api_visits(id):
    """JSON z ostatnimi wizytami (AJAX)"""
    campaign = QRCampaign.query.filter_by(id=id, is_deleted=False).first_or_404()

    page = request.args.get('page', 1, type=int)
    per_page = 50
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    query = QRVisit.query.filter_by(campaign_id=campaign.id)

    if date_from:
        from datetime import datetime
        try:
            query = query.filter(QRVisit.visited_at >= datetime.strptime(date_from, '%Y-%m-%d'))
        except ValueError:
            pass
    if date_to:
        from datetime import datetime
        try:
            dt_to = datetime.strptime(date_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            query = query.filter(QRVisit.visited_at <= dt_to)
        except ValueError:
            pass

    visits = query.order_by(QRVisit.visited_at.desc()).limit(per_page).offset((page - 1) * per_page).all()
    total = query.count()

    return jsonify({
        'visits': [{
            'visited_at': v.visited_at.strftime('%d.%m.%Y %H:%M') if v.visited_at else '',
            'device_type': v.device_type or '',
            'browser': v.browser or '',
            'os': v.os or '',
            'country': v.country or '',
            'city': v.city or '',
            'is_unique': v.is_unique,
        } for v in visits],
        'total': total,
        'page': page,
        'pages': (total + per_page - 1) // per_page,
    })
```

Then update the `loadRecentVisits` function in `qr-tracking.js` to call this endpoint and render the table rows.

- [ ] **Step 2: Commit**

```bash
git add static/js/pages/admin/qr-tracking.js modules/tracking/routes.py
git commit -m "feat: add QR tracking JavaScript (charts, AJAX, interactions)"
```

---

## Chunk 6: Sidebar Reorganization + Final Integration

### Task 11: Reorganize sidebar — create "Komunikacja" accordion

**Files:**
- Modify: `templates/components/sidebar_admin.html`

- [ ] **Step 1: Replace flat Feedback, Popupy, Powiadomienia items with "Komunikacja" accordion**

In `templates/components/sidebar_admin.html`, replace the three flat sidebar items (Feedback lines 136-143, Popupy lines 145-152, Powiadomienia lines 154-161) with a single collapsible accordion:

```html
<!-- Komunikacja (Collapsible Category) -->
<li class="sidebar-item sidebar-category">
    <div class="sidebar-category-header {% if request.endpoint and ('feedback' in request.endpoint or 'popup' in request.endpoint or 'broadcast' in request.endpoint or 'tracking' in request.endpoint) %}active{% endif %}" onclick="toggleSidebarCategory(this)" data-tooltip="Komunikacja">
        <div class="sidebar-category-main">
            <img src="{{ url_for('static', filename='img/icons/feedback.svg') }}" alt="Komunikacja" class="sidebar-icon">
            <span class="sidebar-text">Komunikacja</span>
        </div>
        <svg class="category-chevron" width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
            <path fill-rule="evenodd" d="M1.646 4.646a.5.5 0 01.708 0L8 10.293l5.646-5.647a.5.5 0 01.708.708l-6 6a.5.5 0 01-.708 0l-6-6a.5.5 0 010-.708z"/>
        </svg>
    </div>
    <ul class="sidebar-subcategories" data-category-name="Komunikacja">
        <li class="sidebar-subitem">
            <a href="{{ url_for('feedback.admin_list') }}"
               class="sidebar-sublink {% if request.endpoint and 'feedback' in request.endpoint %}active{% endif %}"
               data-tooltip="Feedback">
                <span class="sidebar-text">Feedback</span>
            </a>
        </li>
        <li class="sidebar-subitem">
            <a href="{{ url_for('admin.popups_list') }}"
               class="sidebar-sublink {% if request.endpoint and 'popup' in request.endpoint %}active{% endif %}"
               data-tooltip="Popupy">
                <span class="sidebar-text">Popupy</span>
            </a>
        </li>
        <li class="sidebar-subitem">
            <a href="{{ url_for('admin.broadcasts_list') }}"
               class="sidebar-sublink {% if request.endpoint and 'broadcast' in request.endpoint %}active{% endif %}"
               data-tooltip="Powiadomienia">
                <span class="sidebar-text">Powiadomienia</span>
            </a>
        </li>
        <li class="sidebar-subitem">
            <a href="{{ url_for('tracking.qr_tracking_list') }}"
               class="sidebar-sublink {% if request.endpoint and 'tracking' in request.endpoint %}active{% endif %}"
               data-tooltip="QR Tracking">
                <span class="sidebar-text">QR Tracking</span>
            </a>
        </li>
    </ul>
</li>
```

- [ ] **Step 2: Verify sidebar renders correctly**

Start dev server, navigate to admin panel. Verify:
- "Komunikacja" accordion appears in sidebar
- Clicking it expands/collapses
- All 4 subitems visible (Feedback, Popupy, Powiadomienia, QR Tracking)
- Active state highlights correctly
- Works in collapsed sidebar mode (tooltip shows)
- Works in both light and dark mode

- [ ] **Step 3: Commit**

```bash
git add templates/components/sidebar_admin.html
git commit -m "feat: reorganize sidebar - create Komunikacja accordion with QR Tracking"
```

---

### Task 12: End-to-end testing and final commit

- [ ] **Step 1: Test full flow**

1. Navigate to Admin → Komunikacja → QR Tracking
2. Create a new campaign (name: "Test Wizytowki", slug auto-generates)
3. Verify campaign appears in list
4. Click QR code — verify preview renders with logo
5. Download SVG and PNG — verify both have transparent background + logo
6. Visit `/qr/test-wizytowki` — verify redirect to target URL
7. Check campaign stats — verify visit was recorded
8. Visit again — verify second visit recorded (is_unique=False)
9. Check charts render (timeline, devices, browsers)
10. Toggle campaign active/inactive — verify works
11. Export XLSX — verify file downloads with correct data
12. Test dark mode — verify all elements look correct
13. Test on mobile viewport — verify responsive layout
14. Edit campaign — change name, verify slug updates
15. Delete campaign — verify soft-deleted, no longer in list, `/qr/<slug>` returns 404

- [ ] **Step 2: Generate migration if not done yet**

```bash
flask db migrate -m "Add QR tracking tables (qr_campaigns, qr_visits)"
flask db upgrade
```

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete QR tracking system - campaigns, analytics, QR generator"
```
