# PWA Bottom Navigation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a native app-style bottom navigation bar visible only in PWA standalone mode, replacing sidebar + topbar + mobile navbar.

**Architecture:** CSS media query `@media (display-mode: standalone)` hides existing navigation and shows the new bottom bar. A reusable bottom sheet component handles sub-menus and "Więcej" panel. All new code goes into dedicated files (HTML templates, one CSS file, one JS file).

**Tech Stack:** Jinja2 templates, vanilla CSS (with CSS variables from `variables.css`), vanilla JavaScript.

**Spec:** `docs/superpowers/specs/2026-03-18-pwa-bottom-navigation-design.md`

---

## File Structure

### New Files
| File | Responsibility |
|------|----------------|
| `templates/components/bottom_bar_client.html` | Client bottom bar HTML (5 icons) |
| `templates/components/bottom_bar_admin.html` | Admin bottom bar HTML (5 icons) |
| `templates/components/bottom_sheet.html` | Reusable sheet container (backdrop + panel + X button) |
| `static/css/components/bottom-bar.css` | All styles: bar, sheet, PWA overrides, light+dark mode |
| `static/js/components/bottom-bar.js` | Sheet open/close, badge polling, history state, viewport-fit, search trigger |

### Modified Files
| File | Change |
|------|--------|
| `templates/admin/base_admin.html` | Add `{% include 'components/bottom_bar_admin.html' %}` |
| `templates/client/base_client.html` | Add `{% include 'components/bottom_bar_client.html' %}` |
| `templates/base.html` | Add CSS link for `bottom-bar.css`, add JS script for `bottom-bar.js` |

**Note:** Sidebar/topbar/mobile-navbar hiding is done purely via CSS in `bottom-bar.css` using `@media (display-mode: standalone)` — no modifications to `sidebar.css` or `topbar.css` needed. This deviates from the spec (which listed those files as modified) but centralizes all PWA overrides in one file for easier maintenance.

**Moderator role:** Moderators use `base_admin.html`, so they automatically get the admin bottom bar.

---

## Chunk 1: HTML Templates + CSS Include

### Task 1: Create bottom sheet template

**Files:**
- Create: `templates/components/bottom_sheet.html`

- [ ] **Step 1: Create the reusable sheet component**

```html
<!-- Bottom Sheet (PWA only) -->
<div class="pwa-bottom-sheet" id="pwaBottomSheet" aria-hidden="true">
    <div class="pwa-sheet-backdrop" id="pwaSheetBackdrop"></div>
    <div class="pwa-sheet-panel">
        <div class="pwa-sheet-header">
            <span class="pwa-sheet-title" id="pwaSheetTitle"></span>
            <button class="pwa-sheet-close" id="pwaSheetClose" aria-label="Zamknij">&times;</button>
        </div>
        <div class="pwa-sheet-body" id="pwaSheetBody">
            <!-- Content injected by JS -->
        </div>
    </div>
</div>
```

- [ ] **Step 2: Commit**

```bash
git add templates/components/bottom_sheet.html
git commit -m "feat(pwa): add reusable bottom sheet template"
```

---

### Task 2: Create client bottom bar template

**Files:**
- Create: `templates/components/bottom_bar_client.html`

The template uses Jinja2 `request.endpoint` for active state detection (same pattern as existing sidebar). Icons use `<img>` tags referencing existing SVGs for direct links, and inline SVGs for Szukaj/Więcej.

- [ ] **Step 1: Create client bottom bar HTML**

