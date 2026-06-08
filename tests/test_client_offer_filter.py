from datetime import datetime

from modules.client.routes import filter_offer_pages, sort_offer_pages


class FakePage:
    def __init__(self, status='active', name=None, starts_at=None,
                 ends_at=None, closed_at=None):
        self.status = status
        self.name = name
        self.starts_at = starts_at
        self.ends_at = ends_at
        self.closed_at = closed_at


def _statuses(pages):
    return [p.status for p in pages]


def _names(pages):
    return [p.name for p in pages]


# ============================================
# filter_offer_pages
# ============================================

def test_filter_live_returns_active_and_paused():
    pages = [FakePage('scheduled'), FakePage('active'), FakePage('paused'),
             FakePage('ended')]
    result = filter_offer_pages(pages, 'live')
    assert _statuses(result) == ['active', 'paused']


def test_filter_upcoming_returns_only_scheduled():
    pages = [FakePage('scheduled'), FakePage('active'), FakePage('paused'),
             FakePage('ended')]
    result = filter_offer_pages(pages, 'upcoming')
    assert _statuses(result) == ['scheduled']


def test_filter_closed_returns_only_ended():
    pages = [FakePage('scheduled'), FakePage('active'), FakePage('paused'),
             FakePage('ended')]
    result = filter_offer_pages(pages, 'closed')
    assert _statuses(result) == ['ended']


def test_filter_defaults_to_live_for_unknown():
    pages = [FakePage('active'), FakePage('scheduled'), FakePage('ended')]
    result = filter_offer_pages(pages, 'garbage')
    assert _statuses(result) == ['active']


def test_filter_preserves_order():
    pages = [FakePage('paused'), FakePage('active')]
    result = filter_offer_pages(pages, 'live')
    assert _statuses(result) == ['paused', 'active']


# ============================================
# sort_offer_pages — per zakładka
# ============================================

def test_sort_live_dated_by_ends_then_undated_by_starts():
    # Z datą zamknięcia: górą najszybciej zamykane (ends_at rosnąco).
    a = FakePage(name='A', starts_at=datetime(2026, 6, 1), ends_at=datetime(2026, 6, 20))
    b = FakePage(name='B', starts_at=datetime(2026, 6, 2), ends_at=datetime(2026, 6, 10))
    # Bez daty zamknięcia: poniżej, rosnąco po starcie.
    c = FakePage(name='C', starts_at=datetime(2026, 6, 5), ends_at=None)
    d = FakePage(name='D', starts_at=datetime(2026, 6, 3), ends_at=None)
    pages = [a, b, c, d]
    sort_offer_pages(pages, 'live')
    assert _names(pages) == ['B', 'A', 'D', 'C']


def test_sort_live_undated_without_starts_at_goes_last():
    a = FakePage(name='A', starts_at=datetime(2026, 6, 3), ends_at=None)
    b = FakePage(name='B', starts_at=None, ends_at=None)
    pages = [b, a]
    sort_offer_pages(pages, 'live')
    assert _names(pages) == ['A', 'B']


def test_sort_live_without_any_dates_goes_last():
    a = FakePage(name='A', starts_at=datetime(2026, 6, 1), ends_at=datetime(2026, 6, 10))
    b = FakePage(name='B', starts_at=datetime(2026, 6, 3), ends_at=None)
    c = FakePage(name='C', starts_at=None, ends_at=None)
    pages = [c, b, a]
    sort_offer_pages(pages, 'live')
    assert _names(pages) == ['A', 'B', 'C']


def test_sort_upcoming_by_starts_ascending():
    a = FakePage(name='A', starts_at=datetime(2026, 7, 1))
    b = FakePage(name='B', starts_at=datetime(2026, 6, 15))
    c = FakePage(name='C', starts_at=datetime(2026, 6, 20))
    pages = [a, b, c]
    sort_offer_pages(pages, 'upcoming')
    assert _names(pages) == ['B', 'C', 'A']


def test_sort_closed_newest_first_using_closed_at_or_ends_at():
    # A zakończona po dacie (ends_at). B zamknięta ręcznie (closed_at późniejszy
    # niż jej ends_at). C zakończona po dacie.
    a = FakePage(name='A', ends_at=datetime(2026, 6, 1))
    b = FakePage(name='B', ends_at=datetime(2026, 5, 1), closed_at=datetime(2026, 6, 5))
    c = FakePage(name='C', ends_at=datetime(2026, 6, 3))
    pages = [a, b, c]
    sort_offer_pages(pages, 'closed')
    # Czas zamknięcia: A=6/1, B=6/5 (closed_at), C=6/3 -> malejąco: B, C, A
    assert _names(pages) == ['B', 'C', 'A']


def test_sort_closed_uses_closed_at_when_ends_at_missing():
    a = FakePage(name='A', ends_at=datetime(2026, 6, 2))
    b = FakePage(name='B', ends_at=None, closed_at=datetime(2026, 6, 4))
    pages = [a, b]
    sort_offer_pages(pages, 'closed')
    # B zamknięta 6/4 (closed_at, brak ends_at), A 6/2 -> malejąco: B, A
    assert _names(pages) == ['B', 'A']


def test_sort_closed_without_dates_goes_last():
    a = FakePage(name='A', ends_at=datetime(2026, 6, 1))
    b = FakePage(name='B', ends_at=None, closed_at=None)
    pages = [b, a]
    sort_offer_pages(pages, 'closed')
    assert _names(pages) == ['A', 'B']
