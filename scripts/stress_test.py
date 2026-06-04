"""
Stress test ThunderOrders — 20 jednoczesnych userów na ofercie 79.

Trzy fazy:
1. Sanity   — 20 userów loguje się + dołącza jako visitor; admin powinien
              widzieć 20 osób na stronie order
2. Race     — 20 userów próbuje JEDNOCZEŚNIE zarezerwować product_id=487
              z limit=5. Powinno wygrać dokładnie 5, reszta dostać
              insufficient_availability
3. Chaos    — random mix reserve/release na różnych produktach, sprawdzenie
              że visitor count się zgadza i że nie ma deadlocków

Wymaga:
- 20 test userów stworzonych przez scripts/create_test_users.py
- HTTP gunicorn na 127.0.0.1:8000, WS gunicorn na 127.0.0.1:8001
- nginx na localhost:8090 (routuje /socket.io/ na 8001, reszta na 8000)
- Redis na localhost:6379
"""
import asyncio
import time
import uuid
import statistics
import sys
from collections import Counter

import aiohttp
import socketio

# HTTP traffic: bezpośrednio do gunicorn (cookies muszą żyć na tym samym hoście).
# X-Forwarded-For per user obchodzi rate limiter 15/min/IP w lokalnym teście
# (na produkcji każdy user ma swój prawdziwy IP).
BASE_URL = "http://127.0.0.1:8000"

# Socket.IO traffic: przez nginx (testuje pełen stack proxy /socket.io/* → WS process)
WS_BASE_URL = "http://localhost:8090"
PAGE_ID = 79
PAGE_TOKEN = "0xPLnb2LXtrKResxH-D-SA"
TARGET_PRODUCT_ID = 487  # Hongjoong — limit = 5 (set_max_sets)
ALL_PRODUCT_IDS = [487, 488, 489, 490, 491, 492, 493, 494]
NUM_USERS = 20
PASSWORD = "test1234"


async def login(session, user_idx):
    """Login user via AJAX endpoint (zwraca JSON, CSRF-exempt)."""
    email = f"stresstest{user_idx}@local.test"
    # Fake IP per user — żeby rate limiter (15/min/IP) widział różne IP
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
        body_text = await r.text()
        if r.status != 200:
            raise RuntimeError(f"Login failed for {email}: status={r.status} body={body_text[:200]}")
        try:
            data = await r.json(content_type=None)
        except Exception:
            raise RuntimeError(f"Login failed for {email}: non-JSON response: {body_text[:200]}")
        if not data.get("success"):
            raise RuntimeError(f"Login failed for {email}: {data.get('error', body_text[:200])}")
        return data


async def get_user_id_from_login_response(data):
    """Wyciąga user_id z AJAX response loginu."""
    if not data:
        return None
    return (data.get("user") or {}).get("id") or data.get("user_id")


class StressUser:
    def __init__(self, idx):
        self.idx = idx
        self.email = f"stresstest{idx}@local.test"
        self.session_id = str(uuid.uuid4())
        self.session = None
        self.user_id = None
        self.sio = None
        self.connected = False
        self.events = []  # raporty z testu
        self.cookie_jar = aiohttp.CookieJar(unsafe=True)

    async def connect(self):
        """Login HTTP + connect SocketIO."""
        self.session = aiohttp.ClientSession(cookie_jar=self.cookie_jar)
        login_data = await login(self.session, self.idx)
        self.user_id = await get_user_id_from_login_response(login_data)

        # Extract cookies for SocketIO
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
            self.events.append(('force_disconnect', data))

        await self.sio.connect(
            WS_BASE_URL,
            headers={'Cookie': '; '.join(f'{k}={v}' for k, v in cookies.items())},
            transports=['websocket', 'polling'],
            wait=True,
        )

    async def join_reservation(self):
        """Dołącz do systemu rezerwacji oferty."""
        ack = await self.sio.call('join_offer_reservation', {
            'page_id': PAGE_ID,
            'session_id': self.session_id,
            'user_id': self.user_id,
            'token': PAGE_TOKEN,
        }, timeout=10)
        return ack

    async def reserve(self, product_id, quantity=1):
        """Spróbuj zarezerwować produkt."""
        start = time.perf_counter()
        try:
            ack = await self.sio.call('reserve_product', {
                'page_id': PAGE_ID,
                'session_id': self.session_id,
                'product_id': product_id,
                'quantity': quantity,
            }, timeout=10)
            elapsed = (time.perf_counter() - start) * 1000
            return ack, elapsed
        except asyncio.TimeoutError:
            return {'success': False, 'error': 'timeout'}, (time.perf_counter() - start) * 1000

    async def release(self, product_id, quantity=1):
        try:
            ack = await self.sio.call('release_product', {
                'page_id': PAGE_ID,
                'session_id': self.session_id,
                'product_id': product_id,
                'quantity': quantity,
            }, timeout=10)
            return ack
        except asyncio.TimeoutError:
            return {'success': False, 'error': 'timeout'}

    async def disconnect(self):
        if self.sio and self.connected:
            await self.sio.disconnect()
        if self.session:
            await self.session.close()


