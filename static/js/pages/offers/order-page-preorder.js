/**
 * Preorder Order Page - Cart without reservations
 * Simplified version of order-page.js for preorder pages
 */

// ============================================
// Google Analytics 4 — Ecommerce funnel helpers
// ============================================
function buildGaItemsFromCart() {
    return getOrderableItems().map(item => ({
        item_id: item.product_id,
        item_name: item.name,
        price: item.price,
        quantity: item.quantity,
    }));
}

// view_item_list best-effort z DOM: karty produktów, zestawy (.set-item), warianty (.variant-product)
function collectOfferItems() {
    const items = [];
    const seen = new Set();

    function readPrice(el) {
        if (!el) return 0;
        const parsed = parseFloat(el.textContent.replace(/[^\d.,]/g, '').replace(',', '.'));
        return isNaN(parsed) ? 0 : parsed;
    }

    function addFrom(selector, nameSel, priceSels) {
        document.querySelectorAll(selector).forEach(el => {
            const id = el.dataset.productId;
            if (!id || seen.has(id)) return;
            seen.add(id);
            const nameEl = el.querySelector(nameSel);
            let priceEl = null;
            for (const s of priceSels) { priceEl = el.querySelector(s); if (priceEl) break; }
            items.push({ item_id: id, item_name: nameEl ? nameEl.textContent.trim() : '', price: readPrice(priceEl), quantity: 1 });
        });
    }

    addFrom('.section-product', '.product-name', ['.product-price']);
    addFrom('.set-item[data-product-id]', '.set-item-name', ['.set-item-price', '.set-item-price-mobile']);
    addFrom('.variant-product[data-product-id]', '.variant-product-name', ['.variant-product-price']);
    return items;
}

function trackPreorderPageViewed() {
    if (typeof window.trackOfferPageView === 'function' && window.offerToken && window.offerName) {
        window.trackOfferPageView(window.offerToken, window.offerName);
    }
    if (typeof window.trackViewItemList === 'function') {
        window.trackViewItemList(collectOfferItems(), window.offerName || 'Preorder');
    }
}

// ============================================
// Set Image Toggle (shared with exclusive)
// ============================================
function toggleSetImage(el) {
    el.classList.toggle('collapsed');
    const text = el.querySelector('.expand-text');
    if (text) {
        text.textContent = el.classList.contains('collapsed') ? 'Pokaż cały obraz' : 'Zwiń obraz';
    }
}

// ============================================
// Niedostępność produktów (sekcje Sold-out / Ukryte)
// ============================================
// Mapa {product_id: 'sold_out'|'hidden'} z szablonu, aktualizowana po SocketIO.
// Klient mógł dodać produkt do koszyka, zanim admin wyłączył sekcję — taka
// pozycja zostaje widoczna w koszyku, ale wygaszona i wyłączona z zamówienia.
window.unavailableProducts = window.unavailableProducts || {};

function getUnavailableState(productId) {
    // Klucze z JSON-a są stringami, product_id w koszyku bywa liczbą
    return window.unavailableProducts[String(productId)] || null;
}

function isItemUnavailable(item) {
    return !item.is_bonus && getUnavailableState(item.product_id) !== null;
}

function unavailableLabel(state) {
    return state === 'sold_out' ? 'Sold-out' : 'Niedostępne';
}

// ============================================
// Cart State
// ============================================
let cart = [];
const CART_KEY = `preorder_cart_${window.pageToken}`;
const selectedProductSizes = {};

