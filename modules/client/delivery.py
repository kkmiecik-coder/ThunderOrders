"""Potwierdzenie odbioru paczki i ocena dostawy w panelu klienta (task 869efhwph).

Wszystko pod @login_required: akcja zmienia statusy zlecenia i zamówień w bazie, więc
musi być przypisana do konkretnego użytkownika. Żadnych anonimowych linków z tokenem —
mail i push prowadzą tutaj, a niezalogowany przechodzi przez logowanie z `next`.

Paczka zbiorcza: lista zleceń w panelu ukrywa zlecenie zbiorcze (patrz
list_client_requests), więc klient wiodący widzi WŁASNE zlecenie źródłowe. Potwierdzenie
z tego zlecenia domyka paczkę zbiorczą, a propagacja zjeżdża na wszystkie źródła.
Pozostali uczestnicy nie mogą potwierdzić — karton fizycznie odbiera wiodący.
"""
from datetime import timedelta

from flask import abort, jsonify, render_template, request
from flask_login import current_user, login_required

from extensions import db
from modules.client import client_bp
from modules.orders.delivery_config import pobierz_konfig_dostawy
from modules.orders.models import ShippingRequest, get_local_now
from modules.orders.review_models import DeliveryReview
from modules.orders.wms_utils import (
    ZlecenieJuzDostarczone, ZlecenieZrodloweNieDomykane, dostarcz_zlecenie)


def zlecenie_do_potwierdzenia(user_id, request_id):
    """(zlecenie klienta, zlecenie do domknięcia) albo (None, None) gdy cudze/nieznane.

    Drugi element to None, gdy klient nie ma prawa domykać tej paczki — czyli gdy jest
    uczestnikiem paczki zbiorczej, ale nie jej klientem wiodącym.
    """
    sr = ShippingRequest.query.filter_by(id=request_id, user_id=user_id).first()
    if sr is None:
        return None, None

    # Samo zlecenie ZBIORCZE jest tu nie do przyjęcia, mimo że filtr po user_id je
    # przepuszcza: `_kopiuj_adres` ustawia `zbiorcze.user_id = lead.user_id`, więc
    # klient wiodący formalnie jest jego właścicielem. Tyle że pod tym id wiszą
    # wiersze junction WSZYSTKICH uczestników — strona pokazałaby mu cudze numery
    # zamówień, a zapis oceny założyłby DRUGI wiersz DeliveryReview dla tej samej
    # fizycznej przesyłki (UNIQUE jest per shipping_request_id, więc nic tego nie
    # blokuje) i statystyki policzyłyby jedną dostawę dwa razy. Klient nie ma tu
    # czego oglądać: swoje zlecenie źródłowe widzi pod własnym id, i to na nie
    # prowadzą wszystkie linki z maili i pushy.
    if sr.is_consolidation:
        return None, None

    if not sr.is_consolidated_source:
        return sr, sr

    zbiorcze = sr.consolidated_into
    if zbiorcze is None:
        return sr, sr
    if zbiorcze.lead_source_request_id == sr.id:
        return sr, zbiorcze
    return sr, None


# Statusy, w których ocena dostawy ma jakikolwiek sens. 'wyslane' jest tu, bo
# klient ocenia razem z potwierdzeniem odbioru — paczka fizycznie już u niego jest,
# tylko system dowie się o tym w tej samej sekundzie.
STATUSY_Z_OCENA = ('wyslane', 'dostarczone')


def _okno_oceny_otwarte(sr):
    """Czy można jeszcze wystawić ocenę tej paczki.

    Poprzednia wersja odpowiadała True dla KAŻDEGO statusu innego niż 'dostarczone'
    (warunek `if sr.status != 'dostarczone': return True`), a endpointy oceny — webowy
    i mobilny — nie sprawdzają statusu w ogóle. Dało się więc ocenić zlecenie
    'czeka_na_wycene', 'spakowane' czy 'anulowane', a strona potwierdzenia sama to
    podsuwała: komunikat „tej paczki nie da się potwierdzić" i tuż pod nim żywe
    gwiazdki. Takie oceny wchodziły wprost do średniej w statystykach.
    """
    if sr.status not in STATUSY_Z_OCENA:
        return False
    if sr.status != 'dostarczone':
        return True
    if sr.delivered_at is None:
        # Rekord historyczny: status 'dostarczone' bez daty (backfill objął tylko
        # shipped_at). Nie ma od czego liczyć okna, więc go nie zamykamy.
        return True
    dni = pobierz_konfig_dostawy()['review_window_days']
    return get_local_now() - sr.delivered_at <= timedelta(days=dni)


