# POMYSLY THUNDER - Zaparkowane pomysly i przyszle funkcjonalnosci

**Data utworzenia:** 2026-02-21

---

## Zaparkowane z audytu flow Exclusive (2026-02-21)

### 1. Email platnosci dla goscia
**Kontekst:** Kod sprawdza `order.user` ktore jest `None` dla gosci - gosc nigdy nie dostanie emaila o zatwierdzeniu/odrzuceniu platnosci.
**Wymagane:** Omowienie szczegolow implementacji (fallback na `guest_email`, dostep goscia do panelu platnosci).
**Status:** Do omowienia

### 2. Gosc - upload dowodu platnosci
**Kontekst:** Panel `/client/payment-confirmations` wymaga `@login_required`. Gosc nie ma jak wgrac potwierdzenia platnosci.
**Wymagane:** Omowienie - czy stworzyc osobna sciezke z tokenem, czy wymusic rejestracje.
**Status:** Do omowienia

### 3. Przypomnienie o platnosci (CRON)
**Kontekst:** Jesli klient nie zaplaci od X dni, brak automatycznego followupu emailowego.
**Wymagane:** Konfiguracja zadania CRON na serwerze VPS. Potrzebne:
- Skrypt Python sprawdzajacy niezaplacone zamowienia starsze niz X dni
- Konfiguracja CRON na VPS: `crontab -e` -> np. `0 9 * * * cd /var/www/ThunderOrders && venv/bin/python -m utils.payment_reminders`
- Lub uzycie Flask CLI command: `flask send-payment-reminders`
- Szablon emaila z przypomnieniem
**Status:** Zaparkowane - wymaga konfiguracji serwera

### 4. System powiadomien in-app (dzwoneczek)
**Kontekst:** Dzwoneczek powiadomien zostal usuniety. Przywrocic po wdrozeniu pelnego systemu powiadomien.
**Wymagane:** Model Notification, endpointy API, frontend z real-time updates.
**Status:** Przyszla faza

---

## Inne pomysly

_(Miejsce na nowe pomysly w trakcie rozwoju)_
