"""Algorytm rozdziału gratisowych kart — czysta funkcja, bez dostępu do bazy.

Zasady (z projektu):
1. Rundy: w każdej rundzie każdy, komu jeszcze należy się karta, dostaje jedną — w kolejności kolejki.
2. W swojej turze osoba dostaje najwyżej oceniony rodzaj, którego jeszcze nie ma.
3. Unikanie powtórek u KOGOKOLWIEK ma pierwszeństwo przed rankingiem i kolejką.
4. Powtórki tylko gdy nieuniknione, w minimalnej łącznej liczbie, w ostatnich rundach.
5. Niedobór kart: mniej dostają osoby z końca kolejki, w ostatnich rundach.
6. Brak rankingu: osoba dostaje rodzaj o największym pozostałym stanie.

Minimalna liczba powtórek wynika z maksymalnego przepływu
(źródło -> osoba [pozostało do wydania] -> rodzaj [1, jeśli osoba go nie ma] -> ujście [stan]):
F* = największa możliwa liczba kart bez powtórek. Wybór w turze jest dopuszczalny tylko wtedy,
gdy da się go dokończyć tak, żeby łącznie nadal było F* kart bez powtórek. Przepływ jest
utrzymywany przyrostowo (zamiast liczenia od zera dla każdego kandydata), co daje te same
decyzje, a działa szybko dla ~150 osób / ~400 kart.
"""
from collections import deque
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Person:
    user_id: int
    need: int
    ranking: tuple[int, ...]  # id rodzajów, najlepszy pierwszy; () = brak rankingu


@dataclass
class Pick:
    type_id: int
    round_no: int
    is_duplicate: bool
    rank_position: int | None


@dataclass
class AllocationResult:
    picks: dict[int, list[Pick]]
    shortage: dict[int, int] = field(default_factory=dict)  # tylko wpisy > 0


def allocate(people: list[Person], stock: dict[int, int]) -> AllocationResult:
    """Rozdziela karty. `people` w kolejności kolejki, `stock` = rodzaj -> liczba sztuk."""
    user_ids = [p.user_id for p in people]
    if len(set(user_ids)) != len(user_ids):
        raise ValueError('Powtórzony user_id w kolejce')

    stock = {t: c for t, c in sorted(stock.items()) if c > 0}
    served = _served_counts(people, sum(stock.values()))
    shortage = {p.user_id: p.need - s for p, s in zip(people, served) if p.need - s > 0}

    net = _DistinctFlow(served, list(stock), stock)
    picks = {p.user_id: [] for p in people}
    for round_no in range(1, max(served, default=0) + 1):
        for i, person in enumerate(people):
            if served[i] < round_no:
                continue
            for type_id in _candidates(person, net.held[i], stock):
                is_duplicate = type_id in net.held[i]
                if net.try_take(i, type_id):
                    picks[person.user_id].append(Pick(
                        type_id=type_id,
                        round_no=round_no,
                        is_duplicate=is_duplicate,
                        rank_position=_rank_position(person.ranking, type_id),
                    ))
                    break
            else:  # pragma: no cover — matematycznie niemożliwe (suma stanu >= suma potrzeb)
                raise RuntimeError('Brak dopuszczalnego rodzaju karty')
    return AllocationResult(picks=picks, shortage=shortage)


def _served_counts(people, total_stock):
    """Ile kart dostanie każda osoba: rundami w kolejności kolejki, aż skończą się karty."""
    served = [0] * len(people)
    left = total_stock
    round_no = 1
    while left > 0 and any(p.need >= round_no for p in people):
        for i, person in enumerate(people):
            if person.need >= round_no and left > 0:
                served[i] += 1
                left -= 1
        round_no += 1
    return served


def _candidates(person, held, stock):
    """Kolejność prób: najpierw rodzaje bez powtórki, potem z powtórką.

    W każdej grupie: rodzaje z rankingu w jego kolejności, potem pozostałe
    wg największego pozostałego stanu (jak przy braku rankingu).
    """
    ranked = [t for t in dict.fromkeys(person.ranking) if stock.get(t, 0) > 0]
    ranked_set = set(ranked)
    rest = sorted((t for t in stock if t not in ranked_set and stock[t] > 0),
                  key=lambda t: (-stock[t], t))
    order = ranked + rest
    return [t for t in order if t not in held] + [t for t in order if t in held]


def _rank_position(ranking, type_id):
    return ranking.index(type_id) + 1 if type_id in ranking else None


