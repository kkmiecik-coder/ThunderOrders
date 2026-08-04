# Drag and drop zdjęć produktów — plan implementacji

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dodać przeciąganie plików (drag&drop) na sloty zdjęć w edycji masowej produktów i w formularzu pojedynczego produktu (modal), oraz odroczyć usuwanie istniejącego zdjęcia w tym formularzu do momentu zapisu.

**Architecture:** Czysty frontend (JS + CSS + drobna zmiana szablonu HTML), zero zmian w backendzie. Wykorzystujemy natywne zdarzenia HTML5 `dragover`/`dragleave`/`drop` (bez żadnej biblioteki), refaktorując istniejące funkcje obsługi zdjęć tak, żeby jedna wspólna funkcja obsługiwała zarówno klik, jak i przeciągnięcie pliku.

**Tech Stack:** Vanilla JS (bez frameworka), Jinja2, CSS z konwencją projektu (zmienne `var(--...)` dla trybu jasnego, `[data-theme="dark"]` dla ciemnego).

## Global Constraints

- Zero zmian w backendzie (Python/routes) — cała praca w `static/js/`, `static/css/`, `templates/`.
- Projekt nie ma testów JS (brak jesta/playwrighta) — weryfikacja każdego kroku jest ręczna w przeglądarce (dev server + DevTools console), zamiast `pytest`. Kroki "Verify" w tym planie zawierają gotowe polecenia do wklejenia w konsolę przeglądarki, symulujące prawdziwe przeciągnięcie pliku przez syntetyczne zdarzenie `drop` z obiektem `DataTransfer` (prawdziwego przeciągnięcia z dysku nie da się zeskryptować).
- Gałąź: `feat/drag-and-drop-zdjecia-produktow` (już utworzona, zawiera commity ze specyfikacją w `docs/superpowers/specs/2026-08-03-drag-drop-zdjecia-produktow-design.md`).
- Commity po polsku, konwencja `feat(produkty): ...` / `refactor(produkty): ...`, zgodnie z historią repo.
- Nie ruszamy `templates/admin/warehouse/product_form.html` / `#images-grid` / `uploadImages()`/`deleteImage()`/`setPrimaryImage()` — ten szablon nie jest renderowany z żadnego miejsca w aplikacji (potwierdzone grepem po `url_for('products.edit_product'`/`create_product'` w `templates/`).
- Serwer deweloperski: uruchamiany przez `mcp__Claude_Browser__preview_start` (nigdy przez Bash) — jeśli `.claude/launch.json` nie ma jeszcze wpisu na uruchomienie Flaska, dodaj go przed weryfikacją w przeglądarce (sprawdź istniejący plik, zwykle `python app.py` albo `flask run` na porcie z `.env`/configu).

---

## Plik: `static/js/pages/admin/mass-edit.js` — stan przed zmianami

- `pendingImageUploads` (obiekt `{productId: {slot: File}}`) i `pendingImageRemovals` (tablica `{productId, slot}`) — zadeklarowane linie 30-31, używane przez istniejący flush zapisu (linie ok. 916-1013). Task 1-3 tego nie ruszają, tylko dopisują nowe funkcje obok.
- `renderImageCell(product, slot)` (linie 522-542) — renderuje `<div class="image-slot ...">` bez `id` na wrapperze.
- `handleImageSelect(productId, slot, input)` (linie 709-732) — jedyna dziś droga przypisania pliku do slotu.
- `selectedColumns` (globalna, linia 25) — tablica kolumn aktualnie widocznych w arkuszu; kolumny obrazków mają `type: 'image'` i `slot: <number>` (patrz `getSelectedColumns()`, linia 166-169).

## Task 1: Mass edit — wydzielenie `assignImageFile()` (refaktor bez zmiany zachowania)

**Files:**
- Modify: `static/js/pages/admin/mass-edit.js:522-542` (renderImageCell — dodanie `id` do wrappera)
- Modify: `static/js/pages/admin/mass-edit.js:709-732` (handleImageSelect — wydzielenie logiki)

**Interfaces:**
- Produces: `assignImageFile(productId: number, slot: number, file: File): void` — używane przez Task 2/3 (drag&drop) i przez `handleImageSelect`. `renderImageCell` renderuje teraz slot z `id="slot-${productId}-${slot}"`, na czym opiera się `assignImageFile` (Task 2/3 też z tego korzystają).

- [ ] **Step 1: Zmodyfikuj `renderImageCell`, żeby wrapper miał stabilne `id`**

