/**
 * Preorder Order Page - Cart without reservations
 * Simplified version of order-page.js for preorder pages
 */

// ============================================
// Cart State
// ============================================
let cart = [];
const CART_KEY = `preorder_cart_${window.pageToken}`;

// ============================================
// Initialization
// ============================================
document.addEventListener('DOMContentLoaded', function() {
    loadCart();
    updateCartUI();
    initLightbox();
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
    const productActions = btn.closest('.product-controls-box') ||
                           btn.closest('.variant-product-qty') ||
                           btn.closest('.product-header-controls');
    const qtyInput = productActions ? productActions.querySelector('.qty-input') : null;
    const qty = qtyInput ? (parseInt(qtyInput.value) || 1) : 1;

    const existing = cart.find(item => item.product_id === productId);
    if (existing) {
        existing.quantity += qty;
    } else {
        cart.push({
            product_id: productId,
            name: productName,
            price: parseFloat(price),
            quantity: qty
        });
    }

    // Reset qty input
    if (qtyInput) qtyInput.value = 1;

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
function getCartTotal() {
    return cart.filter(i => !i.is_bonus).reduce((sum, item) => sum + (item.price * item.quantity), 0);
}

function getCartItemCount() {
    return cart.filter(i => !i.is_bonus).reduce((sum, item) => sum + item.quantity, 0);
}

// ============================================
// Bonus Evaluation
// ============================================
function evaluatePreorderBonuses() {
    // Remove old bonus items
    cart = cart.filter(i => !i.is_bonus);

    const config = window.bonusesConfig;
    if (!config || typeof config !== 'object') return;

    const regularItems = cart.filter(i => !i.is_bonus);
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
                return `
                    <div class="cart-item">
                        <div class="cart-item-info">
                            <span class="cart-item-name">${escapeHtml(item.name)}</span>
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
    if (cart.length === 0) return;
    const modal = document.getElementById('orderModal');
    if (modal) modal.classList.add('active');
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
                cart_items: cart.map(item => ({
                    product_id: item.product_id,
                    quantity: item.quantity
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

            // Track with GA4
            if (typeof window.trackOrderPlaced === 'function') {
                window.trackOrderPlaced(data.order_number, data.total_amount, getCartItemCount(), 'preorder');
            }
        } else {
            alert(data.error || 'Wystąpił błąd podczas składania zamówienia.');
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
// Utility
// ============================================
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
