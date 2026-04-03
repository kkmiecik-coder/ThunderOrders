/**
 * Shop Product Detail Page
 * Gallery thumbnails, quantity controls, add-to-cart
 */

(function () {
    'use strict';

    // ---- CSRF Token ----
    function getCsrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) return meta.getAttribute('content');
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var parts = cookies[i].trim().split('=');
            if (parts[0] === 'csrf_token') return decodeURIComponent(parts[1]);
        }
        return '';
    }

    // ---- Cart badge ----
    function updateCartBadge(count) {
        document.querySelectorAll('.cart-badge').forEach(function (badge) {
            badge.textContent = count;
            badge.style.display = count > 0 ? 'flex' : 'none';
        });
    }

    // ---- DOM refs ----
    var mainImage = document.getElementById('galleryMainImage');
    var thumbs = document.querySelectorAll('.product-thumb');
    var qtyInput = document.getElementById('qtyInput');
    var qtyMinus = document.getElementById('qtyMinus');
    var qtyPlus = document.getElementById('qtyPlus');
    var addToCartBtn = document.getElementById('addToCartBtn');
    var stickyAddBtn = document.getElementById('stickyAddToCartBtn');
    var stockEl = document.getElementById('productStock');

    var maxQty = stockEl ? parseInt(stockEl.getAttribute('data-stock'), 10) || 0 : 0;

    // ---- Gallery thumbnails ----
    thumbs.forEach(function (thumb) {
        thumb.addEventListener('click', function () {
            if (!mainImage) return;
            var src = thumb.getAttribute('data-image');
            if (src) {
                mainImage.src = src;
            }
            // Update active state
            thumbs.forEach(function (t) { t.classList.remove('active'); });
            thumb.classList.add('active');
        });
    });

    // ---- Quantity controls ----
    function getQty() {
        return parseInt(qtyInput ? qtyInput.value : '1', 10) || 1;
    }

    function setQty(val) {
        if (val < 1) val = 1;
        if (val > maxQty) val = maxQty;
        if (qtyInput) qtyInput.value = val;
    }

    if (qtyMinus) {
        qtyMinus.addEventListener('click', function () {
            setQty(getQty() - 1);
        });
    }

    if (qtyPlus) {
        qtyPlus.addEventListener('click', function () {
            setQty(getQty() + 1);
        });
    }

    // ---- Add to cart ----
    function addToCart(btn) {
        if (!btn || btn.disabled) return;

        var productId = parseInt(btn.getAttribute('data-product-id'), 10);
        if (!productId) return;

        var quantity = getQty();

        // Disable both buttons during request
        if (addToCartBtn) addToCartBtn.disabled = true;
        if (stickyAddBtn) stickyAddBtn.disabled = true;

        var cartIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 002 1.61h9.72a2 2 0 002-1.61L23 6H6"/></svg>';
        var originalHtml = cartIcon + ' Dodaj do koszyka';
        var checkIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><polyline points="20 6 9 17 4 12"/></svg>';

        btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16" class="spin-icon"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg> Dodawanie...';

        function restoreBtn() {
            if (addToCartBtn) { addToCartBtn.disabled = false; addToCartBtn.innerHTML = originalHtml; addToCartBtn.classList.remove('product-add-to-cart--added'); }
            if (stickyAddBtn) { stickyAddBtn.disabled = false; stickyAddBtn.innerHTML = originalHtml; stickyAddBtn.classList.remove('product-add-to-cart--added'); }
        }

        fetch('/client/shop/api/cart/add', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({ product_id: productId, quantity: quantity })
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.success) {
                // Show "Dodano!" for 3 seconds
                var addedHtml = checkIcon + ' Dodano!';
                if (addToCartBtn) { addToCartBtn.innerHTML = addedHtml; addToCartBtn.classList.add('product-add-to-cart--added'); }
                if (stickyAddBtn) { stickyAddBtn.innerHTML = addedHtml; stickyAddBtn.classList.add('product-add-to-cart--added'); }
                setTimeout(restoreBtn, 3000);

                try {
                    if (typeof window.showToast === 'function') window.showToast('Dodano do koszyka', 'success');
                    if (data.cart_count != null) updateCartBadge(data.cart_count);
                } catch (e) { console.error('Toast/badge error:', e); }
            } else {
                restoreBtn();
                try { if (typeof window.showToast === 'function') window.showToast(data.error || 'Nie udało się dodać do koszyka', 'error'); } catch (e) {}

                // If stock changed, update display
                if (data.available_quantity != null) {
                    maxQty = data.available_quantity;
                    if (qtyInput) qtyInput.max = maxQty;
                    if (maxQty === 0) {
                        if (addToCartBtn) addToCartBtn.disabled = true;
                        if (stickyAddBtn) stickyAddBtn.disabled = true;
                    } else {
                        setQty(getQty());
                    }
                }
            }
        })
        .catch(function () {
            restoreBtn();
            try { if (typeof window.showToast === 'function') window.showToast('Błąd połączenia', 'error'); } catch (e) {}
        });
    }

    if (addToCartBtn) {
        addToCartBtn.addEventListener('click', function () {
            addToCart(addToCartBtn);
        });
    }

    if (stickyAddBtn) {
        stickyAddBtn.addEventListener('click', function () {
            addToCart(stickyAddBtn);
        });
    }

})();
