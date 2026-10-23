"""Zakazy czasu w kodzie aplikacji: jedna konwencja (UTC w bazie i w kodzie), bez naiwnego czasu.

Skanuje `app.py`, `modules/` i `utils/`. Każde trafienie to plik:linia, żeby od razu było widać,
co poprawić. Wyjątek: `utils/timeutil.py` - tam mieszka sam typ `UTCDateTime`.
"""
import re
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent
WYJATKI = {KORZEN / 'utils' / 'timeutil.py'}

ZAKAZY = {
    'get_local_now (naiwny czas polski) - użyj utcnow() z utils.timeutil': re.compile(r'get_local_now'),
    'datetime.now() bez strefy - użyj utcnow()': re.compile(r'datetime\.now\(\s*\)'),
    'datetime.utcnow (naiwny) - użyj utcnow()': re.compile(r'datetime\.utcnow'),
    'date.today() (strefa serwera) - użyj pl_today()': re.compile(r'date\.today\(\)'),
    'db.DateTime - użyj UTCDateTime': re.compile(r'db\.DateTime\b'),
}


def _pliki_aplikacji():
    yield KORZEN / 'app.py'
    for katalog in ('modules', 'utils'):
        yield from sorted((KORZEN / katalog).rglob('*.py'))


def test_brak_naiwnego_czasu_w_kodzie_aplikacji():
    trafienia = []
    for plik in _pliki_aplikacji():
        if plik in WYJATKI:
            continue
        # errors='replace': pojedyncze stare pliki są w cp1250 (np. modules/auth/__init__.py)
        tekst = plik.read_text(encoding='utf-8', errors='replace')
        for nr, linia in enumerate(tekst.splitlines(), start=1):
            for opis, wzorzec in ZAKAZY.items():
                if wzorzec.search(linia):
                    trafienia.append(f'{plik.relative_to(KORZEN)}:{nr}: {opis}\n    {linia.strip()}')
    assert not trafienia, f'Zakazany czas ({len(trafienia)}):\n' + '\n'.join(trafienia)
