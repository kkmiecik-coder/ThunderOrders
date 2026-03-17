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
| Bottom bar | Visible (new) | Hidden |
| Content area | Full height, `padding-bottom` for bar | No change |

## Bottom Bar

### Layout
- `position: fixed; bottom: 0; width: 100%`
- Height: ~60px + `env(safe-area-inset-bottom)` for iPhone notch/home indicator
- 5 icons in equal-width columns with icon + label (~10px) below
- Glassmorphism in dark mode (matching existing sidebar style), white with top shadow in light mode
- `z-index` above content, below sheets

### Client Icons (left to right)
1. **Dashboard** — direct link
2. **Moje zamówienia** — direct link
3. **Szukaj** — opens fullscreen search overlay
4. **Potwierdzenia** — direct link
5. **Więcej** — opens bottom sheet (badge with unread notification count)

### Admin Icons (left to right)
1. **Dashboard** — direct link
2. **Zamówienia** — opens bottom sheet with sub-options (Wszystkie zamówienia, Zlecenia wysyłki, Potwierdzenia płatności, Zwroty, Koszty wysyłki)
3. **Szukaj** — opens fullscreen search overlay
4. **Magazyn** — opens bottom sheet with sub-options (Produkty, Zamówienia proxy, Zamówienia Polska)
5. **Więcej** — opens bottom sheet (badge with unread notification count)

### Active State
- Active page: icon + label colored with accent (`#f093fb` dark, primary color light)
- Inactive: gray color
- If current page is a sub-option of a category (e.g. Zamówienia), that category icon is active

## Bottom Sheet

### Appearance
- Slides up from bottom (`transform: translateY(100%)` → `translateY(0%)`)
- Backdrop: semi-transparent overlay, click to close
- **X button** in top-right corner to close
- Max height: ~60% viewport (bottom bar visible underneath)
- Rounded top corners (~16px `border-radius`)
- Glassmorphism in dark mode, white background in light mode

### "Więcej" Sheet — Client
1. Powiadomienia (with unread badge, from `/notifications/unread-count`)
2. Kolekcja
3. Osiągnięcia
4. Wysyłka → accordion expands: Zlecenia wysyłki, Adresy dostawy
5. Profil
6. Wyloguj się

### "Więcej" Sheet — Admin
1. Powiadomienia (with unread badge)
2. Użytkownicy
3. Statystyki
4. Moje zadania
5. Komunikacja → accordion expands: Ogłoszenia, Feedback, QR Tracking, Maile
6. Profil

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
- Same search mechanism as existing topbar search
- Close: X button in corner or back gesture

## Edge Cases

### Back Gesture / History
- If sheet is open, back gesture closes sheet instead of navigating back

### Safe Areas (iPhone)
- `padding-bottom: env(safe-area-inset-bottom)` on bottom bar
- `viewport-fit=cover` in viewport meta tag

### Landscape Orientation
- Bottom bar reduced height (~48px)
- Sheet max-height adjusted

### Existing Features
- `sidebar_collapsed` user preference: ignored in PWA mode
- Dark mode: works via existing `data-theme` attribute, toggle accessible via Profile
- Push notifications: unchanged (service worker)
- Notification badge on "Więcej": polls `/notifications/unread-count`

## New Files

| File | Purpose |
|------|---------|
| `templates/components/bottom_bar_client.html` | Client bottom bar HTML |
| `templates/components/bottom_bar_admin.html` | Admin bottom bar HTML |
| `templates/components/bottom_sheet.html` | Reusable sheet component |
| `static/css/components/bottom-bar.css` | All bottom bar + sheet styles (light + dark) |
| `static/js/components/bottom-bar.js` | Bottom bar logic, sheet open/close, search overlay, badge polling |

## Modified Files

| File | Change |
|------|--------|
| `templates/base.html` | Add `viewport-fit=cover` to meta viewport |
| `templates/admin/base_admin.html` | Include bottom bar template |
| `templates/client/base_client.html` | Include bottom bar template |
| `static/css/components/sidebar.css` | Add `display: none` rule for PWA standalone |
| `static/css/components/topbar.css` | Add `display: none` rule for PWA standalone |

## Design Tokens

### Light Mode
- Bar background: `#ffffff`
- Bar border-top: `1px solid #e0e0e0`
- Active icon: primary color
- Inactive icon: `#9ca3af`
- Sheet background: `#ffffff`

### Dark Mode
- Bar background: `rgba(255, 255, 255, 0.05)` with `backdrop-filter: blur(20px)`
- Bar border-top: `1px solid rgba(240, 147, 251, 0.15)`
- Active icon: `#f093fb`
- Inactive icon: `rgba(255, 255, 255, 0.5)`
- Sheet background: `rgba(30, 30, 50, 0.95)` with `backdrop-filter: blur(20px)`
- Sheet border: `1px solid rgba(240, 147, 251, 0.15)`