def zapisz_ocene(sr, dane):
    """(opinia|None, błąd|None, kod HTTP). Tworzy albo aktualizuje opinię.

    Publiczna (bez podkreślnika) — poza panelem klienta korzysta z niej też API
    mobilne (Task 11), więc kontrakt (parametry, zwracana krotka) jest stabilny.
    """
    surowa = dane.get('rating')
    if surowa in (None, ''):
        return None, None, 200

    try:
        ocena = int(surowa)
        # int() samego stringa z ułamkiem ("4.9") już rzuca ValueError, ale JSON
        # (mobile API i fetch()) przysyła liczby jako float — int(4.9) ucina cicho
        # do 4 zamiast się wywalić. Odrzucamy taki przypadek jawnie, żeby niecałkowita
        # ocena nie wjechała do średniej w statystykach pod zafałszowaną wartością.
        if isinstance(surowa, float) and ocena != surowa:
            raise ValueError
    except (TypeError, ValueError):
        return None, 'Ocena musi być liczbą od 1 do 5', 400
    if ocena < 1 or ocena > 5:
        return None, 'Ocena musi być liczbą od 1 do 5', 400

    if not _okno_oceny_otwarte(sr):
        if sr.status not in STATUSY_Z_OCENA:
            # Inny powód niż upływ czasu — komunikat o „N dniach od dostarczenia"
            # mówiłby klientowi nieprawdę o paczce, która jeszcze nie wyjechała.
            return None, 'Ocenić można dopiero wysłaną paczkę', 409
        dni = pobierz_konfig_dostawy()['review_window_days']
        return None, f'Ocenę można wystawić w ciągu {dni} dni od dostarczenia', 409

    opinia = sr.review
    if opinia is None:
        opinia = DeliveryReview(shipping_request_id=sr.id, user_id=sr.user_id)
        db.session.add(opinia)
    elif not opinia.mozna_edytowac:
        return None, (f'Ocenę można zmienić w ciągu '
                      f'{DeliveryReview.OKNO_EDYCJI_DNI} dni od wystawienia'), 409

    opinia.rating = ocena
    try:
        # Walidacja długości siedzi w modelu (@validates) — tu tylko tłumaczymy
        # jej ValueError na ten sam kontrakt błędu 400, co reszta tej funkcji.
        opinia.comment = dane.get('comment')
    except ValueError as err:
        return None, str(err), 400
    return opinia, None, 200


@client_bp.route('/shipping/requests/<int:request_id>/potwierdz')
@login_required
def confirm_delivery(request_id):
    """Strona potwierdzenia odbioru — cel linku z maila i pusha."""
    sr, do_domkniecia = zlecenie_do_potwierdzenia(current_user.id, request_id)
    if sr is None:
        abort(404)

    okno_oceny_otwarte = _okno_oceny_otwarte(sr)
    return render_template(
        'client/shipping/confirm_delivery.html',
        title='Potwierdzenie odbioru',
        sr=sr,
        moze_potwierdzic=(do_domkniecia is not None and sr.status == 'wyslane'),
        okno_oceny_otwarte=okno_oceny_otwarte,
        # Sekcja oceny nie ma prawa pojawić się na zleceniu, na które nigdy nie dało
        # się wystawić oceny (np. 'czeka_na_wycene' bez recenzji) — o tym mówi
        # `okno_oceny_otwarte` (samo w sobie zawsze False dla statusów spoza
        # STATUSY_Z_OCENA). Ale gdy opinia już istnieje, ma zostać widoczna również
        # po tym, jak status zjechał poza ten zbiór (np. admin ręcznie cofnął
        # błędnie oznaczone 'dostarczone' z powrotem na 'spakowane') — inaczej
        # klient traci z oczu to, co sam napisał, wbrew temu, co obiecuje ten
        # komentarz. Dawny warunek `sr.status in STATUSY_Z_OCENA and (...)` chował
        # tu istniejącą opinię właśnie w tym przypadku — poprawiamy zachowanie,
        # nie komentarz, bo intencja komentarza jest słuszna.
        pokaz_ocene=(okno_oceny_otwarte or sr.review is not None),
        review=sr.review,
        okno_edycji_dni=DeliveryReview.OKNO_EDYCJI_DNI,
        konfig=pobierz_konfig_dostawy(),
    )


