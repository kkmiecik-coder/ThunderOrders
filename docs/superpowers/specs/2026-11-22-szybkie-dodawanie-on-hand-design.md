# Szybkie dodawanie produktów on hand — design (krótki)

Data: 2026-11-22 · Rozmiar: mała zmiana (jeden nowy ekran + endpoint)

## Po co
Karolina wystawia dużo rzeczy on hand, wszystko z telefonu: robi zdjęcie, wpisuje nazwę, cenę i ilość. Dziś robi to dużym formularzem produktu (kilkanaście pól, okienko w magazynie), z którego używa 3–4 pól, a do tego musi pamiętać o typie „On-hand” i ilości > 0, bo inaczej produkt nie pokaże się w sklepie. Cel: zdjęcie → nazwa → cena → ilość → „Dodaj i następny”, bez niczego więcej.

## Cele
- Osobny ekran w panelu admina, robiony pod telefon (mobile-first), dostępny dla `admin` i `mod`.
- Pola: zdjęcie (aparat albo galeria), nazwa, cena sprzedaży, ilość (domyślnie 1).
- Po zapisie produkt od razu jest w sklepie: typ `on-hand`, `is_active=True`, podana ilość.
- Formularz czyści się po zapisie i jest gotowy na kolejną rzecz.
- Pod formularzem lista rzeczy dodanych w tej rundzie (miniatura, nazwa, cena, ilość) z możliwością szybkiej poprawki nazwy, ceny i ilości oraz ukrycia pomyłki.

## Poza zakresem
- Rozmiary i grupy wariantów — zostają w starym formularzu.
- Dodawanie paczką wielu zdjęć naraz (wariant B) — może dojść później do tego samego ekranu.
- Zmiany w starym formularzu produktu, w sklepie klientki i w aplikacji mobilnej.

## Czego nie może zepsuć (anty-cele)
- Ekran nie może być wolniejszy ani bardziej upierdliwy niż dziś: żadnych dodatkowych wymaganych pól, żadnych okienek po drodze.
- Nie może zgubić wpisanych danych przy słabym internecie bez ostrzeżenia — błąd zapisu ma być widoczny, a pola mają zostać wypełnione, żeby dało się ponowić.
- Produkty dodane tym ekranem muszą zachowywać się w sklepie, koszyku, zamówieniach i magazynie dokładnie tak jak dodane starym formularzem.

## Podejścia (rozważone)
- **A. Osobny prosty ekran „Szybkie dodawanie on hand”** — WYBRANE przez Karolinę. Najkrótsza droga dla jednej rzeczy, zgodna z jej sposobem pracy (rzecz po rzeczy).
- B. Paczka zdjęć naraz → kafelki do uzupełnienia → „Zapisz wszystko”. Odrzucone na teraz: większe ryzyko utraty pracy przy zerwanym internecie, trudniej o kilka zdjęć na rzecz. Można dołożyć później.
- C. Ukrywanie zbędnych pól w obecnym formularzu. Odrzucone: dalej duże okienko niewygodne na telefonie, mały zysk.

## Ustalenia z Karoliną
- Robi wszystko na telefonie.
- Potrzebne pola: zdjęcie, nazwa, cena, ilość (ilość dodana na jej prośbę).

## Decyzje Claude'a (do sprawdzenia przez Karolinę)
- Zdjęcie jest wymagane (zawsze je robi); można dodać więcej niż jedno, pierwsze = główne. Limit jak w ustawieniach zdjęć (`max_per_product`).
- Nazwa i cena wymagane, ilość ≥ 1.
- Zdjęcie zmniejszane w przeglądarce przed wysłaniem (JPEG, dłuższy bok ~1600 px) — szybciej na słabym internecie i omija problem formatu HEIC z iPhone'a (dziś serwer przyjmuje tylko jpg/png/webp/gif i po cichu pomija inne pliki).
- Pozostałe pola produktu puste/domyślne: brak SKU, EAN, kategorii, ceny zakupu, marży (`calculate_margin` da `None`), dostawcy, opisu.
- „Usuń pomyłkę” z listy = ukrycie produktu (`is_active=False`), nie twarde kasowanie — bezpieczne, gdyby ktoś zdążył już kupić.
- Lista „dodane w tej rundzie” pokazuje produkty dodane tym ekranem w bieżącej sesji przeglądarki (po odświeżeniu może być pusta — wystarczy).
- Wejście na ekran: link w menu panelu admina (sekcja magazyn/produkty) oraz przycisk na liście produktów.
- Zapis jednym żądaniem (dane + zdjęcia), po stronie serwera ponowne użycie `process_upload` i istniejącego modelu `Product`/`ProductImage`; typ on-hand przez `get_on_hand_type()` z `modules/client/shop_service.py`.

## Zostawione budowniczemu
- Dokładne miejsce trasy w blueprincie produktów i nazwa szablonu.
- Wygląd zgodny z konwencjami: CSS w trybie jasnym i ciemnym, przyciski min. 44 px, toasty i CSRF wg istniejących wzorców.
- Testy (pytest): zapis tworzy aktywny produkt on-hand z ilością i zdjęciem i jest widoczny w zapytaniu sklepu; walidacja brakującej nazwy/ceny/zdjęcia; dostęp tylko dla admin/mod; ukrycie ustawia `is_active=False`.
- Gdy typ `on-hand` nie istnieje w bazie — czytelny błąd zamiast cichego zapisu bez typu.
