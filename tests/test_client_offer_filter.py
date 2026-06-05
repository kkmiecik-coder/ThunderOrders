from modules.client.routes import filter_offer_pages


class FakePage:
    def __init__(self, status):
        self.status = status


def _statuses(pages):
    return [p.status for p in pages]


def test_filter_current_returns_scheduled_active_paused():
    pages = [FakePage('scheduled'), FakePage('active'), FakePage('paused'),
             FakePage('ended')]
    result = filter_offer_pages(pages, 'current')
    assert _statuses(result) == ['scheduled', 'active', 'paused']


def test_filter_closed_returns_only_ended():
    pages = [FakePage('scheduled'), FakePage('active'), FakePage('paused'),
             FakePage('ended')]
    result = filter_offer_pages(pages, 'closed')
    assert _statuses(result) == ['ended']


def test_filter_defaults_to_current_for_unknown():
    pages = [FakePage('active'), FakePage('ended')]
    result = filter_offer_pages(pages, 'garbage')
    assert _statuses(result) == ['active']


def test_filter_preserves_order():
    pages = [FakePage('active'), FakePage('scheduled'), FakePage('paused')]
    result = filter_offer_pages(pages, 'current')
    assert _statuses(result) == ['active', 'scheduled', 'paused']
