/* Potwierdzenie odbioru i ocena dostawy (task 869efhwph) */
(function () {
    'use strict';

    const kontener = document.querySelector('.confirm-delivery');
    if (!kontener) {
        return;
    }

    const idZlecenia = kontener.dataset.requestId;
    const sekcjaOceny = document.getElementById('deliveryReview');
    const gwiazdki = Array.from(document.querySelectorAll('.rating__star'));
    const komentarz = document.getElementById('deliveryComment');
    const przyciskPotwierdz = document.getElementById('confirmDeliveryBtn');
    const przyciskOcena = document.getElementById('saveReviewBtn');

    const edytowalna = !sekcjaOceny || sekcjaOceny.dataset.editable === 'true';
    // Gwiazdki 1..N mają is-active nadane w szablonie aż do wartości oceny (fill-up),
    // więc liczba aktywnych == wartość oceny — bez potrzeby czytania osobnego atrybutu.
    let wybranaOcena = gwiazdki.filter((g) => g.classList.contains('is-active')).length || null;

    if (!edytowalna) {
        const grupa = document.querySelector('.rating');
        if (grupa) {
            grupa.dataset.locked = 'true';
        }
        if (komentarz) {
            komentarz.disabled = true;
        }
        if (przyciskOcena) {
            przyciskOcena.disabled = true;
        }
    }

    function pokazOcene(wartosc) {
        gwiazdki.forEach((gwiazdka) => {
            const wartoscGwiazdki = Number(gwiazdka.dataset.value);
            gwiazdka.classList.toggle('is-active', wartoscGwiazdki <= wartosc);
            gwiazdka.setAttribute('aria-checked', wartoscGwiazdki === wartosc ? 'true' : 'false');
        });
    }

    gwiazdki.forEach((gwiazdka) => {
        gwiazdka.addEventListener('click', () => {
            if (!edytowalna) {
                return;
            }
            wybranaOcena = Number(gwiazdka.dataset.value);
            pokazOcene(wybranaOcena);
        });
    });

    function tokenCsrf() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) {
            return meta.getAttribute('content');
        }
        const ciasteczko = document.cookie
            .split('; ')
            .find((c) => c.startsWith('csrf_token='));
        return ciasteczko ? decodeURIComponent(ciasteczko.split('=')[1]) : '';
    }

    async function wyslij(sciezka, dane, przycisk) {
        if (przycisk) {
            przycisk.disabled = true;
        }
        try {
            const odpowiedz = await fetch(
                `/client/shipping/requests/${idZlecenia}/${sciezka}`,
                {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': tokenCsrf(),
                    },
                    body: JSON.stringify(dane),
                }
            );
            const wynik = await odpowiedz.json();
            window.showToast(
                wynik.message || (wynik.success ? 'Gotowe' : 'Nie udało się zapisać'),
                wynik.success ? 'success' : 'error'
            );
            if (wynik.success) {
                window.setTimeout(() => window.location.reload(), 900);
                return;
            }
        } catch (blad) {
            window.showToast('Brak połączenia — spróbuj ponownie', 'error');
        }
        if (przycisk) {
            przycisk.disabled = false;
        }
    }

    if (przyciskPotwierdz) {
        przyciskPotwierdz.addEventListener('click', () => {
            wyslij('potwierdz', {
                rating: wybranaOcena,
                comment: komentarz ? komentarz.value : null,
            }, przyciskPotwierdz);
        });
    }

    if (przyciskOcena) {
        przyciskOcena.addEventListener('click', () => {
            if (!wybranaOcena) {
                window.showToast('Wybierz ocenę od 1 do 5', 'error');
                return;
            }
            wyslij('ocena', {
                rating: wybranaOcena,
                comment: komentarz ? komentarz.value : null,
            }, przyciskOcena);
        });
    }
})();
