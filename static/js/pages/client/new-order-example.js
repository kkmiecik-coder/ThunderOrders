/**
 * Client - New Order Page (EXAMPLE - nie używany jeszcze w aplikacji)
 * Ten plik pokazuje jak dodać Google Analytics tracking do przyszłej strony nowego zamówienia
 */

// ============================================
// Google Analytics Tracking
// ============================================

// Track dodania produktu do koszyka
function handleAddToCart(productName, productSku, price, quantity) {
    // Twój kod dodawania do koszyka...
    addToCart(productName, productSku, price, quantity);

    // GA4: Track add to cart
    if (typeof window.trackAddToCart === 'function') {
        window.trackAddToCart(productName, productSku, price, quantity);
    }
}

// Track złożenia zamówienia
async function handleOrderSubmit(event) {
    event.preventDefault();

    const formData = new FormData(event.target);

    try {
        const response = await fetch('/client/orders/new', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            // GA4: Track order placed
            if (typeof window.trackOrderPlaced === 'function') {
                window.trackOrderPlaced(
                    data.order_number,  // np. 'ST/00000123'
                    data.total_amount,  // np. 450.00
                    data.items_count,   // np. 3
                    'standard'          // typ: 'standard'
                );
            }

            // Redirect lub pokazanie sukcesu
            window.location.href = `/client/orders/${data.order_id}`;
        } else {
            // Obsługa błędu
            alert(data.message);
        }
    } catch (error) {
        console.error('Order submission error:', error);
        alert('Wystąpił błąd. Spróbuj ponownie.');
    }
}

// ============================================
// Event Listeners
// ============================================

document.addEventListener('DOMContentLoaded', function() {
    // Przykład: Przycisk "Dodaj do koszyka"
    document.querySelectorAll('.btn-add-to-cart').forEach(btn => {
        btn.addEventListener('click', function() {
            const productName = this.dataset.productName;
            const productSku = this.dataset.productSku;
            const price = parseFloat(this.dataset.price);
            const quantity = 1;

            handleAddToCart(productName, productSku, price, quantity);
        });
    });

    // Przykład: Formularz zamówienia
    const orderForm = document.getElementById('order-form');
    if (orderForm) {
        orderForm.addEventListener('submit', handleOrderSubmit);
    }
});
