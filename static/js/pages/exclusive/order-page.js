/**
 * Exclusive Order Page - JavaScript
 * Handles cart, reservation system, modals, confetti, deadline timer, and Google Analytics tracking
 */

// ============================================
// Google Analytics Tracking Helpers
// ============================================
function trackExclusivePageViewed() {
    // Track page view with exclusive page info
    if (typeof window.trackExclusivePageView === 'function' && window.exclusiveToken && window.exclusiveName) {
        window.trackExclusivePageView(window.exclusiveToken, window.exclusiveName);
    }
}

function trackProductAddedToCart(productName, productId, price, quantity) {
    // Track add to cart event
    if (typeof window.trackAddToCart === 'function') {
        window.trackAddToCart(productName, productId, price, quantity);
    }
}

function trackOrderSubmitted(orderNumber, totalAmount, isGuest) {
    // Track order placement
    if (isGuest && typeof window.trackGuestOrderPlaced === 'function') {
        window.trackGuestOrderPlaced(orderNumber, totalAmount);
    } else if (!isGuest && typeof window.trackOrderPlaced === 'function') {
        // Count items in cart
        const itemsCount = cart.reduce((sum, item) => sum + item.qty, 0);
        window.trackOrderPlaced(orderNumber, totalAmount, itemsCount, 'exclusive');
    }
}

function trackUserLoginSuccess() {
    // Track successful login
    if (typeof window.trackUserLogin === 'function') {
        window.trackUserLogin('email');
    }
}

// ============================================
// Image Lightbox
// ============================================
function openLightbox(wrapper) {
    const img = wrapper.querySelector('img');
    if (!img) return;

    const fullSrc = img.dataset.fullSrc || img.src;
    const lightbox = document.getElementById('imageLightbox');
    const lightboxImg = document.getElementById('lightboxImage');

    lightboxImg.src = fullSrc;
    lightboxImg.alt = img.alt;
    lightbox.classList.add('active');

    // Prevent body scroll
    document.body.style.overflow = 'hidden';
}

function closeLightbox() {
    const lightbox = document.getElementById('imageLightbox');
    lightbox.classList.remove('active');

    // Restore body scroll
    document.body.style.overflow = '';
}

// Close on Escape key
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeLightbox();
    }
});

// ============================================
// Expandable Set Background Image
// ============================================
function toggleSetImage(wrapper) {
    const isCollapsed = wrapper.classList.contains('collapsed');
    const expandText = wrapper.querySelector('.expand-text');

    if (isCollapsed) {
        // Expand
        wrapper.classList.remove('collapsed');
        wrapper.classList.add('expanded');
        if (expandText) {
            expandText.textContent = 'Ukryj obraz';
        }
    } else {
        // Collapse
        wrapper.classList.remove('expanded');
        wrapper.classList.add('collapsed');
        if (expandText) {
            expandText.textContent = 'Pokaż cały obraz';
        }
    }
}

// ============================================
// Cart state
// ============================================
let cart = [];

