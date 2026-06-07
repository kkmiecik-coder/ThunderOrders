from utils.excel_export import _safe_sheet_title


def test_short_name_unchanged():
    assert _safe_sheet_title('Lato 2026', set()) == 'Lato 2026'


def test_long_name_truncated_to_31():
    name = 'A' * 50
    title = _safe_sheet_title(name, set())
    assert len(title) <= 31
    assert title == 'A' * 31


def test_illegal_chars_replaced():
    title = _safe_sheet_title('Sprzedaż: K-pop / [2026]', set())
    for ch in '[]:*?/\\':
        assert ch not in title


def test_duplicate_gets_suffix():
    used = {'lato 2026'}
    title = _safe_sheet_title('Lato 2026', used)
    assert title != 'Lato 2026'
    assert title.lower() not in used


def test_duplicate_suffix_fits_31_chars():
    used = {('a' * 31).lower()}
    title = _safe_sheet_title('A' * 31, used)
    assert len(title) <= 31
    assert title.lower() not in used


def test_empty_name_gets_fallback():
    assert _safe_sheet_title('', set()) == 'Oferta'


def test_does_not_mutate_used_titles():
    used = {'lato 2026'}
    _safe_sheet_title('Lato 2026', used)
    assert used == {'lato 2026'}
