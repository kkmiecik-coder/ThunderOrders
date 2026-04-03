/**
 * Cart Sidebar Component
 * Handles cart drawer open/close, AJAX cart operations, and badge updates.
 */
(function () {
    'use strict';

    // ── Helpers ──────────────────────────────────────────────────────────
    function getCsrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) return meta.getAttribute('content');
        var match = document.cookie.match(/csrf_token=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    function jsonHeaders() {
        return {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        };
    }

    // ── DOM refs (resolved lazily) ──────────────────────────────────────
    var overlay, sidebar, closeBtn, body, footer, empty, totalEl, recsEl;

    function refs() {
        if (!sidebar) {
            overlay  = document.getElementById('cartOverlay');
            sidebar  = document.getElementById('cartSidebar');
            closeBtn = document.getElementById('cartClose');
            body     = document.getElementById('cartBody');
            footer   = document.getElementById('cartFooter');
            empty    = document.getElementById('cartEmpty');
            totalEl  = document.getElementById('cartTotal');
            recsEl   = document.getElementById('cartEmptyRecs');
        }
    }

    // ── Open / Close ────────────────────────────────────────────────────
    function open() {
        refs();
        if (!sidebar) return;
        sidebar.classList.add('active');
        overlay.classList.add('active');
        document.body.style.overflow = 'hidden';
        loadCart();
    }

    function close() {
        refs();
        if (!sidebar) return;
        sidebar.classList.remove('active');
        overlay.classList.remove('active');
        document.body.style.overflow = '';
    }

    // ── Load cart data ──────────────────────────────────────────────────
    function loadCart() {
        refs();
        fetch('/client/shop/api/cart')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                renderCart(data.items, data.total, data.count);
                updateBadge(data.count);
            })
            .catch(function () {
                body.innerHTML = '<p class="cart-sidebar-error">Nie udalo sie zaladowac koszyka.</p>';
            });
    }

    // ── Render ──────────────────────────────────────────────────────────
    function renderCart(items, total, count) {
        refs();
        if (!items || items.length === 0) {
            body.innerHTML = '';
            footer.style.display = 'none';
            empty.style.display = 'flex';
            loadRecommendations();
            return;
        }

        empty.style.display = 'none';
        footer.style.display = '';
        totalEl.textContent = total.toFixed(2) + ' PLN';

        var html = '';
        items.forEach(function (item) {
            var unavailableClass = item.is_available ? '' : ' cart-item--unavailable';
            var productUrl = '/client/shop/product/' + item.product_id + '-' + item.slug;
            var imgHtml = item.image_url
                ? '<img src="' + escapeHtml(item.image_url) + '" alt="' + escapeHtml(item.name) + '" class="cart-item-img">'
                : '<div class="cart-item-img cart-item-img--placeholder"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="32" height="32"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg></div>';

            html += '<div class="cart-item' + unavailableClass + '" data-item-id="' + item.id + '">';
            html += '  <a href="' + productUrl + '" class="cart-item-image-link">' + imgHtml + '</a>';
            html += '  <div class="cart-item-info">';
            html += '    <a href="' + productUrl + '" class="cart-item-name">' + escapeHtml(item.name) + '</a>';
            if (item.size) {
                html += '    <span class="cart-item-size">' + escapeHtml(item.size) + '</span>';
            }
            if (!item.is_available) {
                html += '    <span class="cart-item-unavailable-label">Niedostepny</span>';
            }
            html += '    <span class="cart-item-price">' + item.price.toFixed(2) + ' PLN</span>';
            html += '    <div class="cart-item-qty">';
            html += '      <button class="cart-qty-btn" data-action="qty-decrease" data-item-id="' + item.id + '" data-current="' + item.quantity + '">-</button>';
            html += '      <span class="cart-qty-value">' + item.quantity + '</span>';
            html += '      <button class="cart-qty-btn" data-action="qty-increase" data-item-id="' + item.id + '" data-current="' + item.quantity + '" data-max="' + item.available + '">+</button>';
            html += '    </div>';
            html += '  </div>';
            html += '  <button class="cart-item-remove" data-action="remove-item" data-item-id="' + item.id + '" aria-label="Usun">&times;</button>';
            html += '</div>';
        });

        body.innerHTML = html;
    }

    function escapeHtml(str) {
        if (!str) return '';
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }

    // ── Recommendations for empty cart ──────────────────────────────────
    function loadRecommendations() {
        refs();
        fetch('/client/shop/api/products?per_page=4')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var products = data.products || data.items || [];
                if (!products.length) { recsEl.innerHTML = ''; return; }

                var html = '<p class="cart-recs-title">Może Cię zainteresować</p>';
                html += '<div class="cart-recs-grid">';
                products.forEach(function (p) {
                    var slug = p.slug || '';
                    var url = '/client/shop/product/' + p.id + '-' + slug;
                    var img = p.image_url
                        ? '<img src="' + escapeHtml(p.image_url) + '" alt="' + escapeHtml(p.name) + '">'
                        : '<div class="cart-rec-placeholder"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="32" height="32"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg></div>';
                    html += '<a href="' + url + '" class="cart-rec-card">';
                    html += img;
                    html += '<span class="cart-rec-name">' + escapeHtml(p.name) + '</span>';
                    html += '<span class="cart-rec-price">' + (p.price ? p.price.toFixed(2) : '0.00') + ' PLN</span>';
                    html += '</a>';
                });
                html += '</div>';
                recsEl.innerHTML = html;
            })
            .catch(function () {
                recsEl.innerHTML = '';
            });
    }

    // ── Cart actions (event delegation) ─────────────────────────────────
    function handleBodyClick(e) {
        var btn = e.target.closest('[data-action]');
        if (!btn) return;

        var action = btn.getAttribute('data-action');
        var itemId = btn.getAttribute('data-item-id');

        if (action === 'qty-decrease') {
            var current = parseInt(btn.getAttribute('data-current'), 10);
            updateQuantity(itemId, current - 1);
        } else if (action === 'qty-increase') {
            var cur = parseInt(btn.getAttribute('data-current'), 10);
            var max = parseInt(btn.getAttribute('data-max'), 10);
            if (cur < max) {
                updateQuantity(itemId, cur + 1);
            } else {
                if (window.Toast) window.Toast.show('Maksymalna dostepna ilosc: ' + max, 'warning');
            }
        } else if (action === 'remove-item') {
            removeItem(itemId);
        }
    }

    function updateQuantity(itemId, qty) {
        fetch('/client/shop/api/cart/update', {
            method: 'POST',
            headers: jsonHeaders(),
            body: JSON.stringify({ item_id: parseInt(itemId, 10), quantity: qty })
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.success) {
                loadCart();
            } else {
                if (window.Toast) window.Toast.show(data.error || 'Blad aktualizacji.', 'error');
            }
        })
        .catch(function () {
            if (window.Toast) window.Toast.show('Blad polaczenia.', 'error');
        });
    }

    function removeItem(itemId) {
        fetch('/client/shop/api/cart/remove', {
            method: 'POST',
            headers: jsonHeaders(),
            body: JSON.stringify({ item_id: parseInt(itemId, 10) })
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.success) {
                loadCart();
            } else {
                if (window.Toast) window.Toast.show(data.error || 'Blad usuwania.', 'error');
            }
        })
        .catch(function () {
            if (window.Toast) window.Toast.show('Blad polaczenia.', 'error');
        });
    }

    // ── Badge update ────────────────────────────────────────────────────
    function updateBadge(count) {
        document.querySelectorAll('.cart-badge').forEach(function (badge) {
            if (count > 0) {
                badge.textContent = count;
                badge.style.display = '';
            } else {
                badge.textContent = '';
                badge.style.display = 'none';
            }
        });
    }

    function loadBadge() {
        fetch('/client/shop/api/cart/count')
            .then(function (r) { return r.json(); })
            .then(function (data) { updateBadge(data.count); })
            .catch(function () { /* silent */ });
    }

    // ── Init ────────────────────────────────────────────────────────────
    function init() {
        refs();
        if (!sidebar) return;

        // Close handlers
        if (overlay) overlay.addEventListener('click', close);
        if (closeBtn) closeBtn.addEventListener('click', close);

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && sidebar.classList.contains('active')) {
                close();
            }
        });

        // Event delegation for cart item actions
        if (body) body.addEventListener('click', handleBodyClick);

        // Global open-cart triggers
        document.addEventListener('click', function (e) {
            var trigger = e.target.closest('[data-action="open-cart"]');
            if (trigger) {
                e.preventDefault();
                open();
            }
        });

        // Load badge on page load
        loadBadge();
    }

    // Expose globally
    window.openCartSidebar = open;
    window.closeCartSidebar = close;
    window.refreshCartBadge = loadBadge;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
