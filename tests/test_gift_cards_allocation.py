"""Algorytm rozdziału gratisowych kart (czysty Python, bez bazy)."""
import random
import time
from collections import deque

from modules.gift_cards.allocation import Person, allocate

SAN, YUNHO, MINGI, WOOYOUNG = 1, 2, 3, 4


def test_rounds_follow_queue_and_ranking():
    # A (need 2), B (need 1); stan po 2 szt. San/Yunho
    r = allocate([Person(1, 2, (SAN, YUNHO)), Person(2, 1, (SAN, YUNHO))], {SAN: 2, YUNHO: 1})
    assert [p.type_id for p in r.picks[1]] == [SAN, YUNHO]   # runda 1: San, runda 2: Yunho
    assert [p.type_id for p in r.picks[2]] == [SAN]
    assert r.picks[1][1].round_no == 2


def test_favorite_kept_when_no_conflict():
    # bez konfliktu reguła „bez powtórek” nie odbiera nikomu ulubionego
    people = [Person(9, 2, (YUNHO, SAN)), Person(5, 1, (SAN, YUNHO))]
    r = allocate(people, {YUNHO: 1, SAN: 2})
    assert [p.type_id for p in r.picks[9]] == [YUNHO, SAN]
    assert [p.type_id for p in r.picks[5]] == [SAN]


def test_spec_example_queue_earlier_person_gets_second_choice():
    # A (nr 5) need 1 ranking San>Yunho; B (nr 9) need 2 ranking Yunho>San; stan: San 1, Yunho 2
    # Runda 1: A chciałaby San; gdyby wzięła San, B dostałaby Yunho+Yunho -> A dostaje Yunho
    r = allocate([Person(5, 1, (SAN, YUNHO)), Person(9, 2, (YUNHO, SAN))], {SAN: 1, YUNHO: 2})
    assert [p.type_id for p in r.picks[5]] == [YUNHO]
    assert sorted(p.type_id for p in r.picks[9]) == [SAN, YUNHO]
    assert r.picks[5][0].rank_position == 2
    assert not any(p.is_duplicate for ps in r.picks.values() for p in ps)


def test_duplicates_only_when_unavoidable_and_minimal():
    # 6 kart, 4 rodzaje unitowe po 2 szt. -> dokładnie 2 powtórki, w ostatnich rundach
    r = allocate([Person(1, 6, (1, 2, 3, 4))], {1: 2, 2: 2, 3: 2, 4: 2})
    picks = r.picks[1]
    assert sum(p.is_duplicate for p in picks) == 2
    assert [p.is_duplicate for p in picks] == [False] * 4 + [True] * 2


def test_shortage_hits_last_rounds_end_of_queue():
    # potrzeby 1, 3, 3 (kolejka A, B, C); stan 5 -> runda1: A,B,C; runda2: B,C; brak dla C w rundzie 3 i B w rundzie 3
    r = allocate([Person(1, 1, ()), Person(2, 3, ()), Person(3, 3, ())], {1: 2, 2: 2, 3: 1})
    assert len(r.picks[1]) == 1 and len(r.picks[2]) == 2 and len(r.picks[3]) == 2
    assert r.shortage == {2: 1, 3: 1}


def test_no_ranking_takes_most_plentiful_type():
    r = allocate([Person(1, 1, ())], {1: 1, 2: 5})
    assert r.picks[1][0].type_id == 2 and r.picks[1][0].rank_position is None


def test_deterministic():
    people = [Person(i, 2, (1, 2, 3)) for i in range(1, 8)]
    s = {1: 5, 2: 5, 3: 4}
    assert allocate(people, s) == allocate(people, s)


def test_empty_inputs():
    assert allocate([], {1: 3}).picks == {}
    r = allocate([Person(1, 2, (1,))], {})
    assert r.picks.get(1, []) == [] and r.shortage == {1: 2}


# --- dodatkowe testy -------------------------------------------------------

def test_partial_ranking_does_not_crash_and_ranked_first():
    # rodzaje spoza rankingu idą po rankingowych, jak przy braku rankingu (najliczniejszy pierwszy)
    r = allocate([Person(1, 3, (MINGI,))], {SAN: 1, YUNHO: 4, MINGI: 1})
    picks = r.picks[1]
    assert [p.type_id for p in picks] == [MINGI, YUNHO, SAN]
    assert [p.rank_position for p in picks] == [1, None, None]
    assert not any(p.is_duplicate for p in picks)


