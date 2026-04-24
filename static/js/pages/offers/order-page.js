/**
 * Offer Order Page - JavaScript
 * Handles cart, reservation system, modals, confetti, deadline timer, and Google Analytics tracking
 */

// ============================================
// Google Analytics Tracking Helpers
// ============================================
function trackOfferPageViewed() {
    // Track page view with offer page info
    if (typeof window.trackOfferPageView === 'function' && window.offerToken && window.offerName) {
        window.trackOfferPageView(window.offerToken, window.offerName);
    }
}

function trackProductAddedToCart(productName, productId, price, quantity) {
    // Track add to cart event
    if (typeof window.trackAddToCart === 'function') {
        window.trackAddToCart(productName, productId, price, quantity);
    }
}

function trackOrderSubmitted(orderNumber, totalAmount) {
    // Track order placement
    if (typeof window.trackOrderPlaced === 'function') {
        const itemsCount = cart.reduce((sum, item) => sum + item.qty, 0);
        window.trackOrderPlaced(orderNumber, totalAmount, itemsCount, 'offer');
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
    // Don't toggle if image doesn't need expanding
    if (wrapper.classList.contains('no-expand')) return;

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

// Check if expandable images actually need the expand feature
function initExpandableImages() {
    const MAX_HEIGHT = 300; // Same as CSS max-height for collapsed state

    document.querySelectorAll('.set-background.expandable-image').forEach(wrapper => {
        const img = wrapper.querySelector('img');
        if (!img) return;

        // Wait for image to load to get actual height
        const checkImageHeight = () => {
            const imgHeight = img.naturalHeight;
            const imgWidth = img.naturalWidth;

            // Guard: image failed to load (naturalWidth/Height are 0)
            if (!imgWidth || !imgHeight) {
                wrapper.style.display = 'none';
                return;
            }

            const wrapperWidth = wrapper.offsetWidth;
            const displayedHeight = (imgHeight / imgWidth) * wrapperWidth;

            if (displayedHeight <= MAX_HEIGHT) {
                // Image fits without scrolling - disable expand feature
                wrapper.classList.remove('collapsed');
                wrapper.classList.add('no-expand');
                const overlay = wrapper.querySelector('.expand-overlay');
                if (overlay) {
                    overlay.style.display = 'none';
                }
            }
        };

        if (img.complete) {
            checkImageHeight();
        } else {
            img.addEventListener('load', checkImageHeight);
            img.addEventListener('error', () => {
                wrapper.style.display = 'none';
            });
        }
    });
}

// Initialize expandable images on page load
document.addEventListener('DOMContentLoaded', initExpandableImages);

// ============================================
// Mobile Cart FAB
// ============================================

// Move cart sidebar to body level on mobile so z-index works correctly
// (inside .page-content it's trapped in its stacking context)
(function() {
    function setupMobileCart() {
        const sidebar = document.querySelector('.cart-sidebar');
        const overlay = document.getElementById('cartMobileOverlay');
        if (!sidebar || !overlay) return;

        if (window.innerWidth <= 1024) {
            // Move cart sidebar right before the overlay element (both at body level)
            if (sidebar.parentElement !== overlay.parentElement || sidebar.nextElementSibling !== overlay) {
                overlay.parentNode.insertBefore(sidebar, overlay);
            }
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', setupMobileCart);
    } else {
        setupMobileCart();
    }
})();

function toggleMobileCart() {
    const sidebar = document.querySelector('.cart-sidebar');
    const overlay = document.getElementById('cartMobileOverlay');
    if (!sidebar || !overlay) return;

    const isOpen = sidebar.classList.contains('mobile-open');
    if (isOpen) {
        sidebar.classList.remove('mobile-open');
        overlay.classList.remove('active');
    } else {
        sidebar.classList.add('mobile-open');
        overlay.classList.add('active');
    }
}

// ============================================
// Bottom Checkout Bar
// ============================================
function updateCheckoutBottomBar(totalItems, totalPrice) {
    const bar = document.getElementById('checkoutBottomBar');
    const countEl = document.getElementById('checkoutBottomCount');
    const totalEl = document.getElementById('checkoutBottomTotal');
    const btn = document.getElementById('checkoutBottomBtn');
    if (!bar) return;

    if (totalItems > 0) {
        const label = totalItems === 1 ? 'produkt' : (totalItems < 5 ? 'produkty' : 'produktów');
        countEl.textContent = totalItems + ' ' + label;
        totalEl.textContent = totalPrice.toFixed(2) + ' PLN';
        if (btn) btn.disabled = false;
    } else {
        countEl.textContent = 'Koszyk pusty';
        totalEl.textContent = '0.00 PLN';
        if (btn) btn.disabled = true;
    }
}

// ============================================
// Cart state
// ============================================
let cart = [];
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
                cart.push({ productId: parseInt(productId), name, qty, price, isFullSet: false, selectedSize: selectedProductSizes[productId] || null });
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

    // Update bottom checkout bar
    updateCheckoutBottomBar(totalItems, totalPrice);

    // Evaluate bonuses (gratisy) — this also renders the cart items HTML
    // (cart rendering is done inside evaluateBonuses to avoid double-rendering)
    // Skip during batch claimBonus operations to avoid N redundant recalculations
    if (!window._claimingBonus) {
        evaluateBonuses();
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
    // User powinien być zawsze zalogowany (overlay blokuje niezalogowanych).
    // Safety net: gdyby jakoś przeszedł — otwórz login modal.
    if (!window.isAuthenticated) {
        openLoginModal();
        return;
    }
    const modal = document.getElementById('orderModal');
    modal.classList.add('active');
}

function closeOrderModal() {
    const modal = document.getElementById('orderModal');
    modal.classList.add('closing');
    setTimeout(() => {
        modal.classList.remove('active', 'closing');
    }, 350);
}

function openLoginModal() {
    const modal = document.getElementById('loginModal');
    if (modal) {
        modal.classList.add('active');
    }
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

// Show/hide login overlay
function showLoginOverlay() {
    const overlay = document.getElementById('loginOverlay');
    if (overlay) {
        overlay.classList.add('active');
    }
}

function hideLoginOverlay() {
    const overlay = document.getElementById('loginOverlay');
    if (overlay) {
        overlay.classList.remove('active');
    }
}

// Toggle password visibility
function togglePasswordVisibility() {
    const passwordInput = document.getElementById('loginPassword');
    const eyeShow = document.querySelector('.offer-password-toggle .eye-show');
    const eyeHide = document.querySelector('.offer-password-toggle .eye-hide');

    if (passwordInput.type === 'password') {
        passwordInput.type = 'text';
        eyeShow.style.display = 'none';
        eyeHide.style.display = 'block';
    } else {
        passwordInput.type = 'password';
        eyeShow.style.display = 'block';
        eyeHide.style.display = 'none';
    }
}

// Generate HTML for logged-in user view in order modal
function generateLoggedInUserHTML(user) {
    const avatarContent = user.avatar_url
        ? `<img src="${user.avatar_url}" alt="${user.full_name}" class="user-avatar-img">`
        : `<svg width="28" height="28" viewBox="0 0 16 16" fill="currentColor">
               <path d="M11 6a3 3 0 1 1-6 0 3 3 0 0 1 6 0z"/>
               <path fill-rule="evenodd" d="M0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8zm8-7a7 7 0 0 0-5.468 11.37C3.242 11.226 4.805 10 8 10s4.757 1.225 5.468 2.37A7 7 0 0 0 8 1z"/>
           </svg>`;

    return `
        <div class="offer-user-card">
            <div class="offer-user-avatar">
                ${avatarContent}
            </div>
            <div class="offer-user-info">
                <p class="offer-user-name">${user.full_name}</p>
                <p class="offer-user-email">${user.email}</p>
            </div>
            <button type="button" class="offer-logout-btn" onclick="handleLogout()" title="Wyloguj się">
                <svg width="18" height="18" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M7.5 1v7h1V1h-1z"/>
                    <path d="M3 8.812a4.999 4.999 0 0 1 2.578-4.375l-.485-.874A6 6 0 1 0 11 3.616l-.501.865A5 5 0 1 1 3 8.812z"/>
                </svg>
                <span>Wyloguj</span>
            </button>
        </div>

        <div class="offer-form-field">
            <label class="offer-form-label">
                <svg width="18" height="18" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M5 4a.5.5 0 0 0 0 1h6a.5.5 0 0 0 0-1H5zm-.5 2.5A.5.5 0 0 1 5 6h6a.5.5 0 0 1 0 1H5a.5.5 0 0 1-.5-.5zM5 8a.5.5 0 0 0 0 1h6a.5.5 0 0 0 0-1H5zm0 2a.5.5 0 0 0 0 1h3a.5.5 0 0 0 0-1H5z"/>
                    <path d="M2 2a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V2zm10-1H4a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V2a1 1 0 0 0-1-1z"/>
                </svg>
                <span>Notatka do zamówienia <span class="offer-opt">(opcjonalnie)</span></span>
            </label>
            <textarea id="orderNote" class="offer-form-textarea" rows="3" placeholder="Dodatkowe informacje, uwagi, preferencje..."></textarea>
        </div>
    `;
}

// Handle logout from offer page
async function handleLogout() {
    try {
        const response = await fetch('/auth/logout', {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        // Reload page after logout to reset state
        window.location.reload();
    } catch (error) {
        console.error('Logout error:', error);
        // Fallback - redirect to logout URL
        window.location.href = '/auth/logout';
    }
}

// Update order modal to show logged-in user view
function updateOrderModalForLoggedInUser(user) {
    const orderModal = document.getElementById('orderModal');
    if (!orderModal) return;

    const modalBody = orderModal.querySelector('.offer-modal-body');
    if (!modalBody) return;

    // Replace modal body content with logged-in user view
    modalBody.innerHTML = generateLoggedInUserHTML(user);

    // Update global state
    window.isAuthenticated = true;
}

async function handleLogin(event) {
    event.preventDefault();

    const btn = document.getElementById('loginSubmitBtn');
    const originalText = btn.innerHTML;
    const errorEl = document.getElementById('loginError');

    // Hide any previous errors
    errorEl.style.display = 'none';

    // Show overlay with loading animation
    showLoginOverlay();

    // Disable button (as backup, overlay covers it anyway)
    btn.disabled = true;

    try {
        const email = document.getElementById('loginEmail').value;
        const password = document.getElementById('loginPassword').value;

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
            // GA4: Track successful login
            trackUserLoginSuccess();

            // Update order modal with logged-in user view
            updateOrderModalForLoggedInUser(data.user);

            // Set authenticated state
            window.isAuthenticated = true;
            window.currentUserId = data.user.id || null;

            // Remove login required overlay (if present)
            const loginRequiredOverlay = document.getElementById('loginRequiredOverlay');
            if (loginRequiredOverlay) {
                loginRequiredOverlay.classList.add('fade-out');
                setTimeout(() => loginRequiredOverlay.remove(), 400);
            }

            // Hide overlay
            hideLoginOverlay();

            // Close login modal
            closeLoginModal();

            // Initialize reservation system (socket + polling)
            initReservationSystem();

        } else {
            // Hide overlay
            hideLoginOverlay();

            // Show error message
            errorEl.textContent = data.error || 'Nieprawidłowy email lub hasło.';
            errorEl.style.display = 'block';

            // Re-enable button
            btn.disabled = false;
            btn.innerHTML = originalText;
        }

    } catch (error) {
        console.error('Login error:', error);

        // Hide overlay
        hideLoginOverlay();

        // Show error message
        errorEl.textContent = 'Wystąpił błąd połączenia. Spróbuj ponownie.';
        errorEl.style.display = 'block';

        // Re-enable button
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}

let _orderSubmitting = false;

async function submitOrder() {
    // Guard: prevent double-submit (double-tap on mobile)
    if (_orderSubmitting) return;
    _orderSubmitting = true;

    const btn = document.querySelector('.offer-btn-submit');
    const originalText = btn.innerHTML;

    btn.disabled = true;
    btn.style.pointerEvents = 'none';
    btn.innerHTML = '<span>Wysyłanie...</span>';

    try {
        const orderNote = document.getElementById('orderNote').value.trim();

        // Collect full set items from cart (they don't have reservations)
        const fullSetItems = cart
            .filter(item => item.isFullSet && item.qty > 0)
            .map(item => ({ product_id: item.productId, quantity: item.qty }));

        let requestData = {
            session_id: reservationState.sessionId,
            order_note: orderNote || null,
            full_set_items: fullSetItems
        };

        // Order URL set by template
        const response = await fetch(window.placeOrderUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestData)
        });

        if (response.status === 429) {
            alert('Zbyt wiele prób złożenia zamówienia. Poczekaj chwilę i spróbuj ponownie.');
            btn.disabled = false;
            btn.style.pointerEvents = '';
            btn.innerHTML = originalText;
            _orderSubmitting = false;
            return;
        }

        const data = await response.json();

        if (data.success) {
            // GA4: Track order submission
            const totalAmount = cart.reduce((sum, item) => sum + (item.qty * item.price), 0);
            trackOrderSubmitted(data.order_number, totalAmount);

            // Clear localStorage reservation (storage key set by template)
            localStorage.removeItem(window.reservationStorageKey);

            // Zatrzymaj polling i countdown
            if (reservationState.pollingInterval) {
                clearInterval(reservationState.pollingInterval);
                reservationState.pollingInterval = null;
            }
            if (reservationState.countdownInterval) {
                clearInterval(reservationState.countdownInterval);
                reservationState.countdownInterval = null;
            }

            // Redirect to thank you page (URL set by template)
            window.location.href = window.thankYouUrl;
            // Keep _orderSubmitting = true — redirect in progress, block any further submits

        } else {
            let errorMessage = 'Wystąpił błąd podczas składania zamówienia.';

            if (data.error === 'size_required') {
                errorMessage = data.message || 'Wybierz rozmiar dla wszystkich produktów.';
            } else if (data.error === 'no_reservations') {
                errorMessage = 'Brak produktów w koszyku. Rezerwacja mogła wygasnąć.';
            } else if (data.error === 'insufficient_stock') {
                errorMessage = `Produkt "${data.product_name}" nie ma wystarczającej ilości w magazynie.`;
            } else if (data.error === 'page_not_active') {
                errorMessage = 'Sprzedaż nie jest już aktywna.';
            } else if (data.error === 'login_required') {
                errorMessage = data.message || 'Musisz się zalogować, aby złożyć zamówienie.';
            } else if (data.message) {
                errorMessage = data.message;
            }

            alert(errorMessage);
            btn.disabled = false;
            btn.style.pointerEvents = '';
            btn.innerHTML = originalText;
            _orderSubmitting = false;

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
        btn.style.pointerEvents = '';
        btn.innerHTML = originalText;
        _orderSubmitting = false;
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
    countdownInterval: null,
    socketConnected: false,     // Czy SocketIO jest połączony
    forceDisconnected: false,   // Czy sesja została przejęta
};

// Generate UUID v4
function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

/**
 * Sprawdza czy socket jest połączony i gotowy do użycia.
 * Używane jako warunek: socket vs HTTP fallback.
 */
function isSocketReady() {
    return window.offerSocket &&
           window.offerSocket.connected &&
           reservationState.socketConnected &&
           !reservationState.forceDisconnected;
}

// Inicjalizacja systemu rezerwacji
function initReservationSystem() {
    // Blokada dla niezalogowanych - nie uruchamiaj systemu rezerwacji
    if (!window.isAuthenticated) {
        console.log('[Reservation] Użytkownik niezalogowany — system rezerwacji zablokowany');
        return;
    }

    // Klucz localStorage ustawiony przez template
    let stored = localStorage.getItem(window.reservationStorageKey);
    if (stored) {
        try {
            const data = JSON.parse(stored);
            reservationState.sessionId = data.sessionId;
            restoreReservation(data);
        } catch (e) {
            console.error('[Reservation] Błąd parsowania localStorage', e);
            createNewSession();
        }
    } else {
        createNewSession();
    }

    // Próba połączenia SocketIO, fallback na polling
    initSocketConnection();
}

/**
 * Inicjalizuje połączenie SocketIO dla systemu rezerwacji.
 * Jeśli socket niedostępny — fallback na HTTP polling.
 */
function initSocketConnection() {
    const socket = window.offerSocket;

    // Zawsze uruchom polling od razu — daje dane zanim SocketIO się połączy.
    // Polling automatycznie się zatrzyma gdy SocketIO przejmie (logika w startPolling).
    startPolling();
    startStatusPolling();

    if (!socket) {
        console.log('[SocketIO] Niedostępny — polling HTTP aktywny');
        return;
    }

    // --- CONNECT ---
    socket.on('connect', function() {
        console.log('[SocketIO] Połączono, dołączanie do rezerwacji...');
        _joinReservationRoom();
    });

    // --- RECONNECT ---
    socket.on('reconnect', function() {
        console.log('[SocketIO] Ponowne połączenie, synchronizacja stanu...');
        if (!reservationState.forceDisconnected) {
            _joinReservationRoom();
        }
    });

    // --- DISCONNECT ---
    socket.on('disconnect', function() {
        console.log('[SocketIO] Rozłączono');
        reservationState.socketConnected = false;
    });

    // --- AVAILABILITY UPDATED (broadcast z serwera) ---
    socket.on('availability_updated', function(data) {
        if (data && data.products) {
            Object.entries(data.products).forEach(([productId, productData]) => {
                updateProductAvailability(productId, productData);
            });
            // Re-ewaluuj kupony bonusowe (dostępność mogła się zmienić po auto-increase)
            evaluateBonuses();
        }
    });

    // --- PAGE STATUS CHANGED (admin zmienił status) ---
    socket.on('page_status_changed', function(data) {
        handleSaleClosed(data);
    });

    // --- DEADLINE CHANGED (admin zmienił deadline) ---
    socket.on('deadline_changed', function(data) {
        handleDeadlineChanged(data.ends_at);
    });

    // --- FORCE DISCONNECT (sesja przejęta w innej karcie) ---
    socket.on('force_disconnect', function(data) {
        console.warn('[SocketIO] Force disconnect:', data.reason);
        reservationState.forceDisconnected = true;
        reservationState.socketConnected = false;

        // Zatrzymaj countdown timer
        stopCountdown();

        // Zablokuj przyciski +/-
        document.querySelectorAll('.qty-plus, .qty-minus').forEach(btn => {
            btn.disabled = true;
            btn.style.opacity = '0.3';
            btn.style.cursor = 'not-allowed';
        });

        // Pokaż popup z opcją przejęcia kontroli
        showForceDisconnectPopup();
    });

    // --- PRODUCT AVAILABLE (powiadomienie "Powiadom mnie") ---
    socket.on('product_available', function(data) {
        showToast(`Produkt "${data.product_name}" jest ponownie dostępny!`, 'success');
    });

    // Jeśli socket już jest połączony — dołącz od razu
    if (socket.connected) {
        _joinReservationRoom();
    }
}

/**
 * Synchronizuje koszyk UI z rezerwacjami z serwera.
 * Ważne po przejęciu sesji — koszyk na nowym urządzeniu
 * powinien odzwierciedlać przeniesione rezerwacje.
 */
function _syncCartFromSnapshot(products) {
    let hasChanges = false;

    Object.entries(products).forEach(([productId, data]) => {
        const serverQty = data.user_reserved || 0;
        const productElements = document.querySelectorAll(`[data-product-id="${productId}"]`);

        productElements.forEach(element => {
            // Pomiń full-set sections (mają osobną logikę)
            if (element.classList.contains('full-set-section')) return;

            const input = element.querySelector('.qty-input');
            if (!input) return;

            const currentQty = parseInt(input.value) || 0;
            if (currentQty !== serverQty) {
                input.value = serverQty;
                hasChanges = true;
            }
        });
    });

    if (hasChanges) {
        updateCart();
        saveToLocalStorage();
        console.log('[Sync] Koszyk zsynchronizowany z rezerwacjami serwera');
    }
}

/**
 * Dołącza do rooma rezerwacji i pobiera snapshot dostępności.
 */
function _joinReservationRoom() {
    const socket = window.offerSocket;
    if (!socket || !socket.connected) return;

    socket.emit('join_offer_reservation', {
        page_id: window.offerPageId,
        session_id: reservationState.sessionId,
        user_id: window.currentUserId || null,
        token: window.offerPageToken,
    }, function(response) {
        // Ack callback z pełnym snapshotem
        if (response && response.success) {
            console.log('[SocketIO] Dołączono do rezerwacji, snapshot otrzymany');
            reservationState.socketConnected = true;
            reservationState.forceDisconnected = false;

            // Odblokuj przyciski (mogły być zablokowane przez force_disconnect)
            document.querySelectorAll('.qty-plus, .qty-minus').forEach(btn => {
                btn.disabled = false;
                btn.style.opacity = '1';
                btn.style.cursor = 'pointer';
            });

            // Zastosuj snapshot dostępności (updateProductAvailability ponownie zablokuje "+" jeśli available=0)
            if (response.products) {
                // Synchronizuj koszyk UI z server-side rezerwacjami
                // (ważne po przejęciu sesji z innego urządzenia)
                _syncCartFromSnapshot(response.products);

                Object.entries(response.products).forEach(([productId, data]) => {
                    updateProductAvailability(productId, data);
                });

                // Re-ewaluuj kupony bonusowe (teraz productAvailability jest wypełniony)
                evaluateBonuses();
            }

            // Zastosuj info o sesji
            if (response.session && response.session.has_reservations) {
                reservationState.expiresAt = response.session.expires_at;
                reservationState.extended = response.session.extended || false;
                reservationState.firstReservedAt = response.session.first_reserved_at;
                showReservationHeader();
            } else if (response.session && !response.session.has_reservations) {
                hideReservationHeader();
            }

            // Zatrzymaj polling jeśli działa (SocketIO przejmuje)
            if (reservationState.pollingInterval) {
                clearInterval(reservationState.pollingInterval);
                reservationState.pollingInterval = null;
                console.log('[SocketIO] Polling HTTP zatrzymany');
            }
        } else {
            console.warn('[SocketIO] Nie udało się dołączyć:', response);
            // Fallback na polling
            startPolling();
            startStatusPolling();
        }
    });
}

/**
 * Obsługa zamknięcia/wstrzymania sprzedaży (z socketa lub pollingu).
 */
function handleSaleClosed(data) {
    if (!data.is_active) {
        // Sprzedaż nieaktywna — przeładuj stronę
        showToast('Sprzedaż została zakończona lub wstrzymana', 'warning');
        setTimeout(() => {
            window.location.reload();
        }, 2000);
    }
}

/**
 * Obsługa zmiany deadline (z socketa lub pollingu).
 */
function handleDeadlineChanged(endsAt) {
    if (endsAt) {
        window.initialEndsAt = endsAt;
    }
}

/**
 * Status polling — fallback gdy SocketIO niedostępne.
 * Sprawdza status strony co 5s (czy admin nie zamknął sprzedaży).
 */
function startStatusPolling() {
    // Nie uruchamiaj jeśli socket jest połączony
    if (isSocketReady()) return;

    setInterval(async () => {
        // Pomiń jeśli socket się połączył w międzyczasie
        if (isSocketReady()) return;

        try {
            const resp = await fetch(window.statusCheckUrl);
            const data = await resp.json();

            handleSaleClosed(data);

            if (data.ends_at) {
                handleDeadlineChanged(data.ends_at);
            }
        } catch (e) {
            // Cichy błąd
        }
    }, 5000);
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

// Rezerwacja produktu z optimistic UI (SocketIO z HTTP fallback)
function increaseQtyWithReservation(btn) {
    if (btn.disabled || reservationState.forceDisconnected) return;

    const quantityControl = btn.closest('.quantity-control');
    if (!quantityControl) return;

    const input = quantityControl.querySelector('.qty-input');
    if (!input) return;

    const productSection = input.closest('.section-product, .set-item, .variant-product');
    const productId = productSection.dataset.productId;

    // Size validation - require size selection before adding to cart
    const sizeSelector = document.querySelector(`.size-selector[data-product-id="${productId}"]`);
    if (sizeSelector && !selectedProductSizes[productId]) {
        sizeSelector.classList.add('size-required');
        setTimeout(() => sizeSelector.classList.remove('size-required'), 1500);
        return;
    }

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

    // NATYCHMIASTOWY update UI
    input.value = val + 1;
    optimisticUpdateAvailability(productId, -1);
    updateCart();
    saveToLocalStorage();

    // Callback po odpowiedzi (wspólny dla socket i HTTP)
    function onSuccess(result) {
        if (result.reservation && result.reservation.first_reservation_at) {
            reservationState.firstReservedAt = result.reservation.first_reservation_at;
            reservationState.expiresAt = result.reservation.expires_at;
            showReservationHeader();
        }
        // GA4: Track dodanie do koszyka (tylko przy pierwszym dodaniu)
        if (val === 0) {
            const cartItem = cart.find(item => item.productId == productId);
            if (cartItem) {
                trackProductAddedToCart(cartItem.name, productId, cartItem.price, 1);
            }
        }
    }

    function onError(result) {
        input.value = Math.max(0, parseInt(input.value) - 1);
        optimisticUpdateAvailability(productId, +1);
        updateCart();
        saveToLocalStorage();
        if (result && result.error === 'insufficient_availability') {
            showUnavailablePopup(result.message, result.check_back_at);
        } else if (result && result.error === 'rate_limited') {
            if (typeof showToast === 'function') {
                showToast(result.message || 'Zbyt wiele prób. Poczekaj chwilę.', 'warning');
            }
        } else if (result && result.error === 'login_required') {
            showToast('Zaloguj się, aby rezerwować produkty.', 'warning');
        } else if (result && result.error === 'reservation_expired') {
            showToast(result.message || 'Twoja rezerwacja wygasła.', 'error');
            clearReservation();
        } else if (result && result.message) {
            showToast(result.message, 'error');
        }
    }

    // SocketIO lub HTTP fallback
    if (isSocketReady()) {
        window.offerSocket.emit('reserve_product', {
            page_id: window.offerPageId,
            session_id: reservationState.sessionId,
            product_id: productId,
            quantity: 1,
            selected_size: selectedProductSizes[productId] || null,
        }, function(result) {
            if (result && result.success) {
                onSuccess(result);
            } else {
                onError(result);
            }
        });
    } else {
        fetch(window.reserveProductUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: reservationState.sessionId,
                product_id: productId,
                quantity: 1,
                action: val === 0 ? 'add' : 'increase',
                selected_size: selectedProductSizes[productId] || null
            })
        }).then(r => {
            if (r.status === 429) {
                onError({ error: 'rate_limited', message: 'Zbyt wiele prób. Poczekaj chwilę.' });
                return;
            }
            return r.json();
        }).then(result => {
            if (!result) return; // 429 — już obsłużone
            if (result.success) {
                onSuccess(result);
            } else {
                onError(result);
            }
        }).catch(() => onError(null));
    }
}

// Zwolnienie rezerwacji produktu (SocketIO z HTTP fallback)
function decreaseQtyWithReservation(btn) {
    if (btn.disabled || reservationState.forceDisconnected) return;

    const quantityControl = btn.closest('.quantity-control');
    if (!quantityControl) return;

    const input = quantityControl.querySelector('.qty-input');
    if (!input) return;

    let val = parseInt(input.value) || 0;
    if (val === 0) return;

    const productSection = input.closest('.section-product, .set-item, .variant-product');
    const productId = productSection.dataset.productId;

    // NATYCHMIASTOWY update UI
    input.value = val - 1;
    optimisticUpdateAvailability(productId, +1);
    updateCart();
    saveToLocalStorage();

    if (cart.length === 0) {
        hideReservationHeader();
    }

    // SocketIO lub HTTP fallback
    if (isSocketReady()) {
        window.offerSocket.emit('release_product', {
            page_id: window.offerPageId,
            session_id: reservationState.sessionId,
            product_id: productId,
            quantity: 1,
        });
    } else {
        fetch(window.releaseProductUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: reservationState.sessionId,
                product_id: productId,
                quantity: 1,
                action: 'decrease'
            })
        }).catch(() => {});
    }
}

// Polling dostępności — FALLBACK gdy SocketIO niedostępne (co 1s)
function startPolling() {
    if (reservationState.pollingInterval) return;
    // Nie uruchamiaj jeśli socket jest gotowy
    if (isSocketReady()) return;

    console.log('[Polling] Uruchomiono HTTP polling (fallback)');
    reservationState.pollingInterval = setInterval(async () => {
        // Zatrzymaj polling jeśli socket się połączył
        if (isSocketReady()) {
            clearInterval(reservationState.pollingInterval);
            reservationState.pollingInterval = null;
            console.log('[Polling] Zatrzymano — SocketIO przejął');
            return;
        }
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

        if (shouldDisable || reservationState.forceDisconnected) {
            plusBtn.disabled = true;
            plusBtn.style.opacity = shouldDisable ? '0.5' : '0.3';
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

    // Handle notification bell visibility
    updateNotificationBellVisibility(productId, available);
}

function optimisticUpdateAvailability(productId, delta) {
    if (productAvailability[productId] === undefined) return;
    if (productAvailability[productId] >= 999999) return;

    productAvailability[productId] = Math.max(0, productAvailability[productId] + delta);

    const availabilityElements = document.querySelectorAll(`[data-availability-for="${productId}"]`);
    availabilityElements.forEach(el => el.classList.add('availability-updating'));

    renderAvailabilityInfo(productId, productAvailability[productId]);

    // Zablokuj/odblokuj przycisk "+" w zależności od dostępności
    const productElements = document.querySelectorAll(`[data-product-id="${productId}"]`);
    productElements.forEach(element => {
        const quantityControl = element.querySelector('.quantity-control');
        if (!quantityControl) return;
        const plusBtn = quantityControl.querySelector('.qty-plus');
        if (!plusBtn) return;

        if (productAvailability[productId] <= 0) {
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

function showReservationHeader() {
    const header = document.getElementById('reservationHeader');
    header.classList.remove('hidden');

    const extendBtn = document.getElementById('extendBtn');
    extendBtn.disabled = true;
    extendBtn.textContent = reservationState.extended ? 'Przedłużono' : 'Przedłuż +1 min';

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
    const extendTooltip = document.getElementById('extendTooltip');
    const canExtend = !reservationState.extended && diff < 60;
    extendBtn.disabled = !canExtend;

    if (reservationState.extended) {
        extendBtn.textContent = 'Przedłużono';
        if (extendTooltip) {
            extendTooltip.textContent = 'Rezerwację można przedłużyć tylko raz';
        }
    } else if (diff >= 60) {
        extendBtn.textContent = 'Przedłuż +1 min';
        if (extendTooltip) {
            extendTooltip.textContent = 'Możesz przedłużyć gdy zostanie < 1 min';
        }
    } else {
        extendBtn.textContent = 'Przedłuż +1 min';
    }

    const header = document.getElementById('reservationHeader');
    if (diff < 60) {
        header.classList.add('reservation-warning');
    } else {
        header.classList.remove('reservation-warning');
    }
}

// Przedłużenie rezerwacji (SocketIO z HTTP fallback)
async function extendReservation() {
    if (reservationState.extended) return;

    function onSuccess(result) {
        reservationState.expiresAt = result.new_expires_at;
        reservationState.extended = true;
        saveToLocalStorage();
        showToast('Rezerwacja przedłużona o 2 minuty', 'success');
    }

    function onError(result) {
        const msg = (result && result.message) || 'Nie można przedłużyć rezerwacji';
        showToast(msg, 'error');

        // Jeśli rezerwacja wygasła — wyczyść koszyk
        if (result && result.error === 'reservation_expired') {
            clearReservation();
        }
    }

    if (isSocketReady()) {
        window.offerSocket.emit('extend_reservation', {
            page_id: window.offerPageId,
            session_id: reservationState.sessionId,
        }, function(result) {
            if (result && result.success) {
                onSuccess(result);
            } else {
                onError(result);
            }
        });
    } else {
        try {
            const response = await fetch(window.extendReservationUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: reservationState.sessionId
                })
            });

            const result = await response.json();

            if (result.success) {
                onSuccess(result);
            } else {
                onError(result);
            }
        } catch (error) {
            console.error('[Extend] Błąd:', error);
            onError('Błąd przedłużania rezerwacji');
        }
    }
}

function clearReservation() {
    // Zwolnij rezerwacje na serwerze (żeby produkty były dostępne natychmiast)
    _releaseAllServerReservations();

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

/**
 * Zwalnia wszystkie rezerwacje sesji na serwerze.
 * Fire-and-forget — nie czekamy na odpowiedź.
 */
function _releaseAllServerReservations() {
    // Zbierz produkty z koszyka które mają qty > 0 (pomijaj full sety — nie mają rezerwacji)
    const productsToRelease = [];
    document.querySelectorAll('.qty-input:not(.full-set-qty-input)').forEach(input => {
        const qty = parseInt(input.value) || 0;
        if (qty <= 0) return;
        const section = input.closest('[data-product-id]');
        if (section) {
            productsToRelease.push({
                product_id: parseInt(section.dataset.productId),
                quantity: qty
            });
        }
    });

    if (productsToRelease.length === 0) return;

    for (const item of productsToRelease) {
        if (isSocketReady()) {
            window.offerSocket.emit('release_product', {
                page_id: window.offerPageId,
                session_id: reservationState.sessionId,
                product_id: item.product_id,
                quantity: item.quantity,
            });
        } else {
            fetch(window.releaseProductUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: reservationState.sessionId,
                    product_id: item.product_id,
                    quantity: item.quantity,
                })
            }).catch(() => {});
        }
    }
}

function showUnavailablePopup(message, checkBackAtTimestamp) {
    let checkBackHtml = '';
    if (checkBackAtTimestamp) {
        const checkBackDate = new Date(checkBackAtTimestamp * 1000);
        const formatter = new Intl.DateTimeFormat('pl-PL', {
            timeZone: 'Europe/Warsaw',
            hour: '2-digit',
            minute: '2-digit'
        });
        const timeStr = formatter.format(checkBackDate);
        checkBackHtml = `<p class="check-back" style="margin-bottom:24px;">Sprawdź dostępność o <strong>${timeStr}</strong></p>`;
    }

    const modal = document.createElement('div');
    modal.className = 'unavailable-modal';
    modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);display:flex;align-items:center;justify-content:center;z-index:10001;';
    modal.innerHTML = `
        <div class="unavailable-content" style="background:white;padding:32px;border-radius:12px;max-width:500px;text-align:center;">
            <div class="unavailable-icon" style="font-size:48px;margin-bottom:16px;">⚠️</div>
            <h3 style="margin-bottom:16px;">Produkt niedostępny</h3>
            <p style="margin-bottom:16px;">${message}</p>
            ${checkBackHtml}
            <button onclick="this.closest('.unavailable-modal').remove()" class="btn-close-modal" style="padding:12px 24px;background:#7B2CBF;color:white;border:none;border-radius:8px;cursor:pointer;">
                Rozumiem
            </button>
        </div>
    `;

    document.body.appendChild(modal);
}

function showForceDisconnectPopup() {
    // Usuń istniejący popup jeśli jest (unikaj duplikatów)
    const existing = document.querySelector('.force-disconnect-modal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.className = 'force-disconnect-modal';
    modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);display:flex;align-items:center;justify-content:center;z-index:10001;';
    modal.innerHTML = `
        <div style="background:white;padding:32px;border-radius:12px;max-width:500px;text-align:center;">
            <div style="font-size:48px;margin-bottom:16px;">🔒</div>
            <h3 style="margin-bottom:16px;">Sesja przejęta</h3>
            <p style="margin-bottom:24px;">Twoja sesja została przeniesiona na inną kartę lub urządzenie. Przyciski zostały zablokowane.</p>
            <div style="display:flex;gap:12px;justify-content:center;">
                <button class="btn-takeover" style="padding:12px 24px;background:#7B2CBF;color:white;border:none;border-radius:8px;cursor:pointer;font-weight:600;">
                    Przejmij kontrolę
                </button>
                <button class="btn-close-popup" style="padding:12px 24px;background:#e0e0e0;color:#333;border:none;border-radius:8px;cursor:pointer;">
                    Zamknij
                </button>
            </div>
        </div>
    `;

    modal.querySelector('.btn-takeover').addEventListener('click', function() {
        takeOverSession();
        modal.remove();
    });

    modal.querySelector('.btn-close-popup').addEventListener('click', function() {
        // Rozłącz socket żeby nie odbierać broadcastów na przejętej sesji
        const socket = window.offerSocket;
        if (socket && socket.connected) {
            socket.disconnect();
        }
        modal.remove();
    });

    document.body.appendChild(modal);
}

function takeOverSession() {
    const socket = window.offerSocket;
    if (!socket) return;

    // Reset flagi — pozwól reconnectowi
    reservationState.forceDisconnected = false;

    // Jeśli socket rozłączony — reconnect (on connect wywoła _joinReservationRoom)
    if (!socket.connected) {
        socket.connect();
        return;
    }

    // Socket jest połączony — dołącz ponownie (serwer zrobi force takeover na "nową" kartę)
    _joinReservationRoom();
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
            if (cart.length === 0) {
                hideReservationHeader();
            }
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

    // Zwolnienie rezerwacji — SocketIO lub HTTP fallback
    input.value = 0;
    optimisticUpdateAvailability(productId, +currentQty);
    updateCart();
    saveToLocalStorage();

    if (cart.length === 0) {
        hideReservationHeader();
    }

    if (isSocketReady()) {
        window.offerSocket.emit('release_product', {
            page_id: window.offerPageId,
            session_id: reservationState.sessionId,
            product_id: productId,
            quantity: currentQty,
        });
    } else {
        try {
            await fetch(window.releaseProductUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: reservationState.sessionId,
                    product_id: productId,
                    quantity: currentQty
                })
            });
            await checkAvailability();
        } catch (error) {
            console.error('[Cart] Błąd zwalniania produktu:', error);
        }
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
// Full sets are unlimited — no time-limited reservations needed.
// ============================================

// Helper: check if cart has any regular (non-full-set) products
function hasRegularProductsInCart() {
    return cart.some(item => !item.isFullSet);
}

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
    const maxFullSets = 5;

    if (val >= maxFullSets) {
        if (window.Toast) window.Toast.show('Maksymalnie ' + maxFullSets + ' pełnych setów w jednym zamówieniu', 'warning');
        return;
    }

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

        // Hide reservation header only if no regular products remain
        if (!hasRegularProductsInCart()) {
            hideReservationHeader();
        }

        // Full sets are unlimited — no release needed
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
    const maxFullSets = 5;
    if (val < 0) val = 0;
    if (val > maxFullSets) {
        val = maxFullSets;
        if (window.Toast) window.Toast.show('Maksymalnie ' + maxFullSets + ' pełnych setów w jednym zamówieniu', 'warning');
    }
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

    // Full sets are unlimited — no reservation/release needed.
    // Hide reservation header only if no regular products remain.
    if (delta < 0 && !hasRegularProductsInCart()) {
        hideReservationHeader();
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
    evaluateBonuses();

    // GA4: Track offer page view (once on load)
    trackOfferPageViewed();
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


// ============================================
// NOTIFICATION SUBSCRIPTION MODULE
// ============================================

// Current product ID for notification subscription
let currentNotificationProductId = null;

/**
 * Updates visibility of notification bell based on product availability
 * @param {number} productId - Product ID
 * @param {number} available - Available quantity
 */
function updateNotificationBellVisibility(productId, available) {
    // Find all quantity wrappers for this product
    const availabilityElements = document.querySelectorAll(`[data-availability-for="${productId}"]`);

    availabilityElements.forEach(el => {
        const quantityWrapper = el.closest('.quantity-wrapper');
        if (!quantityWrapper) return;

        const quantityControl = quantityWrapper.querySelector('.quantity-control');
        if (!quantityControl) return;

        // Check if bell already exists
        let bellBtn = quantityWrapper.querySelector('.notification-bell-btn');

        // Check if current user has this product in cart (they reserved it)
        const qtyInput = quantityControl.querySelector('.qty-input');
        const currentUserQty = qtyInput ? (parseInt(qtyInput.value) || 0) : 0;

        // Show bell only if: product unavailable AND current user doesn't have any reserved
        const shouldShowBell = available <= 0 && currentUserQty === 0;

        if (shouldShowBell) {
            // Product is unavailable and user doesn't have it - show bell, hide quantity control
            quantityControl.style.display = 'none';

            if (!bellBtn) {
                // Create bell button
                bellBtn = document.createElement('button');
                bellBtn.type = 'button';
                bellBtn.className = 'notification-bell-btn';
                bellBtn.setAttribute('data-product-id', productId);
                bellBtn.onclick = function() { openNotificationModal(productId); };
                bellBtn.innerHTML = `
                    <svg width="24" height="24" viewBox="0 0 16 16" fill="currentColor">
                        <path d="M8 16a2 2 0 0 0 2-2H6a2 2 0 0 0 2 2zM8 1.918l-.797.161A4.002 4.002 0 0 0 4 6c0 .628-.134 2.197-.459 3.742-.16.767-.376 1.566-.663 2.258h10.244c-.287-.692-.502-1.49-.663-2.258C12.134 8.197 12 6.628 12 6a4.002 4.002 0 0 0-3.203-3.92L8 1.917zM14.22 12c.223.447.481.801.78 1H1c.299-.199.557-.553.78-1C2.68 10.2 3 6.88 3 6c0-2.42 1.72-4.44 4.005-4.901a1 1 0 1 1 1.99 0A5.002 5.002 0 0 1 13 6c0 .88.32 4.2 1.22 6z"/>
                    </svg>
                    <span>Powiadom mnie</span>
                `;
                quantityWrapper.insertBefore(bellBtn, quantityControl);
            }
            bellBtn.style.display = '';
        } else {
            // Product is available OR user has it reserved - show quantity control, hide bell
            quantityControl.style.display = '';

            if (bellBtn) {
                bellBtn.style.display = 'none';
            }
        }
    });
}

/**
 * Opens notification subscription modal
 * @param {number} productId - Product ID
 */
function openNotificationModal(productId) {
    // Subskrypcja wymaga zalogowania.
    if (!window.isAuthenticated) {
        openLoginModal();
        return;
    }

    currentNotificationProductId = productId;

    const modal = document.getElementById('notificationModal');
    const productNameEl = document.getElementById('notificationProductName');

    // Try to find product name
    const productCard = document.querySelector(`[data-product-id="${productId}"]`);
    let productName = 'tego produktu';

    if (productCard) {
        const nameEl = productCard.querySelector('.product-name, .variant-name, h4');
        if (nameEl) {
            productName = nameEl.textContent.trim();
        }
    }

    // Also try to find via availability element
    if (productName === 'tego produktu') {
        const availEl = document.querySelector(`[data-availability-for="${productId}"]`);
        if (availEl) {
            const section = availEl.closest('.section-product, .set-item, .variant-option');
            if (section) {
                const nameEl = section.querySelector('.product-name, .variant-name, .set-item-name');
                if (nameEl) {
                    productName = nameEl.textContent.trim();
                }
            }
        }
    }

    productNameEl.textContent = `o dostępności: ${productName}`;

    const submitBtn = document.getElementById('notificationSubmitBtn');
    if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.querySelector('span').textContent = 'Powiadom mnie';
    }

    modal.classList.add('active');
}

/**
 * Closes notification subscription modal
 */
function closeNotificationModal() {
    const modal = document.getElementById('notificationModal');
    modal.classList.remove('active');
    currentNotificationProductId = null;
}

/**
 * Submits notification subscription
 */
async function submitNotificationSubscription() {
    if (!currentNotificationProductId) return;

    const submitBtn = document.getElementById('notificationSubmitBtn');

    // Disable button
    submitBtn.disabled = true;
    submitBtn.querySelector('span').textContent = 'Zapisuję...';

    try {
        const response = await fetch(window.subscribeNotificationUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                product_id: currentNotificationProductId
            })
        });

        const data = await response.json();

        if (data.success) {
            // Show success state
            submitBtn.querySelector('span').textContent = 'Zapisano!';
            submitBtn.classList.add('success');

            // Show toast
            if (typeof showToast === 'function') {
                showToast(data.message || 'Zapisano na powiadomienie!', 'success');
            }

            // Close modal after delay
            setTimeout(() => {
                closeNotificationModal();
            }, 1500);
        } else {
            showNotificationError(data.message || 'Wystąpił błąd');
            submitBtn.disabled = false;
            submitBtn.querySelector('span').textContent = 'Powiadom mnie';
        }
    } catch (error) {
        console.error('Notification subscription error:', error);
        showNotificationError('Wystąpił błąd. Spróbuj ponownie.');
        submitBtn.disabled = false;
        submitBtn.querySelector('span').textContent = 'Powiadom mnie';
    }
}

