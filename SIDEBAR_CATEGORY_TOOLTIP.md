# Sidebar Category Tooltip - Dokumentacja

## Opis
Uniwersalny system tooltipów dla kategorii z podkategoriami w sidebarze. Gdy sidebar jest zwinięty (collapsed), po najechaniu myszą na kategorię wyświetla się chmurka z nazwą kategorii i listą podkategorii.

## Cechy
- ✅ Tooltip z nagłówkiem kategorii
- ✅ Lista klikanych podkategorii
- ✅ Strzałka (ogonek) wskazująca na ikonę
- ✅ Natychmiastowe wyświetlanie (bez opóźnienia)
- ✅ Wycentrowana ikona w collapsed sidebar
- ✅ Aktywne podświetlenie dla wybranej podkategorii

## Jak dodać tooltip do nowej kategorii?

### 1. HTML Structure (sidebar_admin.html)

```html
<li class="sidebar-item sidebar-category">
    <!-- Header kategorii -->
    <div class="sidebar-category-header" onclick="toggleSidebarCategory(this)" data-tooltip="Nazwa Kategorii">
        <div class="sidebar-category-main">
            <img src="{{ url_for('static', filename='img/icons/twoja-ikona.svg') }}" alt="Nazwa" class="sidebar-icon">
            <span class="sidebar-text">Nazwa Kategorii</span>
        </div>
        <svg class="category-chevron" width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
            <path fill-rule="evenodd" d="M1.646 4.646a.5.5 0 01.708 0L8 10.293l5.646-5.647a.5.5 0 01.708.708l-6 6a.5.5 0 01-.708 0l-6-6a.5.5 0 010-.708z"/>
        </svg>
    </div>

    <!-- Lista podkategorii - WAŻNE: data-category-name musi być taki sam jak nazwa kategorii -->
    <ul class="sidebar-subcategories" data-category-name="Nazwa Kategorii">
        <li class="sidebar-subitem">
            <a href="{{ url_for('blueprint.route1') }}"
               class="sidebar-sublink {% if request.endpoint == 'blueprint.route1' %}active{% endif %}"
               data-tooltip="Podkategoria 1">
                <span class="sidebar-text">Podkategoria 1</span>
            </a>
        </li>
        <li class="sidebar-subitem">
            <a href="{{ url_for('blueprint.route2') }}"
               class="sidebar-sublink {% if request.endpoint == 'blueprint.route2' %}active{% endif %}"
               data-tooltip="Podkategoria 2">
                <span class="sidebar-text">Podkategoria 2</span>
            </a>
        </li>
    </ul>
</li>
```

### 2. Kluczowe atrybuty

| Atrybut | Element | Opis |
|---------|---------|------|
| `data-tooltip` | `.sidebar-category-header` | Nazwa kategorii dla tooltipa (gdy sidebar zwinięty) |
| `data-category-name` | `.sidebar-subcategories` | Nazwa kategorii wyświetlana jako nagłówek w tooltipie |
| `class="sidebar-category"` | `<li>` | Główna klasa kategorii - **wymagana** |
| `onclick="toggleSidebarCategory(this)"` | `.sidebar-category-header` | Funkcja JS dla rozwijania/zwijania (w rozwiniętym sidebar) |

### 3. Aktywne podświetlenie

Aby podkategoria była podświetlona jako aktywna:

```html
class="sidebar-sublink {% if request.endpoint == 'twoj.endpoint' %}active{% endif %}"
```

**WAŻNE:** Używaj **dokładnego** dopasowania endpoint (`==`), a nie częściowego (`in`), aby uniknąć podświetlania całej kategorii.

## Przykład (kategoria "Magazyn")