// ============================================
// Size Selection
// ============================================
function selectProductSize(btn) {
    const productId = btn.dataset.productId;
    const container = btn.closest('.size-selector');
    container.querySelectorAll('.size-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    selectedProductSizes[productId] = btn.dataset.sizeName;
}

function selectProductSizeDropdown(select) {
    const productId = select.dataset.productId;
    selectedProductSizes[productId] = select.value;
}

// ============================================
// Initialization
// ============================================
document.addEventListener('DOMContentLoaded', function() {
    loadCart();
    updateCartUI();
    initLightbox();
    initSectionStateSocket();

    // GA4: view_item_list + view_offer_page
    trackPreorderPageViewed();
});

// ============================================
// Cart Persistence (localStorage)
// ============================================
function loadCart() {
    try {
        const stored = localStorage.getItem(CART_KEY);
        if (stored) {
            cart = JSON.parse(stored);
        }
    } catch (e) {
        cart = [];
    }
}

function saveCart() {
    localStorage.setItem(CART_KEY, JSON.stringify(cart));
    updateCartUI();
}

// ============================================
// Quantity Controls (before adding to cart)
// ============================================
function adjustPreorderQty(btn, delta) {
    const container = btn.closest('.quantity-control');
    const input = container.querySelector('.qty-input');
    let val = parseInt(input.value) || 1;
    val = Math.max(1, val + delta);
    input.value = val;
}

// ============================================
// Add to Cart
// ============================================
function addToPreorderCart(productId, productName, price, btn) {
    // Sekcja wyłączona w międzyczasie (SocketIO) — karta mogła zostać kliknięta
    // zanim przerysowaliśmy stronę
    const unavailableState = getUnavailableState(productId);
    if (unavailableState) {
        if (typeof window.showToast === 'function') {
            window.showToast(`${productName} — ${unavailableLabel(unavailableState).toLowerCase()}.`, 'error');
        }
        return;
    }

    // Size validation
    const sizeSelector = document.querySelector(`.size-selector[data-product-id="${productId}"]`);
    if (sizeSelector && !selectedProductSizes[productId]) {
        sizeSelector.classList.add('size-required');
        setTimeout(() => sizeSelector.classList.remove('size-required'), 1500);
        return;
    }

    // Na mobile (≤640px) licznik jest w nagłówku (.product-header-controls),
    // a na desktopie w .product-controls-box — oba mają ten sam data-product-id,
    // ale ukryte (display:none) zostaje na wartości 1. Czytamy WIDOCZNE pole.
    const qtyInputs = Array.from(document.querySelectorAll(`.qty-input[data-product-id="${productId}"]`));
    const visibleQtyInput = qtyInputs.find(inp => inp.offsetParent !== null) || qtyInputs[0] || null;
    const qty = visibleQtyInput ? (parseInt(visibleQtyInput.value) || 1) : 1;

    const selectedSize = selectedProductSizes[productId] || null;
    const existing = cart.find(item => item.product_id === productId && item.selected_size === selectedSize);
    if (existing) {
        existing.quantity += qty;
    } else {
        cart.push({
            product_id: productId,
            name: productName,
            price: parseFloat(price),
            quantity: qty,
            selected_size: selectedSize
        });
    }

    // Reset wszystkich pól ilości tego produktu (mobile + desktop)
    qtyInputs.forEach(inp => { inp.value = 1; });

    // GA4: add_to_cart
    if (typeof window.trackAddToCart === 'function') {
        window.trackAddToCart(productName, productId, parseFloat(price), qty);
    }

    // Visual feedback
    const originalHTML = btn.innerHTML;
    btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><path d="M13.854 3.646a.5.5 0 0 1 0 .708l-7 7a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6.5 10.293l6.646-6.647a.5.5 0 0 1 .708 0z"/></svg> Dodano!';
    btn.classList.add('added');
    setTimeout(() => {
        btn.innerHTML = originalHTML;
        btn.classList.remove('added');
    }, 1500);

    saveCart();
}

// ============================================
// Cart Item Controls
// ============================================
function updateCartItemQty(productId, delta) {
    const item = cart.find(i => i.product_id === productId);
    if (!item) return;

    item.quantity += delta;
    if (item.quantity <= 0) {
        cart = cart.filter(i => i.product_id !== productId);
    }
    saveCart();
}

function removeCartItem(productId) {
    cart = cart.filter(i => i.product_id !== productId);
    saveCart();
}

// ============================================
// Cart Calculations
// ============================================
function getOrderableItems() {
    return cart.filter(i => !i.is_bonus && !isItemUnavailable(i));
}

function getCartTotal() {
    return getOrderableItems().reduce((sum, item) => sum + (item.price * item.quantity), 0);
}

function getCartItemCount() {
    return getOrderableItems().reduce((sum, item) => sum + item.quantity, 0);
}

// ============================================
// Bonus Evaluation
// ============================================
function evaluatePreorderBonuses() {
    // Remove old bonus items
    cart = cart.filter(i => !i.is_bonus);

    const config = window.bonusesConfig;
    if (!config || typeof config !== 'object') return;

    const regularItems = getOrderableItems();
    const totalAmount = regularItems.reduce((sum, i) => sum + (i.price * i.quantity), 0);
    const totalQty = regularItems.reduce((sum, i) => sum + i.quantity, 0);

    // Iterate over all bonus sections
    for (const [sectionId, bonuses] of Object.entries(config)) {
        for (const bonus of bonuses) {
            if (bonus.is_exhausted) continue;

            let earned = 0;

            if (bonus.trigger_type === 'buy_products' && bonus.required_products) {
                const ratios = bonus.required_products.map(rp => {
                    const bought = regularItems
                        .filter(i => i.product_id === rp.product_id)
                        .reduce((s, i) => s + i.quantity, 0);
                    return rp.min_quantity > 0 ? Math.floor(bought / rp.min_quantity) : bought;
                });
                earned = ratios.length > 0 ? Math.min(...ratios) : 0;
                if (!bonus.repeatable) earned = Math.min(earned, 1);

            } else if (bonus.trigger_type === 'price_threshold' && bonus.threshold_value) {
                if (totalAmount >= bonus.threshold_value) {
                    earned = bonus.repeatable ? Math.floor(totalAmount / bonus.threshold_value) : 1;
                }

            } else if (bonus.trigger_type === 'quantity_threshold' && bonus.threshold_value) {
                if (totalQty >= bonus.threshold_value) {
                    earned = bonus.repeatable ? Math.floor(totalQty / bonus.threshold_value) : 1;
                }
            }

            // Apply max_available
            if (earned > 0 && bonus.max_available) {
                earned = Math.min(earned, bonus.max_available - (bonus.already_claimed || 0));
            }

            if (earned > 0) {
                cart.push({
                    product_id: bonus.bonus_product_id,
                    name: bonus.bonus_product_name + ' (GRATIS)',
                    price: 0,
                    quantity: bonus.bonus_quantity * earned,
                    is_bonus: true
                });
            }
        }
    }
}

// ============================================
// Cart UI Update
// ============================================
function updateCartUI() {
    evaluatePreorderBonuses();
    const total = getCartTotal();
    const count = getCartItemCount();

    // Desktop sidebar
    const cartCountEl = document.getElementById('cartCount');
    const cartItemsEl = document.getElementById('cartItems');
    const cartTotalEl = document.getElementById('cartTotal');
    const submitOrderBtn = document.getElementById('submitOrderBtn');

    if (cartCountEl) cartCountEl.textContent = count;
    if (cartTotalEl) cartTotalEl.textContent = total.toFixed(2) + ' PLN';
    if (submitOrderBtn) submitOrderBtn.disabled = count === 0;

    // Mobile bottom bar
    const checkoutBottomCount = document.getElementById('checkoutBottomCount');
    const checkoutBottomTotal = document.getElementById('checkoutBottomTotal');
    const checkoutBottomBtn = document.getElementById('checkoutBottomBtn');

    if (checkoutBottomCount) {
        checkoutBottomCount.textContent = count > 0 ? (count + ' szt.') : 'Koszyk pusty';
    }
    if (checkoutBottomTotal) checkoutBottomTotal.textContent = total.toFixed(2) + ' PLN';
    if (checkoutBottomBtn) checkoutBottomBtn.disabled = count === 0;

    // Render cart items
    if (cartItemsEl) {
        if (cart.length === 0) {
            cartItemsEl.innerHTML = '<div class="cart-empty"><p>Koszyk jest pusty</p></div>';
        } else {
            cartItemsEl.innerHTML = cart.map(item => {
                if (item.is_bonus) {
                    return `
                        <div class="cart-item cart-item-bonus">
                            <div class="cart-item-info">
                                <span class="cart-item-name">🎁 ${escapeHtml(item.name)}</span>
                                <span class="cart-item-price">GRATIS</span>
                            </div>
                            <div class="cart-item-controls">
                                <span class="cart-item-qty">${item.quantity} szt.</span>
                            </div>
                        </div>
                    `;
                }
                const sizeBadge = item.selected_size ? ` <span class="size-badge">${escapeHtml(item.selected_size)}</span>` : '';
                const unavailableState = getUnavailableState(item.product_id);

                // Pozycja z wyłączonej sekcji: zostaje widoczna (klient wie, co odpadło),
                // ale z wyzerowaną ilością i kwotą oraz bez kontrolek ilości.
                if (unavailableState) {
                    return `
                        <div class="cart-item is-unavailable">
                            <div class="cart-item-info">
                                <span class="cart-item-name">${escapeHtml(item.name)}${sizeBadge}</span>
                                <span class="cart-item-price">0.00 PLN</span>
                                <span class="cart-item-unavailable-note">${escapeHtml(unavailableLabel(unavailableState))}</span>
                            </div>
                            <div class="cart-item-controls">
                                <span class="cart-item-qty">0 szt.</span>
                                <button type="button" class="cart-item-remove" onclick="removeCartItem(${item.product_id})" aria-label="Usuń z koszyka">
                                    <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                                        <path d="M2.146 2.854a.5.5 0 1 1 .708-.708L8 7.293l5.146-5.147a.5.5 0 0 1 .708.708L8.707 8l5.147 5.146a.5.5 0 0 1-.708.708L8 8.707l-5.146 5.147a.5.5 0 0 1-.708-.708L7.293 8 2.146 2.854Z"/>
                                    </svg>
                                </button>
                            </div>
                        </div>
                    `;
                }

                return `
                    <div class="cart-item">
                        <div class="cart-item-info">
                            <span class="cart-item-name">${escapeHtml(item.name)}${sizeBadge}</span>
                            <span class="cart-item-price">${item.price.toFixed(2)} PLN</span>
                        </div>
                        <div class="cart-item-controls">
                            <button type="button" class="qty-btn qty-minus" onclick="updateCartItemQty(${item.product_id}, -1)">-</button>
                            <span class="cart-item-qty">${item.quantity}</span>
                            <button type="button" class="qty-btn qty-plus" onclick="updateCartItemQty(${item.product_id}, 1)">+</button>
                            <button type="button" class="cart-item-remove" onclick="removeCartItem(${item.product_id})">
                                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                                    <path d="M2.146 2.854a.5.5 0 1 1 .708-.708L8 7.293l5.146-5.147a.5.5 0 0 1 .708.708L8.707 8l5.147 5.146a.5.5 0 0 1-.708.708L8 8.707l-5.146 5.147a.5.5 0 0 1-.708-.708L7.293 8 2.146 2.854Z"/>
                                </svg>
                            </button>
                        </div>
                    </div>
                `;
            }).join('');
        }
    }
}

// ============================================
// Mobile Cart Toggle
// ============================================
function toggleMobileCart() {
    const sidebar = document.getElementById('cartSidebar');
    const overlay = document.getElementById('cartMobileOverlay');
    if (sidebar && overlay) {
        sidebar.classList.toggle('mobile-open');
        overlay.classList.toggle('active');
    }
}

// ============================================
// Order Modal
// ============================================
function openOrderModal() {
    if (getOrderableItems().length === 0) return;
    const modal = document.getElementById('orderModal');
    if (modal) modal.classList.add('active');

    // GA4: begin_checkout
    if (typeof window.trackBeginCheckout === 'function') {
        const value = getOrderableItems().reduce((sum, item) => sum + (item.quantity * item.price), 0);
        window.trackBeginCheckout(buildGaItemsFromCart(), value);
    }
}

function closeOrderModal() {
    const modal = document.getElementById('orderModal');
    if (modal) modal.classList.remove('active');
}

// ============================================
// Submit Order
// ============================================
async function submitOrder() {
    if (cart.length === 0) return;

    // Do zamówienia idą wyłącznie pozycje z sekcji aktywnych — pozycje sold-out
    // zostają w koszyku widoczne, ale nie trafiają do payloadu
    const orderableItems = getOrderableItems();
    if (orderableItems.length === 0) {
        if (typeof window.showToast === 'function') {
            window.showToast('Produkty w koszyku nie są już dostępne.', 'error');
        }
        return;
    }

    const noteEl = document.getElementById('orderNote');
    const orderNote = noteEl ? noteEl.value.trim() : '';

    const submitBtn = document.querySelector('#orderModal .offer-btn-submit');
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.querySelector('span').textContent = 'Składanie zamówienia...';
    }

    try {
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
        const response = await fetch(window.placeOrderUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({
                cart_items: orderableItems.map(item => ({
                    product_id: item.product_id,
                    quantity: item.quantity,
                    selected_size: item.selected_size || null
                })),
                order_note: orderNote
            })
        });

        const data = await response.json();

        if (data.success) {
            // Clear cart
            cart = [];
            localStorage.removeItem(CART_KEY);

            // Close order modal
            closeOrderModal();

            // Show success modal
            const successModal = document.getElementById('successModal');
            const orderNumberEl = document.getElementById('successOrderNumber');
            const orderTotalEl = document.getElementById('successOrderTotal');

            if (orderNumberEl) orderNumberEl.textContent = data.order_number || '-';
            if (orderTotalEl) orderTotalEl.textContent = (data.total_amount ? data.total_amount.toFixed(2) : '0.00') + ' PLN';
            if (successModal) successModal.classList.add('active');

            updateCartUI();

            // Track with GA4 (purchase z items[] z backendu — koszyk jest już wyczyszczony)
            if (typeof window.trackOrderPlaced === 'function') {
                window.trackOrderPlaced(data.order_number, data.total_amount, data.items || [], 'preorder');
            }
        } else {
            alert(data.message || data.error || 'Wystąpił błąd podczas składania zamówienia.');
        }
    } catch (error) {
        console.error('Order error:', error);
        alert('Wystąpił błąd połączenia. Spróbuj ponownie.');
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            const spanEl = submitBtn.querySelector('span');
            if (spanEl) spanEl.textContent = 'Potwierdź zamówienie';
        }
    }
}

