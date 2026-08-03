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
2. **Formularz pojedynczego produktu** — otwierany zawsze jako modal
   (`templates/admin/warehouse/product_form_modal.html`; szablon
   `product_form.html` z inną, niezależną siatką `#images-grid` i funkcjami
   `uploadImages()`/`deleteImage()`/`setPrimaryImage()` w
   `product-form.js:746-901` **nie jest nigdzie w aplikacji linkowany ani
   renderowany** — każde wywołanie tras `create_product`/`edit_product` z
   UI idzie z `modal=1`, więc realnie używany jest tylko wariant modalowy;
   pozostaje poza zakresem tej zmiany).

   W modalu zdjęcia są w 10 ponumerowanych slotach
   (`.image-slot`, `templates/admin/warehouse/product_form_modal.html:351-384`,
   każdy z własnym `<input type="file" name="product_image_N">`). Dodanie/
   podmiana zdjęcia (`handleSlotImageSelect`, `product-form.js:959`) **już
   dziś jest odroczone do zapisu** — to zwykłe pole pliku w formularzu;
   backend (`create_product`/`edit_product`,
   `modules/products/routes.py:219-251,376-420`) czyta `product_image_1..10`
   z `request.files` dopiero przy zapisie całego formularza i dla zajętego
   slotu podmienia stare zdjęcie na nowe — działa to identycznie dla nowego
   i istniejącego produktu, bez żadnych zmian potrzebnych z naszej strony.
   Nie ma tu koncepcji "zdjęcia głównego" do ustawienia ręcznie — slot #1
   zawsze jest główny (ta sama reguła po stronie backendu).

   Prawdziwe braki: (a) brak przeciągania — działa tylko klik na slot; (b)
   usunięcie istniejącego zdjęcia (`removeSlotImage`, linia 993) woła DELETE
   na serwer **od razu** (po `confirm()`), zamiast czekać do zapisu.

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
2. Drag&drop wgrywania plików w formularzu pojedynczego produktu (modal) —
   upuszczenie na konkretny slot obrazkowy.
3. Odroczenie usuwania istniejącego zdjęcia w formularzu pojedynczego
   produktu do momentu zapisu — dziś usuwa od razu, ma czekać jak reszta
   operacji na zdjęciach w tym formularzu.

**Poza zakresem (świadomie, YAGNI):**
- Zmiana kolejności zdjęć przez przeciąganie (reorder) — to nie było celem
  zadania z ClickUp; obecny mechanizm kolejności (`sort_order`,
  `modules/products/models.py:51,276-277`) zostaje bez zmian.
- Zmiany w backendzie — wszystkie potrzebne endpointy już istnieją
  (`mass_edit_upload_image`/`mass_edit_delete_image` w
  `modules/products/routes.py:4536,4591`; obsługa `product_image_1..10` w
  `create_product`/`edit_product`; DELETE `/images/<id>` używane już dziś
  przez `removeSlotImage`). Ta praca jest wyłącznie frontendowa (JS + CSS).
- Nieużywany szablon `product_form.html` (pełnostronicowy, bez modala) i
  jego siatka `#images-grid` — nie jest renderowany z żadnego miejsca w UI,
  więc nie ma sensu go poprawiać. Do rozważenia w osobnym zadaniu, czy go
  usunąć jako martwy kod (nie teraz — poza zakresem).
- "Ustawianie zdjęcia głównego" — nie istnieje jako osobna operacja w
  używanym (modalowym) formularzu; slot #1 zawsze jest główny.

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

## Formularz pojedynczego produktu (modal) — zachowanie

- Każdy `.image-slot` staje się celem upuszczenia (`dragover` podświetla,
  `dragleave`/`drop` zdejmuje podświetlenie) — analogicznie do edycji
  masowej.
- Upuszczenie pliku na slot **N**: plik trafia do
  `input#imageInput{{N}}` (przez `DataTransfer`, bo `.files` inputa nie da
  się nadpisać bezpośrednio) i wywołuje tę samą logikę podglądu co dziś przy
  kliknięciu (`handleSlotImageSelect`) — nadpisuje istniejący podgląd w tym
  slocie bez pytania o potwierdzenie, tak jak przy kliknięciu. Realna
  wysyłka i tak nastąpi dopiero przy zapisie całego formularza (bez zmian —
  to już działa).
- Upuszczenie kilku plików na jeden slot: pierwszy plik trafia do slotu, na
  który upuszczono, pozostałe rozkładają się po kolejnych **wolnych**
  slotach (tych, gdzie `uploadLabel` jest widoczny, czyli nic jeszcze nie
  wybrano ani nie ma istniejącego zdjęcia), w rosnącej kolejności numeru
  slotu. Nadmiarowe pliki ponad liczbę wolnych slotów są pomijane z
  komunikatem (toast) ile i dlaczego.
- **Usuwanie istniejącego zdjęcia** (`removeSlotImage` ze slotu z
  `imageId`): zamiast wołać DELETE i `confirm()` od razu, slot się czyści
  wizualnie (podgląd znika, wraca "Dodaj zdjęcie") i `imageId` trafia do
  lokalnej listy `pendingSlotRemovals`. Potwierdzenie (`confirm()`) zostaje
  — pytamy raz, przy kliknięciu "Usuń", tak jak dziś, tylko bez wysyłki.
  Jeśli po oznaczeniu do usunięcia użytkownik wgra (klik lub drag&drop) nowe
  zdjęcie do tego samego slotu — wpis w `pendingSlotRemovals` dla tego
  slotu jest kasowany (i tak zostanie nadpisany przy zapisie, backend sam to
  obsłuży).
- **Zapis formularza**: po udanym zapisie głównego POST-a (który już dziś
  wysyła nowe/podmienione zdjęcia razem z resztą pól — bez zmian), jeśli
  `pendingSlotRemovals` nie jest puste, wysyłamy DELETE dla każdego ID
  sekwencyjnie, ignorując błędy pojedynczych żądań (analogicznie do
  `mass-edit.js` przy usuwaniu, ok. linia 941-942) — również gdyby dany ID
  już nie istniał (bo slot został nadpisany nowym zdjęciem w tym samym
  zapisie). Dopiero po tym pokazuje się finalny toast / modal się zamyka
  (dziś: `product-form.js:606-625`).

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
  formularz produktu — modal (drag&drop na slot, podmiana istniejącego
  zdjęcia przez przeciągnięcie, usunięcie zdjęcia odroczone do zapisu,
  nadpisanie slotu oznaczonego do usunięcia nowym zdjęciem przed zapisem,
  nowy produkt od zera).
