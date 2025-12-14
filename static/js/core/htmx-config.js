/**
 * ThunderOrders - HTMX Configuration
 * Konfiguracja HTMX event handlers
 */

document.addEventListener('DOMContentLoaded', function() {
    // HTMX event: Request started
    document.body.addEventListener('htmx:beforeRequest', function(evt) {
        console.log('HTMX Request:', evt.detail.path);
    });

    // HTMX event: Request completed
    document.body.addEventListener('htmx:afterRequest', function(evt) {
        console.log('HTMX Response:', evt.detail.xhr.status);
    });

    // HTMX event: Content swapped
    document.body.addEventListener('htmx:afterSwap', function(evt) {
        console.log('HTMX Content swapped');
    });

    // HTMX event: Error handling
    document.body.addEventListener('htmx:responseError', function(evt) {
        window.showToast('Wystąpił błąd połączenia. Spróbuj ponownie.', 'error');
    });

    document.body.addEventListener('htmx:sendError', function(evt) {
        window.showToast('Nie można wysłać żądania. Sprawdź połączenie internetowe.', 'error');
    });

    // HTMX event: Custom showToast trigger from HX-Trigger header
    // HX-Trigger sends the event detail in evt.detail (for simple) or evt.detail.value (for complex JSON)
    document.body.addEventListener('showToast', function(evt) {
        console.log('showToast event received:', evt.detail);

        // Handle both formats: direct object or nested in value
        let data = evt.detail;
        if (data && typeof data === 'object') {
            // If it's an object with message property, use it directly
            if (data.message) {
                window.showToast(data.message, data.type || 'success');
            }
            // If message is nested in value (some HTMX versions)
            else if (data.value && data.value.message) {
                window.showToast(data.value.message, data.value.type || 'success');
            }
        }
    });
});

// HTMX config
htmx.config.defaultSwapStyle = 'innerHTML';
htmx.config.timeout = 30000; // 30 seconds
