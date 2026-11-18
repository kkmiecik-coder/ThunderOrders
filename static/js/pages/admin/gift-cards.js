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

    // Pole startu zgłoszeń: kliknięcie w dowolne miejsce pola od razu otwiera kalendarz.
    document.querySelectorAll('input[type="datetime-local"].gc-input').forEach(function (input) {
        input.addEventListener('click', function () {
            if (typeof input.showPicker === 'function') {
                try { input.showPicker(); } catch (e) { /* przeglądarka nie pozwala — zostaje zwykłe pole */ }
            }
        });
    });

    // Formularz akcji: pola ilości — po jednym na każdy wybrany gratis/produkt (pulę), w każdym wierszu rodzaju.
    var kindBlocks = document.querySelectorAll('[data-gc-kind]');
    var productSelect = kindBlocks.length ? document.getElementById('giftCampaignForm') : null;

    function activeProductList() {
        var block = document.querySelector('[data-gc-kind]:not([hidden])');
        return block ? block.querySelector('.gc-product-list') : null;
    }

    function selectedProducts() {
        var listEl = activeProductList();
        if (!listEl) return [];
        return Array.prototype.map.call(
            listEl.querySelectorAll('input[type="checkbox"]:checked'),
            function (box) {
                var label = box.closest('.gc-check');
                return {id: box.value, name: (label ? label.textContent : box.value).trim()};
            });
    }

    function syncQtyGroup(group, products) {
        var existing = {};
        Array.prototype.forEach.call(group.querySelectorAll('.gc-qty'), function (el) {
            existing[el.getAttribute('data-product-id')] = el;
        });
        var listEl = activeProductList();
        var disabled = !!(listEl && listEl.querySelector('input[type="checkbox"]:disabled'));
        products.forEach(function (product) {
            var el = existing[product.id];
            if (!el) {
                el = document.createElement('label');
                el.className = 'gc-qty';
                el.setAttribute('data-product-id', product.id);
                var caption = document.createElement('span');
                caption.className = 'gc-qty__label';
                caption.textContent = product.name;
                var input = document.createElement('input');
                input.type = 'number';
                input.name = 'type_quantity_' + product.id;
                input.className = 'gc-input gc-input--qty';
                input.min = '0';
                input.step = '1';
                input.inputMode = 'numeric';
                input.placeholder = 'Ilość';
                input.disabled = !!disabled;
                el.appendChild(caption);
                el.appendChild(input);
            }
            delete existing[product.id];
            group.appendChild(el);  // dopina w kolejności wyboru (istniejące elementy są przenoszone)
        });
        Object.keys(existing).forEach(function (id) { existing[id].remove(); });
    }

    function syncAllQty() {
        var products = selectedProducts();
        document.querySelectorAll('#gcTypeList [data-gc-qty-group]').forEach(function (group) {
            syncQtyGroup(group, products);
        });
    }

    if (productSelect) {
        productSelect.addEventListener('change', function (event) {
            if (event.target.name === 'kind') {
                switchKind(event.target.value);
            } else if (event.target.closest('.gc-product-list')) {
                syncAllQty();
            }
        });
        // Wyszukiwarka produktów: chowa wiersze, których nazwa nie pasuje (bez rozróżniania wielkości liter).
        productSelect.addEventListener('input', function (event) {
            var search = event.target.closest('[data-gc-filter]');
            if (!search) return;
            var listEl = search.parentElement.querySelector('.gc-product-list');
            var query = search.value.trim().toLowerCase();
            if (!listEl) return;
            Array.prototype.forEach.call(listEl.querySelectorAll('.gc-check'), function (row) {
                row.hidden = query !== '' && row.textContent.toLowerCase().indexOf(query) === -1;
            });
        });
    }

    // Zmiana rodzaju akcji: pokazuje zestaw list tego rodzaju; pola ukrytego zestawu są wyłączone
    // (nie trafiają do formularza), żeby nie wysłać stron/produktów z drugiego rodzaju.
    function switchKind(kind) {
        Array.prototype.forEach.call(kindBlocks, function (block) {
            var active = block.getAttribute('data-gc-kind') === kind;
            block.hidden = !active;
            Array.prototype.forEach.call(block.querySelectorAll('input'), function (input) {
                input.disabled = !active;
            });
        });
        syncAllQty();
    }

    // Formularz akcji: dodawanie i usuwanie wierszy rodzajów kart.
    var addButton = document.getElementById('gcAddType');
    var list = document.getElementById('gcTypeList');
    var template = document.getElementById('gcTypeTemplate');
    if (addButton && list && template) {
        addButton.addEventListener('click', function () {
            var fragment = template.content.cloneNode(true);
            var group = fragment.querySelector('[data-gc-qty-group]');
            if (group) syncQtyGroup(group, selectedProducts());
            list.appendChild(fragment);
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
