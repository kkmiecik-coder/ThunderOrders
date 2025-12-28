# Cookie Consent Implementation Guide (RODO-Compliant)

## ✅ Status: CZĘŚCIOWO WDROŻONE

### Co zostało już zrobione:
1. ✅ Dodano kolumnę `analytics_consent` do tabeli `users` (BOOLEAN, nullable)
2. ✅ Zaktualizowano model `User` w `modules/auth/models.py`

### Co pozostało do zrobienia:

---

## KROK 1: Modyfikacja `templates/base.html`

**Lokalizacja:** `templates/base.html` (linie 8-24)

**Znajdź:**
```html
<!-- Google Analytics 4 (GA4) -->
{% if config.GA_MEASUREMENT_ID %}
<!-- Global site tag (gtag.js) - Google Analytics -->
<script async src="https://www.googletagmanager.com/gtag/js?id={{ config.GA_MEASUREMENT_ID }}"></script>
<script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){dataLayer.push(arguments);}
    gtag('js', new Date());
    gtag('config', '{{ config.GA_MEASUREMENT_ID }}', {
        'anonymize_ip': true,  // Anonimizacja IP (RODO compliance)
        'cookie_flags': 'SameSite=None;Secure'
    });

    // Expose gtag globally for custom event tracking
    window.gtag = gtag;
</script>
{% endif %}
```

**Zamień na:**
```html
<!-- Google Analytics 4 (GA4) - Warunkowe ładowanie zgodne z RODO -->
{% if config.GA_MEASUREMENT_ID %}
<script>
    // Funkcja ładująca GA4
    function loadGoogleAnalytics() {
        const script = document.createElement('script');
        script.async = true;
        script.src = 'https://www.googletagmanager.com/gtag/js?id={{ config.GA_MEASUREMENT_ID }}';
        document.head.appendChild(script);

        script.onload = function() {
            window.dataLayer = window.dataLayer || [];
            function gtag(){dataLayer.push(arguments);}
            gtag('js', new Date());
            gtag('config', '{{ config.GA_MEASUREMENT_ID }}', {
                'anonymize_ip': true,
                'cookie_flags': 'SameSite=None;Secure'
            });
            window.gtag = gtag;
        };
    }

    // Sprawdź zgodę użytkownika
    {% if current_user.is_authenticated %}
        // Zalogowany użytkownik
        {% if current_user.analytics_consent %}
            // Ma zgodę → Ładuj GA4 od razu
            loadGoogleAnalytics();
        {% else %}
            // Nie ma zgody → Pokaż banner
            window.showCookieBanner = true;
        {% endif %}
    {% else %}
        // Gość → Sprawdź localStorage
        const consent = localStorage.getItem('analytics_consent');
        if (consent === 'accepted') {
            loadGoogleAnalytics();
        } else if (consent !== 'rejected') {
            // Nie podjął decyzji → Pokaż banner
            window.showCookieBanner = true;
        }
    {% endif %}
</script>
{% endif %}
```

---

## KROK 2: Dodaj Cookie Banner do `templates/base.html`

**Lokalizacja:** `templates/base.html` (tuż przed `{% block body_content %}`).

**Dodaj przed linią 78:**
```html
<!-- Cookie Consent Banner -->
{% include 'components/cookie_banner.html' %}
```

---

## KROK 3: Utwórz komponent Cookie Banner

**Utwórz plik:** `templates/components/cookie_banner.html`

**Zawartość:**
```html
<!-- Cookie Consent Banner (RODO-compliant) -->
<div id="cookieBanner" class="cookie-banner" style="display: none;">
    <div class="cookie-banner-content">
        <div class="cookie-banner-text">
            <h3>🍪 Ta strona używa plików cookie</h3>
            <p>
                Używamy Google Analytics w celu poprawy jakości usług i analizy ruchu na stronie.
                Dane są anonimizowane i nie identyfikują Cię osobiście.
                <a href="{{ url_for('main.privacy_policy') }}" target="_blank">Polityka prywatności</a>
            </p>
        </div>
        <div class="cookie-banner-actions">
            <button id="cookieAccept" class="btn btn-primary">Akceptuję</button>
            <button id="cookieReject" class="btn btn-secondary">Odrzuć</button>
        </div>
    </div>
</div>

<script>
    // Pokaż banner jeśli potrzeba
    if (window.showCookieBanner) {
        document.getElementById('cookieBanner').style.display = 'block';
    }

    // Akceptuj
    document.getElementById('cookieAccept')?.addEventListener('click', function() {
        {% if current_user.is_authenticated %}
            // Zapisz zgodę w bazie
            fetch('/api/analytics-consent', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
                },
                body: JSON.stringify({ consent: true })
            }).then(() => {
                if (typeof loadGoogleAnalytics === 'function') {
                    loadGoogleAnalytics();
                }
                document.getElementById('cookieBanner').style.display = 'none';
            });
        {% else %}
            // Gość → localStorage
            localStorage.setItem('analytics_consent', 'accepted');
            if (typeof loadGoogleAnalytics === 'function') {
                loadGoogleAnalytics();
            }
            document.getElementById('cookieBanner').style.display = 'none';
        {% endif %}
    });

    // Odrzuć
    document.getElementById('cookieReject')?.addEventListener('click', function() {
        {% if current_user.is_authenticated %}
            fetch('/api/analytics-consent', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
                },
                body: JSON.stringify({ consent: false })
            }).then(() => {
                document.getElementById('cookieBanner').style.display = 'none';
            });
        {% else %}
            localStorage.setItem('analytics_consent', 'rejected');
            document.getElementById('cookieBanner').style.display = 'none';
        {% endif %}
    });
</script>
```

