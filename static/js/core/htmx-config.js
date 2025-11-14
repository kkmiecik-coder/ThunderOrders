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
});

// HTMX config
htmx.config.defaultSwapStyle = 'innerHTML';
htmx.config.timeout = 30000; // 30 seconds
