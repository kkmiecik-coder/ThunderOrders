/* Ekran „Nieodebrane" — zakładki, zaznaczanie klientów, wysyłka przypomnień. */
(function () {
    'use strict';

    const DNI_OSTRZEZENIA = 7;

    /* ===== Zakładki ===== */
    const zakladki = Array.from(document.querySelectorAll('.unclaimed__tab'));

    function przelaczZakladke(tab) {
        const nazwa = tab.dataset.tab;
        zakladki.forEach(function (t) {
            const aktywna = t === tab;
            t.classList.toggle('is-active', aktywna);
            // aria-selected i roving tabindex — tylko aktywna zakładka jest w kolejności Tab,
            // strzałki poruszają się między wszystkimi (patrz obsługa klawiatury niżej).
            t.setAttribute('aria-selected', aktywna ? 'true' : 'false');
            t.tabIndex = aktywna ? 0 : -1;
        });
        document.querySelectorAll('.unclaimed__panel').forEach(function (p) {
            p.classList.toggle('is-active', p.dataset.panel === nazwa);
        });
    }

    zakladki.forEach(function (tab, i) {
        tab.addEventListener('click', function () {
            przelaczZakladke(tab);
        });

        // Strzałki lewo/prawo przełączają zakładki, gdy fokus jest na zakładce
        // (standardowy wzorzec klawiatury dla ARIA tabs).
        tab.addEventListener('keydown', function (e) {
            if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') {
                return;
            }
            e.preventDefault();
            const kierunek = e.key === 'ArrowRight' ? 1 : -1;
            const kolejny = zakladki[(i + kierunek + zakladki.length) % zakladki.length];
            przelaczZakladke(kolejny);
            kolejny.focus();
        });
    });

    /* ===== Rozwijanie szczegółów ===== */
    document.querySelectorAll('.unclaimed__expand').forEach(function (btn) {
        btn.addEventListener('click', function () {
            const wiersz = document.getElementById(btn.dataset.target);
            if (wiersz) {
                wiersz.hidden = !wiersz.hidden;
            }
        });
    });

    /* ===== Zaznaczanie ===== */
    const przycisk = document.getElementById('unclaimedRemindBtn');
    const licznik = document.getElementById('unclaimedCount');
    const zaznaczWszystkie = document.getElementById('unclaimedSelectAll');
    if (!przycisk) {
        return;  // ekran bez zaległości — nie ma czego obsługiwać
    }

    function zaznaczone() {
        return Array.from(document.querySelectorAll('.unclaimed__pick:checked'));
    }

    function odswiezLicznik() {
        const n = zaznaczone().length;
        licznik.textContent = n;
        przycisk.disabled = n === 0;
    }

    document.querySelectorAll('.unclaimed__pick').forEach(function (cb) {
        cb.addEventListener('change', odswiezLicznik);
    });

    if (zaznaczWszystkie) {
        zaznaczWszystkie.addEventListener('change', function () {
            document.querySelectorAll('.unclaimed__pick').forEach(function (cb) {
                cb.checked = zaznaczWszystkie.checked;
            });
            odswiezLicznik();
        });
    }

    /* ===== Wysyłka ===== */
    function niedawnoPrzypomniane(pola) {
        // Ostrzegamy, zanim admin drugi raz w tym tygodniu napisze do tej samej osoby —
        // to tylko ostrzeżenie, nie blokada: właścicielka może mieć powód, żeby napisać ponownie.
        const prog = Date.now() - DNI_OSTRZEZENIA * 24 * 60 * 60 * 1000;
        return pola.filter(function (cb) {
            const data = cb.dataset.ostatnie;
            return data && Date.parse(data) > prog;
        });
    }

    function pobierzCsrfToken() {
        // Ten sam wzorzec co orders-list.js: najpierw meta tag, potem ukryte pole formularza.
        const metaTag = document.querySelector('meta[name="csrf-token"]');
        if (metaTag) {
            return metaTag.getAttribute('content');
        }
        const csrfInput = document.querySelector('input[name="csrf_token"]');
        if (csrfInput) {
            return csrfInput.value;
        }
        return '';
    }

    function komunikatSukcesu(dane) {
        // Kontrakt trasy (Zadanie 6 po recenzji): 'wyslane' to liczba klientów — ta liczba
        // idzie do komunikatu. 'maile' może być 0 mimo wyslane > 0, gdy właścicielka wyłączyła
        // maile w ustawieniach (push i wpis w apce poszły i tak) — trzeba to powiedzieć wprost,
        // inaczej pomyśli, że klient dostał e-mail. 'pominieci' to klienci, którzy przestali
        // zalegać między wyrenderowaniem ekranu a kliknięciem.
        const wyslane = dane.wyslane || 0;
        const maile = dane.maile || 0;
        const pominieci = dane.pominieci || [];

        let tekst = 'Wysłano przypomnień: ' + wyslane;
        if (wyslane > 0 && maile === 0) {
            tekst += '. Mail jest wyłączony w ustawieniach — poszło tylko powiadomienie w aplikacji.';
        }
        if (pominieci.length > 0) {
            const ilu = pominieci.length === 1 ? '1 osobę' : pominieci.length + ' osoby';
            tekst += ' Pominięto ' + ilu + ' — przestały już zalegać.';
        }
        return tekst;
    }

    przycisk.addEventListener('click', function () {
        const pola = zaznaczone();
        if (pola.length === 0) {
            return;
        }

        const swiezo = niedawnoPrzypomniane(pola);
        if (swiezo.length > 0) {
            const ilu = swiezo.length === 1 ? 'jednej osobie' : swiezo.length + ' osobom';
            if (!window.confirm(
                'Do ' + ilu + ' przypomnienie poszło w ciągu ostatnich ' +
                DNI_OSTRZEZENIA + ' dni. Wysłać mimo to?'
            )) {
                return;
            }
        }

        przycisk.disabled = true;
        fetch('/admin/orders/nieodebrane/przypomnij', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': pobierzCsrfToken()
            },
            body: JSON.stringify({ user_ids: pola.map(function (cb) { return Number(cb.value); }) })
        })
            .then(function (r) { return r.json(); })
            .then(function (dane) {
                if (dane.success) {
                    window.showToast?.(komunikatSukcesu(dane), 'success');
                    window.location.reload();
                } else {
                    window.showToast?.(dane.message || 'Nie udało się wysłać', 'error');
                    przycisk.disabled = false;
                }
            })
            .catch(function () {
                window.showToast?.('Nie udało się wysłać przypomnień', 'error');
                przycisk.disabled = false;
            });
    });

    odswiezLicznik();
})();