Zamień całą funkcję (linie 522-542) na:

```javascript
function renderImageCell(product, slot) {
    const pid = product.id;
    const imgData = product.images && product.images[String(slot)];
    const fileInputId = `img-${pid}-${slot}`;
    const slotId = `slot-${pid}-${slot}`;

    if (imgData) {
        const imgSrc = imgData.path_compressed.startsWith('static/') ? '/' + imgData.path_compressed : '/static/' + imgData.path_compressed;
        return `<div class="image-slot has-image" id="${slotId}">
            <img src="${imgSrc}" alt="" onclick="document.getElementById('${fileInputId}').click()">
            <span class="image-remove" onclick="removeImage(${pid}, ${slot}, event)" title="Usuń zdjęcie">&times;</span>
            <input type="file" id="${fileInputId}" accept="image/*" style="display:none"
                   onchange="handleImageSelect(${pid}, ${slot}, this)">
        </div>`;
    }

    return `<div class="image-slot empty" id="${slotId}" onclick="document.getElementById('${fileInputId}').click()">
        +
        <input type="file" id="${fileInputId}" accept="image/*" style="display:none"
               onchange="handleImageSelect(${pid}, ${slot}, this)">
    </div>`;
}
```

- [ ] **Step 2: Wydziel `assignImageFile()` z `handleImageSelect()`**

Zamień całą funkcję `handleImageSelect` (linie 709-732) na:

```javascript
function assignImageFile(productId, slot, file) {
    if (!file) return;

    if (!pendingImageUploads[productId]) pendingImageUploads[productId] = {};
    pendingImageUploads[productId][slot] = file;

    // Remove from pending removals if it was marked for deletion
    pendingImageRemovals = pendingImageRemovals.filter(
        r => !(r.productId === productId && r.slot === slot)
    );

    const reader = new FileReader();
    reader.onload = function(e) {
        const slotDiv = document.getElementById(`slot-${productId}-${slot}`);
        if (!slotDiv) return;
        slotDiv.className = 'image-slot has-image';
        slotDiv.innerHTML = `<img src="${e.target.result}" alt="" onclick="document.getElementById('img-${productId}-${slot}').click()">
            <span class="image-remove" onclick="removeImage(${productId}, ${slot}, event)" title="Usuń zdjęcie">&times;</span>
            <input type="file" id="img-${productId}-${slot}" accept="image/*" style="display:none"
                   onchange="handleImageSelect(${productId}, ${slot}, this)">`;
    };
    reader.readAsDataURL(file);
}

function handleImageSelect(productId, slot, input) {
    if (!input.files || !input.files[0]) return;
    assignImageFile(productId, slot, input.files[0]);
}
```

- [ ] **Step 3: Uruchom serwer deweloperski i zweryfikuj brak regresji ręcznie**

Otwórz w przeglądarce (`mcp__Claude_Browser__preview_start` + `navigate`) `/admin/products/mass-edit` z zaznaczonymi produktami, włącz przynajmniej jedną kolumnę "Zdjęcie N" w ustawieniach kolumn, kliknij pusty slot i wybierz plik obrazka z dysku.

Oczekiwane zachowanie (identyczne jak przed zmianą): podgląd zdjęcia pojawia się natychmiast w komórce, `.image-slot` zmienia klasę na `has-image`. Sprawdź w konsoli (`mcp__Claude_Browser__javascript_tool`):

```javascript
Object.keys(pendingImageUploads)
```

Oczekiwany wynik: tablica zawierająca ID produktu, dla którego wybrano plik (potwierdza, że staging działa jak dawniej).

- [ ] **Step 4: Commit**

```bash
git add static/js/pages/admin/mass-edit.js
git commit -m "refactor(produkty): wydziel assignImageFile w edycji masowej zdjęć"
```

---

## Task 2: Mass edit — drag&drop pojedynczego pliku na slot + podświetlenie

**Files:**
- Modify: `static/js/pages/admin/mass-edit.js` (renderImageCell — atrybuty drag, nowa funkcja `handleImageDrop`)
- Modify: `static/css/pages/admin/mass-edit.css:486-546`

**Interfaces:**
- Consumes: `assignImageFile(productId, slot, file)` z Task 1.
- Produces: `handleImageDrop(productId: number, slot: number, event: DragEvent): void` — rozszerzana w Task 3 o obsługę wielu plików.

