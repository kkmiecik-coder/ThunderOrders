/**
 * FILTRY SERWEROWE — wysyłka formularza filtrów bez przycisku „Szukaj".
 *
 * Używane tam, gdzie lista jest paginowana, więc filtrowanie musi iść przez
 * serwer (JS widziałby tylko bieżącą stronę). Formularz oznacza się atrybutem
 * `data-server-filters`, a pola w środku:
 *   data-filter-debounce — pola tekstowe: wysyłka po chwili od ostatniego znaku
 *   data-filter-submit   — daty, checkboxy: wysyłka od razu po zmianie
 *
 * Obsługuje też rozwijaną listę wielokrotnego wyboru (`data-multi-select-*`).
 */
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-server-filters]').forEach(function (form) {
        // Pola tekstowe — debounce, żeby nie przeładowywać po każdym znaku.
        form.querySelectorAll('[data-filter-debounce]').forEach(function (input) {
            var timer = null;
            input.addEventListener('input', function () {
                clearTimeout(timer);
                timer = setTimeout(function () { form.submit(); }, 400);
            });
        });

        // Daty i checkboxy statusów — zmiana jest zamierzona, wysyłamy od razu.
        form.querySelectorAll('[data-filter-submit]').forEach(function (field) {
            field.addEventListener('change', function () { form.submit(); });
        });

        // Rozwijana lista statusów.
        var trigger = form.querySelector('[data-multi-select-trigger]');
        var dropdown = form.querySelector('[data-multi-select-dropdown]');
        if (trigger && dropdown) {
            trigger.addEventListener('click', function (e) {
                e.stopPropagation();
                var otwarta = dropdown.style.display !== 'none';
                dropdown.style.display = otwarta ? 'none' : 'block';
            });

            // Klik w środku listy nie może jej zamykać — inaczej nie dałoby się
            // zaznaczyć checkboxa.
            dropdown.addEventListener('click', function (e) { e.stopPropagation(); });

            document.addEventListener('click', function () {
                dropdown.style.display = 'none';
            });
        }
    });

    // Po przeładowaniu wracamy kursorem na koniec wpisanej frazy, żeby dało się
    // pisać dalej bez klikania w pole.
    var ostatnie = document.querySelector('[data-server-filters] [data-filter-debounce][value]:not([value=""])');
    if (ostatnie && ostatnie.value) {
        ostatnie.focus();
        ostatnie.setSelectionRange(ostatnie.value.length, ostatnie.value.length);
    }
});