def _max_distinct(remaining, held, stock):
    """Niezależny Edmonds–Karp (źródło -> osoba -> rodzaj -> ujście) do weryfikacji."""
    cap = {}

    def add(u, v, c):
        cap[(u, v)] = cap.get((u, v), 0) + c
        cap.setdefault((v, u), 0)

    for i, need in remaining.items():
        add('S', ('p', i), need)
        for t in stock:
            if t not in held.get(i, set()):
                add(('p', i), ('t', t), 1)
    for t, c in stock.items():
        add(('t', t), 'K', c)
    adj = {}
    for (u, v) in cap:
        adj.setdefault(u, []).append(v)
    flow = 0
    while True:
        parent = {'S': None}
        q = deque(['S'])
        while q and 'K' not in parent:
            u = q.popleft()
            for v in adj.get(u, []):
                if v not in parent and cap[(u, v)] > 0:
                    parent[v] = u
                    q.append(v)
        if 'K' not in parent:
            return flow
        v = 'K'
        while parent[v] is not None:
            u = parent[v]
            cap[(u, v)] -= 1
            cap[(v, u)] += 1
            v = u
        flow += 1


def _reference_allocate(people, stock):
    """Dosłowna transkrypcja algorytmu z projektu (max-flow od zera dla każdego kandydata)."""
    stock = {t: c for t, c in stock.items() if c > 0}
    left = sum(stock.values())
    served = {p.user_id: 0 for p in people}
    r = 1
    while left > 0 and any(p.need >= r for p in people):
        for p in people:
            if p.need >= r and left > 0:
                served[p.user_id] += 1
                left -= 1
        r += 1
    f_star = _max_distinct(served, {}, stock)
    remaining = dict(served)
    held = {p.user_id: set() for p in people}
    picks = {p.user_id: [] for p in people}
    distinct = 0
    for rnd in range(1, max(served.values(), default=0) + 1):
        for p in people:
            if served[p.user_id] < rnd:
                continue
            uid = p.user_id
            ranked = [t for t in dict.fromkeys(p.ranking) if t in stock]
            rest = sorted((t for t in stock if t not in ranked), key=lambda t: (-stock[t], t))
            order = ranked + rest
            cands = [t for t in order if t not in held[uid]] + [t for t in order if t in held[uid]]
            for t in cands:
                if stock[t] <= 0:
                    continue
                new = t not in held[uid]
                st2 = dict(stock)
                st2[t] -= 1
                rem2 = dict(remaining)
                rem2[uid] -= 1
                held2 = {k: set(v) for k, v in held.items()}
                held2[uid].add(t)
                if distinct + new + _max_distinct(rem2, held2, st2) == f_star:
                    picks[uid].append((t, rnd, not new))
                    stock, remaining, held = st2, rem2, held2
                    distinct += new
                    break
            else:
                raise AssertionError('brak kandydata')
    return picks, f_star


def _random_instance(rng, max_types=8, max_people=12, max_need=6):
    n_types = rng.randint(1, max_types)
    stock = {t: rng.randint(0, 6) for t in range(1, n_types + 1)}
    people = []
    for uid in range(1, rng.randint(1, max_people) + 1):
        types = list(stock)
        rng.shuffle(types)
        kind = rng.random()
        if kind < 0.2:
            ranking = ()
        elif kind < 0.35:
            ranking = tuple(types[:rng.randint(1, len(types))])
        else:
            ranking = tuple(types)
        people.append(Person(uid, rng.randint(1, max_need), ranking))
    return people, stock


def test_property_minimal_duplicates_and_stock_respected():
    for seed in range(40):
        rng = random.Random(seed)
        people, stock = _random_instance(rng)
        result = allocate(people, stock)
        served = {uid: len(ps) for uid, ps in result.picks.items()}
        total_served = sum(served.values())
        assert total_served == min(sum(p.need for p in people), sum(stock.values()))
        f_star = _max_distinct(served, {}, {t: c for t, c in stock.items() if c > 0})
        dups = sum(pk.is_duplicate for ps in result.picks.values() for pk in ps)
        assert dups == total_served - f_star, seed
        used = {}
        for ps in result.picks.values():
            for pk in ps:
                used[pk.type_id] = used.get(pk.type_id, 0) + 1
        assert all(used[t] <= stock.get(t, 0) for t in used), seed
        for p in people:
            assert served[p.user_id] + result.shortage.get(p.user_id, 0) == p.need


def test_matches_literal_reference_algorithm():
    for seed in range(100, 130):
        rng = random.Random(seed)
        people, stock = _random_instance(rng, max_types=6, max_people=8, max_need=5)
        result = allocate(people, stock)
        expected, _ = _reference_allocate(people, stock)
        got = {uid: [(pk.type_id, pk.round_no, pk.is_duplicate) for pk in ps]
               for uid, ps in result.picks.items()}
        assert got == expected, seed


def test_performance_realistic_size():
    rng = random.Random(2026)
    stock = {t: 40 for t in range(1, 11)}  # 400 kart, 10 rodzajów
    people = []
    for uid in range(1, 151):
        types = list(stock)
        rng.shuffle(types)
        people.append(Person(uid, rng.randint(1, 5), tuple(types) if rng.random() > 0.2 else ()))
    start = time.perf_counter()
    result = allocate(people, stock)
    assert time.perf_counter() - start < 3
    assert sum(len(ps) for ps in result.picks.values()) == min(400, sum(p.need for p in people))
