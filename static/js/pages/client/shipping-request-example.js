/**
 * Client - Shipping Request Page (EXAMPLE - nie używany jeszcze w aplikacji)
 * Ten plik pokazuje jak dodać Google Analytics tracking do przyszłej strony zlecenia wysyłki
 */

// ============================================
// Google Analytics Tracking
// ============================================

// Track zlecenia wysyłki
async function handleShippingRequest(event) {
    event.preventDefault();

    const form = event.target;
    const selectedOrders = form.querySelectorAll('input[name="orders"]:checked');
    const ordersCount = selectedOrders.length;

    if (ordersCount === 0) {
        alert('Wybierz przynajmniej jedno zamówienie.');
        return;
    }

    try {
        const formData = new FormData(form);

        const response = await fetch('/client/shipping/request', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            // GA4: Track shipping request
            if (typeof window.trackShippingRequested === 'function') {
                window.trackShippingRequested(ordersCount);
            }

            // Pokazanie sukcesu
            alert(`Zlecenie wysyłki zostało wysłane dla ${ordersCount} zamówień.`);

            // Refresh lub redirect
            window.location.reload();
        } else {
            // Obsługa błędu
            alert(data.message || 'Wystąpił błąd. Spróbuj ponownie.');
        }
    } catch (error) {
        console.error('Shipping request error:', error);
        alert('Wystąpił błąd. Spróbuj ponownie.');
    }
}

// ============================================
// Event Listeners
// ============================================

document.addEventListener('DOMContentLoaded', function() {
    const shippingForm = document.getElementById('shipping-request-form');
    if (shippingForm) {
        shippingForm.addEventListener('submit', handleShippingRequest);
    }
});
