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

        var originalHtml = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Dodawanie...';

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
            // Restore buttons
            btn.innerHTML = originalHtml;
            if (addToCartBtn) addToCartBtn.disabled = false;
            if (stickyAddBtn) stickyAddBtn.disabled = false;

            if (data.success) {
                if (typeof window.showToast === 'function') window.showToast('Dodano do koszyka', 'success');
                if (data.cart_count != null) updateCartBadge(data.cart_count);

                // Track event
                if (typeof window.trackAddToCart === 'function') {
                    var name = document.querySelector('.product-title');
                    var sku = document.querySelector('.product-sku');
                    var price = document.querySelector('.product-price');
                    window.trackAddToCart(
                        name ? name.textContent.trim() : '',
                        sku ? sku.textContent.replace('SKU:', '').trim() : '',
                        price ? parseFloat(price.textContent.replace(',', '.').replace(/[^\d.]/g, '')) : 0,
                        quantity
                    );
                }
            } else {
                if (typeof window.showToast === 'function') window.showToast(data.error || 'Nie udalo sie dodac do koszyka', 'error');

                // If stock changed, update display
                if (data.available_quantity != null) {
                    maxQty = data.available_quantity;
                    if (qtyInput) qtyInput.max = maxQty;
                    if (maxQty === 0) {
                        if (addToCartBtn) addToCartBtn.disabled = true;
                        if (stickyAddBtn) stickyAddBtn.disabled = true;
                        if (stockEl) {
                            stockEl.setAttribute('data-stock', '0');
                            stockEl.innerHTML = '<span class="product-stock-badge product-stock-unavailable">' +
                                '<i class="fas fa-times-circle"></i> Brak w magazynie</span>';
                        }
                    } else {
                        setQty(getQty());
                        if (stockEl) {
                            stockEl.setAttribute('data-stock', maxQty);
                            stockEl.innerHTML = '<span class="product-stock-badge product-stock-available">' +
                                '<i class="fas fa-check-circle"></i> Dostepne: ' + maxQty + ' szt.</span>';
                        }
                    }
                }
            }
        })
        .catch(function () {
            btn.innerHTML = originalHtml;
            if (addToCartBtn) addToCartBtn.disabled = false;
            if (stickyAddBtn) stickyAddBtn.disabled = false;
            if (typeof window.showToast === 'function') window.showToast('Blad polaczenia', 'error');
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