```html
<li class="sidebar-item sidebar-category">
    <div class="sidebar-category-header" onclick="toggleSidebarCategory(this)" data-tooltip="Magazyn">
        <div class="sidebar-category-main">
            <img src="{{ url_for('static', filename='img/icons/warehouse.svg') }}" alt="Magazyn" class="sidebar-icon">
            <span class="sidebar-text">Magazyn</span>
        </div>
        <svg class="category-chevron" width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
            <path fill-rule="evenodd" d="M1.646 4.646a.5.5 0 01.708 0L8 10.293l5.646-5.647a.5.5 0 01.708.708l-6 6a.5.5 0 01-.708 0l-6-6a.5.5 0 010-.708z"/>
        </svg>
    </div>
    <ul class="sidebar-subcategories" data-category-name="Magazyn">
        <li class="sidebar-subitem">
            <a href="{{ url_for('products.list_products') }}"
               class="sidebar-sublink {% if request.endpoint == 'products.list_products' %}active{% endif %}"
               data-tooltip="Lista produktów">
                <span class="sidebar-text">Lista produktów</span>
            </a>
        </li>
        <li class="sidebar-subitem">
            <a href="{{ url_for('products.warehouse_settings') }}"
               class="sidebar-sublink {% if request.endpoint == 'products.warehouse_settings' %}active{% endif %}"
               data-tooltip="Ustawienia">
                <span class="sidebar-text">Ustawienia</span>
            </a>
        </li>
    </ul>
</li>
```

## CSS Classes - Automatyczne działanie

Wszystkie style są już zdefiniowane w `static/css/components/sidebar.css`. Po dodaniu odpowiedniej struktury HTML, tooltip będzie działał automatycznie:

### Klasy CSS:
- `.sidebar-category` - główny kontener kategorii
- `.sidebar-category-header` - header kategorii (z ikoną i nazwą)
- `.sidebar-category-main` - kontener ikony i tekstu
- `.category-chevron` - strzałka rozwijania (ukryta w collapsed state)
- `.sidebar-subcategories` - kontener podkategorii
- `.sidebar-subitem` - pojedyncza podkategoria
- `.sidebar-sublink` - link podkategorii
- `.tooltip-visible` - dodawana przez JS podczas hover (pokazuje strzałkę)

### Stany:
- `.expanded` - kategoria rozwinięta (w rozwiniętym sidebar)
- `.active` - aktywna podkategoria
- `[data-collapsed="true"]` - sidebar zwinięty (tooltips widoczne)

## JavaScript

### Funkcje w `static/js/components/sidebar.js`:

1. **`toggleSidebarCategory(headerElement)`** - Rozwijanie/zwijanie kategorii (tylko gdy sidebar rozwinięty)
2. **`setupCategoryTooltips()`** - Obsługa tooltipów w collapsed sidebar
   - Dodaje event listenery `mouseenter`/`mouseleave` na każdej kategorii
   - Wyświetla tooltip przez inline styles (opacity, visibility, pointer-events)
   - Dodaje klasę `.tooltip-visible` do pokazania strzałki (::before)
   - **AUTOMATYCZNE:** Wywoływane w `DOMContentLoaded`

## Troubleshooting

### Problem: Tooltip się nie wyświetla
- Sprawdź czy `<li>` ma klasę `sidebar-category`
- Sprawdź czy `<ul>` ma atrybut `data-category-name`
- Sprawdź czy sidebar jest zwinięty (`data-collapsed="true"`)

### Problem: Ikona nie jest wycentrowana
- Upewnij się że ikona jest w `.sidebar-category-main`
- CSS automatycznie centruje ikony w collapsed state

### Problem: Podświetla się cała kategoria zamiast tylko podkategorii
- Zmień warunek z `'endpoint' in request.endpoint` na `request.endpoint == 'exact.endpoint'`

## Wizualizacja

```
┌─────────────────────────────────────────────────────┐
│  Sidebar (collapsed)                                │
│  ┌──────┐                                           │
│  │ icon │ ───► ◄──────────────────────────┐        │
│  └──────┘     │  ┌─────────────────────┐  │        │
│               │  │ MAGAZYN             │  │        │
│               │  ├─────────────────────┤  │        │
│               └──┤ Lista produktów     │  │        │
│                  │ Ustawienia          │  │        │
│                  └─────────────────────┘  │        │
│                        Tooltip            │        │
│                                            │        │
└────────────────────────────────────────────┘
         ◄── Strzałka (ogonek)
```

## Notatki
- Tooltip pojawia się **natychmiast** (bez animacji/delay)
- Strzałka jest wycentrowana z wysokością ikony
- Szerokość tooltipa: minimum 200px
- Ostatnia podkategoria ma zaokrąglone rogi na dole (border-radius)