```html
<!-- PWA Bottom Bar - Client -->
{% if current_user.is_authenticated %}
<nav class="pwa-bottom-bar" id="pwaBottomBar" role="navigation" aria-label="Nawigacja główna" aria-hidden="true">
    <a href="{{ url_for('client.dashboard') }}"
       class="pwa-bar-item {% if request.endpoint == 'client.dashboard' %}active{% endif %}"
       data-tooltip="Dashboard">
        <img src="{{ url_for('static', filename='img/icons/dashboard.svg') }}" alt="" class="pwa-bar-icon">
        <span class="pwa-bar-label">Dashboard</span>
    </a>

    <a href="{{ url_for('orders.client_list') }}"
       class="pwa-bar-item {% if request.endpoint in ['orders.client_list', 'orders.client_detail'] %}active{% endif %}"
       data-tooltip="Zamówienia">
        <img src="{{ url_for('static', filename='img/icons/orders.svg') }}" alt="" class="pwa-bar-icon">
        <span class="pwa-bar-label">Zamówienia</span>
    </a>

    <button class="pwa-bar-item" id="pwaSearchBtn" aria-label="Szukaj">
        <svg class="pwa-bar-icon pwa-bar-icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
        </svg>
        <span class="pwa-bar-label">Szukaj</span>
    </button>

    <a href="{{ url_for('client.payment_confirmations') }}"
       class="pwa-bar-item {% if request.endpoint == 'client.payment_confirmations' %}active{% endif %}"
       data-tooltip="Potwierdzenia">
        <img src="{{ url_for('static', filename='img/icons/payment.svg') }}" alt="" class="pwa-bar-icon">
        <span class="pwa-bar-label">Potwierdzenia</span>
    </a>

    <button class="pwa-bar-item" id="pwaMoreBtn" aria-label="Więcej" data-sheet="client-more">
        <svg class="pwa-bar-icon pwa-bar-icon-svg" viewBox="0 0 24 24" fill="currentColor">
            <circle cx="12" cy="5" r="2"></circle>
            <circle cx="12" cy="12" r="2"></circle>
            <circle cx="12" cy="19" r="2"></circle>
        </svg>
        <span class="pwa-bar-label">Więcej</span>
        <span class="pwa-bar-badge" id="pwaMoreBadge" style="display:none;">0</span>
    </button>
</nav>

<!-- Sheet content templates (hidden, used by JS) -->
<template id="pwaSheetClientMore">
    <ul class="pwa-sheet-list">
        <li>
            <a href="{{ url_for('notifications.notification_center') }}" class="pwa-sheet-item">
                <img src="{{ url_for('static', filename='img/icons/bell.svg') }}" alt="" class="pwa-sheet-icon">
                <span>Powiadomienia</span>
                <span class="pwa-sheet-badge" id="pwaSheetNotifBadge" style="display:none;">0</span>
            </a>
        </li>
        <li>
            <a href="{{ url_for('client.collection_list') }}" class="pwa-sheet-item {% if request.endpoint and 'collection' in request.endpoint %}active{% endif %}">
                <img src="{{ url_for('static', filename='img/icons/collection.svg') }}" alt="" class="pwa-sheet-icon">
                <span>Moja Kolekcja</span>
            </a>
        </li>
        <li>
            <a href="{{ url_for('achievements.gallery') }}" class="pwa-sheet-item {% if request.endpoint and 'achievements' in request.endpoint %}active{% endif %}">
                <img src="{{ url_for('static', filename='img/icons/achievements.svg') }}" alt="" class="pwa-sheet-icon">
                <span>Osiągnięcia</span>
            </a>
        </li>
        <li class="pwa-sheet-accordion">
            <button class="pwa-sheet-item pwa-sheet-accordion-toggle">
                <img src="{{ url_for('static', filename='img/icons/truck.svg') }}" alt="" class="pwa-sheet-icon">
                <span>Wysyłka</span>
                <svg class="pwa-sheet-chevron" viewBox="0 0 16 16" fill="currentColor" width="16" height="16">
                    <path fill-rule="evenodd" d="M4.646 1.646a.5.5 0 0 1 .708 0l6 6a.5.5 0 0 1 0 .708l-6 6a.5.5 0 0 1-.708-.708L10.293 8 4.646 2.354a.5.5 0 0 1 0-.708z"/>
                </svg>
            </button>
            <ul class="pwa-sheet-subitems">
                <li><a href="{{ url_for('client.shipping_requests_list') }}" class="pwa-sheet-item pwa-sheet-subitem">Zlecenia</a></li>
                <li><a href="{{ url_for('client.shipping_addresses') }}" class="pwa-sheet-item pwa-sheet-subitem">Adresy dostaw</a></li>
            </ul>
        </li>
        <li class="pwa-sheet-divider"></li>
        <li>
            <a href="{{ url_for('profile.index') }}" class="pwa-sheet-item">
                <img src="{{ url_for('static', filename='img/icons/user.svg') }}" alt="" class="pwa-sheet-icon">
                <span>Profil</span>
            </a>
        </li>
        <li>
            <a href="{{ url_for('auth.logout') }}" class="pwa-sheet-item pwa-sheet-item-danger">
                <img src="{{ url_for('static', filename='img/icons/logout.svg') }}" alt="" class="pwa-sheet-icon">
                <span>Wyloguj się</span>
            </a>
        </li>
    </ul>
</template>
{% endif %}

{% include 'components/bottom_sheet.html' %}
```

- [ ] **Step 2: Commit**

```bash
git add templates/components/bottom_bar_client.html
git commit -m "feat(pwa): add client bottom bar template with sheet content"
```

---

### Task 3: Create admin bottom bar template

**Files:**
- Create: `templates/components/bottom_bar_admin.html`

Admin has 3 sheet templates: Zamówienia sub-menu, Magazyn sub-menu, and Więcej.

- [ ] **Step 1: Create admin bottom bar HTML**