- [ ] **Step 1: Dodaj atrybuty drag&drop w `renderImageCell`**

W `static/js/pages/admin/mass-edit.js`, zamień funkcję `renderImageCell` (efekt Task 1) na wersję z atrybutami `ondragover`/`ondragleave`/`ondrop`:

```javascript
function renderImageCell(product, slot) {
    const pid = product.id;
    const imgData = product.images && product.images[String(slot)];
    const fileInputId = `img-${pid}-${slot}`;
    const slotId = `slot-${pid}-${slot}`;
    const dragAttrs = `ondragover="event.preventDefault(); this.classList.add('drag-over')"
            ondragleave="this.classList.remove('drag-over')"
            ondrop="handleImageDrop(${pid}, ${slot}, event)"`;

    if (imgData) {
        const imgSrc = imgData.path_compressed.startsWith('static/') ? '/' + imgData.path_compressed : '/static/' + imgData.path_compressed;
        return `<div class="image-slot has-image" id="${slotId}" ${dragAttrs}>
            <img src="${imgSrc}" alt="" onclick="document.getElementById('${fileInputId}').click()">
            <span class="image-remove" onclick="removeImage(${pid}, ${slot}, event)" title="Usuń zdjęcie">&times;</span>
            <input type="file" id="${fileInputId}" accept="image/*" style="display:none"
                   onchange="handleImageSelect(${pid}, ${slot}, this)">
        </div>`;
    }

    return `<div class="image-slot empty" id="${slotId}" ${dragAttrs} onclick="document.getElementById('${fileInputId}').click()">
        +
        <input type="file" id="${fileInputId}" accept="image/*" style="display:none"
               onchange="handleImageSelect(${pid}, ${slot}, this)">
    </div>`;
}
```

- [ ] **Step 2: Dodaj `handleImageDrop()` (wersja jednoplikowa)**

Dodaj poniższą funkcję zaraz po `handleImageSelect` w `static/js/pages/admin/mass-edit.js`:

```javascript
function handleImageDrop(productId, slot, event) {
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.classList.remove('drag-over');

    const files = Array.from(event.dataTransfer.files).filter(f => f.type.startsWith('image/'));
    if (files.length === 0) return;

    assignImageFile(productId, slot, files[0]);
}
```

- [ ] **Step 3: Dodaj CSS podświetlenia**

W `static/css/pages/admin/mass-edit.css`, zaraz po bloku `.image-slot.has-image:hover` (linia 524, przed sekcją `IMAGE CELLS` kończącą się na linii 546), dodaj:

```css
.image-slot.drag-over {
    border-color: var(--primary-color);
    box-shadow: 0 0 0 2px var(--primary-color);
}
```

- [ ] **Step 4: Zweryfikuj w przeglądarce**

Otwórz `/admin/products/mass-edit`, włącz kolumnę "Zdjęcie 1", w konsoli (`mcp__Claude_Browser__javascript_tool`) uruchom (podmień `PID` na realne ID pierwszego produktu w arkuszu, widoczne w kolumnie ID):

```javascript
(function() {
    const PID = /* wstaw ID pierwszego produktu z kolumny ID w arkuszu */ 0;
    const slot = document.getElementById(`slot-${PID}-1`);
    const blob = new Blob(['test'], {type: 'image/png'});
    const file = new File([blob], 'test.png', {type: 'image/png'});
    const dt = new DataTransfer();
    dt.items.add(file);
    const evt = new DragEvent('drop', {bubbles: true, cancelable: true});
    Object.defineProperty(evt, 'dataTransfer', {value: dt});
    slot.dispatchEvent(evt);
    return slot.className;
})();
```

Oczekiwany wynik: `"image-slot has-image"` (podgląd testowego pliku pojawił się w slocie), oraz `pendingImageUploads[PID]['1']` w konsoli zwraca obiekt `File` o nazwie `test.png`.

- [ ] **Step 5: Commit**

```bash
git add static/js/pages/admin/mass-edit.js static/css/pages/admin/mass-edit.css
git commit -m "feat(produkty): drag&drop pojedynczego zdjęcia w edycji masowej"
```

---

## Task 3: Mass edit — rozkładanie wielu upuszczonych plików na wolne sloty

**Files:**
- Modify: `static/js/pages/admin/mass-edit.js` (rozszerzenie `handleImageDrop`, nowa funkcja `distributeExtraImages`)

