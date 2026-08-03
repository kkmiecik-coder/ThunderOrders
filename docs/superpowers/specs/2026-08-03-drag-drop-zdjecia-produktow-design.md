# Drag and drop zdjęć produktów (edycja masowa + formularz pojedynczego produktu) — projekt

Data: 2026-08-03
Gałąź: `feat/drag-and-drop-zdjecia-produktow`
Źródło: ClickUp task `869e6745z` — "drag and drop w edycji masowej zdjęć produktów"

## Problem

Dziś dodawanie zdjęć produktów wymaga kliknięcia w slot/przycisk i wybrania
pliku z okna systemowego — nie da się przeciągnąć pliku ze zdjęciem
bezpośrednio z dysku. Dotyczy to dwóch niezależnych widoków:

1. **Edycja masowa** (`/admin/products/mass-edit`) — arkusz produktów ×
   kolumn, gdzie zdjęcia są przypisane do sztywnych, ponumerowanych slotów
   (`renderImageCell`, `static/js/pages/admin/mass-edit.js:522-542`). Upload
   już dziś jest odroczony do zapisu — `handleImageSelect` (linia 709) tylko
   zapisuje plik lokalnie w `pendingImageUploads[productId][slot]` i pokazuje
   podgląd przez `FileReader`; realna wysyłka na serwer dzieje się dopiero
   przy kliknięciu "Zapisz" (kolejka wysyłana sekwencyjnie, ok. linia 948).
2. **Formularz pojedynczego produktu** (`templates/admin/warehouse/product_form.html`,
   otwierany jako modal) — siatka zdjęć (`#images-grid`, linia 260) bez
   slotów, gdzie dziś: dodanie zdjęcia (`uploadImages()`,
   `static/js/pages/admin/product-form.js:746`), usunięcie
   (`deleteImage()`, linia 843) i ustawienie głównego (`setPrimaryImage()`,
   linia 890) wysyłają żądanie na serwer **od razu**. Dla nowego,
   niezapisanego produktu zakładka zdjęć w ogóle nie istnieje (tylko komunikat
   "zapisz produkt najpierw", template linie 296-300).

Brak jakiejkolwiek biblioteki drag&drop w projekcie (`static/vendor/`
zawiera tylko panzoom/pdfjs/tinymce) — ale jest już gotowy, zero-zależnościowy
wzorzec natywnego HTML5 drag&drop do naśladowania:
`static/js/pages/admin/feedback-builder.js:76-146` i
`static/js/pages/admin/offer-builder.js:249,381` (tam używany do zmiany
kolejności elementów, tu wykorzystamy te same zdarzenia `dragover`/`dragleave`/
`drop` do przyjmowania plików).

## Zakres

1. Drag&drop wgrywania plików w edycji masowej — upuszczenie na konkretną
   komórkę "Zdjęcie N".
2. Drag&drop wgrywania plików w formularzu pojedynczego produktu —
   upuszczenie w dowolnym miejscu siatki zdjęć.
3. **Zmiana zachowania formularza pojedynczego produktu** (nie tylko nowa
   funkcja): dodawanie (klik i drag&drop), usuwanie i ustawianie zdjęcia
   głównego przestają wysyłać żądania od razu — czekają lokalnie i wysyłają
   się dopiero po kliknięciu głównego przycisku "Zapisz" formularza, tym
   samym mechanizmem co dziś (te same endpointy), tylko odroczonym w czasie.
   Dotyczy to też **nowych, jeszcze niezapisanych produktów** — zakładka
   zdjęć staje się dostępna od razu, zanim produkt istnieje w bazie.

**Poza zakresem (świadomie, YAGNI):**
- Zmiana kolejności zdjęć przez przeciąganie (reorder) — to nie było celem
  zadania z ClickUp; obecny mechanizm kolejności (`sort_order`,
  `modules/products/models.py:51,276-277`) zostaje bez zmian.
- Zmiany w backendzie — wszystkie potrzebne endpointy już istnieją
  (`mass_edit_upload_image`/`mass_edit_delete_image` w
  `modules/products/routes.py:4536,4591`; `/images/upload`,
  `/images/<id>` DELETE, `/images/<id>/set-primary` — używane już dziś przez
  `product-form.js`). Ta praca jest wyłącznie frontendowa (JS + CSS).
- Ujednolicenie dwóch różnych mechanizmów przechowywania zdjęć na backendzie
  (sloty 1–10 wbudowane w `create_product()` POST vs. osobne AJAX-owe
  endpointy per-obraz) — nie ruszamy tego; nowy kod korzysta wyłącznie z
  istniejących AJAX-owych endpointów per-obraz, również dla nowo tworzonego
  produktu (patrz niżej).

## Edycja masowa — zachowanie

- Każda komórka `.image-slot` (i pusta, i zajęta) staje się celem upuszczenia:
  `dragover` podświetla komórkę (nowa klasa CSS, np. `.image-slot.drag-over`),
  `dragleave`/`drop` ją zdejmuje.
- Upuszczenie pliku na komórkę slotu **N** danego produktu:
  - pierwszy przeciągnięty plik trafia do slotu N i **nadpisuje** istniejące
    zdjęcie bez pytania o potwierdzenie (tak jak dziś działa wybór pliku
    kliknięciem);
  - jeśli upuszczono więcej niż jeden plik, pozostałe rozkładają się po
    kolejnych **wolnych** slotach obrazkowych tego produktu, licząc tylko
    kolumny obrazków aktualnie widoczne w arkuszu (`selectedColumns` typu
    `image`), w rosnącej kolejności numeru slotu;
  - jeśli wolnych slotów jest mniej niż plików, nadmiarowe pliki są pomijane,
    a użytkownik dostaje komunikat (toast) ile i dlaczego zostało pominięte;
  - pliki, które nie są obrazkami, są odrzucane po cichu (analogicznie do
    `accept="image/*"` na dzisiejszym input-cie).
