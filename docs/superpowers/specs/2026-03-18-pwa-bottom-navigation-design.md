# PWA Bottom Navigation Bar — Design Spec

**Date:** 2026-03-18
**Status:** Approved

---

## Overview

Replace sidebar + topbar with a native app-style bottom navigation bar **only in PWA standalone mode**. Browser (including mobile browser) keeps the existing sidebar/topbar unchanged.

## Detection

- CSS: `@media (display-mode: standalone)`
- JS: `window.matchMedia('(display-mode: standalone)').matches`

## What Changes in PWA Mode

| Component | PWA Standalone | Browser |
|-----------|---------------|---------|
| Topbar | Hidden (`display: none`) | No change |
| Sidebar | Hidden (`display: none`) | No change |
| Sidebar backdrop | Hidden | No change |
| Bottom bar | Visible (new) | Hidden (`display: none`, also `aria-hidden="true"` for accessibility) |
| Content area | Full height, `padding-bottom` for bar | No change |

## Bottom Bar

### Layout
- `position: fixed; bottom: 0; width: 100%`
- Height: ~60px + `env(safe-area-inset-bottom)` for iPhone notch/home indicator
- 5 icons in equal-width columns with icon + label (~10px) below
- Glassmorphism in dark mode (matching existing sidebar style), white with top shadow in light mode
- `z-index` above content, below sheets
- Icons reuse existing SVG icons from `static/img/icons/` (same as sidebar)

### Client Icons (left to right)
1. **Dashboard** — direct link → `client.dashboard` (icon: `dashboard.svg`)
2. **Zamówienia** — direct link → `orders.client_list` (icon: `orders.svg`)
3. **Szukaj** — opens fullscreen search overlay (icon: magnifying glass inline SVG)
4. **Potwierdzenia** — direct link → `client.payment_confirmations` (icon: `payment.svg`)
5. **Więcej** — opens bottom sheet (icon: three dots/hamburger inline SVG, badge with unread notification count)

### Admin Icons (left to right)
1. **Dashboard** — direct link → `admin.dashboard` (icon: `dashboard.svg`)
2. **Zamówienia** — opens bottom sheet with sub-options (icon: `orders.svg`):
   - Lista zamówień → `orders.admin_list`
   - WMS / Wysyłka → `orders.wms_dashboard`
   - Potwierdzenia płatności → `admin.payment_confirmations_list`
   - Exclusive → `admin.exclusive_list`
   - Ustawienia → `orders.settings`
3. **Szukaj** — opens fullscreen search overlay (icon: magnifying glass inline SVG)
4. **Magazyn** — opens bottom sheet with sub-options (icon: `warehouse.svg`):
   - Lista produktów → `products.list_products`
   - Zamówienia produktów → `products.stock_orders`
   - Ustawienia → `products.warehouse_settings`
5. **Więcej** — opens bottom sheet (icon: three dots/hamburger inline SVG, badge with unread notification count)

### Active State
- Active page: icon + label colored with accent (`#f093fb` dark, `#7c3aed` light)
- Inactive: `#9ca3af` (light), `rgba(255, 255, 255, 0.5)` (dark)
- If current page is a sub-option of a category (e.g. Zamówienia), that category icon is active

### Moderator Role
- Moderators use the **Admin** bottom bar layout (same navigation items)

## Bottom Sheet

### Appearance
- Slides up from bottom (`transform: translateY(100%)` → `translateY(0%)`)
- Animation: 300ms ease-out
- Backdrop: semi-transparent overlay (`rgba(0,0,0,0.5)`), click to close
- **X button** in top-right corner to close
- Max height: ~60% viewport (bottom bar visible underneath)
- Rounded top corners (~16px `border-radius`)
- Glassmorphism in dark mode, white background in light mode

### "Więcej" Sheet — Client
1. Powiadomienia (with unread badge, from `/notifications/unread-count`)
2. Kolekcja → `client.collection_list`
3. Osiągnięcia → `achievements.gallery`
4. Wysyłka → accordion expands: Zlecenia (`client.shipping_requests_list`), Adresy dostaw (`client.shipping_addresses`)
5. Profil → `profile.index`
6. Wyloguj się → `auth.logout`

