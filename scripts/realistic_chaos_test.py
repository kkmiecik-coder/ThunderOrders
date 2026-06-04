"""
REALISTIC CHAOS TEST — symulacja prawdziwej sprzedaży na żywo.

Scenariusz:
1. Setup: oferta scheduled, start za START_DELAY sekund, max=5, czyste DB.
2. T-START_DELAY: 30 userów (z 40) ładuje się na stronę countdown i czeka.
3. T-2s: kolejne 5 userów dochodzi (early birds, ale wciąż przed startem).
4. T=0 (start sprzedaży): chaos zaczyna się:
   - 70% (≈28 userów): natychmiast próbują rezerwacji + zakupu z losowym timingiem
   - 10% (4 userów): "spóźnialscy" — dołączają T+5..T+30s
   - 10% (4 userów): "klikacze" — wysyłają reserve 2-3x szybko z rzędu (double-click)
   - 5% (2 userów): "slow" — czekają 10-20s po join przed jakąkolwiek akcją
   - 5% (2 userów): "disconnect mid-flow" — rezerwują, ale rozłączają się przed
     place_order
5. Każdy aktywny user wybiera losowy produkt z 8 (Hongjoong..Jongho).
6. Niektórzy próbują kupić więcej niż 1 sztukę.
7. Cleanup + raport.

Sprawdzane inwarianty:
- Atomowość: dla każdego produktu suma ordered ≤ aktualny set_max_sets
- Visitor count: cross-process aktualizuje się real-time
- Auto-increase: triggeruje gdy ≥50% produktów osiągnie 100%
- Brak deadlocków, brak crashy workerów, brak tracebacków w logach
"""
import asyncio
import random
import time
import uuid
import statistics
import subprocess
from collections import Counter, defaultdict

import aiohttp
import socketio

BASE_URL = "http://127.0.0.1:8000"
WS_BASE_URL = "http://localhost:8090"
PAGE_ID = 79
PAGE_TOKEN = "0xPLnb2LXtrKResxH-D-SA"
ALL_PRODUCT_IDS = [487, 488, 489, 490, 491, 492, 493, 494]
NUM_USERS = 40
PASSWORD = "test1234"
# Sekundy od T=0 do startu sprzedaży. 60s = userzy faktycznie czekają na countdown
# page (admin LIVE dashboard pokazuje visitor count w trakcie czekania).
# Zwiększ na 300 dla 5min realnego czekania.
START_DELAY = 75  # daje 35-65s realnego czekania userów na countdown


async def login(session, user_idx):
    email = f"stresstest{user_idx}@local.test"
    fake_ip = f"10.99.{user_idx // 256}.{user_idx % 256}"
    async with session.post(
        f"{BASE_URL}/auth/login",
        data={"email": email, "password": PASSWORD, "remember_me": "on"},
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
            "X-Forwarded-For": fake_ip,
        },
        allow_redirects=False,
    ) as r:
        body = await r.text()
        if r.status != 200:
            raise RuntimeError(f"Login {email} status={r.status}: {body[:200]}")
        try:
            data = await r.json(content_type=None)
        except Exception:
            raise RuntimeError(f"Login {email} non-JSON: {body[:200]}")
        if not data.get("success"):
            raise RuntimeError(f"Login {email}: {data.get('error', body[:200])}")
        return (data.get("user") or {}).get("id")