```html
<!-- PWA Bottom Bar - Admin -->
{% if current_user.is_authenticated %}
<nav class="pwa-bottom-bar" id="pwaBottomBar" role="navigation" aria-label="Nawigacja główna" aria-hidden="true">
    <a href="{{ url_for('admin.dashboard') }}"
       class="pwa-bar-item {% if request.endpoint == 'admin.dashboard' %}active{% endif %}">
        <img src="{{ url_for('static', filename='img/icons/dashboard.svg') }}" alt="" class="pwa-bar-icon">
        <span class="pwa-bar-label">Dashboard</span>
    </a>

    <button class="pwa-bar-item {% if request.endpoint and (request.endpoint.startswith('orders.') or request.endpoint == 'admin.payment_confirmations_list' or request.endpoint == 'admin.exclusive_list' or request.endpoint == 'admin.exclusive_edit') %}active{% endif %}"
            data-sheet="admin-orders" aria-label="Zamówienia">
        <img src="{{ url_for('static', filename='img/icons/orders.svg') }}" alt="" class="pwa-bar-icon">
        <span class="pwa-bar-label">Zamówienia</span>
    </button>

    <button class="pwa-bar-item" id="pwaSearchBtn" aria-label="Szukaj">
        <svg class="pwa-bar-icon pwa-bar-icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
        </svg>
        <span class="pwa-bar-label">Szukaj</span>
    </button>

    <button class="pwa-bar-item {% if request.endpoint in ['products.list_products', 'products.stock_orders', 'products.warehouse_settings'] %}active{% endif %}"
            data-sheet="admin-warehouse" aria-label="Magazyn">
        <img src="{{ url_for('static', filename='img/icons/warehouse.svg') }}" alt="" class="pwa-bar-icon">
        <span class="pwa-bar-label">Magazyn</span>
    </button>

    <button class="pwa-bar-item" id="pwaMoreBtn" aria-label="Więcej" data-sheet="admin-more">
        <svg class="pwa-bar-icon pwa-bar-icon-svg" viewBox="0 0 24 24" fill="currentColor">
            <circle cx="12" cy="5" r="2"></circle>
            <circle cx="12" cy="12" r="2"></circle>
            <circle cx="12" cy="19" r="2"></circle>
        </svg>
        <span class="pwa-bar-label">Więcej</span>
        <span class="pwa-bar-badge" id="pwaMoreBadge" style="display:none;">0</span>
    </button>
</nav>

<!-- Sheet: Zamówienia sub-menu -->
<template id="pwaSheetAdminOrders">
    <ul class="pwa-sheet-list">
        <li><a href="{{ url_for('orders.admin_list') }}" class="pwa-sheet-item {% if request.endpoint == 'orders.admin_list' %}active{% endif %}">
            <img src="{{ url_for('static', filename='img/icons/orders.svg') }}" alt="" class="pwa-sheet-icon">
            <span>Lista zamówień</span>
        </a></li>
        <li><a href="{{ url_for('orders.wms_dashboard') }}" class="pwa-sheet-item {% if request.endpoint and 'wms' in request.endpoint %}active{% endif %}">
            <img src="{{ url_for('static', filename='img/icons/truck.svg') }}" alt="" class="pwa-sheet-icon">
            <span>WMS / Wysyłka</span>
        </a></li>
        <li><a href="{{ url_for('admin.payment_confirmations_list') }}" class="pwa-sheet-item {% if request.endpoint == 'admin.payment_confirmations_list' %}active{% endif %}">
            <img src="{{ url_for('static', filename='img/icons/payment.svg') }}" alt="" class="pwa-sheet-icon">
            <span>Potwierdzenia płatności</span>
        </a></li>
        <li><a href="{{ url_for('admin.exclusive_list') }}" class="pwa-sheet-item {% if request.endpoint == 'admin.exclusive_list' or request.endpoint == 'admin.exclusive_edit' %}active{% endif %}">
            <img src="{{ url_for('static', filename='img/icons/exclusive.svg') }}" alt="" class="pwa-sheet-icon">
            <span>Exclusive</span>
        </a></li>
        <li><a href="{{ url_for('orders.settings') }}" class="pwa-sheet-item {% if request.endpoint == 'orders.settings' %}active{% endif %}">
            <img src="{{ url_for('static', filename='img/icons/settings.svg') }}" alt="" class="pwa-sheet-icon">
            <span>Ustawienia</span>
        </a></li>
    </ul>
</template>

<!-- Sheet: Magazyn sub-menu -->
<template id="pwaSheetAdminWarehouse">
    <ul class="pwa-sheet-list">
        <li><a href="{{ url_for('products.list_products') }}" class="pwa-sheet-item {% if request.endpoint == 'products.list_products' %}active{% endif %}">
            <img src="{{ url_for('static', filename='img/icons/products.svg') }}" alt="" class="pwa-sheet-icon">
            <span>Lista produktów</span>
        </a></li>
        <li><a href="{{ url_for('products.stock_orders') }}" class="pwa-sheet-item {% if request.endpoint == 'products.stock_orders' %}active{% endif %}">
            <img src="{{ url_for('static', filename='img/icons/warehouse.svg') }}" alt="" class="pwa-sheet-icon">
            <span>Zamówienia produktów</span>
        </a></li>
        <li><a href="{{ url_for('products.warehouse_settings') }}" class="pwa-sheet-item {% if request.endpoint == 'products.warehouse_settings' %}active{% endif %}">
            <img src="{{ url_for('static', filename='img/icons/settings.svg') }}" alt="" class="pwa-sheet-icon">
            <span>Ustawienia</span>
        </a></li>
    </ul>
</template>

<!-- Sheet: Więcej -->
<template id="pwaSheetAdminMore">
    <ul class="pwa-sheet-list">
        <li>
            <a href="{{ url_for('notifications.notification_center') }}" class="pwa-sheet-item">
                <img src="{{ url_for('static', filename='img/icons/bell.svg') }}" alt="" class="pwa-sheet-icon">
                <span>Powiadomienia</span>
                <span class="pwa-sheet-badge" id="pwaSheetNotifBadge" style="display:none;">0</span>
            </a>
        </li>
        <li>
            <a href="{{ url_for('admin.clients_list') }}" class="pwa-sheet-item {% if request.endpoint and 'client' in request.endpoint %}active{% endif %}">
                <img src="{{ url_for('static', filename='img/icons/clients.svg') }}" alt="" class="pwa-sheet-icon">
                <span>Użytkownicy</span>
            </a>
        </li>
        <li>
            <a href="{{ url_for('admin.statistics') }}" class="pwa-sheet-item {% if request.endpoint and 'statistics' in request.endpoint %}active{% endif %}">
                <img src="{{ url_for('static', filename='img/icons/dashboard.svg') }}" alt="" class="pwa-sheet-icon">
                <span>Statystyki</span>
            </a>
        </li>
        <li>
            <a href="{{ url_for('admin.tasks_list') }}" class="pwa-sheet-item {% if request.endpoint and 'task' in request.endpoint %}active{% endif %}">
                <img src="{{ url_for('static', filename='img/icons/tasks.svg') }}" alt="" class="pwa-sheet-icon">
                <span>Moje zadania</span>
            </a>
        </li>
        <li class="pwa-sheet-accordion">
            <button class="pwa-sheet-item pwa-sheet-accordion-toggle">
                <img src="{{ url_for('static', filename='img/icons/feedback.svg') }}" alt="" class="pwa-sheet-icon">
                <span>Komunikacja</span>
                <svg class="pwa-sheet-chevron" viewBox="0 0 16 16" fill="currentColor" width="16" height="16">
                    <path fill-rule="evenodd" d="M4.646 1.646a.5.5 0 0 1 .708 0l6 6a.5.5 0 0 1 0 .708l-6 6a.5.5 0 0 1-.708-.708L10.293 8 4.646 2.354a.5.5 0 0 1 0-.708z"/>
                </svg>
            </button>
            <ul class="pwa-sheet-subitems">
                <li><a href="{{ url_for('feedback.admin_list') }}" class="pwa-sheet-item pwa-sheet-subitem">Feedback</a></li>
                <li><a href="{{ url_for('admin.popups_list') }}" class="pwa-sheet-item pwa-sheet-subitem">Popupy</a></li>
                <li><a href="{{ url_for('admin.broadcasts_list') }}" class="pwa-sheet-item pwa-sheet-subitem">Powiadomienia</a></li>
                <li><a href="{{ url_for('tracking.qr_campaigns_list') }}" class="pwa-sheet-item pwa-sheet-subitem">QR Tracking</a></li>
            </ul>
        </li>
        <li class="pwa-sheet-divider"></li>
        <li>
            <a href="{{ url_for('profile.index') }}" class="pwa-sheet-item">
                <img src="{{ url_for('static', filename='img/icons/user.svg') }}" alt="" class="pwa-sheet-icon">
                <span>Profil</span>
            </a>
        </li>
        <li>
            <a href="{{ url_for('auth.logout') }}" class="pwa-sheet-item pwa-sheet-item-danger">
                <img src="{{ url_for('static', filename='img/icons/logout.svg') }}" alt="" class="pwa-sheet-icon">
                <span>Wyloguj się</span>
            </a>
        </li>
    </ul>
</template>
{% endif %}

{% include 'components/bottom_sheet.html' %}
```