### "Więcej" Sheet — Admin
1. Powiadomienia (with unread badge)
2. Użytkownicy → `admin.clients_list`
3. Statystyki → `admin.statistics`
4. Moje zadania → `admin.tasks_list`
5. Komunikacja → accordion expands: Feedback (`feedback.admin_list`), Popupy (`admin.popups_list`), Powiadomienia (`admin.broadcasts_list`), QR Tracking (`tracking.qr_campaigns_list`)
6. Profil → `profile.index`
7. Wyloguj się → `auth.logout`

### Category Sheets (Admin: Zamówienia, Magazyn)
- Header with category name + X close button
- List of sub-options with icons (matching sidebar icons)
- Same visual style as "Więcej" sheet

### Sheet Items
- Icon + name (same as sidebar)
- Items with sub-menu: `>` arrow on right, click expands accordion inline
- Click on item → close sheet → navigate to page

## Fullscreen Search Overlay

- Triggered by "Szukaj" icon in bottom bar
- Full screen overlay with input at top + results below
- Reuses the existing `globalSearchMobileOverlay` from `topbar.html` — the DOM element is repurposed for PWA mode (same search logic from `global-search.js`)
- Close: X button in corner or back gesture

## Edge Cases

### Back Gesture / History
- When a sheet opens, push a state via `history.pushState()` — this allows Android's back button to close the sheet via `popstate` event
- On iOS PWA (no native back gesture in standalone), user closes via X button or backdrop tap

### Safe Areas (iPhone)
- `padding-bottom: env(safe-area-inset-bottom)` on bottom bar
- `viewport-fit=cover` added to viewport meta **only in PWA mode** via JS (`meta` tag attribute update on load) to avoid affecting browser mode layout

### Landscape Orientation
- Bottom bar reduced height (~48px)
- Sheet max-height adjusted

### Existing Features
- `sidebar_collapsed` user preference: ignored in PWA mode
- Dark mode: works via existing `data-theme` attribute, toggle accessible via Profile
- Push notifications: unchanged (service worker)
- Notification badge on "Więcej": fetched from `/notifications/unread-count` every 60 seconds + on `visibilitychange` event when page becomes visible

### Accessibility
- Bottom bar HTML is always in DOM (Jinja2 include) but hidden in browser mode with `display: none` + `aria-hidden="true"`
- In PWA mode: `aria-hidden` removed, proper `role="navigation"` and `aria-label` attributes

## New Files

| File | Purpose |
|------|---------|
| `templates/components/bottom_bar_client.html` | Client bottom bar HTML |
| `templates/components/bottom_bar_admin.html` | Admin bottom bar HTML |
| `templates/components/bottom_sheet.html` | Reusable sheet component |
| `static/css/components/bottom-bar.css` | All bottom bar + sheet + search overlay styles (light + dark) |
| `static/js/components/bottom-bar.js` | Bottom bar logic, sheet open/close, search overlay, badge polling, history state management |

## Modified Files

| File | Change |
|------|--------|
| `templates/base.html` | Include bottom bar + sheet templates |
| `templates/admin/base_admin.html` | Include admin bottom bar template |
| `templates/client/base_client.html` | Include client bottom bar template |
| `static/css/components/sidebar.css` | Add `display: none` rule for `@media (display-mode: standalone)` |
| `static/css/components/topbar.css` | Add `display: none` rule for `@media (display-mode: standalone)` |

## Design Tokens

### Light Mode
- Bar background: `#ffffff`
- Bar border-top: `1px solid #e0e0e0`
- Active icon/label: `#7c3aed`
- Inactive icon/label: `#9ca3af`
- Sheet background: `#ffffff`
- Sheet border-top: `1px solid #e0e0e0`

### Dark Mode
- Bar background: `rgba(255, 255, 255, 0.05)` with `backdrop-filter: blur(20px)`
- Bar border-top: `1px solid rgba(240, 147, 251, 0.15)`
- Active icon/label: `#f093fb`
- Inactive icon/label: `rgba(255, 255, 255, 0.5)`
- Sheet background: `rgba(30, 30, 50, 0.95)` with `backdrop-filter: blur(20px)`
- Sheet border: `1px solid rgba(240, 147, 251, 0.15)`
