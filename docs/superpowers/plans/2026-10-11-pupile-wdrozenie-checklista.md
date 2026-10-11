# Pupile — checklista włączenia na produkcji

Spec §7. Kolejność ma znaczenie: kod i migracja wchodzą z flagą WYŁĄCZONĄ, włączenie to osobny krok
z panelu admina. Instrukcja crona: `2026-10-11-pupile-cron-instrukcja.md`.

## 0. Przed pushem (lokalnie)
- [ ] pełna suita zielona (`venv/bin/python -m pytest -q`; jedyny znany czerwony test: DST w `test_mobile_api_auth`, niezwiązany),
- [ ] `git log main..feat/pupile` przejrzany, brak danych infrastruktury w diffie (repo jest publiczne),
- [ ] `static/sw.js` ma podbity `CACHE_VERSION` względem `main`.

## 1. Deploy (push do `main` → webhook → `flask db upgrade`)
- [ ] migracja `f3e9a1c7b2d4` (pupile) wchodzi automatycznie; w logu deployu brak błędów,
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
- [ ] `pets_enabled` = ON, `pets_rollout_pct` = **10** → zapis; admin/mod widzą od razu, klienci wg `user_id % 100 < 10`,
- [ ] po zapisie: strona `/client/pupile` jako admin — odbiór startowego, ogrzanie, akcja; dashboard — widget; towarzysz,
- [ ] po 1 h: `logs/cron-pets.log` ma wpis z `Użytkowników: N`; `flask pets report --days 1`,
- [ ] po ~tygodniu: `pets_rollout_pct` = **50**, po kolejnym: **100**; po każdym kroku `flask pets report --days 7`,
- [ ] e-mail: kill-switch `notify_pet_alert` w ustawieniach maili domyślnie włączony — wyłączyć tylko w razie problemu,
- [ ] ogłoszenie dla klientów: popup `display_mode='once'` z `cta_url=/client/pupile` (decyzja Konrada; krok toura „Twój pupil” działa od razu).

## 4. Rollback
- [ ] `pets_enabled` = OFF w panelu (natychmiast: strona/API 404, widget i towarzysz znikają, cron milczy; dane zostają),
- [ ] bez cofania migracji — tabele `pet_profiles`/`pets`/`pet_events` są nieszkodliwe przy wyłączonej fladze.

## 5. Monitoring pierwszych dni
- [ ] `flask pets report --days 1` codziennie przez tydzień (lejek: profile → odebrali → wyklucie; odejścia/100 żywych; reakcja na ostrzeżenie),
- [ ] GA4: zdarzenia `pet_action` (parametry `action`, `mood`) i `pet_hatch` (`result`) — porównać DAU z „aktywnymi opiekunami” z raportu,
- [ ] Sentry: błędy z `modules/pets/*` i `pets tick` (licznik `błędy: N` w podsumowaniu crona).
