"""Eksport zleceń wysyłki do pliku masowego nadania InPost.

Plik ma format CSV ze średnikiem jako separatorem, zgodny z szablonem
importu w panelu InPost (task ClickUp 869e674py).
"""

import csv
from io import StringIO

INPOST_COLUMNS = [
    'e-mail', 'telefon', 'rozmiar', 'paczkomat', 'numer_referencyjny',
    'dodatkowa_ochrona', 'za_pobraniem', 'imie_i_nazwisko', 'nazwa_firmy',
    'ulica', 'kod_pocztowy', 'miejscowosc', 'typ_przesylki', 'paczka_w_weekend',
]

# Szablon InPost zna gabaryty A/B/C. "mini" nie ma tam odpowiednika,
# więc takie zlecenia wypadają z pliku (decyzja: 2026-08-03).
EXPORTABLE_SIZES = {'A', 'B', 'C'}

# Punkt odbioru obsługiwany przez ten plik. Klient może wybrać także Orlen
# Paczkę — tamtej przesyłki nie da się nadać przez masowe nadanie InPost,
# więc takie zlecenia wypadają z pliku (jak gabaryt mini) zamiast trafiać do
# niego z kodem Orlenu w kolumnie `paczkomat`. Zlecenia sprzed wprowadzenia
# `pickup_courier` mają tam NULL — historycznie był to zawsze InPost.
INPOST_PICKUP_COURIER = 'inpost'

# Zlecenia, które już pojechały. Eksport nie zostawia śladu na rekordzie, więc
# nic nie wykrywa powtórnego nadania — a ponowny eksport (po nieudanym imporcie
# w panelu InPost, przy zaznaczeniu „wszystkie na wszystkich stronach") tworzy
# drugą, płatną przesyłkę. Sam `tracking_number` jest mocniejszym sygnałem niż
# status: numer pojawia się w chwili nadania, status bywa uzupełniany później.
ALREADY_SHIPPED_STATUSES = {'wyslane', 'dostarczone'}


def recipient_name(sr):
    """Kto odbiera paczkę.

    Nazwa z adresu wysyłki, bo to ona trafia na etykietę i to jej szuka
    kurier. Przy paczkomatach adres często nie ma nazwy — wtedy sięgamy
    po dane klienta z konta; tę kolejność trzyma `addressee_name` i to samo
    źródło prawdy widzi magazyn w panelu pakowania.

    Ostatnia deska ratunku (`full_name`, które degraduje do e-maila) zostaje
    bez zmian: e-mail w rubryce adresata jest kiepski, ale pusta rubryka
    w pliku masowego nadania jest gorsza.
    """
    return (sr.addressee_name or (sr.user.full_name if sr.user else '') or '').strip()


def format_phone(raw):
    """Polskie numery jako 9 cyfr, zagraniczne bez zmian.

    W bazie numery są zapisane rozmaicie: +48XXXXXXXXX (dominują), ze
    spacjami, bez prefiksu, a kilka to numery zagraniczne (+49, +47, +372).
    """
    if not raw:
        return ''

    phone = raw.strip().replace(' ', '').replace('-', '')

    if phone.startswith('+48'):
        return phone[3:]
    if phone.startswith('0048'):
        return phone[4:]
    if phone.startswith('48') and len(phone) == 11:
        return phone[2:]

    return phone


def build_inpost_csv(shipping_requests):
    """Buduje zawartość pliku i listę ostrzeżeń dla eksportującego.

    Zwraca krotkę (tekst_csv, ostrzeżenia). Zlecenie bez gabarytu albo
    z gabarytem mini nie trafia do pliku — zamiast tego pojawia się
    ostrzeżenie. Brak telefonu nie blokuje wiersza (to zwykle
    niedokończona rejestracja), ale też jest zgłaszany.
    """
    warnings = []
    out = StringIO()
    writer = csv.writer(out, delimiter=';', lineterminator='\n', quoting=csv.QUOTE_MINIMAL)
    writer.writerow(INPOST_COLUMNS)

    for sr in shipping_requests:
        tracking = (sr.tracking_number or '').strip()
        if tracking:
            warnings.append(
                f'{sr.request_number} — ma już numer przesyłki {tracking}, '
                f'pominięto (ponowny eksport nadałby drugą paczkę)'
            )
            continue

        if sr.status in ALREADY_SHIPPED_STATUSES:
            warnings.append(
                f'{sr.request_number} — zlecenie jest w statusie '
                f'„{sr.status_display_name}", pominięto (już nadane)'
            )
            continue

        size = (sr.parcel_size or '').strip()

        if not size:
            warnings.append(f'{sr.request_number} — brak gabarytu, pominięto')
            continue

        if size not in EXPORTABLE_SIZES:
            warnings.append(
                f'{sr.request_number} — gabaryt „{size}" (mini) nie jest obsługiwany '
                f'przez import InPost, pominięto'
            )
            continue

        user = sr.user
        email = ((user.email if user else '') or '').strip()
        phone = format_phone(user.phone if user else '')

        if not phone:
            warnings.append(
                f'{sr.request_number} — brak telefonu klienta, uzupełnij przed nadaniem'
            )

        to_pickup = sr.address_type == 'pickup_point'

        # Kurier punktu odbioru sprawdzany tylko przy paczkomacie — przy dostawie
        # pod adres `pickup_courier` bywa resztką po wcześniejszym wyborze klienta.
        if to_pickup:
            pickup_courier = (sr.pickup_courier or 'InPost').strip()
            if pickup_courier.lower() != INPOST_PICKUP_COURIER:
                warnings.append(
                    f'{sr.request_number} — punkt odbioru „{pickup_courier}" nie jest '
                    f'obsługiwany przez masowe nadanie InPost, pominięto '
                    f'(nadaj u tego przewoźnika osobno)'
                )
                continue

        name = recipient_name(sr)
        # Referencja wraca w rozliczeniach InPostu — samo WYS/000006 nic nie mówi
        reference = f'{name} {sr.request_number}'.strip()

        writer.writerow([
            email,
            phone,
            size,
            # W bazie zdarzają się kody z wiodącą spacją
            (sr.pickup_point_id or '').strip() if to_pickup else '',
            reference,
            '',                                                  # dodatkowa_ochrona
            '',                                                  # za_pobraniem
            name,
            '',                                                  # nazwa_firmy
            '' if to_pickup else (sr.shipping_address or ''),
            '' if to_pickup else (sr.shipping_postal_code or ''),
            '' if to_pickup else (sr.shipping_city or ''),
            'paczkomat' if to_pickup else 'kurier',
            'NIE',                                               # paczka_w_weekend
        ])

    return out.getvalue(), warnings


def count_exported_rows(csv_text):
    """Liczba wierszy danych w gotowym pliku (bez nagłówka)."""
    return max(0, len([line for line in csv_text.splitlines() if line]) - 1)