**Interfaces:**
- Consumes: `assignImageFile` (Task 1), `selectedColumns` (globalna tablica kolumn), `handleImageDrop` (Task 2, rozszerzane tutaj).
- Produces: `distributeExtraImages(productId: number, droppedSlot: number, files: File[]): void`.

- [ ] **Step 1: Rozszerz `handleImageDrop` i dodaj `distributeExtraImages`**

Zamień `handleImageDrop` z Task 2 na:

```javascript
function handleImageDrop(productId, slot, event) {
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.classList.remove('drag-over');

    const files = Array.from(event.dataTransfer.files).filter(f => f.type.startsWith('image/'));
    if (files.length === 0) return;

    assignImageFile(productId, slot, files[0]);

    if (files.length > 1) {
        distributeExtraImages(productId, slot, files.slice(1));
    }
}

function distributeExtraImages(productId, droppedSlot, files) {
    const imageSlots = selectedColumns
        .filter(c => c.type === 'image' && c.slot !== droppedSlot)
        .map(c => c.slot)
        .sort((a, b) => a - b);

    const freeSlots = imageSlots.filter(s => {
        const slotDiv = document.getElementById(`slot-${productId}-${s}`);
        return slotDiv && slotDiv.classList.contains('empty');
    });

    let assigned = 0;
    for (const s of freeSlots) {
        if (assigned >= files.length) break;
        assignImageFile(productId, s, files[assigned]);
        assigned++;
    }

    const skipped = files.length - assigned;
    if (skipped > 0 && typeof window.showToast === 'function') {
        window.showToast(
            `Pominięto ${skipped} ${skipped === 1 ? 'zdjęcie' : 'zdjęć'} — brak wolnych kolumn "Zdjęcie" w tym wierszu.`,
            'warning'
        );
    }
}
```

Uwaga: `freeSlots` jest liczone raz, przed pętlą przypisań — `assignImageFile` zmienia DOM dopiero asynchronicznie (w `reader.onload`), więc odczyt stanu `.empty` na starcie jest bezpieczny i nie wymaga dodatkowej synchronizacji.

- [ ] **Step 2: Zweryfikuj w przeglądarce**

Włącz w arkuszu kolumny "Zdjęcie 1", "Zdjęcie 2", "Zdjęcie 3" dla tego samego produktu. W konsoli:

```javascript
(function() {
    const PID = /* ID produktu */ 0;
    const slot = document.getElementById(`slot-${PID}-1`);
    const files = ['a.png', 'b.png', 'c.png'].map(name => {
        const blob = new Blob(['test'], {type: 'image/png'});
        return new File([blob], name, {type: 'image/png'});
    });
    const dt = new DataTransfer();
    files.forEach(f => dt.items.add(f));
    const evt = new DragEvent('drop', {bubbles: true, cancelable: true});
    Object.defineProperty(evt, 'dataTransfer', {value: dt});
    slot.dispatchEvent(evt);
})();
```

Poczekaj chwilę (FileReader jest asynchroniczny) i sprawdź:

```javascript
[1, 2, 3].map(s => document.getElementById(`slot-${/* to samo PID */0}-${s}`).className)
```

Oczekiwany wynik: wszystkie trzy sloty mają klasę `"image-slot has-image"` (plik `a.png` w slocie 1 — tam, gdzie upuszczono, `b.png`/`c.png` rozłożone na sloty 2 i 3). Następnie sprawdź scenariusz "za mało wolnych slotów": zostaw tylko kolumnę "Zdjęcie 1" widoczną i powtórz drop z 3 plikami — oczekiwany toast "Pominięto 2 zdjęcia — brak wolnych kolumn...".

- [ ] **Step 3: Commit**

```bash
git add static/js/pages/admin/mass-edit.js
git commit -m "feat(produkty): rozkładanie wielu przeciągniętych zdjęć na wolne sloty (edycja masowa)"
```

---

## Plik: `templates/admin/warehouse/product_form_modal.html` i `static/js/pages/admin/product-form.js` — stan przed zmianami

