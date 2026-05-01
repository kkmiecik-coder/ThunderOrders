/**
 * Offer Extra-Order Wizard
 * Pozwala adminowi/modowi dodać ręczne zamówienie do zamkniętej strony PRE-ORDER.
 */
(function () {
    'use strict';

    var URLS = window.EXTRA_ORDER_URLS;
    if (!URLS) return;

    var modal = document.getElementById('extraOrderModal');
    var openBtn = document.getElementById('extraOrderBtn');
    var closeBtns = document.querySelectorAll('[data-close-extra-order]');
    var nextBtn = document.getElementById('extraOrderNextBtn');
    var backBtn = document.getElementById('extraOrderBackBtn');
    var submitBtn = document.getElementById('extraOrderSubmitBtn');

    var userSearchInput = document.getElementById('extraOrderUserSearch');
    var userResults = document.getElementById('extraOrderUserResults');
    var selectedUserBox = document.getElementById('extraOrderSelectedUser');
    var userSearchGroup = userSearchInput.closest('.user-search-group');
    var productsList = document.getElementById('extraOrderProductsList');
    var summaryBox = document.getElementById('extraOrderSummary');
    var noteInput = document.getElementById('extraOrderNote');

    var state = {
        step: 1,
        selectedUser: null,
        products: [],
        bonuses: [],
        cart: {},
        bonusCart: {},
        searchTimer: null,
        productsLoaded: false,
    };

    function getCsrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) return meta.getAttribute('content');
        var match = document.cookie.match(/csrf_token=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    function escapeHtml(s) {
        if (s == null) return '';
        return String(s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function showToast(msg, type) {
        if (window.Toast && typeof window.Toast.show === 'function') {
            window.Toast.show(msg, type || 'info');
        } else {
            alert(msg);
        }
    }

    function openModal() {
        resetWizard();
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
        setTimeout(function () { userSearchInput && userSearchInput.focus(); }, 100);
    }

    function closeModal() {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }

    function resetWizard() {
        state.step = 1;
        state.selectedUser = null;
        state.cart = {};
        state.bonusCart = {};
        state.productsLoaded = false;
        userSearchInput.value = '';
        userResults.innerHTML = '';
        selectedUserBox.style.display = 'none';
        selectedUserBox.innerHTML = '';
        productsList.innerHTML = '<div class="loading-spinner">Ładowanie produktów...</div>';
        summaryBox.innerHTML = '';
        noteInput.value = '';
        if (userSearchGroup) userSearchGroup.style.display = '';
        updateStepUI();
    }

    function updateStepUI() {
        document.querySelectorAll('.wizard-pane').forEach(function (pane) {
            pane.classList.toggle('wizard-pane-active', pane.dataset.step === String(state.step));
        });
        document.querySelectorAll('.wizard-step').forEach(function (el) {
            var n = Number(el.dataset.stepIndicator);
            el.classList.toggle('wizard-step-active', n === state.step);
            el.classList.toggle('wizard-step-done', n < state.step);
        });
        backBtn.style.display = state.step > 1 ? '' : 'none';
        nextBtn.style.display = state.step < 3 ? '' : 'none';
        submitBtn.style.display = state.step === 3 ? '' : 'none';
        validateStep();
    }

    function validateStep() {
        if (state.step === 1) {
            nextBtn.disabled = !state.selectedUser;
        } else if (state.step === 2) {
            var ok = hasItemsInCart()
                && getMissingSizeProductIds().length === 0
                && getMissingSizeBonusIds().length === 0;
            nextBtn.disabled = !ok;
            updateSizeValidationUI();
        } else {
            nextBtn.disabled = true;
        }
    }

    function hasItemsInCart() {
        return Object.keys(state.cart).some(function (k) { return state.cart[k].quantity > 0; });
    }

    function getMissingSizeProductIds() {
        var missing = [];
        Object.values(state.cart).forEach(function (item) {
            if (item.quantity <= 0) return;
            var prod = state.products.find(function (p) { return p.product_id === item.product_id; });
            if (prod && prod.sizes && prod.sizes.length && !item.selected_size) {
                missing.push(item.product_id);
            }
        });
        return missing;
    }

    function getMissingSizeBonusIds() {
        var missing = [];
        Object.values(state.bonusCart).forEach(function (item) {
            if (item.quantity <= 0) return;
            var bonus = state.bonuses.find(function (b) { return b.bonus_id === item.bonus_id; });
            if (bonus && bonus.sizes && bonus.sizes.length && !item.selected_size) {
                missing.push(item.bonus_id);
            }
        });
        return missing;
    }

    function updateSizeValidationUI() {
        var missingProducts = getMissingSizeProductIds();
        productsList.querySelectorAll('.extra-order-product-row').forEach(function (row) {
            var pid = Number(row.dataset.productId);
            var sel = row.querySelector('.product-size-select');
            if (missingProducts.indexOf(pid) !== -1) {
                row.classList.add('row-error');
                if (sel) sel.classList.add('input-error');
            } else {
                row.classList.remove('row-error');
                if (sel) sel.classList.remove('input-error');
            }
        });
        var missingBonuses = getMissingSizeBonusIds();
        productsList.querySelectorAll('.extra-order-bonus-row').forEach(function (row) {
            var bid = Number(row.dataset.bonusId);
            var sel = row.querySelector('.bonus-size-select');
            if (missingBonuses.indexOf(bid) !== -1) {
                row.classList.add('row-error');
                if (sel) sel.classList.add('input-error');
            } else {
                row.classList.remove('row-error');
                if (sel) sel.classList.remove('input-error');
            }
        });
    }

    // ===== Step 1: User search =====

    function searchUsers(q) {
        if (q.length < 2) {
            userResults.innerHTML = '';
            return;
        }
        fetch(URLS.users + '?q=' + encodeURIComponent(q), {
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                renderUserResults(data.users || []);
            })
            .catch(function () {
                userResults.innerHTML = '<div class="user-search-empty">Błąd podczas wyszukiwania.</div>';
            });
    }

    function renderUserResults(users) {
        if (state.selectedUser) return;
        if (!users.length) {
            userResults.innerHTML = '<div class="user-search-empty">Nie znaleziono klientów.</div>';
            return;
        }
        var html = users.map(function (u) {
            return '<div class="user-search-item" data-user-id="' + u.id + '">' +
                '<div class="user-search-name">' + escapeHtml(u.full_name) + '</div>' +
                '<div class="user-search-email">' + escapeHtml(u.email) + '</div>' +
                '</div>';
        }).join('');
        userResults.innerHTML = html;

        userResults.querySelectorAll('.user-search-item').forEach(function (item) {
            item.addEventListener('click', function () {
                var uid = Number(item.dataset.userId);
                var user = users.find(function (u) { return u.id === uid; });
                selectUser(user);
            });
        });
    }

    function selectUser(user) {
        state.selectedUser = user;
        clearTimeout(state.searchTimer);
        userSearchInput.value = '';
        userResults.innerHTML = '';
        if (userSearchGroup) userSearchGroup.style.display = 'none';
        selectedUserBox.innerHTML =
            '<div class="selected-user-info">' +
            '<strong>' + escapeHtml(user.full_name) + '</strong>' +
            '<span>' + escapeHtml(user.email) + '</span>' +
            '</div>' +
            '<button type="button" class="btn-link" id="extraOrderUserChange">Zmień</button>';
        selectedUserBox.style.display = '';

        document.getElementById('extraOrderUserChange').addEventListener('click', function () {
            state.selectedUser = null;
            selectedUserBox.style.display = 'none';
            selectedUserBox.innerHTML = '';
            if (userSearchGroup) userSearchGroup.style.display = '';
            validateStep();
            userSearchInput.focus();
        });

        validateStep();
    }

    // ===== Step 2: Products =====

    function loadProducts() {
        if (state.productsLoaded) return;
        fetch(URLS.products, {
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                state.products = data.products || [];
                state.bonuses = data.bonuses || [];
                state.productsLoaded = true;
                renderProducts();
            })
            .catch(function () {
                productsList.innerHTML = '<div class="user-search-empty">Nie udało się pobrać produktów.</div>';
            });
    }

    function renderProducts() {
        var html = '';

        if (state.products.length) {
            html += '<div class="extra-order-section-label">Produkty</div>';
            html += state.products.map(function (p) {
                var sizesHTML = '';
                if (p.sizes && p.sizes.length) {
                    sizesHTML = '<select class="form-input product-size-select" data-product-id="' + p.product_id + '">' +
                        '<option value="">— rozmiar —</option>' +
                        p.sizes.map(function (s) {
                            return '<option value="' + escapeHtml(s.name) + '">' + escapeHtml(s.name) + '</option>';
                        }).join('') +
                        '</select>';
                }
                return '<div class="extra-order-product-row" data-product-id="' + p.product_id + '">' +
                    '<div class="extra-order-product-info">' +
                    '<div class="extra-order-product-name">' + escapeHtml(p.name) + '</div>' +
                    '<div class="extra-order-product-meta">' +
                    '<span>SKU: ' + escapeHtml(p.sku || '-') + '</span>' +
                    '<span>' + p.price.toFixed(2) + ' PLN</span>' +
                    '</div>' +
                    '</div>' +
                    '<div class="extra-order-product-controls">' +
                    sizesHTML +
                    '<input type="number" class="form-input product-qty-input" min="0" value="0" data-product-id="' + p.product_id + '" data-price="' + p.price + '">' +
                    '</div>' +
                    '</div>';
            }).join('');
        } else {
            html += '<div class="user-search-empty">Brak produktów na tej stronie.</div>';
        }

        if (state.bonuses.length) {
            html += '<div class="extra-order-section-label">Bonusy (opcjonalnie, gratis)</div>';
            html += state.bonuses.map(function (b) {
                var sizesHTML = '';
                if (b.sizes && b.sizes.length) {
                    sizesHTML = '<select class="form-input bonus-size-select" data-bonus-id="' + b.bonus_id + '">' +
                        '<option value="">— rozmiar —</option>' +
                        b.sizes.map(function (s) {
                            return '<option value="' + escapeHtml(s.name) + '">' + escapeHtml(s.name) + '</option>';
                        }).join('') +
                        '</select>';
                }
                return '<div class="extra-order-bonus-row" data-bonus-id="' + b.bonus_id + '">' +
                    '<div class="extra-order-product-info">' +
                    '<div class="extra-order-product-name">🎁 ' + escapeHtml(b.name) + '</div>' +
                    '<div class="extra-order-product-meta">' +
                    '<span>SKU: ' + escapeHtml(b.sku || '-') + '</span>' +
                    '<span>cena: 0.00 PLN</span>' +
                    '</div>' +
                    '</div>' +
                    '<div class="extra-order-product-controls">' +
                    sizesHTML +
                    '<input type="number" class="form-input bonus-qty-input" min="0" value="0" data-bonus-id="' + b.bonus_id + '">' +
                    '</div>' +
                    '</div>';
            }).join('');
        }

        productsList.innerHTML = html;

        productsList.querySelectorAll('.product-qty-input').forEach(function (inp) {
            inp.addEventListener('input', function () {
                var pid = inp.dataset.productId;
                var qty = Math.max(0, parseInt(inp.value, 10) || 0);
                var prod = state.products.find(function (p) { return String(p.product_id) === pid; });
                var row = inp.closest('.extra-order-product-row');
                var sizeSel = row ? row.querySelector('.product-size-select') : null;
                var currentSize = (state.cart[pid] && state.cart[pid].selected_size)
                    || (sizeSel && sizeSel.value)
                    || null;
                if (qty > 0) {
                    state.cart[pid] = {
                        product_id: Number(pid),
                        quantity: qty,
                        name: prod ? prod.name : '',
                        price: prod ? prod.price : 0,
                        selected_size: currentSize,
                    };
                } else {
                    delete state.cart[pid];
                }
                validateStep();
            });
        });

        productsList.querySelectorAll('.product-size-select').forEach(function (sel) {
            sel.addEventListener('change', function () {
                var pid = sel.dataset.productId;
                if (state.cart[pid]) {
                    state.cart[pid].selected_size = sel.value || null;
                }
                validateStep();
            });
        });

        // Bonus inputs
        productsList.querySelectorAll('.bonus-qty-input').forEach(function (inp) {
            inp.addEventListener('input', function () {
                var bid = inp.dataset.bonusId;
                var qty = Math.max(0, parseInt(inp.value, 10) || 0);
                var bonus = state.bonuses.find(function (b) { return String(b.bonus_id) === bid; });
                var row = inp.closest('.extra-order-bonus-row');
                var sizeSel = row ? row.querySelector('.bonus-size-select') : null;
                var currentSize = (state.bonusCart[bid] && state.bonusCart[bid].selected_size)
                    || (sizeSel && sizeSel.value)
                    || null;
                if (qty > 0 && bonus) {
                    state.bonusCart[bid] = {
                        bonus_id: Number(bid),
                        quantity: qty,
                        name: bonus.name,
                        bonus_product_id: bonus.bonus_product_id,
                        selected_size: currentSize,
                    };
                } else {
                    delete state.bonusCart[bid];
                }
                validateStep();
            });
        });

        productsList.querySelectorAll('.bonus-size-select').forEach(function (sel) {
            sel.addEventListener('change', function () {
                var bid = sel.dataset.bonusId;
                if (state.bonusCart[bid]) {
                    state.bonusCart[bid].selected_size = sel.value || null;
                }
                validateStep();
            });
        });
    }

    // ===== Step 3: Summary =====

    function renderSummary() {
        if (!state.selectedUser) return;
        var items = Object.values(state.cart).filter(function (i) { return i.quantity > 0; });
        var bonusItems = Object.values(state.bonusCart).filter(function (i) { return i.quantity > 0; });
        var total = items.reduce(function (sum, i) { return sum + (i.price * i.quantity); }, 0);

        var rows = items.map(function (i) {
            var sizeStr = i.selected_size ? ' (rozm. ' + escapeHtml(i.selected_size) + ')' : '';
            return '<tr>' +
                '<td>' + escapeHtml(i.name) + sizeStr + '</td>' +
                '<td class="text-center">' + i.quantity + '</td>' +
                '<td class="text-right">' + (i.price * i.quantity).toFixed(2) + ' PLN</td>' +
                '</tr>';
        }).join('');

        var bonusHTML = '';
        if (bonusItems.length) {
            var bonusRows = bonusItems.map(function (b) {
                var sizeStr = b.selected_size ? ' (rozm. ' + escapeHtml(b.selected_size) + ')' : '';
                return '<tr>' +
                    '<td>🎁 ' + escapeHtml(b.name) + sizeStr + '</td>' +
                    '<td class="text-center">' + b.quantity + '</td>' +
                    '<td class="text-right">gratis</td>' +
                    '</tr>';
            }).join('');
            bonusHTML =
                '<div class="summary-section">' +
                '<h3>Bonusy</h3>' +
                '<table class="summary-table">' +
                '<thead><tr><th>Produkt</th><th class="text-center">Ilość</th><th class="text-right">Cena</th></tr></thead>' +
                '<tbody>' + bonusRows + '</tbody>' +
                '</table>' +
                '</div>';
        }

        summaryBox.innerHTML =
            '<div class="summary-section">' +
            '<h3>Klient</h3>' +
            '<p><strong>' + escapeHtml(state.selectedUser.full_name) + '</strong> &middot; ' + escapeHtml(state.selectedUser.email) + '</p>' +
            '</div>' +
            '<div class="summary-section">' +
            '<h3>Produkty</h3>' +
            '<table class="summary-table">' +
            '<thead><tr><th>Produkt</th><th class="text-center">Ilość</th><th class="text-right">Wartość</th></tr></thead>' +
            '<tbody>' + rows + '</tbody>' +
            '<tfoot><tr><td colspan="2"><strong>SUMA</strong></td><td class="text-right"><strong>' + total.toFixed(2) + ' PLN</strong></td></tr></tfoot>' +
            '</table>' +
            '</div>' +
            bonusHTML;
    }

    // ===== Submit =====

    function validateBeforeSubmit() {
        // Sprawdź czy każdy produkt z cart wymagający rozmiaru ma rozmiar
        var missing = [];
        Object.values(state.cart).forEach(function (item) {
            var prod = state.products.find(function (p) { return p.product_id === item.product_id; });
            if (prod && prod.sizes && prod.sizes.length && !item.selected_size) {
                missing.push(prod.name);
            }
        });
        if (missing.length) {
            showToast('Wybierz rozmiar dla: ' + missing.join(', '), 'error');
            return false;
        }
        return true;
    }

    function submitOrder() {
        if (!validateBeforeSubmit()) return;

        submitBtn.disabled = true;
        submitBtn.textContent = 'Tworzenie...';

        var items = Object.values(state.cart).filter(function (i) { return i.quantity > 0; })
            .map(function (i) {
                return {
                    product_id: i.product_id,
                    quantity: i.quantity,
                    selected_size: i.selected_size || null,
                };
            });

        var bonuses = Object.values(state.bonusCart).filter(function (b) { return b.quantity > 0; })
            .map(function (b) {
                return {
                    bonus_id: b.bonus_id,
                    quantity: b.quantity,
                    selected_size: b.selected_size || null,
                };
            });

        fetch(URLS.create, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify({
                user_id: state.selectedUser.id,
                items: items,
                bonuses: bonuses,
                note: noteInput.value.trim() || null
            })
        })
            .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, data: j }; }); })
            .then(function (res) {
                if (!res.ok || !res.data.success) {
                    showToast(res.data.message || 'Nie udało się utworzyć zamówienia.', 'error');
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Utwórz zamówienie';
                    return;
                }
                showToast('Zamówienie ' + res.data.order_number + ' utworzone.', 'success');
                closeModal();
                setTimeout(function () { window.location.reload(); }, 800);
            })
            .catch(function () {
                showToast('Błąd sieci.', 'error');
                submitBtn.disabled = false;
                submitBtn.textContent = 'Utwórz zamówienie';
            });
    }

    // ===== Wiring =====

    if (openBtn) {
        openBtn.addEventListener('click', openModal);
    }
    closeBtns.forEach(function (b) { b.addEventListener('click', closeModal); });
    modal.addEventListener('click', function (e) {
        if (e.target === modal) closeModal();
    });

    userSearchInput.addEventListener('input', function () {
        clearTimeout(state.searchTimer);
        var q = userSearchInput.value.trim();
        state.searchTimer = setTimeout(function () { searchUsers(q); }, 250);
    });

    nextBtn.addEventListener('click', function () {
        if (state.step === 1 && state.selectedUser) {
            state.step = 2;
            loadProducts();
        } else if (state.step === 2 && hasItemsInCart()) {
            state.step = 3;
            renderSummary();
        }
        updateStepUI();
    });

    backBtn.addEventListener('click', function () {
        if (state.step > 1) state.step--;
        updateStepUI();
    });

    submitBtn.addEventListener('click', submitOrder);
})();
