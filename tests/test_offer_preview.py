from modules.offers.routes import should_show_preview


class FakePage:
    def __init__(self, preview_enabled):
        self.preview_enabled = preview_enabled


def test_show_when_enabled_and_sections():
    assert should_show_preview(FakePage(True), [object(), object()]) is True


def test_hide_when_disabled():
    assert should_show_preview(FakePage(False), [object()]) is False


def test_hide_when_no_sections():
    assert should_show_preview(FakePage(True), []) is False


def test_hide_when_disabled_and_no_sections():
    assert should_show_preview(FakePage(False), []) is False