- `.image-slot` (linie 354-382 w `product_form_modal.html`) — 10 slotów (`{% for i in range(1, max_images + 1) %}`), każdy z `<input type="file" name="product_image_{{ i }}" id="imageInput{{ i }}">`, etykietą `#uploadLabel{{ i }}` (widoczna gdy slot pusty) i podglądem `#preview{{ i }}`/`#previewImg{{ i }}`.
- `handleSlotImageSelect(slotNumber, event)` (`product-form.js:959-991`) — podgląd przez `FileReader`, bez wysyłki na serwer (plik zostaje w polu formularza do właściwego submitu).
- `removeSlotImage(slotNumber, imageId)` (`product-form.js:993-1054`) — dziś: jeśli `imageId` podane, woła DELETE **od razu** po `confirm()`; jeśli brak `imageId` (nowo wybrany, niezapisany plik), tylko czyści podgląd lokalnie.
- Zapis formularza: `initFormSubmission()` (`product-form.js:529-701`) — AJAX POST na `form.action`, sukces w blokach linii 596-625.

## Task 4: Formularz produktu (modal) — drag&drop pojedynczego pliku na slot

**Files:**
- Modify: `templates/admin/warehouse/product_form_modal.html:354` (atrybuty drag na `.image-slot`)
- Modify: `static/js/pages/admin/product-form.js` (nowe funkcje `assignFileToSlot`, `handleSlotImageDrop`)
- Modify: `static/css/pages/admin/product-form.css:1063-1076` i `:1538-1542`

**Interfaces:**
- Consumes: `handleSlotImageSelect(slotNumber, event)` (istniejące, niezmienione).
- Produces: `assignFileToSlot(slotNumber: number, file: File): void`, `handleSlotImageDrop(slotNumber: number, event: DragEvent): void` — używane też w Task 5 i Task 6.

- [ ] **Step 1: Dodaj atrybuty drag&drop w szablonie**

W `templates/admin/warehouse/product_form_modal.html`, zamień linię 354:

```html
            <div class="image-slot" data-slot="{{ i }}" id="imageSlot{{ i }}">
```

na:

```html
            <div class="image-slot" data-slot="{{ i }}" id="imageSlot{{ i }}"
                 ondragover="event.preventDefault(); this.classList.add('drag-over')"
                 ondragleave="this.classList.remove('drag-over')"
                 ondrop="handleSlotImageDrop({{ i }}, event)">
```

- [ ] **Step 2: Dodaj `assignFileToSlot` i `handleSlotImageDrop` w `product-form.js`**

Dodaj poniższy kod zaraz po `window.handleSlotImageSelect = function(...) {...};` (po linii 991, przed `window.removeSlotImage`):

```javascript
function assignFileToSlot(slotNumber, file) {
    const input = document.getElementById(`imageInput${slotNumber}`);
    if (!input) return;

    const dt = new DataTransfer();
    dt.items.add(file);
    input.files = dt.files;

    handleSlotImageSelect(slotNumber, { target: input });

    if (typeof pendingSlotRemovals !== 'undefined') {
        pendingSlotRemovals = pendingSlotRemovals.filter(r => r.slot !== slotNumber);
    }
}

window.handleSlotImageDrop = function(slotNumber, event) {
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.classList.remove('drag-over');

    const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp'];
    const files = Array.from(event.dataTransfer.files).filter(f => allowedTypes.includes(f.type));
    if (files.length === 0) return;

    assignFileToSlot(slotNumber, files[0]);
};
```

Uwaga: `pendingSlotRemovals` jeszcze nie istnieje (dodawane w Task 6) — stąd `typeof ... !== 'undefined'` (guard, żeby Task 4 działał samodzielnie i nie rzucał błędu przed wykonaniem Task 6).

- [ ] **Step 3: Dodaj CSS podświetlenia (jasny i ciemny motyw)**

W `static/css/pages/admin/product-form.css`, zaraz po bloku `.image-slot:hover` (linie 1073-1076):

```css
.image-slot.drag-over {
  border-color: var(--primary-color);
  border-style: solid;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
}
```

Zaraz po bloku `[data-theme="dark"] .image-item:hover, [data-theme="dark"] .image-slot:hover` (linie 1538-1542):

```css
[data-theme="dark"] .image-slot.drag-over {
  border-color: #f093fb;
  border-style: solid;
  box-shadow: 0 4px 20px rgba(240, 147, 251, 0.35);
}
```

- [ ] **Step 4: Zweryfikuj w przeglądarce**

Otwórz listę produktów, kliknij "Edytuj" na dowolnym produkcie (otwiera modal), przejdź na zakładkę "Zdjęcia". W konsoli:

```javascript
(function() {
    const slotEl = document.getElementById('imageSlot2');
    const blob = new Blob(['test'], {type: 'image/png'});
    const file = new File([blob], 'test.png', {type: 'image/png'});
    const dt = new DataTransfer();
    dt.items.add(file);
    const evt = new DragEvent('drop', {bubbles: true, cancelable: true});
    Object.defineProperty(evt, 'dataTransfer', {value: dt});
    slotEl.dispatchEvent(evt);
    return document.getElementById('preview2').style.display;
})();
```