/**
 * Shows error message as toast (notification modal no longer has inline email field)
 * @param {string} message - Error message
 */
function showNotificationError(message) {
    if (typeof showToast === 'function') {
        showToast(message, 'error');
    }
}

// Close modal on overlay click
document.addEventListener('DOMContentLoaded', function() {
    const modal = document.getElementById('notificationModal');
    if (modal) {
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                closeNotificationModal();
            }
        });
    }
});

// ============================================
// STATUS & DEADLINE — SocketIO push + HTTP fallback
// ============================================
(function() {
    // Pomiń w trybie podglądu
    if (window.previewMode) return;
    if (!window.statusCheckUrl) return;

    let currentEndsAt = window.initialEndsAt;
    let _statusPollingInterval = null;
    let _isClosed = false;

    /**
     * Formatuje datę deadline do wyświetlenia
     */
    function formatDeadlineDate(date) {
        const day = String(date.getDate()).padStart(2, '0');
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const year = date.getFullYear();
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        return `${day}.${month}.${year}, ${hours}:${minutes}`;
    }

    /**
     * Inicjalizuje lub reinicjalizuje timer deadline
     */
    function initializeDeadlineTimer(deadlineStr) {
        const deadlineDate = new Date(deadlineStr);
        const dynamicCountdown = document.getElementById('dynamicCountdown');
        const countdownTime = document.getElementById('countdownTime');

        if (window._deadlineTimerInterval) {
            clearInterval(window._deadlineTimerInterval);
        }

        function formatTime(minutes, seconds) {
            return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
        }

        function updateTimer() {
            const now = new Date();
            const diff = deadlineDate - now;

            if (diff <= 0) {
                window.location.reload();
                return;
            }

            const totalSeconds = Math.floor(diff / 1000);
            const totalMinutes = Math.floor(totalSeconds / 60);
            const minutes = Math.floor(totalMinutes % 60);
            const seconds = totalSeconds % 60;

            if (totalMinutes < 10 && dynamicCountdown && countdownTime) {
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
        }

        updateTimer();
        window._deadlineTimerInterval = setInterval(updateTimer, 1000);
    }

    // Nadpisz globalne handlery — wzbogacone o UI deadline
    const _origHandleSaleClosed = window.handleSaleClosed || handleSaleClosed;
    handleSaleClosed = function(data) {
        if (_isClosed) return;

        // Obsługa danych z SocketIO (obiekt z is_active) lub z pollingu
        const isActive = data ? data.is_active : false;
        const isClosed = data ? (data.is_manually_closed || !isActive) : true;

        if (!isClosed) return;

        _isClosed = true;
        if (_statusPollingInterval) {
            clearInterval(_statusPollingInterval);
            _statusPollingInterval = null;
        }

        if (typeof showToast === 'function') {
            showToast('Sprzedaż została zakończona lub wstrzymana', 'info');
        }
        setTimeout(() => window.location.reload(), 2000);
    };

    const _origHandleDeadlineChanged = window.handleDeadlineChanged || handleDeadlineChanged;
    handleDeadlineChanged = function(newEndsAt) {
        if (newEndsAt === currentEndsAt) return;

        const oldEndsAt = currentEndsAt;
        currentEndsAt = newEndsAt;
        window.initialEndsAt = newEndsAt;

        if (!newEndsAt) {
            window.location.reload();
            return;
        }

        const headerRight = document.querySelector('.header-right');
        if (!headerRight) return;

        const newDeadlineDate = new Date(newEndsAt);
        const formattedDate = formatDeadlineDate(newDeadlineDate);

        const existingBanner = headerRight.querySelector('.deadline-banner:not(.deadline-unknown)');
        const unknownBanner = headerRight.querySelector('.deadline-unknown');

        if (unknownBanner) {
            unknownBanner.outerHTML = `
                <div class="deadline-banner" data-deadline="${newEndsAt}">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                        <path d="M8 3.5a.5.5 0 0 0-1 0V9a.5.5 0 0 0 .252.434l3.5 2a.5.5 0 0 0 .496-.868L8 8.71V3.5z"/>
                        <path d="M8 16A8 8 0 1 0 8 0a8 8 0 0 0 0 16zm7-8A7 7 0 1 1 1 8a7 7 0 0 1 14 0z"/>
                    </svg>
                    <span>Koniec zamówień: <strong>${formattedDate}</strong></span>
                </div>
                <div id="dynamicCountdown" class="deadline-countdown hidden">
                    <svg width="18" height="18" viewBox="0 0 16 16" fill="currentColor">
                        <path d="M8 3.5a.5.5 0 0 0-1 0V9a.5.5 0 0 0 .252.434l3.5 2a.5.5 0 0 0 .496-.868L8 8.71V3.5z"/>
                        <path d="M8 16A8 8 0 1 0 8 0a8 8 0 0 0 0 16zm7-8A7 7 0 1 1 1 8a7 7 0 0 1 14 0z"/>
                    </svg>
                    <span>Do końca: <strong id="countdownTime">--:--</strong></span>
                </div>
            `;

            initializeDeadlineTimer(newEndsAt);

            if (typeof showToast === 'function') {
                showToast('Ustawiono datę zakończenia sprzedaży: ' + formattedDate, 'info');
            }
        } else if (existingBanner) {
            existingBanner.setAttribute('data-deadline', newEndsAt);
            const strongEl = existingBanner.querySelector('strong');
            if (strongEl) {
                strongEl.textContent = formattedDate;
            }

            initializeDeadlineTimer(newEndsAt);

            if (typeof showToast === 'function') {
                showToast('Zmieniono datę zakończenia sprzedaży: ' + formattedDate, 'info');
            }
        }
    };

    // HTTP fallback polling — uruchamiany TYLKO gdy socket niedostępny
    // SocketIO listenery (page_status_changed, deadline_changed) obsługują to automatycznie
    function startStatusPollingFallback() {
        if (isSocketReady()) return; // Socket obsługuje — nie potrzeba pollingu

        _statusPollingInterval = setInterval(async () => {
            // Zatrzymaj polling jeśli socket się połączył
            if (isSocketReady()) {
                clearInterval(_statusPollingInterval);
                _statusPollingInterval = null;
                return;
            }

            if (_isClosed) return;

            try {
                const response = await fetch(window.statusCheckUrl);
                if (!response.ok) return;

                const data = await response.json();

                if (data.is_manually_closed || !data.is_active) {
                    handleSaleClosed(data);
                    return;
                }

                if (data.ends_at !== currentEndsAt) {
                    handleDeadlineChanged(data.ends_at);
                }
            } catch (e) {
                // Cichy błąd
            }
        }, 5000); // Co 5s zamiast co 1s (SocketIO obsługuje natychmiast)
    }

    // Uruchom fallback polling po krótkim opóźnieniu
    // (dając czas SocketIO na połączenie)
    setTimeout(() => {
        if (!isSocketReady()) {
            startStatusPollingFallback();
        }
    }, 3000);
})();


// ============================================
// BONUS (GRATIS) SYSTEM
// ============================================

/**
 * Check if a buy_products bonus can be claimed (all required products available).
 */
function canClaimBonus(bonus, sectionEl) {
    if (!bonus || bonus.trigger_type !== 'buy_products' || !sectionEl) return false;

    // Check if bonus is exhausted (max_available reached)
    if (bonus.max_available !== null && bonus.max_available !== undefined) {
        if ((bonus.already_claimed || 0) >= bonus.max_available) return false;
    }

    // Full set contribution
    let fullSetQty = 0;
    if (bonus.count_full_set) {
        const fsInput = sectionEl.querySelector('.full-set-qty-input');
        fullSetQty = fsInput ? (parseInt(fsInput.value) || 0) : 0;
    }

    for (const req of bonus.required_products) {
        const itemEl = sectionEl.querySelector(`.set-item[data-product-id="${req.product_id}"]`);
        if (!itemEl) return false;

        const input = itemEl.querySelector('.qty-input');
        let currentQty = input ? (parseInt(input.value) || 0) : 0;

        // Full set provides quantityPerSet of each product
        if (fullSetQty > 0) {
            const qps = parseInt(itemEl.dataset.quantityPerSet) || 1;
            currentQty += fullSetQty * qps;
        }

        const needed = req.min_quantity - currentQty;

        if (needed > 0) {
            const available = productAvailability[req.product_id];
            if (available !== undefined && available < 999999 && available < needed) return false;
        }
    }
    return true;
}

/**
 * Check if a bonus is unavailable due to stock issues.
 * Returns true only if a required product has no stock AND the current user
 * doesn't already have it in their cart (their own reservation).
 */
function isBonusUnavailable(bonus, sectionEl) {
    if (!bonus.required_products) return false;

    for (const req of bonus.required_products) {
        const available = productAvailability[req.product_id];
        // Jeśli dostępność nie jest jeszcze załadowana, nie oznaczaj jako niedostępne
        if (available === undefined) continue;
        // Jeśli jest dostępny — OK
        if (available > 0) continue;

        // available === 0 — sprawdź czy użytkownik ma ten produkt w koszyku
        const inCart = cart.find(item => item.productId === req.product_id && !item.isBonus);
        if (inCart && inCart.qty >= req.min_quantity) {
            // Użytkownik sam zarezerwował wymagane sztuki — nie jest niedostępne dla niego
            continue;
        }

        return true;
    }
    return false;
}

/**
 * Claim a bonus by adding the required products to the cart.
 * Simulates clicking the + button for each missing product.
 */
function claimBonus(sectionId, bonusId) {
    const config = window.bonusesConfig;
    if (!config || !config[sectionId]) return;

    const bonus = config[sectionId].find(b => b.id === bonusId);
    if (!bonus || bonus.trigger_type !== 'buy_products') return;

    const sectionEl = document.querySelector(`.section-set[data-section-id="${sectionId}"]`);
    if (!sectionEl) return;

    // Suppress evaluateBonuses() calls during batch claiming
    window._claimingBonus = true;

    // Full set contribution
    let fullSetQty = 0;
    if (bonus.count_full_set) {
        const fsInput = sectionEl.querySelector('.full-set-qty-input');
        fullSetQty = fsInput ? (parseInt(fsInput.value) || 0) : 0;
    }

    for (const req of bonus.required_products) {
        const itemEl = sectionEl.querySelector(`.set-item[data-product-id="${req.product_id}"]`);
        if (!itemEl) continue;

        const input = itemEl.querySelector('.qty-input');
        if (!input) continue;

        let currentQty = parseInt(input.value) || 0;

        // Account for full set contribution
        if (fullSetQty > 0) {
            const qps = parseInt(itemEl.dataset.quantityPerSet) || 1;
            currentQty += fullSetQty * qps;
        }

        const needed = req.min_quantity - currentQty;

        if (needed > 0) {
            const plusBtn = itemEl.querySelector('.qty-plus');
            if (plusBtn && !plusBtn.disabled) {
                for (let i = 0; i < needed; i++) {
                    plusBtn.click();
                }
            }
        }
    }

    // Re-enable and trigger a single full update
    window._claimingBonus = false;
    updateCart();
}

/**
 * Evaluate bonuses based on current cart state.
 * Called from updateCart().
 * Adds bonus items to cart[] and updates bonus UI (progress bars, bundle sections).
 */
function evaluateBonuses() {
    // NOTE: already_claimed is static (loaded at page load). Real-time updates would require WebSocket integration.
    const config = window.bonusesConfig;
    if (!config || typeof config !== 'object') return;

    // Remove existing bonus items from cart
    cart = cart.filter(item => !item.isBonus);

    // Get regular (non-bonus) cart items grouped by section
    const regularItems = cart.filter(item => !item.isBonus);

    // Build section->products mapping from DOM
    const sectionProducts = {};
    document.querySelectorAll('.section-set').forEach(sectionEl => {
        const sectionId = sectionEl.dataset.sectionId;
        if (!sectionId) return;

        sectionProducts[sectionId] = [];

        // Collect individual set items
        sectionEl.querySelectorAll('.set-item').forEach(itemEl => {
            const productId = parseInt(itemEl.dataset.productId);
            if (!productId) return;

            const cartItem = regularItems.find(ci => ci.productId === productId && !ci.isFullSet);
            if (!sectionProducts[sectionId].find(p => p.productId === productId)) {
                sectionProducts[sectionId].push({
                    productId,
                    qty: cartItem ? cartItem.qty : 0,
                    price: cartItem ? cartItem.price : 0,
                    quantityPerSet: parseInt(itemEl.dataset.quantityPerSet) || 1,
                });
            }
        });

        // Also collect variant products within set
        sectionEl.querySelectorAll('.variant-product').forEach(vpEl => {
            const productId = parseInt(vpEl.dataset.productId);
            if (!productId) return;

            const cartItem = regularItems.find(ci => ci.productId === productId && !ci.isFullSet);
            if (!sectionProducts[sectionId].find(p => p.productId === productId)) {
                sectionProducts[sectionId].push({
                    productId,
                    qty: cartItem ? cartItem.qty : 0,
                    price: cartItem ? cartItem.price : 0,
                    quantityPerSet: 1,
                });
            }
        });
    });

    // Evaluate each section's bonuses
    for (const [sectionId, bonuses] of Object.entries(config)) {
        const products = sectionProducts[sectionId] || [];
        const bonusContainer = document.querySelector(`.bonus-container[data-section-id="${sectionId}"]`);

        // Full set qty for this section
        let fullSetQty = 0;
        let itemsPerSet = 0;
        const sectionEl = document.querySelector(`.section-set[data-section-id="${sectionId}"]`);
        if (sectionEl) {
            const fsInput = sectionEl.querySelector('.full-set-qty-input');
            fullSetQty = fsInput ? (parseInt(fsInput.value) || 0) : 0;
            // Count total items per one full set (sum of quantity_per_set for all products)
            sectionEl.querySelectorAll('.set-item').forEach(itemEl => {
                itemsPerSet += parseInt(itemEl.dataset.quantityPerSet) || 1;
            });
        }

        let bonusHtml = '';

        for (const bonus of bonuses) {
            let earned = 0;

            if (bonus.is_exhausted) {
                bonusHtml += `
                    <div class="bonus-coupon bonus-exhausted" data-bonus-id="${bonus.id}">
                        <div class="bonus-coupon-icon-area">
                            <span class="bonus-coupon-icon">🎁</span>
                        </div>
                        <div class="bonus-coupon-body">
                            <div class="bonus-coupon-title">${bonus.bonus_product_name}</div>
                            <div class="bonus-coupon-exhausted-text">Wyczerpany</div>
                        </div>
                    </div>`;
                continue;
            }

            if (bonus.trigger_type === 'buy_products') {
                const bundleCounts = [];
                const prevFullSetQty = bonus.prev_full_set_qty || 0;
                const totalFullSetQty = fullSetQty + prevFullSetQty;
                for (const req of bonus.required_products) {
                    const inCart = products.find(p => p.productId === req.product_id);
                    let qty = inCart ? inCart.qty : 0;
                    // Add previous orders quantity
                    qty += (bonus.prev_product_counts && bonus.prev_product_counts[String(req.product_id)]) || 0;
                    // Full set contribution (current + previous)
                    if (bonus.count_full_set && totalFullSetQty > 0) {
                        const qps = inCart ? (inCart.quantityPerSet || 1) : 1;
                        qty += totalFullSetQty * qps;
                    }
                    bundleCounts.push(Math.floor(qty / req.min_quantity));
                }
                earned = bundleCounts.length > 0 ? Math.min(...bundleCounts) : 0;
                // Subtract bonuses already earned in previous orders
                earned = Math.max(0, earned - (bonus.user_already_earned || 0));

                if (bonus.max_available !== null) {
                    earned = Math.min(earned, bonus.max_available - bonus.already_claimed);
                }

                const isUnlocked = earned > 0 && regularItems.length > 0;
                const isUnavailable = isBonusUnavailable(bonus, sectionEl);
                const canClaim = !isUnlocked && !isUnavailable && canClaimBonus(bonus, sectionEl);
                const reqLines = bonus.required_products.map(r =>
                    `<div class="bonus-coupon-req-item">${r.product_name}${r.min_quantity > 1 ? ' x' + r.min_quantity : ''}</div>`
                ).join('');
                const rewardName = bonus.bonus_product_name;

                let statusHtml = '';
                let claimAreaHtml = '';
                if (isUnlocked) {
                    claimAreaHtml = `<div class="bonus-coupon-claim-area bonus-coupon-added">
                        <span class="bonus-coupon-claim-text">Dodano!</span>
                    </div>`;
                } else if (isUnavailable) {
                    claimAreaHtml = `<div class="bonus-coupon-claim-area bonus-coupon-unavailable">
                        <span class="bonus-coupon-claim-text-unavailable">CHWILO<br/>NIEDOSTĘPNE</span>
                    </div>`;
                } else if (canClaim) {
                    claimAreaHtml = `<div class="bonus-coupon-claim-area" onclick="event.stopPropagation(); claimBonus('${sectionId}', ${bonus.id})">
                        <span class="bonus-coupon-claim-text">Odbierz!</span>
                    </div>`;
                } else {
                    statusHtml = `<div class="bonus-coupon-hint">Dodaj wymagane produkty do koszyka</div>`;
                }

                bonusHtml += `
                    <div class="bonus-coupon ${canClaim ? 'bonus-claimable' : ''} ${isUnlocked ? 'bonus-added' : ''} ${!isUnlocked && isUnavailable ? 'bonus-unavailable' : ''}"
                         data-bonus-id="${bonus.id}"
                         ${canClaim ? `onclick="claimBonus('${sectionId}', ${bonus.id})"` : ''}>
                        <div class="bonus-coupon-icon-area">
                            <span class="bonus-coupon-icon">🎁</span>
                        </div>
                        <div class="bonus-coupon-body">
                            <div class="bonus-coupon-condition-label">KUP RAZEM</div>
                            <div class="bonus-coupon-req-list">${reqLines}</div>
                            <div class="bonus-coupon-reward-line">${rewardName}${bonus.bonus_quantity > 1 ? ' x' + bonus.bonus_quantity : ''}</div>
                            ${statusHtml}
                        </div>
                        ${claimAreaHtml}
                    </div>`;

            } else if (bonus.trigger_type === 'price_threshold') {
                let sectionTotal = products.reduce((sum, p) => sum + (p.qty * p.price), 0);
                // Add previous orders total
                sectionTotal += bonus.prev_total || 0;
                if (bonus.count_full_set) {
                    if (fullSetQty > 0) {
                        const fsSection = sectionEl.querySelector('.full-set-section');
                        const fsPrice = fsSection ? parseFloat(fsSection.dataset.setPrice) || 0 : 0;
                        sectionTotal += fullSetQty * fsPrice;
                    }
                    sectionTotal += bonus.prev_fs_total || 0;
                }

                const threshold = bonus.threshold_value || 0;

                if (sectionTotal >= threshold) {
                    earned = bonus.repeatable ? Math.floor(sectionTotal / threshold) : 1;
                }
                // Subtract bonuses already earned in previous orders
                earned = Math.max(0, earned - (bonus.user_already_earned || 0));
                if (bonus.max_available !== null) {
                    earned = Math.min(earned, bonus.max_available - bonus.already_claimed);
                }

                // Show as unlocked only if there are new bonuses to earn AND items in cart
                const isUnlocked = earned > 0 && regularItems.length > 0;
                const isAlreadyClaimed = sectionTotal >= threshold && earned <= 0 && !bonus.repeatable;
                const isPendingPickup = regularItems.length === 0 && (earned > 0 || (bonus.repeatable && sectionTotal >= threshold));
                const alreadyEarnedPrice = bonus.user_already_earned || 0;
                const nextMilestonePrice = (alreadyEarnedPrice + 1) * threshold;
                const remaining = Math.max(0, nextMilestonePrice - sectionTotal);
                const progress = Math.min(100, (sectionTotal / nextMilestonePrice) * 100);
                const earnedLabel = earned > 1 ? ` x${earned}` : '';

                let priceStatusHtml;
                if (isUnlocked) {
                    priceStatusHtml = `<div class="bonus-coupon-status">
                        <span class="bonus-coupon-check">✓</span>
                        <span class="bonus-coupon-unlocked-text">Odblokowano!</span>
                    </div>`;
                } else if (isAlreadyClaimed) {
                    priceStatusHtml = `<div class="bonus-coupon-status">
                        <span class="bonus-coupon-check">✓</span>
                        <span class="bonus-coupon-unlocked-text">Już odebrane</span>
                    </div>`;
                } else if (isPendingPickup) {
                    priceStatusHtml = `<div class="bonus-coupon-remaining">Jeszcze <strong>${remaining.toFixed(2)} PLN</strong> do gratisu!</div>
                        <div class="bonus-coupon-progress-wrapper">
                            <div class="bonus-coupon-progress-bar" style="width: ${progress}%"></div>
                        </div>`;
                } else {
                    priceStatusHtml = `<div class="bonus-coupon-remaining">Jeszcze <strong>${remaining.toFixed(2)} PLN</strong> do gratisu!</div>
                        <div class="bonus-coupon-progress-wrapper">
                            <div class="bonus-coupon-progress-bar" style="width: ${progress}%"></div>
                        </div>`;
                }

                bonusHtml += `
                    <div class="bonus-coupon ${isUnlocked ? 'bonus-unlocked' : ''} ${isAlreadyClaimed ? 'bonus-claimed' : ''} ${isPendingPickup ? 'bonus-pending' : ''}" data-bonus-id="${bonus.id}">
                        <div class="bonus-coupon-icon-area">
                            <span class="bonus-coupon-icon">${isUnlocked ? '🎉' : isAlreadyClaimed ? '✅' : isPendingPickup ? '🎁' : '🎁'}</span>
                        </div>
                        <div class="bonus-coupon-body">
                            <div class="bonus-coupon-title">${bonus.bonus_product_name}${earnedLabel}</div>
                            ${priceStatusHtml}
                        </div>
                    </div>`;

            } else if (bonus.trigger_type === 'quantity_threshold') {
                let sectionQty = products.reduce((sum, p) => sum + p.qty, 0);
                // Add previous orders quantity
                sectionQty += bonus.prev_qty || 0;
                // Full set contribution (current + previous)
                const totalFullSetQtyThresh = fullSetQty + (bonus.prev_full_set_qty || 0);
                if (bonus.count_full_set && totalFullSetQtyThresh > 0) sectionQty += totalFullSetQtyThresh * itemsPerSet;

                const threshold = bonus.threshold_value || 0;

                if (sectionQty >= threshold) {
                    earned = bonus.repeatable ? Math.floor(sectionQty / threshold) : 1;
                }
                // Subtract bonuses already earned in previous orders
                earned = Math.max(0, earned - (bonus.user_already_earned || 0));
                if (bonus.max_available !== null) {
                    earned = Math.min(earned, bonus.max_available - bonus.already_claimed);
                }

                // Show as unlocked only if there are new bonuses to earn AND items in cart
                const isUnlocked = earned > 0 && regularItems.length > 0;
                const isAlreadyClaimed = sectionQty >= threshold && earned <= 0 && !bonus.repeatable;
                const isPendingPickup = regularItems.length === 0 && (earned > 0 || (bonus.repeatable && sectionQty >= threshold));
                // Calculate remaining to NEXT bonus level (not just first threshold)
                const alreadyEarned = bonus.user_already_earned || 0;
                const nextMilestone = (alreadyEarned + 1) * threshold;
                const remaining = Math.max(0, nextMilestone - sectionQty);
                const progress = Math.min(100, (sectionQty / nextMilestone) * 100);
                const earnedLabelQty = earned > 1 ? ` x${earned}` : '';

                let qtyStatusHtml;
                if (isUnlocked) {
                    qtyStatusHtml = `<div class="bonus-coupon-status">
                        <span class="bonus-coupon-check">✓</span>
                        <span class="bonus-coupon-unlocked-text">Odblokowano!</span>
                    </div>`;
                } else if (isAlreadyClaimed) {
                    qtyStatusHtml = `<div class="bonus-coupon-status">
                        <span class="bonus-coupon-check">✓</span>
                        <span class="bonus-coupon-unlocked-text">Już odebrane</span>
                    </div>`;
                } else if (isPendingPickup) {
                    qtyStatusHtml = `<div class="bonus-coupon-remaining">Jeszcze <strong>${remaining} szt.</strong> do gratisu!</div>
                        <div class="bonus-coupon-progress-wrapper">
                            <div class="bonus-coupon-progress-bar" style="width: ${progress}%"></div>
                        </div>`;
                } else {
                    qtyStatusHtml = `<div class="bonus-coupon-remaining">Jeszcze <strong>${remaining} szt.</strong> do gratisu!</div>
                        <div class="bonus-coupon-progress-wrapper">
                            <div class="bonus-coupon-progress-bar" style="width: ${progress}%"></div>
                        </div>`;
                }

                bonusHtml += `
                    <div class="bonus-coupon ${isUnlocked ? 'bonus-unlocked' : ''} ${isAlreadyClaimed ? 'bonus-claimed' : ''} ${isPendingPickup ? 'bonus-pending' : ''}" data-bonus-id="${bonus.id}">
                        <div class="bonus-coupon-icon-area">
                            <span class="bonus-coupon-icon">${isUnlocked ? '🎉' : isAlreadyClaimed ? '✅' : isPendingPickup ? '🎁' : '🎁'}</span>
                        </div>
                        <div class="bonus-coupon-body">
                            <div class="bonus-coupon-title">${bonus.bonus_product_name}${earnedLabelQty}</div>
                            ${qtyStatusHtml}
                        </div>
                    </div>`;
            }

            // Add bonus to cart if earned AND user has items in current cart
            // (don't show gratis with empty cart — cumulative bonuses only apply when placing a new order)
            if (earned > 0 && regularItems.length > 0) {
                cart.push({
                    productId: bonus.bonus_product_id,
                    name: bonus.bonus_product_name,
                    qty: bonus.bonus_quantity * earned,
                    price: 0,
                    isFullSet: false,
                    isBonus: true,
                    bonusId: bonus.id,
                    sectionId: parseInt(sectionId),
                });
            }
        }

        // Update bonus container in DOM
        if (bonusContainer) {
            bonusContainer.innerHTML = bonusHtml;
        }
    }

    // Re-render cart items to include bonuses (update the HTML)
    const cartItems = document.getElementById('cartItems');
    const fullSetItems = cart.filter(item => item.isFullSet);
    const regItems = cart.filter(item => !item.isFullSet && !item.isBonus);
    const bonusCartItems = cart.filter(item => item.isBonus);
    const allItems = [...fullSetItems, ...regItems, ...bonusCartItems];

    if (allItems.length === 0) {
        cartItems.innerHTML = '<div class="cart-empty"><p>Koszyk jest pusty</p></div>';
    } else {
        cartItems.innerHTML = allItems.map(item => {
            const removeIcon = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`;

            if (item.isBonus) {
                return `
                    <div class="cart-item cart-item-bonus">
                        <span class="cart-item-name">🎁 GRATIS: ${item.name}</span>
                        <span class="cart-item-qty">x${item.qty}</span>
                        <span class="cart-item-price cart-item-price-free">GRATIS</span>
                    </div>`;
            } else if (item.isFullSet) {
                return `
                    <div class="cart-item cart-item-fullset">
                        <span class="cart-item-name">${item.name}</span>
                        <span class="cart-item-qty">x${item.qty}</span>
                        <span class="cart-item-price">${(item.qty * item.price).toFixed(2)} PLN</span>
                        <button type="button" class="cart-item-remove" onclick="removeProductFromCart(${item.productId})" title="Usuń z koszyka">${removeIcon}</button>
                    </div>`;
            } else {
                const esc = s => s ? s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') : '';
                const sizeBadge = item.selectedSize ? ` <span class="size-badge">${esc(item.selectedSize)}</span>` : '';
                return `
                    <div class="cart-item">
                        <span class="cart-item-name">${esc(item.name)}${sizeBadge}</span>
                        <span class="cart-item-qty">x${item.qty}</span>
                        <span class="cart-item-price">${(item.qty * item.price).toFixed(2)} PLN</span>
                        <button type="button" class="cart-item-remove" onclick="removeProductFromCart(${item.productId})" title="Usuń z koszyka">${removeIcon}</button>
                    </div>`;
            }
        }).join('');
    }
}
