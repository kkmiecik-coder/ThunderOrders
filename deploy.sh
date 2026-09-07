#!/bin/bash
# ThunderOrders Auto-Deploy Script
# Called by GitHub webhook after push to main

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

LOCK_FILE="/tmp/thunderorders-deploy.lock"
APP_DIR="/var/www/ThunderOrders"
LOG_PREFIX="[DEPLOY $(date '+%Y-%m-%d %H:%M:%S')]"

# Prevent concurrent deploys
if [ -f "$LOCK_FILE" ]; then
    echo "$LOG_PREFIX Already deploying, skipping."
    exit 0
fi
trap "rm -f $LOCK_FILE" EXIT
touch "$LOCK_FILE"

echo "$LOG_PREFIX Starting deploy..."

cd "$APP_DIR" || exit 1

echo "$LOG_PREFIX Pulling latest code..."
# Nieudany `git pull` NIE MOŻE przejść dalej. Wcześniej skrypt leciał do końca i meldował
# "Deploy complete!" mimo starego kodu na dysku: 2026-09-02 produkcja przez ~40 min serwowała
# kod sprzed doby, a log deployu i dostawa webhooka w GitHubie pokazywały sukces. Awaria była
# niewidoczna aż ktoś zauważył, że zmiany "nie weszły".
#
# Powód samego padu: GitHub sporadycznie odrzuca anonimowy fetch po HTTPS
# ("fatal: could not read Username for 'https://github.com'"), mimo że repo jest publiczne
# i kolejne próby przechodzą bez zmian w konfiguracji. Stąd retry przed poddaniem się.
PULL_OK=0
for attempt in 1 2 3; do
    if git pull origin main 2>&1; then
        PULL_OK=1
        break
    fi
    echo "$LOG_PREFIX git pull nie powiódł się (próba $attempt/3), ponawiam za 5 s..."
    sleep 5
done

if [ "$PULL_OK" -ne 1 ]; then
    echo "$LOG_PREFIX ================================================================"
    echo "$LOG_PREFIX BŁĄD: git pull nie powiódł się po 3 próbach. PRZERYWAM DEPLOY."
    echo "$LOG_PREFIX Kod na serwerze zostaje na $(git rev-parse --short HEAD) — usługi NIE"
    echo "$LOG_PREFIX zostały zrestartowane, produkcja dalej chodzi na poprzedniej wersji."
    echo "$LOG_PREFIX Naprawa: zaloguj się na serwer i uruchom ponownie ten skrypt."
    echo "$LOG_PREFIX ================================================================"
    exit 1
fi

echo "$LOG_PREFIX Installing dependencies..."
source venv/bin/activate
pip install -r requirements.txt --quiet 2>&1

echo "$LOG_PREFIX Running migrations..."
flask db upgrade 2>&1

echo "$LOG_PREFIX Reloading application..."
# Architektura rozdzielona (2026-06-04): HTTP (gthread) + WS (eventlet/Socket.IO).
# Stara monolityczna usługa `thunderorders` jest martwa (disabled) — NIE ruszać jej tutaj,
# bo failuje z "Connection in use: 8000" i nie przeładowuje żywych procesów.
# UWAGA: osobne komendy per usługa, bo reguła sudoers NOPASSWD dopasowuje dokładne wywołanie.
#
# RELOAD, NIE RESTART. `systemctl restart` zatrzymywał gunicorna do końca i dopiero potem
# startował — przez te ~2-4 s gniazdo 127.0.0.1:8000 nie istniało, nginx dostawał
# ECONNREFUSED i oddawał klientom 502 (2026-09-02: 125 sztuk, głównie na
# /client/api/offer-pages). `reload` wysyła HUP do mastera (ExecReload w .service):
# master i gniazdo nasłuchujące zostają, wymieniane są tylko workery — nginx nie ma
# ani chwili bez upstreamu. Zweryfikowane 2026-09-07: MainPID identyczny przed i po.
#
# Fallback na restart jest ŚWIADOMY: gdyby reload kiedykolwiek nie przeszedł (brak reguły
# sudoers po zmianie kont, usługa nie stoi, zmiana w samym gunicorn_*.py której HUP nie
# podnosi), lepiej wdrożyć z krótkim 502 niż zostawić produkcję na starym kodzie i meldować
# przy tym sukces — na tym już raz się przejechaliśmy.
#
# Zwolnij lock PRZED przeładowaniem: skrypt biegnie w cgroupie usługi thunderorders-http
# (webhook obsługuje ta sama usługa). Reload go nie ubija, ale awaryjny restart owszem
# (SIGTERM, "Terminated") — zanim trap EXIT zdąży usunąć lock. Bez tego lock zostaje
# osierocony i blokuje WSZYSTKIE kolejne deploye ("Already deploying, skipping").
rm -f "$LOCK_FILE"
# KOLEJNOŚĆ: najpierw -ws, potem -http — istotna dla ścieżki awaryjnej. Restart -http
# ubija ten skrypt natychmiast, więc linia po nim nigdy by się nie wykonała. Przy starej
# kolejności -ws nie był restartowany NIGDY (potwierdzone 2026-06-12: ws działał na kodzie
# sprzed 10h mimo deployu) i procesy serwowały rozjechane wersje kodu.
przeladuj() {
    local usluga="$1"
    if sudo systemctl reload "$usluga" 2>&1; then
        echo "$LOG_PREFIX $usluga przeładowana łagodnie (bez przerwy w obsłudze)"
    else
        echo "$LOG_PREFIX UWAGA: reload $usluga nie przeszedł — awaryjny restart (możliwe krótkie 502)"
        sudo systemctl restart "$usluga" 2>&1
    fi
}
przeladuj thunderorders-ws
przeladuj thunderorders-http

# Reload nie ubija tego skryptu, więc w odróżnieniu od restartu ta linia naprawdę się wykona.
echo "$LOG_PREFIX Deploy complete!"