async def phase1_sanity(users):
    """Faza 1: 20 userów dołącza, sprawdzamy że all connected."""
    print("\n=== FAZA 1: SANITY (20 userów dołącza do oferty) ===")
    start = time.perf_counter()
    results = await asyncio.gather(*(u.connect() for u in users), return_exceptions=True)
    errors = [r for r in results if isinstance(r, Exception)]
    print(f"  Connect: {NUM_USERS - len(errors)}/{NUM_USERS} OK, {len(errors)} errors")
    for e in errors[:3]:
        print(f"    Error: {type(e).__name__}: {e}")

    # Join reservation room
    join_results = await asyncio.gather(*(u.join_reservation() for u in users if u.connected),
                                          return_exceptions=True)
    join_ok = sum(1 for r in join_results if isinstance(r, dict) and r.get('success'))
    print(f"  Join reservation: {join_ok}/{len([u for u in users if u.connected])} OK")
    print(f"  Phase 1 took {(time.perf_counter()-start)*1000:.0f}ms")
    return join_ok


async def phase2_race(users):
    """Faza 2: 20 userów próbuje JEDNOCZEŚNIE zarezerwować Hongjoong (limit 5)."""
    print("\n=== FAZA 2: RACE (20 userów na produkt z limit=5) ===")
    connected_users = [u for u in users if u.connected]
    print(f"  Atak: {len(connected_users)} userów reserve(product={TARGET_PRODUCT_ID}, qty=1) jednocześnie")

    start = time.perf_counter()
    results = await asyncio.gather(*(u.reserve(TARGET_PRODUCT_ID) for u in connected_users),
                                     return_exceptions=True)
    elapsed_total = (time.perf_counter() - start) * 1000

    successes = []
    failures = Counter()
    latencies = []

    for r in results:
        if isinstance(r, Exception):
            failures[f'exception:{type(r).__name__}'] += 1
            continue
        ack, latency = r
        latencies.append(latency)
        if ack.get('success'):
            successes.append(ack)
        else:
            failures[ack.get('error', 'unknown')] += 1

    print(f"  Sukcesy: {len(successes)}")
    print(f"  Niepowodzenia: {dict(failures)}")
    if latencies:
        print(f"  Latencja: avg={statistics.mean(latencies):.0f}ms, "
              f"p50={statistics.median(latencies):.0f}ms, "
              f"max={max(latencies):.0f}ms")
    print(f"  Phase 2 took {elapsed_total:.0f}ms")

    if len(successes) == 5:
        print("  ✅ RACE OK — dokładnie 5 sukcesów (zgodnie z limitem set_max_sets=5)")
    else:
        print(f"  ❌ RACE FAIL — oczekiwano 5 sukcesów, dostaliśmy {len(successes)}")
    return successes, failures


