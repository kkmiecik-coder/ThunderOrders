from modules.admin.offers import bulk_eligibility_error


class FakePage:
    def __init__(self, status, is_fully_closed=False):
        self.status = status
        self.is_fully_closed = is_fully_closed


def test_publish_ok_when_no_fully_closed():
    pages = [FakePage('draft'), FakePage('active'), FakePage('paused')]
    assert bulk_eligibility_error(pages, 'publish') is None


def test_publish_blocked_when_any_fully_closed():
    pages = [FakePage('draft'), FakePage('ended', is_fully_closed=True)]
    assert bulk_eligibility_error(pages, 'publish') is not None


def test_end_ok_when_all_active_or_paused():
    pages = [FakePage('active'), FakePage('paused')]
    assert bulk_eligibility_error(pages, 'end') is None


def test_end_blocked_when_any_not_active_or_paused():
    pages = [FakePage('active'), FakePage('ended')]
    assert bulk_eligibility_error(pages, 'end') is not None


def test_set_dates_ok_when_no_fully_closed():
    pages = [FakePage('draft'), FakePage('active'), FakePage('ended')]
    assert bulk_eligibility_error(pages, 'set-dates') is None


def test_set_dates_blocked_when_any_fully_closed():
    pages = [FakePage('ended', is_fully_closed=True)]
    assert bulk_eligibility_error(pages, 'set-dates') is not None


def test_delete_ok_when_no_active():
    pages = [FakePage('draft'), FakePage('ended'), FakePage('ended', is_fully_closed=True)]
    assert bulk_eligibility_error(pages, 'delete') is None


def test_delete_blocked_when_any_active():
    pages = [FakePage('active'), FakePage('draft')]
    assert bulk_eligibility_error(pages, 'delete') is not None


def test_unknown_action_returns_error():
    assert bulk_eligibility_error([FakePage('draft')], 'frobnicate') is not None
