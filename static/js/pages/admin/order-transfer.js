/**
 * Przepisanie zamówienia (całego albo wybranych pozycji) na inną klientkę.
 * Modal #transferOrderModal w templates/admin/orders/detail.html,
 * backend: POST /admin/orders/<id>/transfer (modules/orders/transfer.py).
 */
(function () {
    'use strict';

    let chosenClientId = null;
    let searchTimer = null;

    function $(id) { return document.getElementById(id); }

    function csrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text == null ? '' : String(text);
        return div.innerHTML;
    }

    function toast(message, type) {
        if (typeof window.showToast === 'function') {
            window.showToast(message, type);
        } else {
            alert(message);
        }
    }

    function mode() {
        const checked = document.querySelector('input[name="transferMode"]:checked');
        return checked ? checked.value : 'items';
    }

    function refreshMode() {
        const whole = mode() === 'whole';
        $('transferItems').hidden = whole;
        $('transferWholeInfo').hidden = !whole;
        // Przy całym zamówieniu wpłaty zostają w zamówieniu — przełącznik nie ma sensu.
        $('transferPaymentRow').hidden = whole;
        $('transferPaymentHint').hidden = whole;
    }

    window.openTransferModal = function () {
        const modal = $('transferOrderModal');
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
        refreshMode();
        setTimeout(function () { $('transferClientSearch').focus(); }, 100);
    };

    window.closeTransferModal = function () {
        const modal = $('transferOrderModal');
        modal.classList.add('closing');
        setTimeout(function () {
            modal.classList.remove('active', 'closing');
            document.body.style.overflow = '';
        }, 200);
    };

    window.resetTransferClient = function () {
        chosenClientId = null;
        $('transferClientChosen').hidden = true;
        $('transferClientPicker').hidden = false;
        $('transferClientSearch').value = '';
        $('transferClientResults').innerHTML = '';
        $('transferClientSearch').focus();
    };

    function chooseClient(id, label) {
        chosenClientId = id;
        $('transferClientName').textContent = label;
        $('transferClientChosen').hidden = false;
        $('transferClientPicker').hidden = true;
    }

    function renderResults(clients) {
        const box = $('transferClientResults');
        if (!clients.length) {
            box.innerHTML = '<div class="transfer-empty">Nie znaleziono klientek</div>';
            return;
        }
        box.innerHTML = clients.map(function (c) {
            return '<button type="button" class="transfer-client-item" data-id="' + c.id + '"' +
                ' data-label="' + escapeHtml(c.full_name + ' (' + c.email + ')') + '">' +
                '<span class="transfer-client-item-name">' + escapeHtml(c.full_name) + '</span>' +
                '<span class="transfer-client-item-email">' + escapeHtml(c.email) + '</span>' +
                '</button>';
        }).join('');
    }

    function search(query) {
        fetch('/api/clients/search?q=' + encodeURIComponent(query))
            .then(function (r) { return r.json(); })
            .then(function (data) { renderResults(data.clients || []); })
            .catch(function () {
                $('transferClientResults').innerHTML = '<div class="transfer-empty">Błąd wyszukiwania</div>';
            });
    }

    function selectedItems() {
        const items = [];
        document.querySelectorAll('#transferItems .transfer-item').forEach(function (row) {
            if (!row.querySelector('.transfer-item-checkbox').checked) return;
            items.push({
                item_id: parseInt(row.dataset.itemId, 10),
                quantity: parseInt(row.querySelector('.transfer-item-qty').value, 10)
            });
        });
        return items;
    }

    window.submitTransfer = function () {
        if (!chosenClientId) {
            toast('Najpierw wybierz klientkę.', 'warning');
            return;
        }
        const body = {
            client_id: chosenClientId,
            mode: mode(),
            items: mode() === 'items' ? selectedItems() : [],
            payment_follows: $('transferPaymentFollows').checked,
            notify: $('transferNotify').checked
        };
        if (body.mode === 'items' && !body.items.length) {
            toast('Zaznacz przynajmniej jedną pozycję.', 'warning');
            return;
        }
        const orderNumber = $('transferOrderModal').dataset.orderNumber;
        const pytanie = body.mode === 'whole'
            ? 'Przepisać całe zamówienie ' + orderNumber + ' na: ' + $('transferClientName').textContent + '?'
            : 'Przepisać zaznaczone pozycje na: ' + $('transferClientName').textContent + '?';
        if (!confirm(pytanie)) return;

        const button = $('transferSubmit');
        button.disabled = true;
        fetch('/admin/orders/' + $('transferOrderModal').dataset.orderId + '/transfer', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
            body: JSON.stringify(body)
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    toast(data.message, 'success');
                    setTimeout(function () { window.location.href = data.redirect_url; }, 600);
                } else {
                    toast(data.message || 'Nie udało się przepisać.', 'error');
                    button.disabled = false;
                }
            })
            .catch(function () {
                toast('Błąd połączenia — spróbuj ponownie.', 'error');
                button.disabled = false;
            });
    };

    document.addEventListener('DOMContentLoaded', function () {
        const modal = $('transferOrderModal');
        if (!modal) return;

        $('transferClientSearch').addEventListener('input', function (e) {
            const query = e.target.value.trim();
            clearTimeout(searchTimer);
            if (query.length < 3) {
                $('transferClientResults').innerHTML = '';
                return;
            }
            searchTimer = setTimeout(function () { search(query); }, 300);
        });

        $('transferClientResults').addEventListener('click', function (e) {
            const item = e.target.closest('.transfer-client-item');
            if (item) chooseClient(parseInt(item.dataset.id, 10), item.dataset.label);
        });

        document.querySelectorAll('input[name="transferMode"]').forEach(function (radio) {
            radio.addEventListener('change', refreshMode);
        });

        document.querySelectorAll('#transferItems .transfer-item-qty').forEach(function (input) {
            input.addEventListener('change', function () {
                const max = parseInt(input.max, 10);
                let value = parseInt(input.value, 10);
                if (isNaN(value) || value < 1) value = 1;
                if (value > max) value = max;
                input.value = value;
            });
        });

        modal.addEventListener('click', function (e) {
            if (e.target === modal) window.closeTransferModal();
        });
    });
})();