async def phase4_purchase(users):
    """Faza 4: 20 userów rozdzielonych na 4 produkty (po 5), rezerwują + kupują.

    Cel:
    - Sprawdzić pełen flow purchase (reserve → place_order)
    - Po: 4 z 8 produktów ma 5/5 ordered = 50% set_threshold → auto-increase trigger
    - Oczekujemy: set_max_sets z 5 → 7 (amount=2)
    """
    print("\n=== FAZA 4: PURCHASE (20 userów × 4 produkty po 5, weryfikacja auto-increase) ===")

    # Wyczyść poprzednie rezerwacje (chaos zostawił bałagan)
    connected_users = [u for u in users if u.connected]
    await asyncio.gather(*(u.release(pid, quantity=99) for u in connected_users for pid in ALL_PRODUCT_IDS),
                          return_exceptions=True)
    await asyncio.sleep(1)

    # Mapping: każda piątka userów → 1 produkt
    products_to_buy = ALL_PRODUCT_IDS[:4]  # 487, 488, 489, 490
    user_product_map = []
    for i, user in enumerate(connected_users[:20]):
        product = products_to_buy[i // 5]
        user_product_map.append((user, product))

    # Krok 1: każdy user rezerwuje swój przypisany produkt
    print(f"  Krok 1: {len(user_product_map)} userów rezerwuje swoje produkty...")
    reserve_results = await asyncio.gather(
        *(user.reserve(product) for user, product in user_product_map),
        return_exceptions=True
    )
    reserve_ok = sum(1 for r in reserve_results if not isinstance(r, Exception) and r[0].get('success'))
    print(f"  Rezerwacje: {reserve_ok}/{len(user_product_map)} OK")

    # Krok 2: każdy user składa zamówienie HTTP POST /offer/<token>/place-order
    async def place_order_user(user, product_id):
        start = time.perf_counter()
        # Fake IP per user (rate limit per-user dla place_order — limit 15/min/user)
        fake_ip = f"10.99.{user.idx // 256}.{user.idx % 256}"
        try:
            async with user.session.post(
                f"{BASE_URL}/offer/{PAGE_TOKEN}/place-order",
                json={"session_id": user.session_id, "order_note": f"stress test user {user.idx}"},
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "X-Forwarded-For": fake_ip,
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                latency = (time.perf_counter() - start) * 1000
                try:
                    data = await r.json()
                except Exception:
                    data = {'success': False, 'error': 'non_json', 'status': r.status}
                return data, latency
        except Exception as e:
            return {'success': False, 'error': type(e).__name__, 'message': str(e)}, (time.perf_counter()-start)*1000

    print(f"  Krok 2: {len(user_product_map)} userów składa zamówienia (place_order)...")
    order_results = await asyncio.gather(
        *(place_order_user(user, product) for user, product in user_product_map),
        return_exceptions=True
    )

    order_ok = []
    order_failures = Counter()
    order_latencies = []
    for r in order_results:
        if isinstance(r, Exception):
            order_failures[f'exception:{type(r).__name__}'] += 1
            continue
        data, latency = r
        order_latencies.append(latency)
        if data.get('success'):
            order_ok.append(data)
        else:
            order_failures[data.get('error', 'unknown')] += 1

    print(f"  Zamówienia: {len(order_ok)} sukcesów, niepowodzenia: {dict(order_failures)}")
    if order_latencies:
        print(f"  Latencja place_order: avg={statistics.mean(order_latencies):.0f}ms, "
              f"p95={sorted(order_latencies)[int(len(order_latencies)*0.95)]:.0f}ms, "
              f"max={max(order_latencies):.0f}ms")

    return len(order_ok)


async def phase3_chaos(users, duration=10):
    """Faza 3: 10 sekund chaosu — random reserve/release na różnych produktach."""
    print(f"\n=== FAZA 3: CHAOS ({duration}s mixed reserve/release) ===")
    import random
    connected_users = [u for u in users if u.connected]

    op_counter = Counter()
    error_counter = Counter()
    latencies = []
    end_time = time.time() + duration

    async def chaos_loop(user):
        while time.time() < end_time:
            await asyncio.sleep(random.uniform(0.1, 0.5))
            action = random.choice(['reserve', 'release', 'reserve', 'reserve'])
            product_id = random.choice(ALL_PRODUCT_IDS)
            if action == 'reserve':
                ack, lat = await user.reserve(product_id)
                latencies.append(lat)
                op_counter['reserve_attempts'] += 1
                if ack.get('success'):
                    op_counter['reserve_ok'] += 1
                else:
                    error_counter[ack.get('error', '?')] += 1
            else:
                ack = await user.release(product_id)
                op_counter['release_attempts'] += 1
                if ack.get('success'):
                    op_counter['release_ok'] += 1

    start = time.perf_counter()
    await asyncio.gather(*(chaos_loop(u) for u in connected_users), return_exceptions=True)
    elapsed = (time.perf_counter() - start) * 1000

    print(f"  Operacje: {dict(op_counter)}")
    print(f"  Błędy (oczekiwane gdy limit): {dict(error_counter)}")
    if latencies:
        print(f"  Latencja reserve: avg={statistics.mean(latencies):.0f}ms, "
              f"p95={sorted(latencies)[int(len(latencies)*0.95)]:.0f}ms, "
              f"max={max(latencies):.0f}ms")
    print(f"  Phase 3 took {elapsed:.0f}ms")


async def check_auto_increase_triggered():
    """Sprawdza w DB czy auto-increase log ma nowe wpisy."""
    import subprocess
    result = subprocess.run(
        ['/Applications/XAMPP/xamppfiles/bin/mysql', '-u', 'root', 'thunder_orders', '-e',
         f"""SELECT
             (SELECT set_max_sets FROM offer_sections WHERE offer_page_id={PAGE_ID} AND section_type='set' LIMIT 1) AS current_set_max,
             (SELECT COUNT(*) FROM offer_auto_increase_log WHERE offer_page_id={PAGE_ID}) AS triggers_count,
             (SELECT increased_to FROM offer_auto_increase_log WHERE offer_page_id={PAGE_ID} ORDER BY id DESC LIMIT 1) AS last_increased_to;"""],
        capture_output=True, text=True
    )
    return result.stdout


async def main():
    print(f"Stress test: {NUM_USERS} userów na ofertę {PAGE_ID}")
    users = [StressUser(i) for i in range(1, NUM_USERS + 1)]
    try:
        await phase1_sanity(users)
        await asyncio.sleep(1)
        await phase2_race(users)
        await asyncio.sleep(1)
        await phase3_chaos(users, duration=5)  # krótszy chaos
        await asyncio.sleep(1)

        print("\n=== Pre-phase4: stan auto-increase ===")
        print(await check_auto_increase_triggered())

        await phase4_purchase(users)
        await asyncio.sleep(2)  # pozwól auto-increase się policzyć

        print("\n=== Post-phase4: weryfikacja auto-increase ===")
        print(await check_auto_increase_triggered())
    finally:
        print("\n=== Cleanup ===")
        await asyncio.gather(*(u.disconnect() for u in users), return_exceptions=True)
        print("Done.")


if __name__ == '__main__':
    asyncio.run(main())