// ============================================
// Success / Redirect
// ============================================
function closeSuccessAndContinue() {
    const modal = document.getElementById('successModal');
    if (modal) modal.classList.remove('active');
}

function redirectToOrders() {
    if (window.redirectAfterOrderUrl && window.redirectAfterOrderUrl !== '#') {
        window.location.href = window.redirectAfterOrderUrl;
    } else {
        const modal = document.getElementById('successModal');
        if (modal) modal.classList.remove('active');
    }
}

// ============================================
// Login Modal
// ============================================
function openLoginModal() {
    const modal = document.getElementById('loginModal');
    if (modal) modal.classList.add('active');
}

function closeLoginModal() {
    const modal = document.getElementById('loginModal');
    if (modal) modal.classList.remove('active');
}

async function handleLogin(e) {
    e.preventDefault();
    const email = document.getElementById('loginEmail').value;
    const password = document.getElementById('loginPassword').value;
    const errorEl = document.getElementById('loginError');
    const overlay = document.getElementById('loginOverlay');

    if (overlay) overlay.style.display = 'flex';
    if (errorEl) errorEl.style.display = 'none';

    try {
        const response = await fetch('/auth/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': 'application/json'
            },
            body: new URLSearchParams({
                'email': email,
                'password': password,
                'remember_me': 'on'
            })
        });
        const data = await response.json();

        if (data.success) {
            window.location.reload();
        } else {
            if (errorEl) {
                errorEl.textContent = data.error || 'Nieprawidłowe dane logowania';
                errorEl.style.display = 'block';
            }
        }
    } catch (err) {
        if (errorEl) {
            errorEl.textContent = 'Błąd połączenia';
            errorEl.style.display = 'block';
        }
    } finally {
        if (overlay) overlay.style.display = 'none';
    }
}