class _DistinctFlow:
    """Maksymalny przepływ „kart bez powtórek” utrzymywany przyrostowo.

    Węzły: osoby 0..n-1, rodzaje, źródło S, ujście K. Krawędź osoba->rodzaj ma
    pojemność 1, jeśli osoba nie ma jeszcze tego rodzaju. `person_flow[i]` to rodzaje,
    którymi płynie jednostka od osoby i; `type_flow[t]` — osoby, od których płynie do t.
    Wartość przepływu = liczba kart bez powtórek możliwa do wydania z obecnego stanu.
    """

    _S = ('S',)
    _K = ('K',)

    def __init__(self, remaining, types, stock):
        self.remaining = list(remaining)
        self.types = types
        self.stock = stock  # współdzielony z allocate (zmniejszany przy wydaniu)
        self.held = [set() for _ in remaining]
        self.person_flow = [set() for _ in remaining]
        self.type_flow = {t: set() for t in types}
        self.value = 0
        self._log = None
        while self._augment():
            self.value += 1

    def try_take(self, i, t):
        """Wydaj osobie i kartę rodzaju t, jeśli nie zmniejsza to maksimum kart bez powtórek.

        Warunek z projektu: distinct_dotąd + nowy + max_distinct(po) == F*, czyli
        (przy niezmienniku distinct_dotąd + value == F*) max_distinct(po) == value - nowy.
        Zwraca False i nie zmienia stanu, gdy wybór jest niedopuszczalny.
        """
        is_new = t not in self.held[i]
        target = self.value - (1 if is_new else 0)
        self._log = []
        current = self.value
        if is_new and t in self.person_flow[i]:
            self._remove(i, t)  # ta jednostka przepływu staje się wydaną kartą
            current -= 1
        if is_new:
            self.held[i].add(t)
        self.remaining[i] -= 1
        self.stock[t] -= 1
        # przepływ musi zmieścić się w nowych pojemnościach — zdejmij nadmiar
        if len(self.person_flow[i]) > self.remaining[i]:
            self._remove(i, min(self.person_flow[i]))
            current -= 1
        if len(self.type_flow[t]) > self.stock[t]:
            self._remove(min(self.type_flow[t]), t)
            current -= 1
        while current < target and self._augment():
            current += 1
        if current == target:
            self.value = target
            self._log = None
            return True
        # wycofaj
        for op, pi, pt in reversed(self._log):
            if op == 'add':
                self.person_flow[pi].discard(pt)
                self.type_flow[pt].discard(pi)
            else:
                self.person_flow[pi].add(pt)
                self.type_flow[pt].add(pi)
        self._log = None
        if is_new:
            self.held[i].discard(t)
        self.remaining[i] += 1
        self.stock[t] += 1
        return False

    def _add(self, i, t):
        self.person_flow[i].add(t)
        self.type_flow[t].add(i)
        if self._log is not None:
            self._log.append(('add', i, t))

    def _remove(self, i, t):
        self.person_flow[i].discard(t)
        self.type_flow[t].discard(i)
        if self._log is not None:
            self._log.append(('remove', i, t))

    def _augment(self):
        """Jedna ścieżka powiększająca S -> K (BFS w sieci residualnej). True, jeśli znaleziona."""
        S, K = self._S, self._K
        parent = {S: None}
        queue = deque([S])
        while queue:
            node = queue.popleft()
            if node is S:
                nxt = [('p', i) for i in range(len(self.remaining))
                       if len(self.person_flow[i]) < self.remaining[i]]
            elif node[0] == 'p':
                i = node[1]
                nxt = [('t', t) for t in self.types
                       if t not in self.held[i] and t not in self.person_flow[i]]
            else:
                t = node[1]
                if len(self.type_flow[t]) < self.stock[t]:
                    parent[K] = node
                    break
                nxt = [('p', i) for i in sorted(self.type_flow[t])]
            for v in nxt:
                if v not in parent:
                    parent[v] = node
                    queue.append(v)
        if K not in parent:
            return False
        node = parent[K]
        while parent[node] is not S:
            prev = parent[node]
            if node[0] == 't':  # krawędź osoba -> rodzaj w przód
                self._add(prev[1], node[1])
            else:  # krawędź rodzaj -> osoba wstecz: cofnij przepływ osoba -> rodzaj
                self._remove(node[1], prev[1])
            node = prev
        return True
