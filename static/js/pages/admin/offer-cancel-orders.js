/**
 * Modal masowego anulowania zamówień na podsumowaniu zamkniętej zbiórki.
 * Otwierany przez window.openCancelOrdersModal(ids) z offer-summary.js.
 *
 * Podział na grupy (nieopłacone/opłacone) liczony tu jest tylko po to, żeby
 * pokazać go przed kliknięciem — wiążący jest wynik z backendu.
 */
(function () {
    var selectedIds = [];
    var SHIPPED_STATUSES = ['wyslane', 'dostarczone'];

    function getCsrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        if (meta && meta.content) return meta.content;
        var el = document.querySelector('input[name="csrf_token"]');
        return el ? el.value : '';
    }

    function notify(message, type) {
        if (typeof window.showToast === 'function') {
            window.showToast(message, type);
        } else {
            alert(message);
        }
    }

    // Poprawna forma rzeczownika 'zamówienie' w bierniku dla liczby n.
    function pluralZamowien(n) {
        if (n === 1) return 'zamówienie';
        if (n % 10 >= 2 && n % 10 <= 4 && !(n % 100 >= 12 && n % 100 <= 14)) return 'zamówienia';
        return 'zamówień';
    }

    function ordersById() {
        var map = {};
        (window.SUMMARY_ORDERS || []).forEach(function (o) { map[o.order_id] = o; });
        return map;
    }

    function showError(message) {
        var box = document.getElementById('cancelReasonError');
        box.textContent = message;
        box.style.display = 'block';
    }

    function hideError() {
        document.getElementById('cancelReasonError').style.display = 'none';
    }

    function closeModal() {
        var modal = document.getElementById('cancelOrdersModal');
        if (modal) modal.classList.remove('active');
    }

    window.openCancelOrdersModal = function (ids) {
        selectedIds = ids || [];
        if (!selectedIds.length) return;

        var map = ordersById();
        var paid = 0;
        var unpaid = 0;
        var shipped = 0;

        selectedIds.forEach(function (id) {
            var order = map[id];
            if (!order) return;
            if (order.is_paid) { paid++; } else { unpaid++; }
            if (SHIPPED_STATUSES.indexOf(order.status) !== -1) shipped++;
        });

        document.getElementById('cancelTotalCount').textContent = selectedIds.length;
        document.getElementById('cancelTotalLabel').textContent = pluralZamowien(selectedIds.length);
        document.getElementById('cancelPaidCount').textContent = paid;
        document.getElementById('cancelUnpaidCount').textContent = unpaid;

        var warning = document.getElementById('cancelShippedWarning');
        if (shipped > 0) {
            warning.textContent = shipped + ' z zaznaczonych ' + pluralZamowien(shipped) +
                ' zostało już wysłanych lub dostarczonych.';
            warning.style.display = 'block';
        } else {
            warning.style.display = 'none';
        }

        document.getElementById('cancelReason').value = '';
        document.getElementById('cancelNotify').checked = true;
        hideError();

        document.getElementById('cancelOrdersModal').classList.add('active');
        document.getElementById('cancelReason').focus();
    };

    function submit() {
        var reason = document.getElementById('cancelReason').value.trim();
        if (!reason) {
            showError('Powód anulowania jest wymagany.');
            return;
        }
        hideError();

        var btn = document.getElementById('cancelOrdersSubmit');
        btn.disabled = true;
        btn.textContent = 'Anuluję...';

        fetch(window.CANCEL_ORDERS_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                order_ids: selectedIds,
                reason: reason,
                notify: document.getElementById('cancelNotify').checked
            })
        })
            .then(function (r) {
                return r.json().then(function (data) { return { ok: r.ok, data: data }; });
            })
            .then(function (res) {
                if (!res.ok || !res.data.success) {
                    showError((res.data && res.data.message) || 'Nie udało się anulować zamówień.');
                    return;
                }
                notify(res.data.message, 'success');
                closeModal();
                // Statusy zmieniły się po stronie serwera — przeładowanie jest
                // najprostszym sposobem, żeby kafelki i statystyki się zgadzały.
                window.location.reload();
            })
            .catch(function () {
                showError('Błąd połączenia. Spróbuj ponownie.');
            })
            .finally(function () {
                btn.disabled = false;
                btn.textContent = 'Potwierdzam';
            });
    }

    document.addEventListener('DOMContentLoaded', function () {
        var modal = document.getElementById('cancelOrdersModal');
        if (!modal) return;

        document.querySelectorAll('[data-close-cancel-orders]').forEach(function (el) {
            el.addEventListener('click', closeModal);
        });

        modal.addEventListener('click', function (e) {
            if (e.target === modal) closeModal();
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && modal.classList.contains('active')) closeModal();
        });

        document.getElementById('cancelOrdersSubmit').addEventListener('click', submit);
    });
})();