function togglePasswordVisibility() {
    const pwd = document.getElementById('loginPassword');
    const showIcon = document.querySelector('.eye-show');
    const hideIcon = document.querySelector('.eye-hide');

    if (pwd.type === 'password') {
        pwd.type = 'text';
        if (showIcon) showIcon.style.display = 'none';
        if (hideIcon) hideIcon.style.display = 'block';
    } else {
        pwd.type = 'password';
        if (showIcon) showIcon.style.display = 'block';
        if (hideIcon) hideIcon.style.display = 'none';
    }
}

function handleLogout() {
    window.location.href = '/auth/logout';
}

// ============================================
// Image Lightbox
// ============================================
function initLightbox() {
    // Lightbox is handled by onclick attributes in template
}

function openLightbox(wrapper) {
    const img = wrapper.querySelector('img');
    if (!img) return;

    const lightbox = document.getElementById('imageLightbox');
    const lightboxImg = document.getElementById('lightboxImage');
    if (!lightbox || !lightboxImg) return;

    lightboxImg.src = img.dataset.fullSrc || img.src;
    lightbox.classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeLightbox() {
    const lightbox = document.getElementById('imageLightbox');
    if (lightbox) {
        lightbox.classList.remove('active');
        document.body.style.overflow = '';
    }
}

// Close lightbox on Escape
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeLightbox();
        closeOrderModal();
        closeLoginModal();
        const successModal = document.getElementById('successModal');
        if (successModal) successModal.classList.remove('active');
    }
});