---

## KROK 4: Style CSS dla Cookie Banner

**Utwórz plik:** `static/css/components/cookie-banner.css`

**Zawartość:** (podano w osobnym pliku - zobacz COOKIE_BANNER_CSS.md)

**Dodaj import w `static/css/main.css`:**
```css
@import 'components/cookie-banner.css';
```

---

## KROK 5: Dodaj checkbox do formularza rejestracji

**Lokalizacja:** `templates/auth/register.html`

**Znajdź formularz rejestracji i dodaj przed przyciskiem "Zarejestruj się":**
```html
<!-- Zgoda na Analytics -->
<div class="form-group checkbox-group">
    <label class="checkbox-label">
        <input type="checkbox" name="analytics_consent" id="analytics_consent">
        <span class="checkbox-custom"></span>
        <span class="checkbox-text">
            Zgadzam się na używanie plików cookie analitycznych (Google Analytics) w celu poprawy jakości usług.
            <a href="{{ url_for('main.privacy_policy') }}" target="_blank">Polityka prywatności</a>
        </span>
    </label>
</div>
```

---

## KROK 6: Backend - Zapisz zgodę przy rejestracji

**Lokalizacja:** `modules/auth/routes.py` - funkcja `register()`

**Znajdź:**
```python
user = User(
    email=form.email.data,
    first_name=form.first_name.data,
    last_name=form.last_name.data,
    # ...
)
```

**Dodaj przed `db.session.add(user)`:**
```python
# Pobierz zgodę na analytics
analytics_consent = request.form.get('analytics_consent') == 'on'
user.analytics_consent = analytics_consent
```

---

## KROK 7: API Endpoint - Zapisz/aktualizuj zgodę

**Utwórz plik:** `modules/api/analytics.py`

**Zawartość:**
```python
"""
API Module - Analytics Consent
Endpoint do zarządzania zgodą na cookies analityczne
"""
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from extensions import db

analytics_bp = Blueprint('analytics_api', __name__, url_prefix='/api')


@analytics_bp.route('/analytics-consent', methods=['POST'])
@login_required
def update_analytics_consent():
    """
    Aktualizuj zgodę użytkownika na cookies analityczne

    POST Body:
        { "consent": true/false }

    Returns:
        { "success": true, "consent": true/false }
    """
    data = request.get_json()
    consent = data.get('consent', False)

    current_user.analytics_consent = consent
    db.session.commit()

    return jsonify({
        'success': True,
        'consent': consent
    })
```

**Zarejestruj blueprint w `app.py`:**
```python
from modules.api.analytics import analytics_bp
app.register_blueprint(analytics_bp)
```

---

## KROK 8: Ustawienia profilu - Toggle zgody

**Lokalizacja:** `templates/client/profile.html` lub odpowiednia strona ustawień

**Dodaj w sekcji Prywatność:**
```html
<!-- Zgoda na Analytics -->
<div class="form-group toggle-group">
    <label class="toggle-label">
        <span class="toggle-text">
            <strong>Cookies analityczne (Google Analytics)</strong>
            <small>Pomaga nam poprawić jakość usług. Możesz wycofać zgodę w każdej chwili.</small>
        </span>
        <label class="toggle-switch">
            <input
                type="checkbox"
                name="analytics_consent"
                id="analytics_consent_toggle"
                {% if current_user.analytics_consent %}checked{% endif %}
            >
            <span class="toggle-slider"></span>
        </label>
    </label>
</div>
```

