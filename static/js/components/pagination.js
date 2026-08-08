/**
 * PAGINACJA — selektor „ile na stronie" i pole skoku do strony.
 *
 * Oba elementy dostają z szablonu gotowe URL-e (components/_pagination.html),
 * więc ten plik niczego nie skleja z parametrów — tylko przenosi przeglądarkę
 * pod właściwy adres. Na stronie mogą być dwa paski (nad listą i pod nią);
 * oba czytają stan z URL-a, więc pokazują to samo.
 */
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.pagination-per-page-select').forEach(function (select) {
        select.addEventListener('change', function () {
            if (select.value) {
                window.location.href = select.value;
            }
        });
    });

    document.querySelectorAll('.pagination-input').forEach(function (input) {
        var template = input.dataset.pageUrlTemplate;
        if (!template) return;

        var startValue = input.value;

        function idz() {
            var docelowa = parseInt(input.value, 10);
            var ostatnia = parseInt(input.max, 10) || 1;

            // Puste pole albo śmieci: wróć do numeru bieżącej strony.
            if (isNaN(docelowa)) {
                input.value = startValue;
                return;
            }

            // Trzymaj się zakresu — wpisane 0 albo 999 nie ma sensownej strony.
            docelowa = Math.min(Math.max(docelowa, 1), ostatnia);
            input.value = docelowa;

            if (String(docelowa) === String(startValue)) return;
            window.location.href = template.replace('__PAGE__', docelowa);
        }

        input.addEventListener('change', idz);
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                idz();
            }
        });
    });
});