- [ ] **Step 2: Commit**

```bash
git add templates/components/bottom_bar_admin.html
git commit -m "feat(pwa): add admin bottom bar template with sheet content"
```

---

### Task 4: Include bottom bar in base templates

**Files:**
- Modify: `templates/admin/base_admin.html`
- Modify: `templates/client/base_client.html`
- Modify: `templates/base.html`

- [ ] **Step 1: Add bottom bar include to admin base**

In `templates/admin/base_admin.html`, add after `</div>` (closing main-wrapper) and before `{% endblock %}`:

```html
<!-- PWA Bottom Bar -->
{% include 'components/bottom_bar_admin.html' %}
```

- [ ] **Step 2: Add bottom bar include to client base**

In `templates/client/base_client.html`, add after `</div>` (closing main-wrapper) and before `{% endblock %}`:

```html
<!-- PWA Bottom Bar -->
{% include 'components/bottom_bar_client.html' %}
```

- [ ] **Step 3: Add CSS and JS links to base.html**

In `templates/base.html`:

After line 82 (`global-search.css`), add:
```html
<link rel="stylesheet" href="{{ url_for('static', filename='css/components/bottom-bar.css') }}">
```

After line 158 (`global-search.js`), add:
```html
<script src="{{ url_for('static', filename='js/components/bottom-bar.js') }}"></script>
```

- [ ] **Step 4: Commit**

```bash
git add templates/admin/base_admin.html templates/client/base_client.html templates/base.html
git commit -m "feat(pwa): include bottom bar templates and assets in base layouts"
```

---

## Chunk 2: CSS Styles

### Task 5: Create bottom bar CSS with all styles

**Files:**
- Create: `static/css/components/bottom-bar.css`

This single file contains: PWA detection, hiding existing nav, bottom bar layout, sheet styles, search overlay PWA adjustments, light + dark mode, landscape, safe areas.

- [ ] **Step 1: Create the complete CSS file**

Key sections to implement:

1. **PWA Detection & Hiding existing nav** — `@media (display-mode: standalone)` hides `.sidebar`, `.sidebar-backdrop`, `.topbar`, `.mobile-navbar`, `.mobile-menu-overlay`, `.mobile-notif-overlay` and shows `.pwa-bottom-bar`
2. **Bottom bar layout** — fixed bottom, 5 equal columns via `display: grid; grid-template-columns: repeat(5, 1fr)`, 60px height + safe area
3. **Bar items** — flex column, icon 24px + label 10px, active state colors using CSS variables
4. **Badge** — absolute positioned red circle on Więcej icon
5. **Bottom sheet** — fixed overlay with backdrop, panel slides up from bottom with `transform`, 300ms ease-out transition, max-height 60vh, border-radius 16px top
6. **Sheet items** — list with icons, accordion toggle with chevron rotation, subitems indented, divider, danger style for logout
7. **Content area adjustment** — `padding-bottom: calc(60px + env(safe-area-inset-bottom))` on `.main-content` in PWA mode
8. **Dark mode** — `[data-theme="dark"]` variants using glassmorphism tokens from `variables.css`
9. **Landscape** — reduced bar height (48px)
10. **Default state** — `.pwa-bottom-bar` and `.pwa-bottom-sheet` are `display: none` by default (only shown via `@media (display-mode: standalone)`)

Design tokens to use (from spec):
- Light: bar bg `#ffffff`, border `1px solid #e0e0e0`, active `#7c3aed`, inactive `#9ca3af`
- Dark: bar bg `rgba(255,255,255,0.05)` + `backdrop-filter: blur(20px)`, border `1px solid rgba(240,147,251,0.15)`, active `#f093fb`, inactive `rgba(255,255,255,0.5)`

