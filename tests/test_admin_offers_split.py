from datetime import datetime

from modules.admin.offers import split_and_sort_offer_pages


class FakePage:
    def __init__(self, name, status, is_fully_closed=False, starts_at=None):
        self.name = name
        self.status = status
        self.is_fully_closed = is_fully_closed
        self.starts_at = starts_at


def _names(pages):
    return [p.name for p in pages]


def test_closed_is_only_fully_closed():
    pages = [
        FakePage('ended_closed', 'ended', is_fully_closed=True),
        FakePage('ended_open', 'ended', is_fully_closed=False),
        FakePage('active', 'active'),
    ]
    current, closed = split_and_sort_offer_pages(pages)
    assert _names(closed) == ['ended_closed']
    assert set(_names(current)) == {'ended_open', 'active'}


def test_status_order_in_current():
    pages = [
        FakePage('d', 'draft'),
        FakePage('e', 'ended'),
        FakePage('a', 'active'),
        FakePage('p', 'paused'),
        FakePage('s', 'scheduled'),
    ]
    current, _ = split_and_sort_offer_pages(pages)
    assert _names(current) == ['a', 'p', 's', 'd', 'e']


def test_date_desc_within_status():
    pages = [
        FakePage('old', 'active', starts_at=datetime(2026, 1, 1, 10, 0)),
        FakePage('new', 'active', starts_at=datetime(2026, 6, 1, 10, 0)),
        FakePage('mid', 'active', starts_at=datetime(2026, 3, 1, 10, 0)),
    ]
    current, _ = split_and_sort_offer_pages(pages)
    assert _names(current) == ['new', 'mid', 'old']


def test_null_starts_at_last_within_status():
    pages = [
        FakePage('nodate', 'active', starts_at=None),
        FakePage('dated', 'active', starts_at=datetime(2026, 5, 1, 10, 0)),
    ]
    current, _ = split_and_sort_offer_pages(pages)
    assert _names(current) == ['dated', 'nodate']


def test_closed_sorted_by_date_desc():
    pages = [
        FakePage('c_old', 'ended', is_fully_closed=True,
                 starts_at=datetime(2026, 1, 1, 10, 0)),
        FakePage('c_new', 'ended', is_fully_closed=True,
                 starts_at=datetime(2026, 6, 1, 10, 0)),
    ]
    _, closed = split_and_sort_offer_pages(pages)
    assert _names(closed) == ['c_new', 'c_old']


def test_empty_input():
    assert split_and_sort_offer_pages([]) == ([], [])


def test_unknown_status_goes_last():
    pages = [
        FakePage('unknown', 'mystery'),
        FakePage('draft', 'draft'),
        FakePage('ended', 'ended'),
    ]
    current, _ = split_and_sort_offer_pages(pages)
    assert _names(current) == ['draft', 'ended', 'unknown']
