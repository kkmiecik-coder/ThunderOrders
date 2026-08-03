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
        # Numery przepisujemy bez normalizacji — w bazie są też zagraniczne.
        phone = ((user.phone if user else '') or '').strip()

        if not phone:
            warnings.append(
                f'{sr.request_number} — brak telefonu klienta, uzupełnij przed nadaniem'
            )

        to_pickup = sr.address_type == 'pickup_point'

        writer.writerow([
            email,
            phone,
            size,
            # W bazie zdarzają się kody z wiodącą spacją
            (sr.pickup_point_id or '').strip() if to_pickup else '',
            sr.request_number,
            '',                                                  # dodatkowa_ochrona
            '',                                                  # za_pobraniem
            '' if to_pickup else (sr.shipping_name or ''),
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