```css
/* ============================================
   PWA Bottom Navigation Bar
   Only visible in PWA standalone mode
   ============================================ */

/* Default: hidden in browser mode */
.pwa-bottom-bar {
    display: none;
}

.pwa-bottom-sheet {
    display: none;
}

/* ============================================
   PWA Standalone Mode
   ============================================ */
@media (display-mode: standalone) {

    /* --- Hide existing navigation --- */
    .sidebar,
    .sidebar-backdrop,
    .topbar,
    .mobile-navbar,
    .mobile-menu-overlay,
    .mobile-notif-overlay {
        display: none !important;
    }

    /* --- Adjust layout --- */
    .main-wrapper {
        margin-left: 0 !important;
        padding-top: 0 !important;
    }

    .main-content {
        padding-bottom: calc(60px + env(safe-area-inset-bottom, 0px)) !important;
        padding-top: var(--space-4) !important;
    }

    /* --- Bottom Bar --- */
    .pwa-bottom-bar {
        display: grid;
        grid-template-columns: repeat(5, 1fr);
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        height: calc(60px + env(safe-area-inset-bottom, 0px));
        padding-bottom: env(safe-area-inset-bottom, 0px);
        background: #ffffff;
        border-top: 1px solid #e0e0e0;
        z-index: 1000;
        -webkit-user-select: none;
        user-select: none;
    }

    /* --- Bar Items --- */
    .pwa-bar-item {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 2px;
        padding: 6px 0;
        background: none;
        border: none;
        cursor: pointer;
        text-decoration: none;
        color: #9ca3af;
        position: relative;
        -webkit-tap-highlight-color: transparent;
        transition: color var(--transition-fast);
    }

    .pwa-bar-item:active {
        opacity: 0.7;
    }

    .pwa-bar-icon {
        width: 24px;
        height: 24px;
        opacity: 0.5;
        transition: opacity var(--transition-fast);
    }

    .pwa-bar-icon-svg {
        width: 24px;
        height: 24px;
    }

    .pwa-bar-label {
        font-size: 10px;
        font-weight: var(--font-medium);
        line-height: 1;
        white-space: nowrap;
    }

    /* Active state */
    .pwa-bar-item.active {
        color: #7c3aed;
    }

    .pwa-bar-item.active .pwa-bar-icon {
        opacity: 1;
        filter: brightness(0) saturate(100%) invert(22%) sepia(95%) saturate(4800%) hue-rotate(258deg) brightness(87%) contrast(91%);
    }

    .pwa-bar-item.active .pwa-bar-icon-svg {
        color: #7c3aed;
        opacity: 1;
    }

    /* Badge */
    .pwa-bar-badge {
        position: absolute;
        top: 2px;
        right: 50%;
        transform: translateX(14px);
        min-width: 16px;
        height: 16px;
        padding: 0 4px;
        background: #ef4444;
        color: #fff;
        font-size: 9px;
        font-weight: var(--font-bold);
        border-radius: 8px;
        display: flex;
        align-items: center;
        justify-content: center;
        line-height: 1;
    }

    /* --- Bottom Sheet --- */
    .pwa-bottom-sheet {
        display: block;
        position: fixed;
        inset: 0;
        z-index: 1001;
        visibility: hidden;
        pointer-events: none;
    }

    .pwa-bottom-sheet.open {
        visibility: visible;
        pointer-events: auto;
    }

    /* Backdrop */
    .pwa-sheet-backdrop {
        position: absolute;
        inset: 0;
        background: rgba(0, 0, 0, 0.5);
        opacity: 0;
        transition: opacity 300ms ease-out;
    }

    .pwa-bottom-sheet.open .pwa-sheet-backdrop {
        opacity: 1;
    }

    /* Panel */
    .pwa-sheet-panel {
        position: absolute;
        bottom: calc(60px + env(safe-area-inset-bottom, 0px));
        left: 0;
        right: 0;
        max-height: 60vh;
        background: #ffffff;
        border-top-left-radius: 16px;
        border-top-right-radius: 16px;
        box-shadow: 0 -4px 20px rgba(0, 0, 0, 0.15);
        transform: translateY(100%);
        transition: transform 300ms ease-out;
        overflow-y: auto;
        -webkit-overflow-scrolling: touch;
    }

    .pwa-bottom-sheet.open .pwa-sheet-panel {
        transform: translateY(0);
    }

    /* Sheet header */
    .pwa-sheet-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 16px 20px 8px;
        position: sticky;
        top: 0;
        background: inherit;
        border-top-left-radius: 16px;
        border-top-right-radius: 16px;
        z-index: 1;
    }

    .pwa-sheet-title {
        font-size: var(--text-lg);
        font-weight: var(--font-semibold);
        color: var(--text-primary);
    }

    .pwa-sheet-close {
        width: 32px;
        height: 32px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: var(--gray-100);
        border: none;
        border-radius: 50%;
        font-size: 20px;
        color: var(--text-secondary);
        cursor: pointer;
        -webkit-tap-highlight-color: transparent;
    }

    .pwa-sheet-close:active {
        background: var(--gray-200);
    }

    /* Sheet body */
    .pwa-sheet-body {
        padding: 0 8px 16px;
    }

    /* Sheet list */
    .pwa-sheet-list {
        list-style: none;
        margin: 0;
        padding: 0;
    }

    .pwa-sheet-item {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 12px;
        border-radius: var(--radius-lg);
        color: var(--text-primary);
        text-decoration: none;
        cursor: pointer;
        background: none;
        border: none;
        width: 100%;
        font-size: var(--text-base);
        -webkit-tap-highlight-color: transparent;
        transition: background var(--transition-fast);
    }

    .pwa-sheet-item:active {
        background: var(--bg-hover);
    }

    .pwa-sheet-item.active {
        color: #7c3aed;
        background: rgba(124, 58, 237, 0.08);
    }

    .pwa-sheet-icon {
        width: 22px;
        height: 22px;
        opacity: 0.7;
        flex-shrink: 0;
    }

    .pwa-sheet-item.active .pwa-sheet-icon {
        opacity: 1;
        filter: brightness(0) saturate(100%) invert(22%) sepia(95%) saturate(4800%) hue-rotate(258deg) brightness(87%) contrast(91%);
    }

    /* Sheet badge */
    .pwa-sheet-badge {
        margin-left: auto;
        min-width: 20px;
        height: 20px;
        padding: 0 6px;
        background: #ef4444;
        color: #fff;
        font-size: 11px;
        font-weight: var(--font-bold);
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    /* Accordion */
    .pwa-sheet-accordion-toggle {
        font-size: var(--text-base);
        font-family: inherit;
    }

    .pwa-sheet-chevron {
        margin-left: auto;
        transition: transform var(--transition-base);
        opacity: 0.5;
    }

    .pwa-sheet-accordion.open .pwa-sheet-chevron {
        transform: rotate(90deg);
    }

    .pwa-sheet-subitems {
        list-style: none;
        margin: 0;
        padding: 0;
        max-height: 0;
        overflow: hidden;
        transition: max-height var(--transition-slow);
    }

    .pwa-sheet-accordion.open .pwa-sheet-subitems {
        max-height: 300px;
    }

    .pwa-sheet-subitem {
        padding-left: 46px;
        font-size: var(--text-sm);
    }

    /* Divider */
    .pwa-sheet-divider {
        height: 1px;
        background: var(--border-primary);
        margin: 4px 12px;
    }

    /* Danger (logout) */
    .pwa-sheet-item-danger {
        color: var(--error);
    }

    .pwa-sheet-item-danger .pwa-sheet-icon {
        filter: brightness(0) saturate(100%) invert(36%) sepia(93%) saturate(1400%) hue-rotate(338deg) brightness(91%) contrast(97%);
    }

    /* --- Fullscreen Search (PWA adjustments) --- */
    .global-search-mobile-overlay {
        z-index: 1002 !important;
    }

    /* --- Landscape --- */
    @media (orientation: landscape) {
        .pwa-bottom-bar {
            height: calc(48px + env(safe-area-inset-bottom, 0px));
        }

        .pwa-bar-label {
            font-size: 9px;
        }

        .pwa-bar-icon,
        .pwa-bar-icon-svg {
            width: 20px;
            height: 20px;
        }

        .main-content {
            padding-bottom: calc(48px + env(safe-area-inset-bottom, 0px)) !important;
        }

        .pwa-sheet-panel {
            bottom: calc(48px + env(safe-area-inset-bottom, 0px));
        }
    }
}

/* ============================================
   Dark Mode - PWA
   ============================================ */
@media (display-mode: standalone) {
    [data-theme="dark"] .pwa-bottom-bar {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border-top-color: rgba(240, 147, 251, 0.15);
    }

    [data-theme="dark"] .pwa-bar-item {
        color: rgba(255, 255, 255, 0.5);
    }

    [data-theme="dark"] .pwa-bar-item.active {
        color: #f093fb;
    }

    [data-theme="dark"] .pwa-bar-item.active .pwa-bar-icon {
        filter: brightness(0) saturate(100%) invert(72%) sepia(50%) saturate(1000%) hue-rotate(270deg) brightness(105%) contrast(98%);
    }

    [data-theme="dark"] .pwa-bar-item.active .pwa-bar-icon-svg {
        color: #f093fb;
    }

    [data-theme="dark"] .pwa-bar-icon {
        opacity: 0.5;
        filter: brightness(0) invert(1);
    }

    [data-theme="dark"] .pwa-sheet-panel {
        background: rgba(30, 30, 50, 0.95);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border-top: 1px solid rgba(240, 147, 251, 0.15);
        box-shadow: 0 -4px 20px rgba(0, 0, 0, 0.4);
    }

    [data-theme="dark"] .pwa-sheet-close {
        background: rgba(255, 255, 255, 0.1);
        color: rgba(255, 255, 255, 0.7);
    }

    [data-theme="dark"] .pwa-sheet-close:active {
        background: rgba(255, 255, 255, 0.15);
    }

    [data-theme="dark"] .pwa-sheet-item:active {
        background: rgba(255, 255, 255, 0.08);
    }

    [data-theme="dark"] .pwa-sheet-item.active {
        color: #f093fb;
        background: rgba(240, 147, 251, 0.1);
    }

    [data-theme="dark"] .pwa-sheet-item.active .pwa-sheet-icon {
        filter: brightness(0) saturate(100%) invert(72%) sepia(50%) saturate(1000%) hue-rotate(270deg) brightness(105%) contrast(98%);
    }

    [data-theme="dark"] .pwa-sheet-icon {
        filter: brightness(0) invert(1);
        opacity: 0.6;
    }

    [data-theme="dark"] .pwa-sheet-divider {
        background: rgba(240, 147, 251, 0.15);
    }

    [data-theme="dark"] .pwa-sheet-item-danger {
        color: #f87171;
    }

    [data-theme="dark"] .pwa-sheet-item-danger .pwa-sheet-icon {
        filter: brightness(0) saturate(100%) invert(60%) sepia(50%) saturate(1500%) hue-rotate(330deg) brightness(100%) contrast(95%);
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add static/css/components/bottom-bar.css
git commit -m "feat(pwa): add bottom bar CSS with light/dark mode and sheet styles"
```

