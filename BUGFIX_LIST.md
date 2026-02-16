# Lista poprawek do wykonania (Testy użytkowników - Styczeń 2026)

**Data utworzenia:** 2026-01-17
**Status:** W trakcie realizacji

---

## Podział na priorytety

### 🔴 KRYTYCZNE (blokują kluczowe funkcje)
| # | Problem | Status |
|---|---------|--------|
| 1 | Błąd logowania na stronie zamawiania | ✅ Zrobione |
| 2 | Nie przychodzą maile z zamówień, które nie przeszły | ⏳ Do zrobienia |
| 3 | Nie można wysłać wiadomości w widoku klienta w szczegółach zamówienia | ⏳ Do zrobienia |
| 4 | Brak maili o zmianie statusu zamówienia - wszystkie | ⏳ Do zrobienia |
| 27 | Ręczne zakończenie sprzedaży exclusive nie odświeża ekranów użytkowników | ✅ Zrobione |

### 🟠 WAŻNE (znacząco wpływają na UX)
| # | Problem | Status |
|---|---------|--------|
| 5 | Brak maila po akcji dodania kosztów wysyłki | 🅿️ ZAPARKOWANE (przebudowa wysyłki) |
| 6 | Brak maila o potwierdzeniu płatności za dostawę | 🅿️ ZAPARKOWANE (przebudowa wysyłki) |
| 7 | Nie pokazuje ceny wysyłki w "Zlecenia wysyłki" w widoku admina | 🅿️ ZAPARKOWANE (przebudowa wysyłki) |
| 8 | W złym miejscu jest rozdzielanie kosztów wysyłki | 🚫 ODDELEGOWANE (Karolina) |
| 9 | Jeśli ktoś jest na stronie exclusive bez daty końcowej, a między czasie admin doda datę - UI się nie aktualizuje (brak auto-refresh badge/timer) | ✅ Zrobione |
| 10 | Możliwość dodania potwierdzenia zamówienia na statusie X - do ustawienia w ustawieniach | ✅ Zrobione (błędna konfiguracja) |

### 🟡 ŚREDNIE (problemy wizualne/UX)
| # | Problem | Status |
|---|---------|--------|
| 11 | Złe skalowanie logo na stronie countdown oraz po zamknięciu sprzedaży | ✅ Zrobione |
| 12 | Strona zamawiania exclusive > obrazek > "Pokaż cały obrazek" cały czas, nie tylko na hover + fioletowy hover + szybsze zwijanie | ✅ Zrobione |
| 13 | Zrobić statyczną kolumnę statusów na liście zamówień (admin) | ✅ Zrobione |
| 14 | W widoku zamówienia przeprojektować karty produktów w liście produktów | ✅ Zrobione |
| 15 | Brak responsywności w "Zlecenia wysyłki" | ✅ Zrobione |
| 16 | Brak responsywności w "Historia zamówień" w szczegółach zamówienia (brak ikon, brak tłumaczeń akcji) | ✅ Zrobione |
| 17 | W "Zlecenia przesyłki" oprócz ikon dodać labele, która akcja jest do czego | ✅ Zrobione |
| 18 | W "lista zamówień" tooltips muszą mieć max szerokość, żeby robić wrapa | ✅ Zrobione |
| 19 | Widget "Moje zamówienia" wykres nie uwzględnia zmiany trybu jasny/ciemny | ✅ Zrobione |

### 🟢 DROBNE (kosmetyczne)
| # | Problem | Status |
|---|---------|--------|
| 20 | Dodać linkowanie do pozostałych statystyk na dashboard client | ✅ Zrobione |
| 21 | Na dashboardzie client widget "Moje zamówienia" (wykres) oraz "Moje zamówienia" (tabela) - nazewnictwo do zmiany | ✅ Zrobione |
| 22 | Brak info jak brak potwierdzenia przesyłki | ✅ Zrobione |
| 23 | Ikona do kopiowania linku w widgecie exclusive | ✅ Zrobione |
| 24 | Ikona w topbarze/sidebarze ma przenosić do dashboardu | ✅ Zrobione |
| 25 | Ograniczyć liczbę ostatnich zamówień na dashboard widget | ✅ Zrobione |
| 26 | Przy zmianach avatara dodać kontrolki "<" ">" do przesuwania avatarów na desktop | ✅ Zrobione |

---

## Notatki z ustaleń

- **Kolejność prac:** Zaczynamy od DROBNYCH, potem w górę do KRYTYCZNYCH
- **Workflow:** Przed każdym zadaniem pytam o zgodę na start, po zakończeniu krótki raport (3 zdania)
- **Punkt 8:** Oddelegowany do Karoliny - pomijamy
- **Punkt 9 (szczegóły):** Strona sprzedaży exclusive ma badge z datą końcową lub jej brak. Jeśli zbliża się koniec - włącza timer. Problem: gdy admin zaktualizuje datę końcową, a użytkownik jest już na stronie - UI się nie odświeża automatycznie.
- **Punkt 18 (szczegóły):** Tooltips w liście zamówień nie mają max-width, przez co tekst nie zawija się i wychodzi poza ekran.

---