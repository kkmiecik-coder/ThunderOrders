# Pupile — instrukcja crona (etap 3)

Komenda: `flask pets tick` (grupa `pets`), co godzinę o :10 — `:00` ma `check-payment-reminders`,
`:05` `check-delivery-confirmations` (limit połączeń SMTP Hostingera per IP).

Na serwerze (konto z dostępem do `/var/www/ThunderOrders`), `crontab -e`, dopisz na końcu:

```
# Pupile (tamagotchi): zbiorcze pushe/maile o stanie pupili, raz na epizod; porządki pet_events (task 869ffdb58)
10 * * * * cd /var/www/ThunderOrders && flock -n /tmp/pets-tick.lock venv/bin/flask pets tick >> logs/cron-pets.log 2>&1
```

Przed pierwszym uruchomieniem na prodzie: `venv/bin/flask pets tick --dry-run` (wypisuje koszyki,
nic nie zapisuje i nie wysyła). Dopóki `pets_enabled=false`, nikt nie ma pupili, więc przebieg
jest pusty — linię można dopisać od razu po deployu etapu 3.

Co robi przebieg: dla każdego aktywnego klienta z pupilami liczy stan, zapisuje odejścia, wysyła
jeden push (jeśli ma włączone „Powiadomienia o pupilach") i jeden mail przy krytycznym /
odejściu / ratunkowym nieodebranym od 7 dni (jeśli włączony `notify_pet_alert` w ustawieniach
maili admina), kasuje zdarzenia akcji starsze niż 90 dni.

Powiązane komendy z etapu 6 (dopisać przy włączaniu funkcji): `flask achievements seed` (nowe
odznaki kategorii `pets`) oraz sprawdzenie, że `flask achievements check-daily` jest w crontabie
(odznaka „Ośmiu dorosłych" jest typu cron).