---

## Chunk 3: JavaScript

### Task 6: Create bottom bar JavaScript

**Files:**
- Create: `static/js/components/bottom-bar.js`

This file handles:
1. PWA detection and initialization (viewport-fit, aria attributes)
2. Sheet open/close with history state management
3. Accordion toggles in sheets
4. Search button → triggers existing mobile search overlay
5. Badge polling for notifications (every 60s + visibilitychange)

- [ ] **Step 1: Create the JS file**

```javascript
/**
 * PWA Bottom Navigation Bar
 * Only active in standalone (PWA) mode.
 */
(function () {
    'use strict';

    // --- PWA Detection ---
    const isPWA = window.matchMedia('(display-mode: standalone)').matches
                || window.navigator.standalone === true;

    if (!isPWA) return;  // Exit early if not PWA

    // --- Viewport fit for safe areas ---
    const viewport = document.querySelector('meta[name="viewport"]');
    if (viewport && !viewport.content.includes('viewport-fit')) {
        viewport.content += ', viewport-fit=cover';
    }

    // --- DOM References ---
    const bottomBar = document.getElementById('pwaBottomBar');
    const sheet = document.getElementById('pwaBottomSheet');
    const sheetBackdrop = document.getElementById('pwaSheetBackdrop');
    const sheetClose = document.getElementById('pwaSheetClose');
    const sheetTitle = document.getElementById('pwaSheetTitle');
    const sheetBody = document.getElementById('pwaSheetBody');
    const searchBtn = document.getElementById('pwaSearchBtn');
    const moreBtn = document.getElementById('pwaMoreBtn');
    const moreBadge = document.getElementById('pwaMoreBadge');

    if (!bottomBar || !sheet) return;

    // --- Enable bottom bar (remove aria-hidden) ---
    bottomBar.removeAttribute('aria-hidden');

    // --- Sheet titles map ---
    const sheetTitles = {
        'client-more': 'Więcej',
        'admin-more': 'Więcej',
        'admin-orders': 'Zamówienia',
        'admin-warehouse': 'Magazyn'
    };

    // --- Template ID map ---
    const sheetTemplates = {
        'client-more': 'pwaSheetClientMore',
        'admin-more': 'pwaSheetAdminMore',
        'admin-orders': 'pwaSheetAdminOrders',
        'admin-warehouse': 'pwaSheetAdminWarehouse'
    };

    // --- Sheet Open/Close ---
    let sheetOpen = false;
    let currentSheetName = null;
    let closedByPopstate = false;

    function openSheet(sheetName) {
        const templateId = sheetTemplates[sheetName];
        const template = document.getElementById(templateId);
        if (!template) return;

        sheetTitle.textContent = sheetTitles[sheetName] || '';
        sheetBody.innerHTML = '';
        sheetBody.appendChild(template.content.cloneNode(true));

        // Bind accordion toggles
        sheetBody.querySelectorAll('.pwa-sheet-accordion-toggle').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var accordion = btn.closest('.pwa-sheet-accordion');
                if (accordion) accordion.classList.toggle('open');
            });
        });

        sheet.classList.add('open');
        sheetOpen = true;
        currentSheetName = sheetName;

        // Push history state for Android back button
        history.pushState({ pwaSheet: true }, '');
    }

    function closeSheet(fromPopstate) {
        if (!sheetOpen) return;
        sheet.classList.remove('open');
        sheetOpen = false;

        // Clean up history entry if not closed by back button
        if (!fromPopstate) {
            closedByPopstate = true;
            history.back();
        }

        currentSheetName = null;
    }

    // --- Event: Sheet buttons (data-sheet attribute) ---
    bottomBar.querySelectorAll('[data-sheet]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var name = btn.getAttribute('data-sheet');
            if (sheetOpen && currentSheetName === name) {
                // Same sheet — just close
                closeSheet();
            } else if (sheetOpen) {
                // Different sheet — close then reopen
                sheet.classList.remove('open');
                sheetOpen = false;
                currentSheetName = null;
                // Reopen without extra history entry (reuse existing)
                setTimeout(function () { openSheet(name); }, 50);
            } else {
                openSheet(name);
            }
        });
    });

    // --- Event: Close sheet ---
    if (sheetClose) sheetClose.addEventListener('click', function () { closeSheet(); });
    if (sheetBackdrop) sheetBackdrop.addEventListener('click', function () { closeSheet(); });

    // --- Event: Android back button ---
    window.addEventListener('popstate', function (e) {
        if (closedByPopstate) {
            closedByPopstate = false;
            return;  // Ignore — triggered by our own history.back()
        }
        if (sheetOpen) {
            closeSheet(true);
        }
    });

    // --- Event: Search button ---
    if (searchBtn) {
        searchBtn.addEventListener('click', function () {
            // Trigger existing mobile search overlay
            var overlay = document.getElementById('globalSearchMobileOverlay');
            var input = document.getElementById('globalSearchMobileInput');
            if (overlay) {
                overlay.classList.add('active');
                if (input) {
                    setTimeout(function () { input.focus(); }, 100);
                }
            }
        });
    }

    // --- Notification Badge Polling ---
    function updateBadge() {
        fetch('/notifications/unread-count', {
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            var count = data.count || 0;
            // Bottom bar badge
            if (moreBadge) {
                moreBadge.textContent = count;
                moreBadge.style.display = count > 0 ? 'flex' : 'none';
            }
            // Sheet badge (if open)
            var sheetBadge = document.getElementById('pwaSheetNotifBadge');
            if (sheetBadge) {
                sheetBadge.textContent = count;
                sheetBadge.style.display = count > 0 ? 'flex' : 'none';
            }
        })
        .catch(function () { /* silent fail */ });
    }

    // Poll every 60 seconds
    updateBadge();
    setInterval(updateBadge, 60000);

    // Also update on visibility change
    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'visible') {
            updateBadge();
        }
    });

})();
```