**JavaScript (w pliku JS strony profilu):**
```javascript
// Toggle zgody na analytics
document.getElementById('analytics_consent_toggle')?.addEventListener('change', function() {
    const consent = this.checked;

    fetch('/api/analytics-consent', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
        },
        body: JSON.stringify({ consent: consent })
    }).then(response => response.json())
    .then(data => {
        if (data.success) {
            // Pokazanie toastu
            showToast(
                consent ? 'Zgoda na cookies została zapisana' : 'Zgoda na cookies została wycofana',
                'success'
            );

            // Przeładowanie strony (aby załadować/usunąć GA4)
            setTimeout(() => window.location.reload(), 1000);
        }
    });
});
```

---

## KROK 9: Strona Polityki Prywatności

**Utwórz plik:** `templates/legal/privacy_policy.html`

**Zawartość:** (podano w osobnym pliku - zobacz PRIVACY_POLICY_TEMPLATE.md)

**Utwórz route w `app.py` lub `modules/main/routes.py`:**
```python
@main_bp.route('/polityka-prywatnosci')
def privacy_policy():
    """Strona polityki prywatności"""
    return render_template('legal/privacy_policy.html')
```

---

## KROK 10: Testowanie

### Test 1: Nowy użytkownik - Rejestracja BEZ zgody
1. Otwórz `/auth/register`
2. NIE zaznaczaj checkboxa "Zgadzam się na cookies..."
3. Zarejestruj się
4. Po zalogowaniu → Powinieneś zobaczyć cookie banner
5. Kliknij "Akceptuj" → Banner znika, GA4 się ładuje
6. DevTools Console: `typeof window.gtag` powinno być `"function"`

### Test 2: Nowy użytkownik - Rejestracja ZE zgodą
1. Otwórz `/auth/register`
2. ZAZNACZ checkbox "Zgadzam się na cookies..."
3. Zarejestruj się
4. Po zalogowaniu → Banner NIE powinien się pojawić
5. GA4 powinno już działać (sprawdź `typeof window.gtag`)

### Test 3: Gość na stronie Exclusive
1. Otwórz stronę exclusive (nie loguj się)
2. Powinieneś zobaczyć cookie banner
3. Kliknij "Akceptuj" → localStorage `analytics_consent = 'accepted'`
4. Kliknij "Odrzuć" → localStorage `analytics_consent = 'rejected'`
5. Po odświeżeniu strony decyzja powinna być zapamiętana

### Test 4: Wycofanie zgody
1. Zaloguj się jako użytkownik z zgodą
2. Przejdź do Ustawień → Prywatność
3. Wyłącz toggle "Cookies analityczne"
4. Zapisz
5. Po odświeżeniu strony GA4 NIE powinno się ładować
6. Powinieneś zobaczyć cookie banner ponownie

---

## KROK 11: Wdrożenie na VPS

### Na Macu (lokalnie):
```bash
# 1. Commit wszystkich zmian
git add .
git commit -m "Add RODO-compliant cookie consent for Google Analytics"
git push origin main
```

### Na serwerze VPS (SSH):
```bash
# 1. Połącz się SSH
ssh konrad@191.96.53.209

# 2. Przejdź do katalogu aplikacji
cd /var/www/ThunderOrders

# 3. Pobierz najnowszy kod
git pull origin main

# 4. Restartuj aplikację
sudo systemctl restart thunderorders

# 5. Sprawdź status
sudo systemctl status thunderorders

# 6. Sprawdź logi
sudo journalctl -u thunderorders -n 50 --no-pager
```

### Weryfikacja na produkcji:
1. Otwórz https://thunderorders.cloud
2. Sprawdź czy banner się pojawia (dla gości)
3. Sprawdź Google Analytics Realtime - czy dane są zbierane tylko po zgodzie

---

## Pliki do utworzenia:

1. ✅ `modules/auth/models.py` - ZROBIONE (pole analytics_consent dodane)
2. ❌ `templates/components/cookie_banner.html`
3. ❌ `static/css/components/cookie-banner.css`
4. ❌ `modules/api/analytics.py`
5. ❌ `templates/legal/privacy_policy.html`

## Pliki do edycji:

1. ❌ `templates/base.html` (warunkowe ładowanie GA4 + include bannera)
2. ❌ `templates/auth/register.html` (checkbox zgody)
3. ❌ `modules/auth/routes.py` (zapisanie zgody przy rejestracji)
4. ❌ `templates/client/profile.html` (toggle zgody)
5. ❌ `app.py` (rejestracja analytics_bp + route polityki prywatności)
6. ❌ `static/css/main.css` (import cookie-banner.css)

---

**Data utworzenia:** 2025-12-28
**Status:** Dokumentacja wdrożenia - gotowa do implementacji
