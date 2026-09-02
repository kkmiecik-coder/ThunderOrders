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

    function pokazToast(wiadomosc, typ) {
        // Ten sam wzorzec co orders-list.js: gdy globalny toast nie jest dostępny
        // (np. skrypt się nie załadował), komunikat i tak musi dotrzeć do właścicielki.
        if (typeof window.showToast === 'function') {
            window.showToast(wiadomosc, typ);
        } else {
            alert(wiadomosc);
        }
    }

    function odmienOsoby(n, forma1, forma2, formaWiele) {
        // Polska odmiana liczebnika głównego przy rzeczowniku: 1 → forma1; 2-4 z wyjątkiem
        // końcówek 12-14 → forma2 (liczba mnoga "lekka"); pozostałe (5+, 12-14, 0) → formaWiele
        // (dopełniacz). Wywołujący dobiera słowa pod przypadek zdania — np. po "do" (dopełniacz)
        // forma2 i formaWiele są tym samym słowem, bo "do dwóch osób", nie "do dwóch osoby".
        if (n === 1) {
            return forma1;
        }
        const dziesiatki = n % 10;
        const setki = n % 100;
        if (dziesiatki >= 2 && dziesiatki <= 4 && !(setki >= 12 && setki <= 14)) {
            return forma2;
        }
        return formaWiele;
    }

    function opisIluOsob(n) {
        // Biernik — pasuje do "Pominięto kogo? co? — 1 osobę / 2 osoby / 7 osób".
        return n + ' ' + odmienOsoby(n, 'osobę', 'osoby', 'osób');
    }

    function opisDoIluOsob(n) {
        // Dopełniacz — przyimek "do" tego wymaga: "do jednej osoby", "do 2/5/22 osób".
        // Liczba mnoga dopełniacza jest stała niezależnie od 2-4 czy 5+, dlatego forma2
        // i formaWiele w wywołaniu odmienOsoby są tym samym słowem.
        if (n === 1) {
            return 'jednej osoby';
        }
        return n + ' ' + odmienOsoby(n, 'osoby', 'osób', 'osób');
    }

    function opisIluOsobMianownik(n) {
        // Mianownik — pasuje do "Kto? co? nie ma adresu — 1 osoba / 2 osoby / 7 osób".
        return n + ' ' + odmienOsoby(n, 'osoba', 'osoby', 'osób');
    }

    function komunikatSukcesu(dane) {
        // Kontrakt trasy (Zadanie 6 po recenzji, rozszerzony po kolejnej): 'wyslane' to
        // liczba klientów — ta liczba idzie do komunikatu. 'maile' może być 0 mimo
        // wyslane > 0 z DWÓCH różnych powodów, które trzeba odróżnić, inaczej właścicielka
        // źle zrozumie, co się stało:
        //   - 'mail_wylaczony': przełącznik w ustawieniach jest wyłączony (dotyczy WSZYSTKICH);
        //   - brak przełącznika, ale 'bez_maila' === 'wyslane': nikt z zaznaczonych nie ma
        //     zapisanego adresu.
        // Gdy 'maile' jest dodatnie, ale MNIEJSZE niż 'wyslane' (część klientów bez adresu,
        // reszta z adresem), poprzednia wersja milczała o tym całkowicie i właścicielka
        // myślała, że mail poszedł do wszystkich zaznaczonych — teraz mówimy to wprost.
        // 'pominieci' to klienci, którzy przestali zalegać między wyrenderowaniem ekranu
        // a kliknięciem.
        const wyslane = dane.wyslane || 0;
        const maile = dane.maile || 0;
        const bezMaila = dane.bez_maila || 0;
        const mailWylaczony = !!dane.mail_wylaczony;
        const pominieci = dane.pominieci || [];

        let tekst = 'Wysłano przypomnień: ' + wyslane;
        if (wyslane > 0 && maile === 0) {
            if (mailWylaczony) {
                tekst += '. Mail jest wyłączony w ustawieniach — poszło tylko powiadomienie w aplikacji.';
            } else {
                tekst += '. Nikt z zaznaczonych nie ma zapisanego adresu e-mail — poszło tylko powiadomienie w aplikacji.';
            }
        } else if (maile > 0 && maile < wyslane && bezMaila > 0 && !mailWylaczony) {
            tekst += '. Mail nie poszedł do ' + opisIluOsobMianownik(bezMaila) +
                ' (brak zapisanego adresu) — reszta dostała mail normalnie, wszyscy dostali powiadomienie w aplikacji.';
        }
        if (pominieci.length > 0) {
            tekst += ' Pominięto ' + opisIluOsob(pominieci.length) + ' — przestały już zalegać.';
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
            if (!window.confirm(
                'Do ' + opisDoIluOsob(swiezo.length) + ' przypomnienie poszło w ciągu ostatnich ' +
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
                    pokazToast(komunikatSukcesu(dane), 'success');
                    // Wzorzec z orders-list.js: przeładowanie po chwili, żeby zdążyć przeczytać
                    // toast, zanim strona się wyładuje. Gdy komunikat ma drugi człon (mail
                    // wyłączony w ustawieniach albo lista pominiętych klientów), tekst jest
                    // wyraźnie dłuższy do przeczytania niż samo "Wysłano przypomnień: N" —
                    // wydłużamy pauzę do 2500 ms zamiast standardowych 1200 ms.
                    const wieloczlonowy = (dane.wyslane > 0 && (dane.maile || 0) === 0) ||
                        (dane.pominieci || []).length > 0;
                    setTimeout(function () {
                        window.location.reload();
                    }, wieloczlonowy ? 2500 : 1200);
                } else {
                    pokazToast(dane.message || 'Nie udało się wysłać', 'error');
                    przycisk.disabled = false;
                }
            })
            .catch(function () {
                pokazToast('Nie udało się wysłać przypomnień', 'error');
                przycisk.disabled = false;
            });
    });

    odswiezLicznik();
})();
