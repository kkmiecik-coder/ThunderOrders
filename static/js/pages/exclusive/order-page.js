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
            const wrapperWidth = wrapper.offsetWidth;

            // Calculate displayed height based on aspect ratio
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
        }
    });
}

// Initialize expandable images on page load
document.addEventListener('DOMContentLoaded', initExpandableImages);

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
    const eyeShow = document.querySelector('.exclusive-password-toggle .eye-show');
    const eyeHide = document.querySelector('.exclusive-password-toggle .eye-hide');

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
        <div class="exclusive-user-card">
            <div class="exclusive-user-avatar">
                ${avatarContent}
            </div>
            <div class="exclusive-user-info">
                <p class="exclusive-user-name">${user.full_name}</p>
                <p class="exclusive-user-email">${user.email}</p>
            </div>
            <button type="button" class="exclusive-logout-btn" onclick="handleLogout()" title="Wyloguj się">
                <svg width="18" height="18" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M7.5 1v7h1V1h-1z"/>
                    <path d="M3 8.812a4.999 4.999 0 0 1 2.578-4.375l-.485-.874A6 6 0 1 0 11 3.616l-.501.865A5 5 0 1 1 3 8.812z"/>
                </svg>
                <span>Wyloguj</span>
            </button>
        </div>

        <div class="exclusive-form-field">
            <label class="exclusive-form-label">
                <svg width="18" height="18" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M5 4a.5.5 0 0 0 0 1h6a.5.5 0 0 0 0-1H5zm-.5 2.5A.5.5 0 0 1 5 6h6a.5.5 0 0 1 0 1H5a.5.5 0 0 1-.5-.5zM5 8a.5.5 0 0 0 0 1h6a.5.5 0 0 0 0-1H5zm0 2a.5.5 0 0 0 0 1h3a.5.5 0 0 0 0-1H5z"/>
                    <path d="M2 2a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V2zm10-1H4a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V2a1 1 0 0 0-1-1z"/>
                </svg>
                <span>Notatka do zamówienia <span class="exclusive-opt">(opcjonalnie)</span></span>
            </label>
            <textarea id="orderNote" class="exclusive-form-textarea" rows="3" placeholder="Dodatkowe informacje, uwagi, preferencje..."></textarea>
        </div>
    `;
}

// Handle logout from exclusive page
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

    const modalBody = orderModal.querySelector('.exclusive-modal-body');
    if (!modalBody) return;

    // Replace modal body content with logged-in user view
    modalBody.innerHTML = generateLoggedInUserHTML(user);

    // Update global state
    window.isAuthenticated = true;
    window.isGuest = false;
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

            // Hide overlay
            hideLoginOverlay();

            // Close login modal
            closeLoginModal();

            // Open order modal after a short delay
            setTimeout(() => {
                const orderModal = document.getElementById('orderModal');
                if (orderModal) {
                    orderModal.classList.add('active');
                }
            }, 400);

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
    const extendTooltip = document.getElementById('extendTooltip');
    const canExtend = !reservationState.extended && diff < 120;
    extendBtn.disabled = !canExtend;

    if (reservationState.extended) {
        extendBtn.textContent = 'Przedłużono';
        if (extendTooltip) {
            extendTooltip.textContent = 'Rezerwację można przedłużyć tylko raz';
        }
    } else if (diff >= 120) {
        extendBtn.textContent = 'Przedłuż +2 min';
        if (extendTooltip) {
            extendTooltip.textContent = 'Możesz przedłużyć gdy zostanie < 2 min';
        }
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

    // Reset form state
    const emailInput = document.getElementById('notificationEmail');
    const emailError = document.getElementById('notificationEmailError');
    const submitBtn = document.getElementById('notificationSubmitBtn');

    if (emailInput) {
        emailInput.value = '';
        emailInput.classList.remove('error');
    }
    if (emailError) {
        emailError.classList.add('hidden');
        emailError.textContent = '';
    }
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
    const emailInput = document.getElementById('notificationEmail');
    const emailError = document.getElementById('notificationEmailError');

    // For guest users, validate email
    let email = null;
    if (!window.isAuthenticated && emailInput) {
        email = emailInput.value.trim();

        if (!email) {
            showNotificationError('Podaj adres email');
            return;
        }

        // Simple email validation
        const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailPattern.test(email)) {
            showNotificationError('Nieprawidłowy format email');
            return;
        }
    }

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
                product_id: currentNotificationProductId,
                email: email
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
 * Shows error message in notification modal
 * @param {string} message - Error message
 */
function showNotificationError(message) {
    const emailInput = document.getElementById('notificationEmail');
    const emailError = document.getElementById('notificationEmailError');

    if (emailInput) {
        emailInput.classList.add('error');
    }
    if (emailError) {
        emailError.textContent = message;
        emailError.classList.remove('hidden');
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
// STATUS POLLING - Auto-refresh for deadline changes & manual closure
// ============================================
(function() {
    // Skip polling in preview mode
    if (window.previewMode) return;

    // Check if statusCheckUrl is available
    if (!window.statusCheckUrl) return;

    const POLL_INTERVAL = 1000; // 1 second - fast polling for manual closure detection
    let currentEndsAt = window.initialEndsAt;
    let pollingInterval = null;
    let isClosed = false;

    /**
     * Checks status from server and handles changes
     */
    async function checkStatusChanges() {
        // Stop checking if already closed
        if (isClosed) return;

        try {
            const response = await fetch(window.statusCheckUrl);
            if (!response.ok) return;

            const data = await response.json();

            // Handle manual closure by admin
            if (data.is_manually_closed || !data.is_active) {
                handleSaleClosed();
                return;
            }

            // Handle ends_at change (admin added/changed deadline)
            if (data.ends_at !== currentEndsAt) {
                handleDeadlineChanged(data.ends_at);
            }

        } catch (error) {
            console.error('Status check failed:', error);
        }
    }

    /**
     * Handles when sale is closed by admin
     */
    function handleSaleClosed() {
        // Prevent multiple triggers
        if (isClosed) return;
        isClosed = true;

        // Stop polling
        if (pollingInterval) {
            clearInterval(pollingInterval);
            pollingInterval = null;
        }

        // Show toast notification
        if (typeof showToast === 'function') {
            showToast('Sprzedaż została zakończona przez administratora', 'info');
        }

        // Reload page after short delay to show closed state
        setTimeout(() => {
            window.location.reload();
        }, 2000);
    }

    /**
     * Handles when deadline is changed/added by admin
     * @param {string|null} newEndsAt - New deadline ISO string or null
     */
    function handleDeadlineChanged(newEndsAt) {
        const oldEndsAt = currentEndsAt;
        currentEndsAt = newEndsAt;

        if (!newEndsAt) {
            // Deadline was removed - refresh to show "unknown date" state
            window.location.reload();
            return;
        }

        // Deadline was added or changed
        const headerRight = document.querySelector('.header-right');
        if (!headerRight) return;

        const newDeadlineDate = new Date(newEndsAt);
        const formattedDate = formatDeadlineDate(newDeadlineDate);

        // Check if there's already a deadline banner
        const existingBanner = headerRight.querySelector('.deadline-banner:not(.deadline-unknown)');
        const unknownBanner = headerRight.querySelector('.deadline-unknown');

        if (unknownBanner) {
            // Replace "unknown date" banner with real deadline
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

            // Initialize the deadline timer for the new deadline
            initializeDeadlineTimer(newEndsAt);

            // Show toast
            if (typeof showToast === 'function') {
                showToast('Ustawiono datę zakończenia sprzedaży: ' + formattedDate, 'info');
            }
        } else if (existingBanner) {
            // Update existing banner with new date
            existingBanner.setAttribute('data-deadline', newEndsAt);
            const strongEl = existingBanner.querySelector('strong');
            if (strongEl) {
                strongEl.textContent = formattedDate;
            }

            // Reinitialize timer with new deadline
            initializeDeadlineTimer(newEndsAt);

            // Show toast about changed deadline
            if (typeof showToast === 'function') {
                showToast('Zmieniono datę zakończenia sprzedaży: ' + formattedDate, 'info');
            }
        }
    }

    /**
     * Formats deadline date for display
     * @param {Date} date - Date object
     * @returns {string} Formatted date string
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
     * Initializes or reinitializes the deadline timer
     * @param {string} deadlineStr - ISO deadline string
     */
    function initializeDeadlineTimer(deadlineStr) {
        const deadlineDate = new Date(deadlineStr);
        const dynamicCountdown = document.getElementById('dynamicCountdown');
        const countdownTime = document.getElementById('countdownTime');

        // Clear any existing timer
        if (window._deadlineTimerInterval) {
            clearInterval(window._deadlineTimerInterval);
        }

        function formatTime(minutes, seconds) {
            const m = String(minutes).padStart(2, '0');
            const s = String(seconds).padStart(2, '0');
            return `${m}:${s}`;
        }

        function updateTimer() {
            const now = new Date();
            const diff = deadlineDate - now;

            if (diff <= 0) {
                // Deadline passed - reload page
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

    // Start polling
    pollingInterval = setInterval(checkStatusChanges, POLL_INTERVAL);

    // Also check immediately after page load (with small delay)
    setTimeout(checkStatusChanges, 3000);
})();