// ============================================
// Live update stanów sekcji (SocketIO)
// ============================================
// Admin przełącza sekcję w Page Builderze na Aktywna / Sold-out / Ukryta —
// otwarte strony aktualizują się bez przeładowania.

/**
 * Buduje nakładkę "Sold-out". Markup musi odpowiadać
 * templates/offers/_sold_out_overlay.html, żeby sekcja wyglądała identycznie
 * niezależnie od tego, czy stan przyszedł z serwera przy renderze, czy live.
 */
function buildSoldOutOverlay() {
    const overlay = document.createElement('div');
    overlay.className = 'sold-out-overlay';
    overlay.setAttribute('aria-hidden', 'true');

    const badge = document.createElement('span');
    badge.className = 'sold-out-badge';
    badge.textContent = 'Sold-out';
    overlay.appendChild(badge);

    return overlay;
}

function applySectionState(sectionEl, state) {
    if (sectionEl.dataset.displayState === state) return;
    sectionEl.dataset.displayState = state;

    if (state === 'hidden') {
        sectionEl.remove();
        return;
    }

    const isSoldOut = state === 'sold_out';
    sectionEl.classList.toggle('is-sold-out', isSoldOut);

    const existingOverlay = sectionEl.querySelector(':scope > .sold-out-overlay');
    if (isSoldOut && !existingOverlay) {
        sectionEl.prepend(buildSoldOutOverlay());
    } else if (!isSoldOut && existingOverlay) {
        existingOverlay.remove();
    }
}

