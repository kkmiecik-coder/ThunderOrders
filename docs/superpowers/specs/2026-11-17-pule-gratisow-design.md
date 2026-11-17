# Pule gratisów w jednej akcji — projekt

Data: 2026-11-17 · zaakceptowane przez Karolinę w rozmowie („Jedna akcja, dwie pule”, „dobrze rozumiesz”).

## Po co

Jedna strona sprzedaży może dawać kilka gratisów naraz. Przykład: Aniteez ma „50k benefit”
(124 szt. w 58 zamówieniach) i „100k benefit” (46 szt. w 32 zamówieniach). Karty w obu wydaniach
przedstawiają te same postacie (członków), tylko w innym wydaniu. Karolina chce jednej akcji
zamiast dwóch: jeden mail, jeden kafelek, jedno „Zgłaszam się”, jeden ranking.

## Co budujemy

- **Pula = jeden produkt-gratis w akcji.** Akcja ma 1..N pul. Stare akcje = jedna pula.
- **Rodzaje kart wspólne dla akcji** (np. członkowie), wpisywane raz.
- **Ilość sztuk osobno dla każdej pary pula × rodzaj** (np. San: 50k = 15, 100k = 6).
- **Uprawnienia per pula:** gratisowe pozycje zamówień z danym produktem na stronach akcji
  (jak dotąd: bez anulowanych i zwróconych).
- **Klientka:** jeden mail z rozbiciem („2 karty — 50k…, 1 karta — 100k…”), jeden kafelek,
  jedno zgłoszenie (jedna kolejka), **jeden ranking** rodzajów.
- **Nowe pole „Uwagi” klientki** (tekst do 1000 znaków), edytowalne, gdy akcja jest otwarta;
  widoczne w szczegółach akcji i w Excelu.
- **Rozdział:** każda pula osobno, tym samym algorytmem, w tej samej kolejności kolejki
  i z tym samym rankingiem. Powtórka liczy się tylko w ramach jednej puli
  (San 50k + San 100k to nie powtórka).
- **Panel admina:** wybór kilku gratisów; ilości w siatce rodzaj × pula (formularz i szczegóły);
  „Przydzielone / ilość” i problemy ze stanem — per pula; przy kartach osoby znacznik puli.
- **Excel:** kolumny rodzaj × pula, przydzielone karty pogrupowane po pulach, kolumna
  „Uwagi klientki”, podsumowanie per pula.

## Nie robimy

- Osobnych rankingów ani osobnych kolejek per pula.
- Osobnych krótkich nazw pul — nazwa puli to nazwa produktu-gratisu (decyzja Claude, do zmiany
  później, jeśli okaże się za długa).

## Dane (decyzja Claude)

- Nowa tabela `gift_campaign_pools` (campaign_id, bonus_product_id, sort_order; unikat akcja+produkt).
- Nowa tabela `gift_pool_stock` (pool_id, card_type_id, quantity NULL; unikat pula+rodzaj).
- `gift_assignments.pool_id` (NOT NULL), `gift_participants.notes`.
- Usunięte: `gift_campaigns.bonus_product_id`, `gift_card_types.quantity` — migracja przenosi
  dane do pul (jedna pula na istniejącą akcję), downgrade przywraca z pierwszej puli.