Oczekiwany wynik: `"block"` (podgląd w slocie #2 się pokazał), a `document.getElementById('imageInput2').files[0].name === 'test.png'`.

- [ ] **Step 5: Commit**

```bash
git add templates/admin/warehouse/product_form_modal.html static/js/pages/admin/product-form.js static/css/pages/admin/product-form.css
git commit -m "feat(produkty): drag&drop pojedynczego zdjęcia w formularzu produktu"
```

---

## Task 5: Formularz produktu (modal) — rozkładanie wielu upuszczonych plików na wolne sloty

**Files:**
- Modify: `static/js/pages/admin/product-form.js` (rozszerzenie `handleSlotImageDrop`, nowa funkcja `distributeExtraSlotImages`)

**Interfaces:**
- Consumes: `assignFileToSlot` (Task 4).
- Produces: `distributeExtraSlotImages(droppedSlot: number, files: File[]): void`.

- [ ] **Step 1: Rozszerz `handleSlotImageDrop` i dodaj `distributeExtraSlotImages`**

Zamień `window.handleSlotImageDrop` z Task 4 na:

```javascript
window.handleSlotImageDrop = function(slotNumber, event) {
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.classList.remove('drag-over');

    const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp'];
    const files = Array.from(event.dataTransfer.files).filter(f => allowedTypes.includes(f.type));
    if (files.length === 0) return;

    assignFileToSlot(slotNumber, files[0]);

    if (files.length > 1) {
        distributeExtraSlotImages(slotNumber, files.slice(1));
    }
};

function distributeExtraSlotImages(droppedSlot, files) {
    const grid = document.querySelector('.image-slots-grid');
    if (!grid) return;

    const freeSlots = Array.from(grid.querySelectorAll('.image-slot'))
        .map(el => parseInt(el.dataset.slot, 10))
        .filter(s => s !== droppedSlot)
        .sort((a, b) => a - b)
        .filter(s => {
            const uploadLabel = document.getElementById(`uploadLabel${s}`);
            return uploadLabel && uploadLabel.style.display !== 'none';
        });

    let assigned = 0;
    for (const s of freeSlots) {
        if (assigned >= files.length) break;
        assignFileToSlot(s, files[assigned]);
        assigned++;
    }

    const skipped = files.length - assigned;
    if (skipped > 0 && typeof window.showToast === 'function') {
        window.showToast(
            `Pominięto ${skipped} ${skipped === 1 ? 'zdjęcie' : 'zdjęć'} — brak wolnych slotów na zdjęcia.`,
            'warning'
        );
    }
}
```

- [ ] **Step 2: Zweryfikuj w przeglądarce**

Otwórz modal edycji produktu bez żadnych zdjęć (albo produkt z wolnymi slotami 2 i 3). W konsoli:

```javascript
(function() {
    const slotEl = document.getElementById('imageSlot1');
    const files = ['a.png', 'b.png', 'c.png'].map(name => {
        const blob = new Blob(['test'], {type: 'image/png'});
        return new File([blob], name, {type: 'image/png'});
    });
    const dt = new DataTransfer();
    files.forEach(f => dt.items.add(f));
    const evt = new DragEvent('drop', {bubbles: true, cancelable: true});
    Object.defineProperty(evt, 'dataTransfer', {value: dt});
    slotEl.dispatchEvent(evt);
})();
```

Sprawdź: `document.getElementById('imageInput1').files[0].name === 'a.png'`, `document.getElementById('imageInput2').files[0].name === 'b.png'`, `document.getElementById('imageInput3').files[0].name === 'c.png'`. Powtórz test z produktem, w którym wolny jest tylko slot 1 (reszta zajęta) — oczekiwany toast "Pominięto 2 zdjęcia — brak wolnych slotów...".

- [ ] **Step 3: Commit**

```bash
git add static/js/pages/admin/product-form.js
git commit -m "feat(produkty): rozkładanie wielu przeciągniętych zdjęć na wolne sloty (formularz produktu)"
```

---

## Task 6: Formularz produktu (modal) — odroczenie usuwania zdjęcia do zapisu

**Files:**
- Modify: `static/js/pages/admin/product-form.js:993-1054` (`removeSlotImage`)
- Modify: `static/js/pages/admin/product-form.js` (deklaracja stanu `pendingSlotRemovals`, nowa funkcja `flushPendingSlotRemovals`, hak w `initFormSubmission`)

**Interfaces:**
- Consumes: `assignFileToSlot` (Task 4, do anulowania pending removal przy nadpisaniu slotu).
- Produces: `pendingSlotRemovals: Array<{slot: number, imageId: number}>` (moduł-scope state), `flushPendingSlotRemovals(): Promise<void>`.

- [ ] **Step 1: Dodaj stan `pendingSlotRemovals` i podłącz czyszczenie w `assignFileToSlot`**

Na początku pliku `static/js/pages/admin/product-form.js`, zaraz po komentarzu nagłówkowym (po linii 4), dodaj:

```javascript
// ==========================================
// Pending Slot Removals (deferred until form save)
// ==========================================
let pendingSlotRemovals = []; // [{slot, imageId}]
```

W `assignFileToSlot` (Task 4) zamień guardowaną linię:

```javascript
    if (typeof pendingSlotRemovals !== 'undefined') {
        pendingSlotRemovals = pendingSlotRemovals.filter(r => r.slot !== slotNumber);
    }
```

na (guard nie jest już potrzebny, bo `pendingSlotRemovals` istnieje od teraz zawsze):

```javascript
    pendingSlotRemovals = pendingSlotRemovals.filter(r => r.slot !== slotNumber);
```

- [ ] **Step 2: Zmień `removeSlotImage`, żeby odraczał usunięcie zamiast wołać DELETE od razu**

Zamień całą funkcję `window.removeSlotImage` (linie 993-1054) na:

```javascript
window.removeSlotImage = function(slotNumber, imageId) {
    const input = document.getElementById(`imageInput${slotNumber}`);
    const uploadLabel = document.getElementById(`uploadLabel${slotNumber}`);
    const preview = document.getElementById(`preview${slotNumber}`);
    const previewImg = document.getElementById(`previewImg${slotNumber}`);

    if (imageId) {
        // Existing image - defer the actual removal until form save
        if (!confirm('Czy na pewno chcesz usunąć to zdjęcie?')) return;

        pendingSlotRemovals = pendingSlotRemovals.filter(r => r.slot !== slotNumber);
        pendingSlotRemovals.push({ slot: slotNumber, imageId: imageId });

        if (input) input.value = '';
        if (previewImg) previewImg.src = '';
        if (preview) preview.style.display = 'none';
        if (uploadLabel) uploadLabel.style.display = 'flex';
    } else {
        // Newly selected image (not yet saved) - just clear the preview
        if (input) input.value = '';
        if (previewImg) previewImg.src = '';
        if (preview) preview.style.display = 'none';
        if (uploadLabel) uploadLabel.style.display = 'flex';
    }
};
```

- [ ] **Step 3: Dodaj `flushPendingSlotRemovals()`**

Dodaj tę funkcję zaraz po `removeSlotImage`:

```javascript
function flushPendingSlotRemovals() {
    if (pendingSlotRemovals.length === 0) return Promise.resolve();

    const form = document.getElementById('productFormModal');
    const csrfInput = form ? form.querySelector('input[name="csrf_token"]') : null;
    const actionUrl = form ? form.getAttribute('action') : '';
    const productIdMatch = actionUrl.match(/\/products\/(\d+)\//);

    if (!form || !csrfInput || !productIdMatch) {
        pendingSlotRemovals = [];
        return Promise.resolve();
    }

    const productId = productIdMatch[1];
    const csrfToken = csrfInput.value;
    const removals = pendingSlotRemovals;
    pendingSlotRemovals = [];

    return removals.reduce((chain, removal) => {
        return chain.then(() =>
            fetch(`/admin/products/${productId}/images/${removal.imageId}`, {
                method: 'DELETE',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': csrfToken
                }
            }).catch(() => {})
        );
    }, Promise.resolve());
}
```

- [ ] **Step 4: Podłącz flush przed zamknięciem modala po udanym zapisie**

W `static/js/pages/admin/product-form.js`, w bloku `if (data.success) { ... }` wewnątrz `initFormSubmission` (ok. linii 596-625), zamień:

```javascript
                if (data.success) {
                    // Show success message
                    if (typeof window.showToast === 'function') {
                        window.showToast(data.message, 'success');
                    } else {
                        alert(data.message);
                    }

                    console.log('[FORM] Product saved successfully. Refreshing products list...');

                    // Close modal and refresh list after 1.5 seconds (time to read toast)
                    setTimeout(() => {
                        // Close modal
                        if (typeof closeProductModal === 'function') {
                            closeProductModal();
                        }

                        // Refresh products list (instead of full page reload)
                        if (typeof refreshProductsList === 'function') {
                            refreshProductsList();
                        } else {
                            // Fallback to full page reload if function not available
                            console.log('[FORM] refreshProductsList not available, falling back to page reload');
                            if (data.redirect) {
                                window.location.href = data.redirect;
                            } else {
                                window.location.reload();
                            }
                        }
                    }, 1500);
                } else {
```

na:

```javascript
                if (data.success) {
                    flushPendingSlotRemovals().finally(() => {
                        // Show success message
                        if (typeof window.showToast === 'function') {
                            window.showToast(data.message, 'success');
                        } else {
                            alert(data.message);
                        }

                        console.log('[FORM] Product saved successfully. Refreshing products list...');

                        // Close modal and refresh list after 1.5 seconds (time to read toast)
                        setTimeout(() => {
                            // Close modal
                            if (typeof closeProductModal === 'function') {
                                closeProductModal();
                            }

                            // Refresh products list (instead of full page reload)
                            if (typeof refreshProductsList === 'function') {
                                refreshProductsList();
                            } else {
                                // Fallback to full page reload if function not available
                                console.log('[FORM] refreshProductsList not available, falling back to page reload');
                                if (data.redirect) {
                                    window.location.href = data.redirect;
                                } else {
                                    window.location.reload();
                                }
                            }
                        }, 1500);
                    });
                } else {
```

- [ ] **Step 5: Zweryfikuj w przeglądarce (trzy scenariusze)**

**Scenariusz A — odroczone usunięcie:** Otwórz modal edycji produktu z istniejącym zdjęciem w slocie 1. Kliknij "Usuń", potwierdź. Oczekiwane: podgląd znika lokalnie natychmiast, ale sprawdź w konsoli `pendingSlotRemovals` — powinno zawierać `{slot: 1, imageId: <id>}`. Sprawdź w Network tab (`mcp__Claude_Browser__read_network_requests`), że **żadne** żądanie DELETE nie poszło jeszcze do serwera. Kliknij "Zapisz" na dole formularza. Po zapisie sprawdź Network — dopiero teraz powinno pojawić się żądanie `DELETE /admin/products/<id>/images/<imageId>`, a `pendingSlotRemovals` jest puste.

**Scenariusz B — nadpisanie slotu oznaczonego do usunięcia:** Powtórz scenariusz A do momentu potwierdzenia usunięcia (slot pusty, `pendingSlotRemovals` ma wpis), ale zamiast zapisywać, przeciągnij nowy plik na ten sam slot. Sprawdź `pendingSlotRemovals` — wpis dla tego slotu powinien zniknąć. Zapisz formularz — sprawdź Network: powinno pójść tylko żądanie POST zapisu formularza (z nowym plikiem w `product_image_1`), **bez** żadnego DELETE.

**Scenariusz C — brak regresji przy anulowaniu:** Otwórz modal, kliknij "Usuń" na istniejącym zdjęciu, ale odrzuć `confirm()` (Anuluj). Sprawdź, że podgląd zdjęcia dalej jest widoczny i `pendingSlotRemovals` jest puste.

- [ ] **Step 6: Commit**

```bash
git add static/js/pages/admin/product-form.js
git commit -m "feat(produkty): odrocz usuwanie zdjęcia w formularzu produktu do momentu zapisu"
```

---

## Self-Review Notes

- Pokrycie specyfikacji: pkt 1 (drag&drop edycja masowa) → Task 1-3; pkt 2 (drag&drop formularz produktu) → Task 4-5; pkt 3 (odroczone usuwanie) → Task 6. Wszystkie sekcje specyfikacji mają odpowiadające zadanie.
- Brak placeholderów — każdy krok ma kompletny kod.
- Spójność nazw: `assignImageFile`/`handleImageDrop`/`distributeExtraImages` (mass-edit.js) vs `assignFileToSlot`/`handleSlotImageDrop`/`distributeExtraSlotImages` (product-form.js) — celowo różne nazwy między dwoma plikami (różne struktury danych: `pendingImageUploads`/obiekt vs realne pola `<input type="file">`), żeby uniknąć pomyłki przy czytaniu obu plików osobno.