function handleSectionStatesUpdate(data) {
    if (!data || !data.states) return;

    // Sekcja, która wróciła z "Ukryta" do widocznych, nie istnieje w DOM —
    // jej HTML trzeba pobrać z serwera, więc odświeżamy stronę.
    const domSectionIds = new Set(
        Array.from(document.querySelectorAll('.section[data-section-id]'))
            .map(el => parseInt(el.dataset.sectionId))
    );
    const missingVisible = (data.visible_section_ids || [])
        .some(id => !domSectionIds.has(id));

    if (missingVisible) {
        if (typeof window.showToast === 'function') {
            window.showToast('Oferta została zaktualizowana — odświeżam stronę.', 'info');
        }
        setTimeout(() => window.location.reload(), 1200);
        return;
    }

    Object.entries(data.states).forEach(([sectionId, state]) => {
        const sectionEl = document.querySelector(`.section[data-section-id="${sectionId}"]`);
        if (sectionEl) applySectionState(sectionEl, state);
    });

    // Koszyk: pozycje z wyłączonych sekcji zostają widoczne, ale przestają się liczyć
    const previous = window.unavailableProducts || {};
    window.unavailableProducts = data.unavailable_products || {};

    const newlyUnavailable = cart.filter(
        item => !item.is_bonus
            && getUnavailableState(item.product_id)
            && !previous[String(item.product_id)]
    );

    updateCartUI();

    if (newlyUnavailable.length > 0 && typeof window.showToast === 'function') {
        const names = newlyUnavailable.map(i => i.name).join(', ');
        window.showToast(`${names} — produkt nie jest już dostępny.`, 'warning');
    }
}

function initSectionStateSocket() {
    const socket = window.offerSocket;
    if (!socket || !window.offerPageId) return;

    const joinRoom = () => socket.emit('join_offer', {
        page_id: window.offerPageId,
        page_type: 'order'
    });

    socket.on('connect', joinRoom);
    socket.on('reconnect', joinRoom);
    if (socket.connected) joinRoom();

    socket.on('section_states_updated', handleSectionStatesUpdate);
}

// ============================================
// Utility
// ============================================
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
