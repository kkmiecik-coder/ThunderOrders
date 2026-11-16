/* Admin: Rozdział gratisów (formularz akcji + zamiany w tabeli przydziału) */
(function () {
    'use strict';

    function getCsrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function toast(message, type) {
        if (typeof window.showToast === 'function') {
            window.showToast(message, type);
        }
    }

    // Potwierdzenie przed akcjami nieodwracalnymi (np. wysyłka maili).
    document.addEventListener('submit', function (event) {
        var form = event.target.closest('form[data-gc-confirm]');
        if (!form) return;
        var message = form.getAttribute('data-gc-confirm');
        if (message && !window.confirm(message)) {
            event.preventDefault();
        }
    });

    // Pole daty wyścigu: kliknięcie w dowolne miejsce pola od razu otwiera kalendarz.
    document.querySelectorAll('input[type="datetime-local"].gc-input').forEach(function (input) {
        input.addEventListener('click', function () {
            if (typeof input.showPicker === 'function') {
                try { input.showPicker(); } catch (e) { /* przeglądarka nie pozwala — zostaje zwykłe pole */ }
            }
        });
    });

    // Formularz akcji: dodawanie i usuwanie wierszy rodzajów kart.
    var addButton = document.getElementById('gcAddType');
    var list = document.getElementById('gcTypeList');
    var template = document.getElementById('gcTypeTemplate');
    if (addButton && list && template) {
        addButton.addEventListener('click', function () {
            list.appendChild(template.content.cloneNode(true));
        });
    }
    if (list) {
        list.addEventListener('click', function (event) {
            var button = event.target.closest('[data-gc-remove-type]');
            if (button) {
                var row = button.closest('.gc-type-row');
                if (row) row.remove();
            }
        });
    }

    // Szczegóły: zamiana rodzaju karty w przydziale.
    var detail = document.getElementById('gcDetail');
    if (detail) {
        detail.addEventListener('change', function (event) {
            var select = event.target.closest('select[data-assignment-id]');
            if (!select) return;
            var previous = select.getAttribute('data-current');
            select.disabled = true;
            fetch(detail.getAttribute('data-swap-url'), {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken()},
                body: JSON.stringify({
                    assignment_id: parseInt(select.getAttribute('data-assignment-id'), 10),
                    type_id: parseInt(select.value, 10)
                })
            }).then(function (response) {
                return response.json().catch(function () {
                    return {success: false, error: 'Nie udało się zapisać zamiany.'};
                });
            }).then(function (result) {
                if (result.success) {
                    // Duplikaty i numery wyborów liczy serwer — odśwież widok.
                    window.location.reload();
                } else {
                    select.value = previous;
                    select.disabled = false;
                    toast(result.error || 'Nie udało się zapisać zamiany.', 'error');
                }
            }).catch(function () {
                select.value = previous;
                select.disabled = false;
                toast('Błąd połączenia — spróbuj ponownie.', 'error');
            });
        });
    }
})();