@client_bp.route('/shipping/requests/<int:request_id>/potwierdz', methods=['POST'])
@login_required
def confirm_delivery_submit(request_id):
    """Potwierdzenie odbioru (opcjonalnie razem z oceną)."""
    sr, do_domkniecia = zlecenie_do_potwierdzenia(current_user.id, request_id)
    if sr is None:
        return jsonify({'success': False, 'message': 'Nie znaleziono zlecenia'}), 404
    if do_domkniecia is None:
        return jsonify({
            'success': False,
            'message': ('Ta paczka jedzie zbiorczo — odbiór potwierdza osoba, '
                        'na której adres została nadana')
        }), 403

    # Poprawka do briefu: dostarcz_zlecenie() sam pilnuje przed powtórnym domknięciem
    # (delivered_at / status=='dostarczone'), ale to za mało jako jedyna linia obrony —
    # strona GET jedynie UKRYWA przycisk klientowi, gdy status != 'wyslane' (np.
    # 'nowe', 'anulowane', 'w_magazynie'), nic nie broni samego POST-a. Bez tego
    # warunku klient mógłby POST-em na ten endpoint domknąć zlecenie, które fizycznie
    # nigdy nie zostało wysłane, albo — dla już dostarczonego — dociągnąć zapis oceny
    # przez błąd ZlecenieJuzDostarczone (ten wyjątek łapiemy niżej i zwracamy 200 z
    # myślą o podwójnym kliknięciu, nie jako furtkę do zmiany stanu). Sprawdzamy
    # do_domkniecia (a nie sr) — to on faktycznie przechodzi przez dostarcz_zlecenie();
    # dla zlecenia niekonsolidowanego to ten sam obiekt, dla lidera paczki zbiorczej to
    # zlecenie zbiorcze, którego status i tak jest zsynchronizowany ze źródłem przez
    # propaguj_na_zrodla().
    if do_domkniecia.status != 'wyslane':
        return jsonify({
            'success': False,
            'message': (f'Zlecenie {sr.request_number} nie jest gotowe do potwierdzenia '
                        f'odbioru (status: {do_domkniecia.status})')
        }), 409

    dane = request.get_json(silent=True) or {}

    # Ocena PRZED domknięciem: dostarcz_zlecenie() wysyła mail z jej treścią, więc
    # musi ją już widzieć w sesji.
    opinia, blad, kod = zapisz_ocene(sr, dane)
    if blad:
        db.session.rollback()
        return jsonify({'success': False, 'message': blad}), kod

    try:
        dostarcz_zlecenie(do_domkniecia, source='klient', user=current_user)
    except ZlecenieJuzDostarczone:
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Odbiór był już potwierdzony',
            'rating': opinia.rating if opinia else None,
        })
    except ZlecenieZrodloweNieDomykane as err:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(err)}), 403

    return jsonify({
        'success': True,
        'message': 'Dziękujemy za potwierdzenie odbioru',
        'rating': opinia.rating if opinia else None,
    })


@client_bp.route('/shipping/requests/<int:request_id>/ocena', methods=['POST'])
@login_required
def delivery_review_submit(request_id):
    """Wystawienie albo zmiana oceny bez zmiany statusu zlecenia."""
    sr, _ = zlecenie_do_potwierdzenia(current_user.id, request_id)
    if sr is None:
        return jsonify({'success': False, 'message': 'Nie znaleziono zlecenia'}), 404

    dane = request.get_json(silent=True) or {}
    if dane.get('rating') in (None, ''):
        return jsonify({'success': False, 'message': 'Podaj ocenę od 1 do 5'}), 400

    opinia, blad, kod = zapisz_ocene(sr, dane)
    if blad:
        db.session.rollback()
        return jsonify({'success': False, 'message': blad}), kod

    db.session.commit()
    return jsonify({
        'success': True,
        'message': 'Dziękujemy za ocenę',
        'rating': opinia.rating,
        'mozna_edytowac': opinia.mozna_edytowac,
    })
