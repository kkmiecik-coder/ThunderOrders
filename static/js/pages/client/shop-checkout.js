(function () {
    'use strict';

    // --- CSRF helper ---
    function getCsrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) return meta.getAttribute('content');
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var parts = cookies[i].trim().split('=');
            if (parts[0] === 'csrf_token') return decodeURIComponent(parts[1]);
        }
        var input = document.querySelector('input[name="csrf_token"]');
        return input ? input.value : '';
    }

    // --- DOM refs ---
    var itemsList = document.getElementById('checkoutItemsList');
    var loadingEl = document.getElementById('checkoutLoading');
    var summaryCount = document.getElementById('summaryCount');
    var summaryTotal = document.getElementById('summaryTotal');
    var shippingCheckbox = document.getElementById('createShippingCheckbox');
    var addressPicker = document.getElementById('addressPicker');
    var addressSelect = document.getElementById('addressSelect');
    var placeOrderBtn = document.getElementById('placeOrderBtn');

    if (!itemsList) return; // not on checkout page

    var cartData = null;
    var hasUnavailable = false;

    // --- Load cart ---
    function loadCart() {
        fetch('/client/shop/api/cart')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (loadingEl) loadingEl.style.display = 'none';
                cartData = data;
                renderItems(data.items);
                updateSummary(data);
            })
            .catch(function () {
                if (loadingEl) loadingEl.textContent = 'Błąd ładowania koszyka.';
            });
    }

    function renderItems(items) {
        if (!items || items.length === 0) {
            itemsList.innerHTML = '<p class="checkout-empty">Koszyk jest pusty.</p>';
            return;
        }

        hasUnavailable = false;
        var html = '';
        for (var i = 0; i < items.length; i++) {
            var item = items[i];
            var unavailable = !item.is_available;
            if (unavailable) hasUnavailable = true;

            var imgHtml = item.image_url
                ? '<img src="' + item.image_url + '" alt="' + escapeHtml(item.name) + '">'
                : '<div class="checkout-item-placeholder"><i class="fas fa-box"></i></div>';

            html += '<div class="checkout-item' + (unavailable ? ' checkout-item--unavailable' : '') + '">';
            html += '  <div class="checkout-item-image">' + imgHtml + '</div>';
            html += '  <div class="checkout-item-info">';
            html += '    <div class="checkout-item-name">' + escapeHtml(item.name) + '</div>';
            if (item.size) {
                html += '    <div class="checkout-item-size">Rozmiar: ' + escapeHtml(item.size) + '</div>';
            }
            if (unavailable) {
                html += '    <div class="checkout-item-error"><i class="fas fa-exclamation-triangle"></i> Niedostępny</div>';
            }
            html += '  </div>';
            html += '  <div class="checkout-item-qty">' + item.quantity + ' szt.</div>';
            html += '  <div class="checkout-item-price">' + formatPrice(item.price * item.quantity) + ' PLN</div>';
            html += '</div>';
        }
        itemsList.innerHTML = html;
        updatePlaceBtn();
    }

    function updateSummary(data) {
        if (summaryCount) summaryCount.textContent = data.count + ' szt.';
        if (summaryTotal) summaryTotal.textContent = formatPrice(data.total) + ' PLN';
        updatePlaceBtn();
    }

    function updatePlaceBtn() {
        if (!placeOrderBtn) return;
        var disabled = hasUnavailable || !cartData || cartData.count === 0;
        placeOrderBtn.disabled = disabled;
    }

    // --- Shipping toggle ---
    if (shippingCheckbox) {
        shippingCheckbox.addEventListener('change', function () {
            if (addressPicker) {
                addressPicker.style.display = this.checked ? 'block' : 'none';
            }
        });
    }

    // --- Place order ---
    if (placeOrderBtn) {
        placeOrderBtn.addEventListener('click', function () {
            if (placeOrderBtn.disabled) return;
            placeOrderBtn.disabled = true;
            placeOrderBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Składanie...';

            var payload = {
                create_shipping: shippingCheckbox ? shippingCheckbox.checked : false,
                address_id: (shippingCheckbox && shippingCheckbox.checked && addressSelect)
                    ? parseInt(addressSelect.value) || null
                    : null,
            };

            fetch('/client/shop/checkout/place', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
                body: JSON.stringify(payload),
            })
                .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
                .then(function (res) {
                    if (res.data.success) {
                        window.location.href = res.data.redirect_url;
                    } else {
                        // Show errors
                        if (res.data.stock_errors) {
                            var msgs = res.data.stock_errors.map(function (e) { return e.error; });
                            showToast(msgs.join('\n'), 'error');
                            // Reload cart to reflect changes
                            loadCart();
                        } else {
                            showToast(res.data.error || 'Wystąpił błąd.', 'error');
                        }
                        placeOrderBtn.disabled = false;
                        placeOrderBtn.innerHTML = '<i class="fas fa-check"></i> Złóż zamówienie';
                    }
                })
                .catch(function () {
                    showToast('Błąd połączenia z serwerem.', 'error');
                    placeOrderBtn.disabled = false;
                    placeOrderBtn.innerHTML = '<i class="fas fa-check"></i> Złóż zamówienie';
                });
        });
    }

    // --- Helpers ---
    function formatPrice(val) {
        return Number(val).toFixed(2).replace('.', ',');
    }

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }

    function showToast(msg, type) {
        if (window.Toast && typeof window.Toast.show === 'function') {
            window.Toast.show(msg, type);
        } else {
            alert(msg);
        }
    }

    // --- Init ---
    loadCart();
})();
