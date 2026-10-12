# Pupile — checklista włączenia na produkcji

Spec §7. Kolejność ma znaczenie: kod i migracja wchodzą z flagą WYŁĄCZONĄ, włączenie to osobny krok
z panelu admina. Instrukcja crona: `2026-10-11-pupile-cron-instrukcja.md`.

**Co widzą klienci przed włączeniem:** w sidebarze i w arkuszu „Więcej” paska PWA zamiast „Moje pupile” jest wyszarzona,
nieklikalna pozycja z łapką i napisem **„Wkrótce”**. Strona, API, widget i towarzysz są niewidoczne (404). Klienci zobaczą
prawdziwą zakładkę dopiero, gdy ustawisz rollout na **100%** (sekcja 3). Decyzja Konrada: bez stopniowego rolloutu — używamy
TYLKO dwóch stanów: **0%** (tylko admin/mod, klienci widzą „Wkrótce”) albo **100%** (wszyscy); pośrednich wartości (10, 50…) nie wpisujemy.
Przy WYŁĄCZONEJ fladze „Wkrótce” widzą wszyscy, także admin/mod — żeby testować na produkcji przed klientami, włącz flagę z rolloutem **0%**.

## 0. Przed pushem (lokalnie)
- [ ] pełna suita zielona (`venv/bin/python -m pytest -q`; jedyny znany czerwony test: DST w `test_mobile_api_auth`, niezwiązany),
- [ ] `git log main..feat/pupile` przejrzany, brak danych infrastruktury w diffie (repo jest publiczne),
- [ ] `static/sw.js` ma podbity `CACHE_VERSION` względem `main` (na gałęzi: `v39`),
- [ ] `git fetch` i `git log HEAD..origin/main`: jeśli `origin/main` poszedł do przodu, najpierw scalić go do gałęzi i sprawdzić `flask db heads` (musi być JEDNA głowa),
- [ ] w razie kolizji `CACHE_VERSION` z `main` — wziąć wyższą i podbić o 1.

## 1. Deploy (push do `main` → webhook → `flask db upgrade`)
- [ ] trzy migracje wchodzą automatycznie, jeden liniowy łańcuch nad `dde1a45a7d87`: `f3e9a1c7b2d4` (pupile), `b5d8e2f4a917` (szpital, skórki jajek), `c7a4d1e9f2b6` (żarty: tabela `pet_peek_images` + kolumna `pet_profiles.jokes_enabled`); w logu deployu brak błędów, `flask db heads` = jedna głowa,
- [ ] katalog `static/uploads/pet_peeks/` jest zapisywalny dla procesu aplikacji (powstaje przy pierwszym uploadzie obrazka; pliki nie idą do gitu),
- [ ] `pets_enabled` nie istnieje w `settings` → domyślnie `false`, `pets_rollout_pct` → `0`:
      klienci nic nie widzą, cron milczy (`skipped_disabled`).

## 2. Ręcznie na serwerze (konto z sudo, `cd /var/www/ThunderOrders`)
- [ ] `venv/bin/flask achievements seed` — dopisuje 9 odznak kategorii `pets` (deploy.sh robi tylko `db upgrade`),
- [ ] w panelu odznak dograć ikony dla slugów `pet-*` (seed nie tworzy plików),
- [ ] crontab: `10 * * * * cd /var/www/ThunderOrders && flock -n /tmp/pets-tick.lock venv/bin/flask pets tick >> logs/cron-pets.log 2>&1`
      (`:00` i `:05` są zajęte — limit SMTP; `flock -n` = dwa przebiegi nie nachodzą na siebie),
- [ ] sprawdzić, że `flask achievements check-daily` jest w crontabie (odznaka `pet-adults-8` jest cronowa),
- [ ] `venv/bin/flask pets tick --dry-run` → „Funkcja pupili wyłączona … pominięty” (flaga off = OK),
- [ ] `venv/bin/flask pets report --days 7` → tabela bez wyjątków (same zera).

## 3. Włączenie (panel `/admin/pupile`, sekcja „Włącznik i rollout”)
- [ ] **najpierw rollout 0%:** `pets_enabled` = ON, `pets_rollout_pct` = **0** → prawdziwą zakładkę widzą tylko admin/mod, klienci nadal „Wkrótce”; tu przetestować na produkcji,
- [ ] po zapisie: strona `/client/pupile` jako admin — odbiór startowego, ogrzanie, akcja; dashboard — widget; towarzysz (bieg, klik, przenoszenie),
- [ ] żarty: w karcie „Obrazki wychylania” wgrać ozdobniki (bez nich wychylenie się nie zdarza; kradzież kursora działa bez obrazków); checkbox „Żarty pupili włączone” domyślnie ON (awaryjny wyłącznik bez deployu); klient ma własny przełącznik „Żarty pupila” w warsztacie,
- [ ] po 1 h: `logs/cron-pets.log` ma wpis z `Użytkowników: N`; `flask pets report --days 1`,
- [ ] **premiera:** gdy wszystko sprawdzone na rolloucie 0% — `pets_rollout_pct` = **100** (wszyscy klienci od razu widzą prawdziwą zakładkę zamiast „Wkrótce”); potem `flask pets report --days 1` i `--days 7`,
- [ ] powrót do stanu „tylko admin”: `pets_rollout_pct` = **0** (klienci znowu widzą „Wkrótce”; dane i pupile zostają),
- [ ] e-mail: kill-switch `notify_pet_alert` w ustawieniach maili domyślnie włączony — wyłączyć tylko w razie problemu,
- [ ] ogłoszenie dla klientów: popup `display_mode='once'` z `cta_url=/client/pupile` (decyzja Konrada; krok toura „Twój pupil” działa od razu).

## 4. Rollback
- [ ] `pets_enabled` = OFF w panelu (natychmiast: strona/API 404, widget i towarzysz znikają, klienci znowu widzą „Wkrótce”, cron milczy; dane zostają),
- [ ] same żarty (kursor, wychylenie) można wyłączyć osobno: „Żarty pupili włączone” = OFF — bieg i reszta funkcji zostają,
- [ ] bez cofania migracji — tabele `pet_profiles`/`pets`/`pet_events`/`pet_peek_images` są nieszkodliwe przy wyłączonej fladze.

## 5. Monitoring pierwszych dni
- [ ] `flask pets report --days 1` codziennie przez tydzień (lejek: profile → odebrali → wyklucie; odejścia/100 żywych; reakcja na ostrzeżenie),
- [ ] GA4: zdarzenia `pet_action` (parametry `action`, `mood`) i `pet_hatch` (`result`) — porównać DAU z „aktywnymi opiekunami” z raportu,
- [ ] Sentry: błędy z `modules/pets/*` i `pets tick` (licznik `błędy: N` w podsumowaniu crona).