function updateCart() {
    console.log('[Cart] updateCart called');
    const cartItems = document.getElementById('cartItems');
    const cartCount = document.getElementById('cartCount');
    const cartTotal = document.getElementById('cartTotal');
    const submitBtn = document.getElementById('submitOrderBtn');

    // ZMIANA: Zbierz wszystkie produkty (w tym full sety) jako normalne produkty
    cart = [];

    // 1. Collect regular products (NOT full set inputs)
    document.querySelectorAll('.qty-input:not(.full-set-qty-input)').forEach(input => {
        const qty = parseInt(input.value) || 0;
        if (qty > 0) {
            // Find the closest parent container with product info
            const productSection = input.closest('.section-product');
            const setItem = input.closest('.set-item');
            const variantProduct = input.closest('.variant-product');

            let productId, name, price;

            if (productSection) {
                // Product section
                productId = productSection.dataset.productId;
                // Try new layout first (.product-name), fallback to old (.set-name)
                const nameEl = productSection.querySelector('.product-name') || productSection.querySelector('.set-name');
                name = nameEl ? nameEl.textContent.trim() : 'Produkt';
                const priceEl = productSection.querySelector('.product-price');
                if (!priceEl) return; // Skip if price element not found
                const priceText = priceEl.textContent;
                price = parseFloat(priceText.replace(/[^\d.,]/g, '').replace(',', '.'));
            } else if (setItem) {
                // Set item
                productId = setItem.dataset.productId;
                const nameEl = setItem.querySelector('.set-item-name');
                const priceEl = setItem.querySelector('.set-item-price');
                if (!nameEl || !priceEl) return; // Skip if elements not found
                name = nameEl.textContent.trim();
                const priceText = priceEl.textContent;
                price = parseFloat(priceText.replace(/[^\d.,]/g, '').replace(',', '.'));
            } else if (variantProduct) {
                // Variant product
                productId = variantProduct.dataset.productId;
                const nameEl = variantProduct.querySelector('.variant-product-name');
                const priceEl = variantProduct.querySelector('.variant-product-price');
                if (!nameEl || !priceEl) return; // Skip if elements not found
                name = nameEl.textContent.trim();
                const priceText = priceEl.textContent;
                price = parseFloat(priceText.replace(/[^\d.,]/g, '').replace(',', '.'));
            }

            if (productId && name && !isNaN(price)) {
                console.log(`[Cart] Adding product to cart: id=${productId}, name=${name}, qty=${qty}, price=${price}`);
                cart.push({ productId: parseInt(productId), name, qty, price, isFullSet: false });
            } else {
                console.log(`[Cart] Skipping product: id=${productId}, name=${name}, price=${price} (qty=${qty})`);
            }
        }
    });

    // 2. NOWE: Collect full set products (as regular products, not virtual)
    document.querySelectorAll('.full-set-qty-input').forEach(input => {
        const qty = parseInt(input.value) || 0;
        if (qty > 0) {
            const fullSetSection = input.closest('.full-set-section');
            if (fullSetSection) {
                const productId = parseInt(fullSetSection.dataset.productId);
                const name = fullSetSection.dataset.setName || 'Pełny Set';
                const price = parseFloat(fullSetSection.dataset.setPrice);

                if (productId && !isNaN(price)) {
                    console.log(`[Cart] Adding full set as product: id=${productId}, name=${name}, qty=${qty}, price=${price}`);
                    cart.push({
                        productId: productId,
                        name: `✨ ${name}`,
                        qty: qty,
                        price: price,
                        isFullSet: true  // Flag dla wyświetlania
                    });
                }
            }
        }
    });

    // 3. Calculate totals (all items together)
    const totalItems = cart.reduce((sum, item) => sum + item.qty, 0);
    const totalPrice = cart.reduce((sum, item) => sum + (item.qty * item.price), 0);

    console.log(`[Cart] Cart updated: ${cart.length} items, ${totalItems} total qty, ${totalPrice.toFixed(2)} PLN`);

    cartCount.textContent = totalItems;
    cartTotal.textContent = totalPrice.toFixed(2) + ' PLN';
    submitBtn.disabled = totalItems === 0;

    // Update cart items list (full sets first for visual priority)
    const fullSetItems = cart.filter(item => item.isFullSet);
    const regularItems = cart.filter(item => !item.isFullSet);
    const allItems = [...fullSetItems, ...regularItems];

    if (allItems.length === 0) {
        cartItems.innerHTML = '<div class="cart-empty"><p>Koszyk jest pusty</p></div>';
    } else {
        cartItems.innerHTML = allItems.map(item => {
            const removeIcon = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`;

            if (item.isFullSet) {
                return `
                    <div class="cart-item cart-item-fullset">
                        <span class="cart-item-name">${item.name}</span>
                        <span class="cart-item-qty">x${item.qty}</span>
                        <span class="cart-item-price">${(item.qty * item.price).toFixed(2)} PLN</span>
                        <button type="button" class="cart-item-remove" onclick="removeProductFromCart(${item.productId})" title="Usuń z koszyka">
                            ${removeIcon}
                        </button>
                    </div>
                `;
            } else {
                return `
                    <div class="cart-item">
                        <span class="cart-item-name">${item.name}</span>
                        <span class="cart-item-qty">x${item.qty}</span>
                        <span class="cart-item-price">${(item.qty * item.price).toFixed(2)} PLN</span>
                        <button type="button" class="cart-item-remove" onclick="removeProductFromCart(${item.productId})" title="Usuń z koszyka">
                            ${removeIcon}
                        </button>
                    </div>
                `;
            }
        }).join('');
    }

    // Update button states after cart update
    updateButtonStates();

    // Save to localStorage
    saveToLocalStorage();
}

// Update button states based on limits
function updateButtonStates() {
    // Update all quantity controls
    document.querySelectorAll('.qty-input').forEach(input => {
        const val = parseInt(input.value) || 0;
        const max = input.getAttribute('max');
        const quantityControl = input.closest('.quantity-control');
        if (!quantityControl) return;

        const minusBtn = quantityControl.querySelector('.qty-minus');
        const plusBtn = quantityControl.querySelector('.qty-plus');

        if (!minusBtn || !plusBtn) return;

        // Disable minus if at 0
        if (val <= 0) {
            minusBtn.disabled = true;
            minusBtn.style.opacity = '0.5';
            minusBtn.style.cursor = 'not-allowed';
        } else {
            minusBtn.disabled = false;
            minusBtn.style.opacity = '1';
            minusBtn.style.cursor = 'pointer';
        }

        // Check product max limit
        let atMax = max && val >= parseInt(max);

        // Check set max limit if in a set (applies to EACH product, not sum)
        // SKIP for full-set inputs - they are UNLIMITED
        const isFullSetInput = input.classList.contains('full-set-qty-input');
        if (!isFullSetInput) {
            const setSection = input.closest('.section-set');
            if (setSection && !atMax) {
                const setMax = parseInt(setSection.dataset.setMax) || 0;
                if (setMax > 0 && val >= setMax) {
                    atMax = true;
                }
            }
        }

        if (atMax) {
            plusBtn.disabled = true;
            plusBtn.style.opacity = '0.5';
            plusBtn.style.cursor = 'not-allowed';
        } else {
            plusBtn.disabled = false;
            plusBtn.style.opacity = '1';
            plusBtn.style.cursor = 'pointer';
        }
    });
}

function increaseQty(btn) {
    if (btn.disabled) return;

    const quantityControl = btn.closest('.quantity-control');
    if (!quantityControl) return;

    const input = quantityControl.querySelector('.qty-input');
    if (!input) return;

    const max = input.getAttribute('max');
    let val = parseInt(input.value) || 0;

    // Check product max limit
    if (max && val >= parseInt(max)) {
        return;
    }

    // Check set max limit (applies to EACH product, not sum)
    // SKIP for full-set inputs - they are UNLIMITED
    const isFullSetInput = input.classList.contains('full-set-qty-input');
    if (!isFullSetInput) {
        const setSection = input.closest('.section-set');
        if (setSection) {
            const setMax = parseInt(setSection.dataset.setMax) || 0;
            if (setMax > 0 && val >= setMax) {
                return;
            }
        }
    }

    input.value = val + 1;
    updateCart();
}

function decreaseQty(btn) {
    if (btn.disabled) return;

    const quantityControl = btn.closest('.quantity-control');
    if (!quantityControl) return;

    const input = quantityControl.querySelector('.qty-input');
    if (!input) return;

    let val = parseInt(input.value) || 0;
    if (val > 0) {
        input.value = val - 1;
        updateCart();
    }
}

function updateQty(input) {
    let val = parseInt(input.value) || 0;
    const max = input.getAttribute('max');
    if (val < 0) val = 0;
    if (max && val > parseInt(max)) val = parseInt(max);

    // Check set max limit (applies to EACH product, not sum)
    const setSection = input.closest('.section-set');
    if (setSection) {
        const setMax = parseInt(setSection.dataset.setMax) || 0;
        if (setMax > 0 && val > setMax) {
            val = setMax;
        }
    }

    input.value = val;
    updateCart();
}

function openOrderModal() {
    // This will be set by template
    if (window.isAuthenticated) {
        const modal = document.getElementById('orderModal');
        modal.classList.add('active');
    } else {
        const modal = document.getElementById('guestChoiceModal');
        modal.classList.add('active');
    }
}

function closeOrderModal() {
    const modal = document.getElementById('orderModal');
    modal.classList.add('closing');
    setTimeout(() => {
        modal.classList.remove('active', 'closing');
    }, 350);
}

function closeGuestChoiceModal() {
    const modal = document.getElementById('guestChoiceModal');
    modal.classList.add('closing');
    setTimeout(() => {
        modal.classList.remove('active', 'closing');
    }, 350);
}

function continueAsGuest() {
    closeGuestChoiceModal();
    setTimeout(() => {
        const modal = document.getElementById('orderModal');
        modal.classList.add('active');
    }, 400);
}

function showLoginModal() {
    closeGuestChoiceModal();
    setTimeout(() => {
        const modal = document.getElementById('loginModal');
        modal.classList.add('active');
    }, 400);
}

function closeLoginModal() {
    const modal = document.getElementById('loginModal');
    modal.classList.add('closing');
    setTimeout(() => {
        modal.classList.remove('active', 'closing');
        const errorEl = document.getElementById('loginError');
        errorEl.style.display = 'none';
        errorEl.textContent = '';
    }, 350);
}

function backToGuestChoice() {
    closeLoginModal();
    setTimeout(() => {
        const modal = document.getElementById('guestChoiceModal');
        modal.classList.add('active');
    }, 400);
}

async function handleLogin(event) {
    event.preventDefault();

    const btn = document.getElementById('loginSubmitBtn');
    const originalText = btn.innerHTML;
    const errorEl = document.getElementById('loginError');

    errorEl.style.display = 'none';
    btn.disabled = true;
    btn.innerHTML = '<span>Logowanie...</span>';

    try {
        const email = document.getElementById('loginEmail').value;
        const password = document.getElementById('loginPassword').value;

        const response = await fetch('/auth/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: new URLSearchParams({
                'email': email,
                'password': password,
                'remember_me': 'on'
            })
        });

        if (response.ok) {
            // GA4: Track successful login
            trackUserLoginSuccess();

            window.location.reload();
        } else {
            let errorMessage = 'Nieprawidłowy email lub hasło.';
            errorEl.textContent = errorMessage;
            errorEl.style.display = 'block';
            btn.disabled = false;
            btn.innerHTML = originalText;
        }

    } catch (error) {
        console.error('Login error:', error);
        errorEl.textContent = 'Wystąpił błąd połączenia. Spróbuj ponownie.';
        errorEl.style.display = 'block';
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}

async function submitOrder() {
    const btn = document.querySelector('.exclusive-btn-submit');
    const originalText = btn.innerHTML;

    btn.disabled = true;
    btn.innerHTML = '<span>Wysyłanie...</span>';

    try {
        const orderNote = document.getElementById('orderNote').value.trim();

        let requestData = {
            session_id: reservationState.sessionId,
            order_note: orderNote || null
        };

        // If guest, gather guest data (set by template)
        if (window.isGuest) {
            const guestName = document.getElementById('guestName').value.trim();
            const guestEmail = document.getElementById('guestEmail').value.trim();
            const guestPhone = document.getElementById('guestPhone').value.trim();

            if (!guestName || !guestEmail || !guestPhone) {
                alert('Proszę wypełnić wszystkie wymagane pola.');
                btn.disabled = false;
                btn.innerHTML = originalText;
                return;
            }

            requestData.guest_data = {
                name: guestName,
                email: guestEmail,
                phone: guestPhone
            };
        }

        // Order URL set by template
        const response = await fetch(window.placeOrderUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestData)
        });

        const data = await response.json();

        if (data.success) {
            // GA4: Track order submission
            const totalAmount = cart.reduce((sum, item) => sum + (item.qty * item.price), 0);
            trackOrderSubmitted(data.order_number, totalAmount, window.isGuest || false);

            // Clear localStorage reservation (storage key set by template)
            localStorage.removeItem(window.reservationStorageKey);

            if (reservationState.pollingInterval) {
                clearInterval(reservationState.pollingInterval);
            }
            if (reservationState.countdownInterval) {
                clearInterval(reservationState.countdownInterval);
            }

            // Redirect to thank you page (URL set by template)
            window.location.href = window.thankYouUrl;

        } else {
            let errorMessage = 'Wystąpił błąd podczas składania zamówienia.';

            if (data.error === 'no_reservations') {
                errorMessage = 'Brak produktów w koszyku. Rezerwacja mogła wygasnąć.';
            } else if (data.error === 'insufficient_stock') {
                errorMessage = `Produkt "${data.product_name}" nie ma wystarczającej ilości w magazynie.`;
            } else if (data.error === 'page_not_active') {
                errorMessage = 'Sprzedaż nie jest już aktywna.';
            } else if (data.error === 'email_exists') {
                errorMessage = data.message;
                btn.disabled = false;
                btn.innerHTML = originalText;
                showEmailExistsModal(data.message);
                return;
            } else if (data.message) {
                errorMessage = data.message;
            }

            alert(errorMessage);
            btn.disabled = false;
            btn.innerHTML = originalText;

            if (data.error === 'no_reservations') {
                setTimeout(() => {
                    window.location.reload();
                }, 2000);
            }
        }

    } catch (error) {
        console.error('Order submission error:', error);
        alert('Wystąpił błąd połączenia. Spróbuj ponownie.');
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}

function showSuccessModal(orderNumber, totalAmount) {
    document.getElementById('successOrderNumber').textContent = orderNumber;
    document.getElementById('successOrderTotal').textContent = totalAmount.toFixed(2) + ' PLN';

    const modal = document.getElementById('successModal');
    modal.classList.add('active');
    modal.onclick = null;
}

function closeSuccessModal() {
    const modal = document.getElementById('successModal');
    modal.classList.add('closing');
    setTimeout(() => {
        modal.classList.remove('active', 'closing');
        window.location.reload();
    }, 350);
}

function redirectToOrders() {
    // URL set by template
    window.location.href = window.redirectAfterOrderUrl;
}

function showEmailExistsModal(message) {
    const modal = document.getElementById('emailExistsModal');
    const messageEl = document.getElementById('emailExistsMessage');
    if (messageEl) {
        messageEl.textContent = message;
    }
    modal.classList.add('active');
}

function closeEmailExistsModal() {
    const modal = document.getElementById('emailExistsModal');
    modal.classList.add('closing');
    setTimeout(() => {
        modal.classList.remove('active', 'closing');
    }, 350);
}

function redirectToLogin() {
    const currentUrl = window.location.href;
    window.location.href = '/auth/login?next=' + encodeURIComponent(currentUrl);
}

// Initialize button states on page load
document.addEventListener('DOMContentLoaded', function() {
    updateButtonStates();
});

// Close modal on Escape
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        const modal = document.getElementById('orderModal');
        if (modal.classList.contains('active')) {
            closeOrderModal();
        }
    }
});

// Close modal on backdrop click
document.getElementById('orderModal').addEventListener('click', function(e) {
    if (e.target === this) {
        closeOrderModal();
    }
});

// ============================================
// Reservation System
// ============================================

let reservationState = {
    sessionId: null,
    firstReservedAt: null,
    expiresAt: null,
    extended: false,
    pollingInterval: null,
    countdownInterval: null
};

// Generate UUID v4
function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

// Initialize session
function initReservationSystem() {
    // Storage key set by template
    let stored = localStorage.getItem(window.reservationStorageKey);
    if (stored) {
        try {
            const data = JSON.parse(stored);
            reservationState.sessionId = data.sessionId;
            restoreReservation(data);
        } catch (e) {
            console.error('Failed to parse localStorage', e);
            createNewSession();
        }
    } else {
        createNewSession();
    }

    startPolling();
}

function createNewSession() {
    reservationState.sessionId = generateUUID();
    saveToLocalStorage();
}

// Save to localStorage
function saveToLocalStorage() {
    const data = {
        sessionId: reservationState.sessionId,
        firstReservedAt: reservationState.firstReservedAt,
        expiresAt: reservationState.expiresAt,
        extended: reservationState.extended,
        products: {}
    };

    cart.forEach(item => {
        data.products[item.productId] = {
            quantity: item.qty,
            name: item.name,
            price: item.price,
            isFullSet: item.isFullSet || false
        };
    });

    localStorage.setItem(window.reservationStorageKey, JSON.stringify(data));
}

// Restore reservation from localStorage
async function restoreReservation(data) {
    console.log('[Reservation] Restoring reservation:', data);
    try {
        // Restore URL set by template
        const response = await fetch(window.restoreReservationUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                session_id: data.sessionId,
                products: data.products
            })
        });

        const result = await response.json();
        console.log('[Reservation] Restore response:', result);

        if (result.success) {
            Object.entries(result.restored).forEach(([productId, qty]) => {
                console.log(`[Reservation] Restoring product ${productId} with qty ${qty}`);

                const isFullSet = data.products[productId]?.isFullSet || false;

                let input;
                if (isFullSet) {
                    const fullSetSection = document.querySelector(`.full-set-section[data-product-id="${productId}"]`);
                    if (fullSetSection) {
                        input = fullSetSection.querySelector('.full-set-qty-input');

                        if (qty > 0) {
                            const confettiContainer = fullSetSection.querySelector('.full-set-confetti-container');
                            if (confettiContainer) {
                                confettiContainer.classList.add('has-items');
                            }
                        }
                    }
                } else {
                    input = document.querySelector(`[data-product-id="${productId}"]:not(.full-set-section) .qty-input`);
                }

                console.log(`[Reservation] Found input:`, input);
                if (input) {
                    input.value = qty;
                }
            });

            if (result.expired.length > 0) {
                result.expired.forEach(productId => {
                    const productName = data.products[productId]?.name || 'Produkt';
                    showToast(`Rezerwacja wygasła: ${productName}`, 'warning');
                });
            }

            const hasRestoredProducts = Object.values(result.restored).some(qty => qty > 0);
            if (result.session && hasRestoredProducts) {
                reservationState.expiresAt = result.session.expires_at;
                reservationState.firstReservedAt = result.session.first_reserved_at;
                reservationState.extended = result.session.extended || false;
                showReservationHeader();
            } else if (result.session && !hasRestoredProducts) {
                hideReservationHeader();
                localStorage.removeItem(window.reservationStorageKey);
            }

            updateCart();
        }
    } catch (error) {
        console.error('Failed to restore reservation:', error);
    }
}

// Modified increaseQty with reservation (non-blocking)
function increaseQtyWithReservation(btn) {
    if (btn.disabled) return;

    const quantityControl = btn.closest('.quantity-control');
    if (!quantityControl) return;

    const input = quantityControl.querySelector('.qty-input');
    if (!input) return;

    const productSection = input.closest('.section-product, .set-item, .variant-product');
    const productId = productSection.dataset.productId;

    let val = parseInt(input.value) || 0;

    const max = input.getAttribute('max');
    if (max && val >= parseInt(max)) {
        return;
    }

    const setSection = input.closest('.section-set');
    if (setSection) {
        const setMax = parseInt(setSection.dataset.setMax) || 0;
        if (setMax > 0 && val >= setMax) {
            return;
        }
    }

    const available = productAvailability[productId];
    if (available !== undefined && available < 999999 && available <= 0) {
        return;
    }

    // IMMEDIATE UI update
    input.value = val + 1;
    optimisticUpdateAvailability(productId, -1);
    updateCart();
    saveToLocalStorage();

    // Background reservation (reserve URL set by template)
    fetch(window.reserveProductUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            session_id: reservationState.sessionId,
            product_id: productId,
            quantity: 1,
            action: val === 0 ? 'add' : 'increase'
        })
    }).then(r => r.json()).then(result => {
        if (result.success) {
            if (result.reservation.first_reservation_at) {
                reservationState.firstReservedAt = result.reservation.first_reservation_at;
                reservationState.expiresAt = result.reservation.expires_at;
                showReservationHeader();
            }

            // GA4: Track add to cart (only on first add, not on increase)
            if (val === 0) {
                const cartItem = cart.find(item => item.productId == productId);
                if (cartItem) {
                    trackProductAddedToCart(cartItem.name, productId, cartItem.price, 1);
                }
            }
        } else {
            input.value = Math.max(0, parseInt(input.value) - 1);
            optimisticUpdateAvailability(productId, +1);
            updateCart();
            if (result.error === 'insufficient_availability') {
                showUnavailablePopup(result.message, result.check_back_at);
            }
        }
    }).catch(() => {
        input.value = Math.max(0, parseInt(input.value) - 1);
        optimisticUpdateAvailability(productId, +1);
        updateCart();
    });
}

// Modified decreaseQty with release (non-blocking)
function decreaseQtyWithReservation(btn) {
    if (btn.disabled) return;

    const quantityControl = btn.closest('.quantity-control');
    if (!quantityControl) return;

    const input = quantityControl.querySelector('.qty-input');
    if (!input) return;

    let val = parseInt(input.value) || 0;
    if (val === 0) return;

    const productSection = input.closest('.section-product, .set-item, .variant-product');
    const productId = productSection.dataset.productId;

    // IMMEDIATE UI update
    input.value = val - 1;
    optimisticUpdateAvailability(productId, +1);
    updateCart();
    saveToLocalStorage();

    if (cart.length === 0) {
        hideReservationHeader();
    }

    // Background release (release URL set by template)
    fetch(window.releaseProductUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            session_id: reservationState.sessionId,
            product_id: productId,
            quantity: 1,
            action: 'decrease'
        })
    }).catch(() => {
        // Silent fail - polling will sync state
    });
}

// Polling availability (every 1 second)
function startPolling() {
    if (reservationState.pollingInterval) return;

    reservationState.pollingInterval = setInterval(async () => {
        await checkAvailability();
    }, 1000);
}

async function checkAvailability() {
    try {
        // Availability URL set by template (dynamic function)
        const response = await fetch(window.getAvailabilityCheckUrl());

        if (!response.ok) {
            console.warn(`Availability check returned ${response.status}`);
            return;
        }

        const result = await response.json();

        if (result.success) {
            Object.entries(result.products).forEach(([productId, data]) => {
                updateProductAvailability(productId, data);
            });

            if (result.session.has_reservations) {
                reservationState.expiresAt = result.session.expires_at;
                reservationState.extended = result.session.extended;
                updateReservationTimer();
            } else {
                hideReservationHeader();
            }
        }
    } catch (error) {
        console.debug('Availability check failed (network):', error.message);
    }
}

// Store last known availability for optimistic updates
let productAvailability = {};

function updateProductAvailability(productId, data) {
    productAvailability[productId] = data.available;

    const productElements = document.querySelectorAll(`[data-product-id="${productId}"]`);

    productElements.forEach(element => {
        const quantityControl = element.querySelector('.quantity-control');
        if (!quantityControl) return;

        const plusBtn = quantityControl.querySelector('.qty-plus');
        const input = quantityControl.querySelector('.qty-input');

        const currentQty = parseInt(input.value) || 0;

        const shouldDisable = data.available <= 0;

        if (shouldDisable) {
            plusBtn.disabled = true;
            plusBtn.style.opacity = '0.5';
            plusBtn.style.cursor = 'not-allowed';
        } else {
            plusBtn.disabled = false;
            plusBtn.style.opacity = '1';
            plusBtn.style.cursor = 'pointer';
        }
    });

    renderAvailabilityInfo(productId, data.available);
}

function renderAvailabilityInfo(productId, available) {
    const availabilityElements = document.querySelectorAll(`[data-availability-for="${productId}"]`);

    availabilityElements.forEach(el => {
        el.classList.remove('availability-low', 'availability-none', 'availability-unlimited', 'availability-loading', 'availability-updating');

        if (available >= 999999) {
            el.classList.add('availability-unlimited');
            el.textContent = 'Bez limitu';
        } else if (available <= 0) {
            el.classList.add('availability-none');
            el.textContent = 'Niedostępne';
        } else if (available <= 3) {
            el.classList.add('availability-low');
            el.textContent = `Dostępne: ${available}`;
        } else {
            el.textContent = `Dostępne: ${available}`;
        }
    });
}

function optimisticUpdateAvailability(productId, delta) {
    if (productAvailability[productId] === undefined) return;
    if (productAvailability[productId] >= 999999) return;

    productAvailability[productId] = Math.max(0, productAvailability[productId] + delta);

    const availabilityElements = document.querySelectorAll(`[data-availability-for="${productId}"]`);
    availabilityElements.forEach(el => el.classList.add('availability-updating'));

    renderAvailabilityInfo(productId, productAvailability[productId]);
}

function showReservationHeader() {
    const header = document.getElementById('reservationHeader');
    header.classList.remove('hidden');

    const extendBtn = document.getElementById('extendBtn');
    extendBtn.disabled = true;
    extendBtn.textContent = reservationState.extended ? 'Przedłużono' : 'Przedłuż +2 min';

    startCountdown();
}

function hideReservationHeader() {
    const header = document.getElementById('reservationHeader');
    header.classList.add('hidden');
    stopCountdown();

    reservationState.extended = false;
    reservationState.firstReservedAt = null;
    reservationState.expiresAt = null;
}

function startCountdown() {
    if (reservationState.countdownInterval) return;

    reservationState.countdownInterval = setInterval(() => {
        updateReservationTimer();
    }, 1000);
}

function stopCountdown() {
    if (reservationState.countdownInterval) {
        clearInterval(reservationState.countdownInterval);
        reservationState.countdownInterval = null;
    }
}

function updateReservationTimer() {
    if (!reservationState.expiresAt) return;

    const now = Math.floor(Date.now() / 1000);
    const diff = reservationState.expiresAt - now;

    if (diff <= 0) {
        showToast('Twoja rezerwacja wygasła', 'error');
        clearReservation();
        return;
    }

    const minutes = Math.floor(diff / 60);
    const seconds = diff % 60;

    const timerEl = document.getElementById('reservationTimer');
    timerEl.textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;

    const extendBtn = document.getElementById('extendBtn');
    const canExtend = !reservationState.extended && diff < 120;
    extendBtn.disabled = !canExtend;

    if (reservationState.extended) {
        extendBtn.textContent = 'Przedłużono';
    } else if (diff >= 120) {
        extendBtn.textContent = 'Przedłuż +2 min';
    } else {
        extendBtn.textContent = 'Przedłuż +2 min';
    }

    const header = document.getElementById('reservationHeader');
    if (diff < 120) {
        header.classList.add('reservation-warning');
    } else {
        header.classList.remove('reservation-warning');
    }
}

async function extendReservation() {
    if (reservationState.extended) return;

    try {
        // Extend URL set by template
        const response = await fetch(window.extendReservationUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                session_id: reservationState.sessionId
            })
        });

        const result = await response.json();

        if (result.success) {
            reservationState.expiresAt = result.new_expires_at;
            reservationState.extended = true;
            saveToLocalStorage();
            showToast('Rezerwacja przedłużona o 2 minuty', 'success');
        } else {
            showToast(result.message || 'Nie można przedłużyć rezerwacji', 'error');
        }
    } catch (error) {
        console.error('Extend failed:', error);
        showToast('Błąd przedłużania rezerwacji', 'error');
    }
}

function clearReservation() {
    reservationState.firstReservedAt = null;
    reservationState.expiresAt = null;
    reservationState.extended = false;

    document.querySelectorAll('.qty-input').forEach(input => {
        input.value = 0;
    });

    cart = [];
    updateCart();

    localStorage.removeItem(window.reservationStorageKey);
    hideReservationHeader();
}

function showUnavailablePopup(message, checkBackAtTimestamp) {
    const checkBackDate = new Date(checkBackAtTimestamp * 1000);
    const formatter = new Intl.DateTimeFormat('pl-PL', {
        timeZone: 'Europe/Warsaw',
        hour: '2-digit',
        minute: '2-digit'
    });
    const timeStr = formatter.format(checkBackDate);

    const modal = document.createElement('div');
    modal.className = 'unavailable-modal';
    modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);display:flex;align-items:center;justify-content:center;z-index:10001;';
    modal.innerHTML = `
        <div class="unavailable-content" style="background:white;padding:32px;border-radius:12px;max-width:500px;text-align:center;">
            <div class="unavailable-icon" style="font-size:48px;margin-bottom:16px;">⚠️</div>
            <h3 style="margin-bottom:16px;">Produkt zarezerwowany</h3>
            <p style="margin-bottom:16px;">${message}</p>
            <p class="check-back" style="margin-bottom:24px;">Sprawdź dostępność o <strong>${timeStr}</strong></p>
            <button onclick="this.closest('.unavailable-modal').remove()" class="btn-close-modal" style="padding:12px 24px;background:#7B2CBF;color:white;border:none;border-radius:8px;cursor:pointer;">
                Rozumiem
            </button>
        </div>
    `;

    document.body.appendChild(modal);
}

// Replace original functions with reservation-aware versions
window.increaseQty = increaseQtyWithReservation;
window.decreaseQty = decreaseQtyWithReservation;

// ============================================
// Remove Item from Cart Functions
// ============================================

async function removeProductFromCart(productId) {
    console.log(`[Cart] Removing product ${productId} from cart`);

    const fullSetSection = document.querySelector(`.full-set-section[data-product-id="${productId}"]`);
    if (fullSetSection) {
        const input = fullSetSection.querySelector('.full-set-qty-input');
        if (input) {
            const confettiContainer = fullSetSection.querySelector('.full-set-confetti-container');

            input.value = 0;

            if (confettiContainer) {
                confettiContainer.classList.add('fade-out');
                setTimeout(() => {
                    confettiContainer.classList.remove('has-items', 'fade-out');
                }, 500);
            }

            updateCart();
            return;
        }
    }

    const productSection = document.querySelector(`[data-product-id="${productId}"]:not(.full-set-section)`);
    if (!productSection) {
        console.error(`[Cart] Product section not found for id ${productId}`);
        return;
    }

    const input = productSection.querySelector('.qty-input');
    if (!input) {
        console.error(`[Cart] Input not found for product ${productId}`);
        return;
    }

    const currentQty = parseInt(input.value) || 0;
    if (currentQty === 0) return;

    try {
        // Release URL set by template
        const response = await fetch(window.releaseProductUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                session_id: reservationState.sessionId,
                product_id: productId,
                quantity: currentQty
            })
        });

        const result = await response.json();
        console.log(`[Cart] Release result:`, result);

        input.value = 0;
        updateCart();

        await checkAvailability();

    } catch (error) {
        console.error('[Cart] Error releasing product:', error);
        input.value = 0;
        updateCart();
    }
}

function removeFullSetFromCart(sectionId) {
    console.log(`[Cart] Removing full set from section ${sectionId}`);

    const fullSetSection = document.querySelector(`.full-set-section[data-section-id="${sectionId}"]`);
    if (!fullSetSection) {
        console.error(`[Cart] Full set section not found for id ${sectionId}`);
        return;
    }

    const input = fullSetSection.querySelector('.full-set-qty-input');
    if (!input) {
        console.error(`[Cart] Full set input not found in section`);
        return;
    }

    const confettiContainer = fullSetSection.querySelector('.full-set-confetti-container');

    input.value = 0;

    if (confettiContainer) {
        confettiContainer.classList.add('fade-out');
        setTimeout(() => {
            confettiContainer.classList.remove('has-items', 'fade-out');
        }, 500);
    }

    updateCart();
}

// ============================================
// Full Set Functions (No Reservation System)
// ============================================

let fullSets = {};

function increaseFullSet(btn) {
    if (btn.disabled) return;

    const quantityControl = btn.closest('.quantity-control');
    if (!quantityControl) return;

    const input = quantityControl.querySelector('.qty-input');
    if (!input) return;

    const fullSetSection = btn.closest('.full-set-section');
    const confettiContainer = fullSetSection.querySelector('.full-set-confetti-container');

    const productId = parseInt(fullSetSection.dataset.productId);
    const setName = fullSetSection.dataset.setName;
    const setPrice = parseFloat(fullSetSection.dataset.setPrice);

    let val = parseInt(input.value) || 0;

    // IMMEDIATE UI update
    input.value = val + 1;

    confettiContainer.classList.add('has-items');

    if (val === 0) {
        triggerConfetti(fullSetSection, true);
        confettiContainer.classList.add('celebrate');
        setTimeout(() => {
            confettiContainer.classList.remove('celebrate');
        }, 800);
    } else {
        triggerConfetti(fullSetSection, false);
    }

    updateCart();
    saveToLocalStorage();

    // Background reservation (same as regular products)
    fetch(window.reserveProductUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            session_id: reservationState.sessionId,
            product_id: productId,
            quantity: 1,
            action: val === 0 ? 'add' : 'increase'
        })
    }).then(r => r.json()).then(result => {
        if (result.success) {
            if (result.reservation.first_reservation_at) {
                reservationState.firstReservedAt = result.reservation.first_reservation_at;
                reservationState.expiresAt = result.reservation.expires_at;
                showReservationHeader();
            }
        } else {
            // Rollback on error
            input.value = Math.max(0, parseInt(input.value) - 1);
            if (input.value === 0) {
                confettiContainer.classList.add('fade-out');
                setTimeout(() => {
                    confettiContainer.classList.remove('has-items', 'fade-out');
                }, 500);
            }
            updateCart();
            if (result.error === 'insufficient_availability') {
                showUnavailablePopup(result.message, result.check_back_at);
            }
        }
    }).catch(() => {
        // Rollback on network error
        input.value = Math.max(0, parseInt(input.value) - 1);
        if (input.value === 0) {
            confettiContainer.classList.add('fade-out');
            setTimeout(() => {
                confettiContainer.classList.remove('has-items', 'fade-out');
            }, 500);
        }
        updateCart();
    });
}

function decreaseFullSet(btn) {
    if (btn.disabled) return;

    const quantityControl = btn.closest('.quantity-control');
    if (!quantityControl) return;

    const input = quantityControl.querySelector('.qty-input');
    if (!input) return;

    const fullSetSection = btn.closest('.full-set-section');
    const confettiContainer = fullSetSection.querySelector('.full-set-confetti-container');
    const productId = parseInt(fullSetSection.dataset.productId);

    let val = parseInt(input.value) || 0;
    if (val > 0) {
        // IMMEDIATE UI update
        input.value = val - 1;

        if (val - 1 === 0) {
            confettiContainer.classList.add('fade-out');
            setTimeout(() => {
                confettiContainer.classList.remove('has-items', 'fade-out');
            }, 500);
        }

        updateCart();
        saveToLocalStorage();

        if (cart.length === 0) {
            hideReservationHeader();
        }

        // Background release (same as regular products)
        fetch(window.releaseProductUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: reservationState.sessionId,
                product_id: productId,
                quantity: 1
            })
        }).then(r => r.json()).catch(() => {
            // Silent fail - already updated UI
        });
    }
}

function updateFullSetQty(input) {
    const fullSetSection = input.closest('.full-set-section');
    const productId = parseInt(fullSetSection.dataset.productId);
    const confettiContainer = fullSetSection.querySelector('.full-set-confetti-container');

    // Get old value from cart before parsing new value
    const oldCartItem = cart.find(item => item.productId === productId && item.isFullSet);
    const oldVal = oldCartItem ? oldCartItem.qty : 0;

    let val = parseInt(input.value) || 0;
    if (val < 0) val = 0;
    input.value = val;

    const delta = val - oldVal;

    if (delta === 0) {
        return; // No change
    }

    if (val > 0) {
        if (!confettiContainer.classList.contains('has-items')) {
            confettiContainer.classList.add('has-items', 'celebrate');
            triggerConfetti(fullSetSection, true);
            setTimeout(() => {
                confettiContainer.classList.remove('celebrate');
            }, 800);
        }
    } else {
        confettiContainer.classList.add('fade-out');
        setTimeout(() => {
            confettiContainer.classList.remove('has-items', 'fade-out');
        }, 500);
    }

    updateCart();
    saveToLocalStorage();

    // Sync with reservation
    if (delta > 0) {
        // Increased - reserve more
        fetch(window.reserveProductUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: reservationState.sessionId,
                product_id: productId,
                quantity: delta,
                action: oldVal === 0 ? 'add' : 'increase'
            })
        }).then(r => r.json()).then(result => {
            if (result.success) {
                if (result.reservation.first_reservation_at) {
                    reservationState.firstReservedAt = result.reservation.first_reservation_at;
                    reservationState.expiresAt = result.reservation.expires_at;
                    showReservationHeader();
                }
            } else {
                // Rollback to old value
                input.value = oldVal;
                if (oldVal === 0) {
                    confettiContainer.classList.add('fade-out');
                    setTimeout(() => {
                        confettiContainer.classList.remove('has-items', 'fade-out');
                    }, 500);
                }
                updateCart();
                if (result.error === 'insufficient_availability') {
                    showUnavailablePopup(result.message, result.check_back_at);
                }
            }
        }).catch(() => {
            // Rollback on error
            input.value = oldVal;
            if (oldVal === 0) {
                confettiContainer.classList.add('fade-out');
                setTimeout(() => {
                    confettiContainer.classList.remove('has-items', 'fade-out');
                }, 500);
            }
            updateCart();
        });
    } else {
        // Decreased - release
        fetch(window.releaseProductUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: reservationState.sessionId,
                product_id: productId,
                quantity: Math.abs(delta)
            })
        }).then(r => r.json()).catch(() => {
            // Silent fail - already updated UI
        });

        if (cart.length === 0) {
            hideReservationHeader();
        }
    }
}

function triggerConfetti(container, isBig = true) {
    const confettiContainer = container.querySelector('.full-set-confetti-container');
    confettiContainer.classList.add('confetti-active');

    const colors = ['#ff6b6b', '#feca57', '#48dbfb', '#ff9ff3', '#54a0ff', '#5f27cd', '#00d2d3', '#ff9f43', '#ee5a24', '#ffffff'];
    const shapes = ['circle', 'circle', 'square', 'star', 'circle'];

    const particleCount = isBig ? 35 : 18;
    const spreadMultiplier = isBig ? 1.5 : 1;
    const duration = isBig ? 1 : 0.7;

    for (let i = 0; i < particleCount; i++) {
        const particle = document.createElement('div');
        particle.className = `confetti-particle ${shapes[Math.floor(Math.random() * shapes.length)]}`;

        const startX = 80 + (Math.random() - 0.5) * 20;
        const startY = 50 + (Math.random() - 0.5) * 30;

        const angle = (Math.random() * 360) * (Math.PI / 180);
        const distance = 60 + Math.random() * 100 * spreadMultiplier;
        const tx = Math.cos(angle) * distance;
        const ty = Math.sin(angle) * distance - 40;
        const rot = Math.random() * 720 - 360;

        const size = isBig ? (6 + Math.random() * 8) : (5 + Math.random() * 5);

        particle.style.cssText = `
            left: ${startX}%;
            top: ${startY}%;
            width: ${size}px;
            height: ${size}px;
            background: ${colors[Math.floor(Math.random() * colors.length)]};
            --tx: ${tx}px;
            --ty: ${ty}px;
            --rot: ${rot}deg;
            animation: confettiExplode ${duration}s ease-out forwards;
            animation-delay: ${Math.random() * 0.1}s;
        `;

        confettiContainer.appendChild(particle);

        setTimeout(() => {
            particle.remove();
        }, duration * 1000 + 200);
    }

    setTimeout(() => {
        confettiContainer.classList.remove('confetti-active');
    }, 400);
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    initReservationSystem();
    initFullSetButtons();

    // GA4: Track exclusive page view (once on load)
    trackExclusivePageViewed();
});

function initFullSetButtons() {
    document.querySelectorAll('.full-set-qty-input').forEach(input => {
        const val = parseInt(input.value) || 0;
        const quantityControl = input.closest('.quantity-control');
        const minusBtn = quantityControl.querySelector('.qty-minus');

        if (val <= 0) {
            minusBtn.disabled = true;
            minusBtn.style.opacity = '0.5';
            minusBtn.style.cursor = 'not-allowed';
        }
    });
}

// ============================================
// Deadline Timer & Alert System
// ============================================
(function() {
    const deadlineBanner = document.querySelector('.deadline-banner[data-deadline]');
    if (!deadlineBanner) return;

    const deadlineStr = deadlineBanner.getAttribute('data-deadline');
    if (!deadlineStr) return;

    const deadlineDate = new Date(deadlineStr);
    const alertPopup = document.getElementById('deadlineAlertPopup');
    const dynamicCountdown = document.getElementById('dynamicCountdown');
    const countdownTime = document.getElementById('countdownTime');
    const deadlineMinutes = document.getElementById('deadlineMinutes');

    const STORAGE_KEY = 'deadlineAlerts_' + deadlineStr;
    let shownAlerts = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{"10": false, "5": false, "2": false}');

    function formatTime(minutes, seconds) {
        const m = String(minutes).padStart(2, '0');
        const s = String(seconds).padStart(2, '0');
        return `${m}:${s}`;
    }

    function showDeadlineAlert(minutesLeft) {
        if (!alertPopup) return;

        if (minutesLeft === 10) {
            deadlineMinutes.textContent = '10 minut';
        } else if (minutesLeft === 5) {
            deadlineMinutes.textContent = '5 minut';
        } else if (minutesLeft === 2) {
            deadlineMinutes.textContent = '2 minuty';
        }

        alertPopup.classList.remove('hidden');

        shownAlerts[String(minutesLeft)] = true;
        localStorage.setItem(STORAGE_KEY, JSON.stringify(shownAlerts));
    }

    window.closeDeadlineAlert = function() {
        if (alertPopup) {
            alertPopup.classList.add('hidden');
        }
    };

    function updateTimer() {
        const now = new Date();
        const diff = deadlineDate - now;

        if (diff <= 0) {
            if (dynamicCountdown) {
                dynamicCountdown.classList.add('hidden');
            }
            return;
        }

        const totalSeconds = Math.floor(diff / 1000);
        const totalMinutes = Math.floor(totalSeconds / 60);
        const minutes = Math.floor(totalMinutes % 60);
        const seconds = totalSeconds % 60;

        if (totalMinutes < 10 && dynamicCountdown) {
            if (dynamicCountdown.classList.contains('hidden')) {
                dynamicCountdown.classList.remove('hidden');
            }

            countdownTime.textContent = formatTime(minutes, seconds);

            if (totalMinutes < 2) {
                dynamicCountdown.classList.add('urgent');
            } else {
                dynamicCountdown.classList.remove('urgent');
            }
        }

        if (totalMinutes === 10 && totalSeconds >= 595 && totalSeconds <= 605 && !shownAlerts['10']) {
            showDeadlineAlert(10);
        } else if (totalMinutes === 5 && totalSeconds >= 295 && totalSeconds <= 305 && !shownAlerts['5']) {
            showDeadlineAlert(5);
        } else if (totalMinutes === 2 && totalSeconds >= 115 && totalSeconds <= 125 && !shownAlerts['2']) {
            showDeadlineAlert(2);
        }
    }

    updateTimer();
    setInterval(updateTimer, 1000);

    if (alertPopup) {
        alertPopup.addEventListener('click', function(e) {
            if (e.target === alertPopup) {
                closeDeadlineAlert();
            }
        });
    }

    // Testowanie (usuń w produkcji)
    // Uncomment poniżej aby testować popup:
    // setTimeout(() => showDeadlineAlert(10), 2000);
})();