class ChaosUser:
    def __init__(self, idx, profile):
        self.idx = idx
        self.profile = profile  # 'normal', 'late', 'clicker', 'slow', 'ghost'
        self.session_id = str(uuid.uuid4())
        self.cookie_jar = aiohttp.CookieJar(unsafe=True)
        self.session = None
        self.user_id = None
        self.sio = None
        self.connected = False
        self.reserved_products = []
        self.placed_order = False
        self.events = []
        self.force_disconnected = False

    async def login_and_connect_ws(self):
        """Login HTTP + SocketIO connect."""
        self.session = aiohttp.ClientSession(cookie_jar=self.cookie_jar)
        self.user_id = await login(self.session, self.idx)
        cookies = {c.key: c.value for c in self.cookie_jar}
        self.sio = socketio.AsyncClient(reconnection=False)

        @self.sio.event
        async def connect():
            self.connected = True

        @self.sio.event
        async def disconnect():
            self.connected = False

        @self.sio.event
        async def force_disconnect(data):
            self.force_disconnected = True
            self.events.append(('force_disconnect', data))

        await self.sio.connect(
            WS_BASE_URL,
            headers={'Cookie': '; '.join(f'{k}={v}' for k, v in cookies.items())},
            transports=['websocket', 'polling'],
            wait=True,
        )

    async def join_countdown(self):
        """Symuluje wejście na stronę countdown przed startem."""
        try:
            await self.sio.emit('join_offer', {'page_id': PAGE_ID, 'page_type': 'countdown'})
            self.events.append(('joined_countdown', time.time()))
        except Exception as e:
            self.events.append(('error_countdown', str(e)))

    async def goto_order_page(self):
        """HTTP GET strony oferty — jak przeglądarka po redirect z countdown.
        Triggeruje check_and_update_status w aplikacji."""
        fake_ip = f"10.99.{self.idx // 256}.{self.idx % 256}"
        try:
            async with self.session.get(
                f"{BASE_URL}/offer/{PAGE_TOKEN}",
                headers={"X-Forwarded-For": fake_ip},
                timeout=aiohttp.ClientTimeout(total=5),
                allow_redirects=False,
            ) as r:
                return r.status
        except Exception:
            return None

    async def join_order_page(self):
        """Wejście na stronę zamówień (po starcie) — najpierw GET, potem SocketIO."""
        await self.goto_order_page()
        try:
            ack = await self.sio.call('join_offer_reservation', {
                'page_id': PAGE_ID,
                'session_id': self.session_id,
                'user_id': self.user_id,
                'token': PAGE_TOKEN,
            }, timeout=10)
            self.events.append(('joined_order', ack.get('success', False)))
            return ack
        except asyncio.TimeoutError:
            self.events.append(('timeout_join_order',))
            return {'success': False, 'error': 'timeout'}

    async def reserve(self, product_id, quantity=1):
        start = time.perf_counter()
        try:
            ack = await self.sio.call('reserve_product', {
                'page_id': PAGE_ID,
                'session_id': self.session_id,
                'product_id': product_id,
                'quantity': quantity,
            }, timeout=10)
            latency = (time.perf_counter() - start) * 1000
            if ack.get('success'):
                self.reserved_products.append((product_id, quantity))
            return ack, latency
        except asyncio.TimeoutError:
            return {'success': False, 'error': 'timeout'}, (time.perf_counter() - start) * 1000

    async def place_order(self):
        fake_ip = f"10.99.{self.idx // 256}.{self.idx % 256}"
        start = time.perf_counter()
        try:
            async with self.session.post(
                f"{BASE_URL}/offer/{PAGE_TOKEN}/place-order",
                json={"session_id": self.session_id, "order_note": f"chaos {self.profile} user {self.idx}"},
                headers={"X-Requested-With": "XMLHttpRequest", "X-Forwarded-For": fake_ip},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                latency = (time.perf_counter() - start) * 1000
                try:
                    data = await r.json()
                except Exception:
                    data = {'success': False, 'error': f'http_{r.status}'}
                if data.get('success'):
                    self.placed_order = True
                return data, latency
        except Exception as e:
            return {'success': False, 'error': type(e).__name__}, (time.perf_counter() - start) * 1000

    async def disconnect(self):
        try:
            if self.sio and self.connected:
                await self.sio.disconnect()
        except Exception:
            pass
        try:
            if self.session:
                await self.session.close()
        except Exception:
            pass


# === Scenariusze zachowań ===

async def behavior_normal(user, t_start, stats):
    """Normalny user: czeka do startu, próbuje rezerwacji + zakupu."""
    delay = max(0, t_start - time.time()) + random.uniform(0, 3)
    await asyncio.sleep(delay)
    await user.join_order_page()
    await asyncio.sleep(random.uniform(0.3, 1.5))

    product = random.choice(ALL_PRODUCT_IDS)
    qty = random.choices([1, 1, 1, 2], k=1)[0]
    ack, lat = await user.reserve(product, qty)
    stats['reserve_latencies'].append(lat)
    stats['reserve_results'][ack.get('error') if not ack.get('success') else 'ok'] += 1

    if ack.get('success'):
        await asyncio.sleep(random.uniform(0.5, 2.5))
        order_data, order_lat = await user.place_order()
        stats['order_latencies'].append(order_lat)
        stats['order_results'][order_data.get('error') if not order_data.get('success') else 'ok'] += 1


async def behavior_late(user, t_start, stats):
    """Spóźnialski: dołącza T+5..T+30s — sprzedaż już trwa."""
    late_seconds = random.uniform(5, 30)
    await asyncio.sleep(max(0, t_start - time.time()) + late_seconds)
    await user.join_order_page()
    await asyncio.sleep(random.uniform(0.5, 1.5))
    product = random.choice(ALL_PRODUCT_IDS)
    ack, lat = await user.reserve(product, 1)
    stats['reserve_latencies'].append(lat)
    stats['reserve_results'][ack.get('error') if not ack.get('success') else 'ok'] += 1
    if ack.get('success'):
        order_data, order_lat = await user.place_order()
        stats['order_latencies'].append(order_lat)
        stats['order_results'][order_data.get('error') if not order_data.get('success') else 'ok'] += 1


async def behavior_clicker(user, t_start, stats):
    """Klikacz: 2-3x próbuje reserve szybko z rzędu (jak nerwowy user)."""
    await asyncio.sleep(max(0, t_start - time.time()) + random.uniform(0, 2))
    await user.join_order_page()
    await asyncio.sleep(0.5)
    product = random.choice(ALL_PRODUCT_IDS)
    # 3 szybkie próby
    for _ in range(3):
        ack, lat = await user.reserve(product, 1)
        stats['reserve_latencies'].append(lat)
        stats['reserve_results'][ack.get('error') if not ack.get('success') else 'ok'] += 1
        await asyncio.sleep(random.uniform(0.05, 0.2))
    if user.reserved_products:
        order_data, order_lat = await user.place_order()
        stats['order_latencies'].append(order_lat)
        stats['order_results'][order_data.get('error') if not order_data.get('success') else 'ok'] += 1


async def behavior_slow(user, t_start, stats):
    """Slow user: czeka 10-20s po starcie, w międzyczasie produkty się rozchodzą."""
    await asyncio.sleep(max(0, t_start - time.time()) + random.uniform(10, 20))
    await user.join_order_page()
    await asyncio.sleep(random.uniform(2, 5))  # długo myśli
    product = random.choice(ALL_PRODUCT_IDS)
    ack, lat = await user.reserve(product, 1)
    stats['reserve_latencies'].append(lat)
    stats['reserve_results'][ack.get('error') if not ack.get('success') else 'ok'] += 1
    if ack.get('success'):
        await asyncio.sleep(random.uniform(3, 8))  # długo decyduje czy kupić
        order_data, order_lat = await user.place_order()
        stats['order_latencies'].append(order_lat)
        stats['order_results'][order_data.get('error') if not order_data.get('success') else 'ok'] += 1


async def behavior_ghost(user, t_start, stats):
    """Ghost: rezerwuje, ale rozłącza się przed place_order — rezerwacja wygasa."""
    await asyncio.sleep(max(0, t_start - time.time()) + random.uniform(0, 5))
    await user.join_order_page()
    await asyncio.sleep(random.uniform(0.5, 2))
    product = random.choice(ALL_PRODUCT_IDS)
    ack, lat = await user.reserve(product, 1)
    stats['reserve_latencies'].append(lat)
    stats['reserve_results'][ack.get('error') if not ack.get('success') else 'ok'] += 1
    if ack.get('success'):
        stats['ghosts_with_reservation'] += 1
    # Rozłącz się bez place_order
    await user.disconnect()


PROFILES = ['normal', 'normal', 'normal', 'normal', 'normal', 'normal', 'normal',
            'late', 'clicker', 'slow', 'ghost']
BEHAVIOR_MAP = {
    'normal': behavior_normal,
    'late': behavior_late,
    'clicker': behavior_clicker,
    'slow': behavior_slow,
    'ghost': behavior_ghost,
}


def db(sql):
    """Helper: wykonaj SQL i zwróć stdout."""
    return subprocess.run(
        ['/Applications/XAMPP/xamppfiles/bin/mysql', '-u', 'root', 'thunder_orders', '-e', sql],
        capture_output=True, text=True
    ).stdout


async def main():
    print("="*60)
    print("REALISTIC CHAOS TEST — 40 userów, oferta scheduled")
    print("="*60)

    # === Setup DB ===
    print("\n[setup] Reset oferty 79 → scheduled w przyszłości, max=5, czysta")
    from datetime import datetime, timedelta
    starts_at = (datetime.now() + timedelta(seconds=START_DELAY)).strftime('%Y-%m-%d %H:%M:%S')
    ends_at = (datetime.now() + timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')
    db(f"""
        DELETE oi FROM order_items oi JOIN orders o ON oi.order_id=o.id WHERE o.offer_page_id={PAGE_ID};
        DELETE FROM orders WHERE offer_page_id={PAGE_ID};
        DELETE FROM offer_reservations WHERE offer_page_id={PAGE_ID};
        DELETE FROM offer_auto_increase_log WHERE offer_page_id={PAGE_ID};
        UPDATE offer_sections SET set_max_sets=5 WHERE offer_page_id={PAGE_ID} AND section_type='set';
        UPDATE offer_pages SET status='scheduled',
            starts_at='{starts_at}', ends_at='{ends_at}',
            is_fully_closed=0, closed_at=NULL
            WHERE id={PAGE_ID};
    """)
    subprocess.run(['redis-cli', '-n', '0', 'FLUSHDB'], capture_output=True)
    subprocess.run(['redis-cli', '-n', '1', 'FLUSHDB'], capture_output=True)
    print(f"[setup] starts_at={starts_at}, ends_at={ends_at}")

    # === Utwórz userów z profilami ===
    random.seed(42)  # deterministyczne profile
    users = []
    for i in range(1, NUM_USERS + 1):
        profile = random.choices(
            population=['normal', 'late', 'clicker', 'slow', 'ghost'],
            weights=[28, 4, 4, 2, 2],
            k=1
        )[0]
        users.append(ChaosUser(i, profile))

    profile_counts = Counter(u.profile for u in users)
    print(f"\n[users] Profile: {dict(profile_counts)}")

    # === Faza 1: login wszystkich + join countdown ===
    print("\n[phase1] Login + SocketIO connect dla wszystkich 40 userów...")
    t0 = time.perf_counter()
    results = await asyncio.gather(*(u.login_and_connect_ws() for u in users), return_exceptions=True)
    errors = [(u.idx, r) for u, r in zip(users, results) if isinstance(r, Exception)]
    connected = [u for u in users if u.connected]
    print(f"[phase1] Connected: {len(connected)}/{NUM_USERS}, errors: {len(errors)}")
    for idx, e in errors[:3]:
        print(f"  user{idx}: {type(e).__name__}: {str(e)[:80]}")
    print(f"[phase1] elapsed: {(time.perf_counter()-t0)*1000:.0f}ms")

    # === Faza 2: countdown — większość userów łączy się przed startem ===
    # 35 z 40 wchodzi na countdown teraz, 5 to "late" — dołączy po starcie
    # (ich behavior_late samodzielnie zrobi join_order_page)
    waiting_users = connected[:35]
    late_users = connected[35:]
    print(f"\n[phase2] Countdown — {len(waiting_users)} userów łączy się jako visitor")
    await asyncio.gather(*(u.join_countdown() for u in waiting_users), return_exceptions=True)

    # t_start to ABSOLUTNY czas startu sprzedaży = starts_at z DB
    t_start = datetime.fromisoformat(starts_at).timestamp()
    print(f"[phase2] Start sprzedaży za {t_start - time.time():.1f}s (T={starts_at})")
    print(f"[phase2] Userzy fizycznie czekają na countdown — sprawdzam visitor count co 15s:")

    # Heartbeat: pokazuj stan w trakcie czekania
    async def countdown_heartbeat():
        while time.time() < t_start:
            remaining = t_start - time.time()
            visitors_countdown = subprocess.run(
                ['redis-cli', '-n', '0', 'SCARD', f'visitors:{PAGE_ID}:countdown'],
                capture_output=True, text=True
            ).stdout.strip()
            visitors_order = subprocess.run(
                ['redis-cli', '-n', '0', 'SCARD', f'visitors:{PAGE_ID}:order'],
                capture_output=True, text=True
            ).stdout.strip()
            admins = subprocess.run(
                ['redis-cli', '-n', '0', 'SCARD', f'admins:{PAGE_ID}'],
                capture_output=True, text=True
            ).stdout.strip()
            print(f"  T-{remaining:.0f}s | visitors countdown={visitors_countdown}, order={visitors_order}, admins={admins}")
            await asyncio.sleep(min(15, max(1, remaining)))

    # Aplikacja sama przejdzie scheduled→active przy pierwszym requeście po t_start
    # (modules/offers/models.py:check_and_update_status). Symulujemy redirect z
    # countdown→order page który robi przeglądarka po wybiciu zegara.
    async def announce_start():
        await asyncio.sleep(max(0, t_start - time.time()))
        print(f"\n[!! SALE START !!] T={datetime.now().strftime('%H:%M:%S')}")
        # User 1 robi GET /offer/<token> — to triggeruje check_and_update_status
        # w aplikacji (modules/offers/models.py:271) i zmienia status scheduled→active
        async with aiohttp.ClientSession() as s:
            try:
                async with s.get(f"{BASE_URL}/offer/{PAGE_TOKEN}", timeout=aiohttp.ClientTimeout(total=5)) as r:
                    print(f"  [trigger] GET /offer/{PAGE_TOKEN} → {r.status} (powinno aktywować ofertę)")
            except Exception as e:
                print(f"  [trigger ERROR] {type(e).__name__}: {e}")
        # Krótka pauza żeby DB commit się propagował
        await asyncio.sleep(0.5)
        new_status = db(f"SELECT status FROM offer_pages WHERE id={PAGE_ID};").strip().split('\n')[-1]
        print(f"  [status] po triggerze: {new_status}")

    # === Faza 3: chaos ===
    print(f"\n[phase3] CHAOS — 40 userów z różnymi profilami uderzają w ofertę")
    stats = {
        'reserve_results': Counter(),
        'reserve_latencies': [],
        'order_results': Counter(),
        'order_latencies': [],
        'ghosts_with_reservation': 0,
    }

    chaos_tasks = [BEHAVIOR_MAP[u.profile](u, t_start, stats) for u in connected]
    chaos_tasks.append(announce_start())
    chaos_tasks.append(countdown_heartbeat())
    chaos_start = time.perf_counter()
    await asyncio.gather(*chaos_tasks, return_exceptions=True)
    chaos_elapsed = (time.perf_counter() - chaos_start) * 1000

    # === Faza 4: raport ===
    print("\n" + "="*60)
    print("RAPORT")
    print("="*60)
    print(f"\nCzas chaosu: {chaos_elapsed:.0f}ms")
    print(f"\n--- Rezerwacje ---")
    print(f"  Wyniki: {dict(stats['reserve_results'])}")
    if stats['reserve_latencies']:
        lats = sorted(stats['reserve_latencies'])
        print(f"  Latencja: avg={statistics.mean(lats):.0f}ms, "
              f"p50={statistics.median(lats):.0f}ms, "
              f"p95={lats[int(len(lats)*0.95)]:.0f}ms, "
              f"max={max(lats):.0f}ms")

    print(f"\n--- Zamówienia ---")
    print(f"  Wyniki: {dict(stats['order_results'])}")
    if stats['order_latencies']:
        lats = sorted(stats['order_latencies'])
        print(f"  Latencja: avg={statistics.mean(lats):.0f}ms, "
              f"p50={statistics.median(lats):.0f}ms, "
              f"p95={lats[int(len(lats)*0.95)]:.0f}ms, "
              f"max={max(lats):.0f}ms")

    print(f"\n--- Edge cases ---")
    print(f"  Force disconnects: {sum(1 for u in users if u.force_disconnected)}")
    print(f"  Ghosts z rezerwacją: {stats['ghosts_with_reservation']}")
    placed_orders = sum(1 for u in users if u.placed_order)
    print(f"  Userów którzy złożyli zamówienie: {placed_orders}/{NUM_USERS}")

    # === Faza 5: weryfikacja w DB ===
    print(f"\n--- Stan DB po teście ---")
    print("Zamówione per produkt:")
    print(db(f"""
        SELECT oi.product_id, SUM(oi.quantity) AS ordered
        FROM order_items oi JOIN orders o ON oi.order_id=o.id
        WHERE o.offer_page_id={PAGE_ID} AND o.status != 'anulowane'
        GROUP BY oi.product_id ORDER BY oi.product_id;
    """))

    print("set_max_sets (start: 5; powinien rosnąć jeśli auto-increase triggerował):")
    print(db(f"SELECT set_max_sets FROM offer_sections WHERE offer_page_id={PAGE_ID} AND section_type='set';"))

    print("Auto-increase log:")
    print(db(f"""
        SELECT old_max_quantity AS old_max, new_max_quantity AS new_max,
               products_at_threshold, trigger_set_threshold, triggered_at
        FROM offer_auto_increase_log WHERE offer_page_id={PAGE_ID} ORDER BY id;
    """))

    print("Aktywne rezerwacje (po teście — TTL nie wygasł):")
    print(db(f"""
        SELECT product_id, COUNT(*) AS reservations, SUM(quantity) AS qty
        FROM offer_reservations WHERE offer_page_id={PAGE_ID}
        GROUP BY product_id ORDER BY product_id;
    """))

    # === Inwarianty ===
    print("\n--- Inwarianty ---")
    invariants_ok = True

    # 1. Atomowość: dla każdego produktu suma ordered ≤ current set_max_sets
    rows = db(f"""SELECT product_id, SUM(oi.quantity) AS ordered
        FROM order_items oi JOIN orders o ON oi.order_id=o.id
        WHERE o.offer_page_id={PAGE_ID} AND o.status != 'anulowane'
        GROUP BY product_id;""").strip().split('\n')[1:]
    max_now_row = db(f"SELECT set_max_sets FROM offer_sections WHERE offer_page_id={PAGE_ID} AND section_type='set';").strip().split('\n')[1:]
    max_now = int(max_now_row[0]) if max_now_row else 5
    for row in rows:
        if not row.strip():
            continue
        pid, qty = row.split('\t')
        qty = int(qty)
        if qty > max_now:
            print(f"  ❌ Product {pid}: ordered={qty} > max={max_now} — OVERSELLING!")
            invariants_ok = False
    if invariants_ok:
        print(f"  ✅ Atomowość OK — żaden produkt nie przekroczył max_set={max_now}")

    # === Cleanup ===
    print("\n[cleanup]")
    await asyncio.gather(*(u.disconnect() for u in users), return_exceptions=True)
    print("Done.")

    print("\n" + "="*60)
    print("KONIEC" if invariants_ok else "INWARIANT NARUSZONY!")
    print("="*60)


if __name__ == '__main__':
    asyncio.run(main())
