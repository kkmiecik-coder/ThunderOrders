/**
 * Shop Page - Sklep (on-hand products)
 * Grid display, filtering, sorting, pagination, add-to-cart
 */

(function () {
    'use strict';

    // ---- State ----
    var state = {
        page: 1,
        perPage: 12,
        sort: 'newest',
        search: '',
        category: '',
        size: '',
        priceMin: '',
        priceMax: '',
        loading: false
    };

    // ---- DOM refs ----
    var els = {
        grid: document.getElementById('shopGrid'),
        pagination: document.getElementById('shopPagination'),
        resultsCount: document.getElementById('shopResultsCount'),
        empty: document.getElementById('shopEmpty'),
        loading: document.getElementById('shopLoading'),
        searchInput: document.getElementById('shopSearchInput'),
        searchBtn: document.getElementById('shopSearchBtn'),
        sortSelect: document.getElementById('shopSortSelect'),
        categoryOptions: document.getElementById('filterCategoryOptions'),
        sizeOptions: document.getElementById('filterSizeOptions'),
        priceMin: document.getElementById('filterPriceMin'),
        priceMax: document.getElementById('filterPriceMax'),
        applyBtn: document.getElementById('filterApplyBtn'),
        clearBtn: document.getElementById('filterClearBtn'),
        filtersToggle: document.getElementById('shopFiltersToggle'),
        filters: document.getElementById('shopFilters'),
        filtersMobileClose: document.getElementById('shopFiltersMobileClose'),
        emptyClearBtn: document.getElementById('shopEmptyClearBtn')
    };

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

    // ---- URL params ----
    function readUrlParams() {
        var params = new URLSearchParams(window.location.search);
        state.page = parseInt(params.get('page'), 10) || 1;
        state.sort = params.get('sort') || 'newest';
        state.search = params.get('search') || '';
        state.category = params.get('category') || '';
        state.size = params.get('size') || '';
        state.priceMin = params.get('price_min') || '';
        state.priceMax = params.get('price_max') || '';

        // Reflect in DOM
        if (els.searchInput) els.searchInput.value = state.search;
        if (els.sortSelect) els.sortSelect.value = state.sort;
        if (els.priceMin) els.priceMin.value = state.priceMin;
        if (els.priceMax) els.priceMax.value = state.priceMax;
    }

    function pushUrlParams() {
        var params = new URLSearchParams();
        if (state.page > 1) params.set('page', state.page);
        if (state.sort && state.sort !== 'newest') params.set('sort', state.sort);
        if (state.search) params.set('search', state.search);
        if (state.category) params.set('category', state.category);
        if (state.size) params.set('size', state.size);
        if (state.priceMin) params.set('price_min', state.priceMin);
        if (state.priceMax) params.set('price_max', state.priceMax);

        var qs = params.toString();
        var url = window.location.pathname + (qs ? '?' + qs : '');
        history.replaceState(null, '', url);
    }

    // ---- Escape HTML ----
    function esc(str) {
        if (!str) return '';
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }

    // ---- Format price ----
    function formatPrice(val) {
        var n = parseFloat(val);
        if (isNaN(n)) return '0.00';
        return n.toFixed(2).replace('.', ',');
    }

    // ---- Price slider labels ----
    var priceMinLabel = document.getElementById('filterPriceMinLabel');
    var priceMaxLabel = document.getElementById('filterPriceMaxLabel');

    function updatePriceLabels() {
        if (priceMinLabel && els.priceMin) priceMinLabel.textContent = els.priceMin.value + ' PLN';
        if (priceMaxLabel && els.priceMax) priceMaxLabel.textContent = els.priceMax.value + ' PLN';
    }

    if (els.priceMin) els.priceMin.addEventListener('input', updatePriceLabels);
    if (els.priceMax) els.priceMax.addEventListener('input', updatePriceLabels);

    // ---- Render product card ----
    function renderCard(p) {
        var price = formatPrice(p.price);
        var imageHtml = p.image_url
            ? '<img src="' + esc(p.image_url) + '" alt="' + esc(p.name) + '" loading="lazy">'
            : '<div class="shop-product-no-image"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="32" height="32"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg></div>';

        return '<div class="shop-product-card" data-product-id="' + p.id + '">' +
            '<a href="/client/shop/product/' + p.id + '-' + esc(p.slug) + '" class="shop-product-link">' +
                '<div class="shop-product-image">' + imageHtml + '</div>' +
            '</a>' +
            '<div class="shop-product-info">' +
                '<a href="/client/shop/product/' + p.id + '-' + esc(p.slug) + '" class="shop-product-name-link">' +
                    '<h3 class="shop-product-name">' + esc(p.name) + '</h3>' +
                '</a>' +
                '<div class="shop-product-bottom">' +
                    '<div class="shop-product-meta">' +
                        '<span class="shop-product-price">' + price + ' PLN</span>' +
                        (p.brand ? '<span class="shop-product-brand">' + esc(p.brand) + '</span>' : '') +
                    '</div>' +
                    '<button class="shop-product-add-btn" data-product-id="' + p.id + '" title="Dodaj do koszyka">' +
                        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">' +
                            '<circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/>' +
                            '<path d="M1 1h4l2.68 13.39a2 2 0 002 1.61h9.72a2 2 0 002-1.61L23 6H6"/>' +
                        '</svg>' +
                        '<span>Dodaj</span>' +
                    '</button>' +
                '</div>' +
            '</div>' +
        '</div>';
    }

    // ---- Render pagination ----
    function renderPagination(currentPage, totalPages) {
        if (!els.pagination) return;
        if (totalPages <= 1) {
            els.pagination.innerHTML = '';
            return;
        }

        var html = '';
        // Prev
        if (currentPage > 1) {
            html += '<button class="shop-page-btn" data-page="' + (currentPage - 1) + '">&laquo;</button>';
        }

        // Page numbers with ellipsis
        var start = Math.max(1, currentPage - 2);
        var end = Math.min(totalPages, currentPage + 2);

        if (start > 1) {
            html += '<button class="shop-page-btn" data-page="1">1</button>';
            if (start > 2) html += '<span class="shop-page-ellipsis">&hellip;</span>';
        }

        for (var i = start; i <= end; i++) {
            html += '<button class="shop-page-btn' + (i === currentPage ? ' active' : '') + '" data-page="' + i + '">' + i + '</button>';
        }

        if (end < totalPages) {
            if (end < totalPages - 1) html += '<span class="shop-page-ellipsis">&hellip;</span>';
            html += '<button class="shop-page-btn" data-page="' + totalPages + '">' + totalPages + '</button>';
        }

        // Next
        if (currentPage < totalPages) {
            html += '<button class="shop-page-btn" data-page="' + (currentPage + 1) + '">&raquo;</button>';
        }

        els.pagination.innerHTML = html;
    }

    // ---- Fetch products ----
    function fetchProducts() {
        if (state.loading) return;
        state.loading = true;

        if (els.loading) els.loading.style.display = 'flex';
        if (els.grid) els.grid.style.opacity = '0.5';

        var params = new URLSearchParams();
        params.set('page', state.page);
        params.set('per_page', state.perPage);
        params.set('sort', state.sort);
        if (state.search) params.set('search', state.search);
        if (state.category) params.set('category', state.category);
        if (state.size) params.set('size', state.size);
        if (state.priceMin) params.set('price_min', state.priceMin);
        if (state.priceMax) params.set('price_max', state.priceMax);

        fetch('/client/shop/api/products?' + params.toString())
            .then(function (res) { return res.json(); })
            .then(function (data) {
                state.loading = false;
                if (els.loading) els.loading.style.display = 'none';
                if (els.grid) els.grid.style.opacity = '1';

                var products = data.products || [];
                var total = data.total || 0;
                var pages = data.pages || 1;
                var current = data.current_page || 1;

                // Results count
                if (els.resultsCount) {
                    els.resultsCount.textContent = total + ' produkt' + (total === 1 ? '' : 'ów');
                }

                // Grid
                if (els.grid) {
                    if (products.length > 0) {
                        els.grid.innerHTML = products.map(renderCard).join('');
                        els.grid.style.display = '';
                    } else {
                        els.grid.innerHTML = '';
                        els.grid.style.display = 'none';
                    }
                }

                // Empty state
                if (els.empty) {
                    els.empty.style.display = products.length === 0 ? 'flex' : 'none';
                }

                // Pagination
                renderPagination(current, pages);
                pushUrlParams();
            })
            .catch(function (err) {
                state.loading = false;
                if (els.loading) els.loading.style.display = 'none';
                if (els.grid) els.grid.style.opacity = '1';
                console.error('Shop fetch error:', err);
                if (window.Toast) window.Toast.show('Blad ladowania produktow', 'error');
            });
    }

    // ---- Fetch filters (categories, sizes, price range) ----
    function fetchFilters() {
        fetch('/client/shop/api/filters')
            .then(function (res) { return res.json(); })
            .then(function (data) {
                // Categories
                if (els.categoryOptions && data.categories) {
                    els.categoryOptions.innerHTML = data.categories.map(function (cat) {
                        var active = state.category === cat ? ' active' : '';
                        return '<button type="button" class="filter-option-btn' + active + '" data-category="' + esc(cat) + '">' + esc(cat) + '</button>';
                    }).join('');
                }

                // Sizes
                if (els.sizeOptions && data.sizes) {
                    els.sizeOptions.innerHTML = data.sizes.map(function (sz) {
                        var active = state.size === sz ? ' active' : '';
                        return '<button type="button" class="filter-option-btn' + active + '" data-size="' + esc(sz) + '">' + esc(sz) + '</button>';
                    }).join('');
                }

                // Price range sliders
                var pMin = Math.floor(data.price_min || 0);
                var pMax = Math.ceil(data.price_max || 1000);
                if (els.priceMin) {
                    els.priceMin.min = pMin;
                    els.priceMin.max = pMax;
                    els.priceMin.value = state.priceMin || pMin;
                }
                if (els.priceMax) {
                    els.priceMax.min = pMin;
                    els.priceMax.max = pMax;
                    els.priceMax.value = state.priceMax || pMax;
                }
                updatePriceLabels();
            })
            .catch(function (err) {
                console.error('Filters fetch error:', err);
            });
    }

    // ---- Category click (immediate) ----
    if (els.categoryOptions) {
        els.categoryOptions.addEventListener('click', function (e) {
            var btn = e.target.closest('.filter-option-btn');
            if (!btn) return;

            // Toggle: if already active, deselect
            var isActive = btn.classList.contains('active');
            els.categoryOptions.querySelectorAll('.filter-option-btn').forEach(function (b) {
                b.classList.remove('active');
            });

            if (isActive) {
                state.category = '';
            } else {
                btn.classList.add('active');
                state.category = btn.getAttribute('data-category') || '';
            }

            state.page = 1;
            fetchProducts();
        });
    }

    // ---- Size toggle (no immediate fetch) ----
    if (els.sizeOptions) {
        els.sizeOptions.addEventListener('click', function (e) {
            var btn = e.target.closest('.filter-option-btn');
            if (!btn) return;

            // Toggle active
            var isActive = btn.classList.contains('active');
            els.sizeOptions.querySelectorAll('.filter-option-btn').forEach(function (b) {
                b.classList.remove('active');
            });

            if (!isActive) {
                btn.classList.add('active');
            }
        });
    }

    // ---- Apply filters button (price + size) ----
    if (els.applyBtn) {
        els.applyBtn.addEventListener('click', function () {
            // Read size
            var activeSize = els.sizeOptions ? els.sizeOptions.querySelector('.filter-option-btn.active') : null;
            state.size = activeSize ? activeSize.getAttribute('data-size') || '' : '';

            // Read price
            state.priceMin = els.priceMin ? els.priceMin.value.trim() : '';
            state.priceMax = els.priceMax ? els.priceMax.value.trim() : '';

            state.page = 1;
            fetchProducts();

            // Close mobile filters
            if (els.filters) els.filters.classList.remove('open');
        });
    }

    // ---- Clear filters ----
    function clearAllFilters() {
        state.search = '';
        state.category = '';
        state.size = '';
        state.priceMin = '';
        state.priceMax = '';
        state.sort = 'newest';
        state.page = 1;

        if (els.searchInput) els.searchInput.value = '';
        if (els.sortSelect) els.sortSelect.value = 'newest';
        if (els.priceMin) els.priceMin.value = '';
        if (els.priceMax) els.priceMax.value = '';

        // Remove active from filter buttons
        if (els.categoryOptions) {
            els.categoryOptions.querySelectorAll('.filter-option-btn').forEach(function (b) {
                b.classList.remove('active');
            });
        }
        if (els.sizeOptions) {
            els.sizeOptions.querySelectorAll('.filter-option-btn').forEach(function (b) {
                b.classList.remove('active');
            });
        }

        fetchProducts();
    }

    if (els.clearBtn) els.clearBtn.addEventListener('click', clearAllFilters);
    if (els.emptyClearBtn) els.emptyClearBtn.addEventListener('click', clearAllFilters);

    // ---- Search ----
    if (els.searchBtn) {
        els.searchBtn.addEventListener('click', function () {
            state.search = els.searchInput ? els.searchInput.value.trim() : '';
            state.page = 1;
            fetchProducts();
        });
    }

    if (els.searchInput) {
        els.searchInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                state.search = els.searchInput.value.trim();
                state.page = 1;
                fetchProducts();
            }
        });
    }

    // ---- Sort ----
    if (els.sortSelect) {
        els.sortSelect.addEventListener('change', function () {
            state.sort = els.sortSelect.value;
            state.page = 1;
            fetchProducts();
        });
    }

    // ---- Pagination (event delegation) ----
    if (els.pagination) {
        els.pagination.addEventListener('click', function (e) {
            var btn = e.target.closest('.shop-page-btn');
            if (!btn) return;
            var page = parseInt(btn.getAttribute('data-page'), 10);
            if (isNaN(page) || page === state.page) return;

            state.page = page;
            fetchProducts();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }

    // ---- Add to cart (event delegation on grid) ----
    if (els.grid) {
        els.grid.addEventListener('click', function (e) {
            var btn = e.target.closest('.shop-product-add-btn');
            if (!btn) return;
            e.preventDefault();
            e.stopPropagation();

            var productId = btn.getAttribute('data-product-id');
            if (!productId) return;

            btn.disabled = true;
            btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16" class="spin-icon"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>';

            fetch('/client/shop/api/cart/add', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify({ product_id: parseInt(productId, 10), quantity: 1 })
            })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                btn.disabled = false;
                btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 002 1.61h9.72a2 2 0 002-1.61L23 6H6"/></svg>';

                if (data.success) {
                    if (window.Toast) window.Toast.show('Dodano do koszyka', 'success');
                    if (data.cart_count != null) updateCartBadge(data.cart_count);
                } else {
                    if (window.Toast) window.Toast.show(data.error || 'Nie udalo sie dodac do koszyka', 'error');
                }
            })
            .catch(function () {
                btn.disabled = false;
                btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 002 1.61h9.72a2 2 0 002-1.61L23 6H6"/></svg>';
                if (window.Toast) window.Toast.show('Blad polaczenia', 'error');
            });
        });
    }

    // ---- Mobile filters toggle ----
    if (els.filtersToggle) {
        els.filtersToggle.addEventListener('click', function () {
            if (els.filters) els.filters.classList.toggle('open');
        });
    }

    if (els.filtersMobileClose) {
        els.filtersMobileClose.addEventListener('click', function () {
            if (els.filters) els.filters.classList.remove('open');
        });
    }

    // ---- Init ----
    readUrlParams();
    fetchFilters();
    fetchProducts();

})();