- Techniczne: logika z `handleImageSelect(productId, slot, input)` zostaje
  wydzielona do wspólnej funkcji `assignImageFile(productId, slot, file)`
  (przechowanie w `pendingImageUploads`, usunięcie z `pendingImageRemovals`,
  podgląd przez `FileReader`, przerenderowanie komórki) — używanej zarówno
  przez `handleImageSelect` (klik), jak i nowy `handleImageDrop` (drag&drop).
  Żadnej zmiany w momencie faktycznej wysyłki na serwer (nadal dopiero przy
  "Zapisz").

## Formularz pojedynczego produktu — zachowanie

Zapis formularza jest dziś przechwytywany przez JS
(`product-form.js:540-701`, `e.preventDefault()` + `fetch(form.action)`),
zwraca JSON zawierający `product_id` również przy tworzeniu nowego produktu
(`modules/products/routes.py:262-267`). To pozwala odroczyć operacje na
zdjęciach bez zmian w backendzie:

- **Dodawanie** (klik na "Załaduj wiele zdjęć" lub przeciągnięcie
  jednego/wielu plików w dowolne miejsce `#images-grid`): plik trafia do
  lokalnej listy `pendingNewImages` i od razu pokazuje się jako miniaturka
  (podgląd przez `FileReader`/`URL.createObjectURL`), z możliwością
  usunięcia ze staged-listy przed zapisem. Nic nie jest wysyłane na serwer.
  Cała siatka podświetla się podczas przeciągania nad nią (`dragover`).
- **Usuwanie istniejącego zdjęcia**: klik na "Usuń" nie woła już DELETE od
  razu — zdjęcie znika wizualnie i trafia do lokalnej listy
  `pendingRemovals` (lista ID). Można to cofnąć tylko przez odświeżenie
  formularza (bez "undo" w UI — YAGNI, tak jak dziś nie ma undo dla usuwania).
- **Ustawienie głównego**: klik na "Ustaw jako główne" nie woła
  `set-primary` od razu — tylko lokalnie przestawia gwiazdkę/badge
  "Główne" na wybranym zdjęciu (`pendingPrimaryImageId`).
- **Nowy, niezapisany produkt**: zakładka "Zdjęcia" pokazuje pustą siatkę +
  strefę wgrywania (usuwamy dzisiejszy blok `{% else %}` z samym komunikatem)
  od razu na starcie formularza — bez czekania na zapis produktu.
- **Zapis formularza** (`submit` handler): po udanym zapisie pól produktu
  (jak dziś) i uzyskaniu `productId` (z URL dla edycji, z `data.product_id`
  dla nowego produktu), sekwencyjnie odpala się flush kolejki zdjęć:
  1. DELETE dla każdego ID z `pendingRemovals`,
  2. POST `/images/upload` z plikami z `pendingNewImages`,
  3. POST `/images/<id>/set-primary`, jeśli `pendingPrimaryImageId` jest
     ustawiony.
  Dopiero po zakończeniu tej sekwencji pokazuje się finalny toast i modal się
  zamyka / lista produktów odświeża (dziś: `setTimeout` z zamknięciem modala,
  `product-form.js:606-625` — flush kolejki wchodzi przed tym krokiem).
- **Obsługa błędów**: jeśli zapis pól produktu się nie powiedzie — nic z
  kolejki zdjęć się nie wysyła (jak dziś). Jeśli pola zapiszą się poprawnie,
  ale któraś operacja na zdjęciu w kolejce zawiedzie — produkt i tak zostaje
  zapisany, a toast na końcu wypisuje, które konkretnie zdjęcie się nie
  wgrało/nie usunęło (analogicznie do istniejącego raportowania błędów w
  `mass-edit.js` przy flushu kolejki, ok. linia 978-1003).

## CSS

Nowy stan `.drag-over` (podświetlenie komórki w edycji masowej i całej
siatki w formularzu produktu) w `static/css/pages/admin/mass-edit.css` i
odpowiednim pliku CSS formularza produktu — zgodnie z konwencją projektu,
zdefiniowany dla trybu jasnego i ciemnego.

## Testowanie

- Automatyczne testy Pythona (`pytest`) nie dotyczą tej zmiany — nie ma
  zmian w backendzie/routes.
- Weryfikacja ręczna w przeglądarce (Playwright/manualnie): symulacja
  prawdziwego przeciągnięcia pliku z dysku nie jest możliwa do w pełni
  zautomatyzowania, ale zachowanie da się zweryfikować programowo przez
  wywołanie syntetycznego zdarzenia `drop` z obiektem `DataTransfer`
  zawierającym `File` (standardowy sposób testowania HTML5 drag&drop bez
  prawdziwego OS-owego przeciągania). Do zweryfikowania ręcznie: edycja
  masowa (podmiana slotu, rozkładanie wielu plików, komunikat o pominiętych),
  formularz produktu (dodawanie/usuwanie/główne przed zapisem, nowy produkt
  od zera, błąd pojedynczego zdjęcia nie blokujący zapisu produktu).
