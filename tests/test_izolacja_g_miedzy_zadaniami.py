"""Żądania w jednym teście nie dzielą `g` — tożsamość nie przecieka między klientami.

Fixture `app` trzyma przez cały test jeden kontekst aplikacji, a Flask 3 nie zakłada
żądaniu nowego, gdy kontekst tej samej aplikacji już istnieje. Bez podmiany
`request_context` w conftest wszystkie żądania testu dzieliły jedno `g`, a z nim
`g._login_user` wczytany przez Flask-Login przy pierwszym żądaniu. Na produkcji tego
problemu nie ma (każde żądanie dostaje własny kontekst aplikacji) — te testy pilnują,
żeby środowisko testowe zachowywało się tak samo.
"""


def _dziekujemy(strona):
    return f'/offer/{strona.token}/thank-you'


def test_gosc_na_innym_kliencie_nie_wylogowuje_zalogowanego(
        app, client, login, make_user, strona_sprzedazy):
    gosc = app.test_client().get(_dziekujemy(strona_sprzedazy))
    assert gosc.status_code == 200

    login(make_user(profile_completed=True))

    assert client.get('/client/dashboard').status_code == 200, (
        'Żądanie gościa z innego klienta utrwaliło anonima dla całego testu'
    )


def test_swiezy_klient_bez_ciasteczek_jest_anonimem(
        app, client, login, make_user, strona_sprzedazy):
    login(make_user(profile_completed=True))
    assert client.get('/client/dashboard').status_code == 200

    swiezy = app.test_client()

    assert swiezy.get('/client/dashboard').status_code == 302, (
        'Klient bez ciasteczek odziedziczył zalogowanego użytkownika po poprzednim żądaniu'
    )
    strona = swiezy.get(_dziekujemy(strona_sprzedazy)).get_data(as_text=True)
    assert '<!-- LOGGED IN USER -->' not in strona