- [ ] **Step 2: Commit**

```bash
git add static/js/components/bottom-bar.js
git commit -m "feat(pwa): add bottom bar JS — sheet logic, search, badge polling"
```

---

## Chunk 4: Manual Testing

### Task 7: Test in PWA mode

- [ ] **Step 1: Start local dev server**

Run: `flask run --port 5001`

- [ ] **Step 2: Test in browser (should see NO changes)**

Open `http://localhost:5001` in Safari/Chrome. Verify:
- Sidebar visible, topbar visible
- No bottom bar visible
- Everything works as before

- [ ] **Step 3: Test PWA mode**

To simulate PWA standalone mode locally without installing:

**Option A — Chrome DevTools:**
1. Open Chrome → DevTools → Application → Manifest
2. Or override via CSS: temporarily change `@media (display-mode: standalone)` to `@media (display-mode: browser)` to test styles

**Option B — Install PWA:**
1. In Chrome: Menu → "Install ThunderOrders"
2. Open the installed app
3. Verify: sidebar hidden, topbar hidden, bottom bar visible

- [ ] **Step 4: Test all interactions**

In PWA mode, verify:
1. Bottom bar shows 5 icons with correct labels
2. Direct link icons navigate correctly
3. "Szukaj" opens fullscreen search overlay
4. "Więcej" opens bottom sheet with all items
5. Sheet X button closes sheet
6. Sheet backdrop tap closes sheet
7. Accordion items expand/collapse
8. Sheet items navigate to correct pages
9. Active state highlights correct icon
10. Badge shows unread notification count
11. Dark mode: all styles correct (glassmorphism)
12. Light mode: all styles correct

- [ ] **Step 5: Test admin panel**

Switch to admin view and repeat step 4, additionally:
1. "Zamówienia" icon opens sheet with 5 sub-options
2. "Magazyn" icon opens sheet with 3 sub-options
3. Active state on Zamówienia/Magazyn icons when on sub-pages

- [ ] **Step 6: Final commit (if any fixes were needed)**

```bash
git add templates/components/bottom_bar_client.html templates/components/bottom_bar_admin.html templates/components/bottom_sheet.html static/css/components/bottom-bar.css static/js/components/bottom-bar.js templates/admin/base_admin.html templates/client/base_client.html templates/base.html
git commit -m "fix(pwa): adjustments after manual testing"
```
