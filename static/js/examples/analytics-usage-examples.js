/**
 * ====================================================================
 * PRZYKŁADY UŻYCIA GOOGLE ANALYTICS 4 TRACKING
 * ====================================================================
 *
 * Ten plik zawiera przykłady jak używać funkcji trackingowych GA4
 * w różnych miejscach aplikacji ThunderOrders.
 *
 * NIE IMPORTUJ tego pliku w aplikacji - to tylko dokumentacja!
 * Skopiuj potrzebne fragmenty do swoich plików.
 */

// ====================================================================
// PRZYKŁAD 1: Tracking rejestracji i logowania
// Lokalizacja: static/js/pages/auth/*.js
// ====================================================================

// Po SUKCESIE rejestracji (gdy serwer zwróci sukces)
function handleRegistrationSuccess() {
    // Twój kod...

    // Track rejestracji
    if (typeof window.trackUserRegistered === 'function') {
        window.trackUserRegistered('email');
    }

    // Redirect lub pokazanie komunikatu...
}

// Po SUKCESIE logowania (gdy serwer zwróci sukces)
function handleLoginSuccess() {
    // Twój kod...

    // Track logowania
    if (typeof window.trackUserLogin === 'function') {
        window.trackUserLogin('email');
    }

    // Redirect...
}

// ====================================================================
// PRZYKŁAD 2: Tracking złożenia zamówienia (Client - New Order)
// Lokalizacja: static/js/pages/client/new-order.js
// ====================================================================

// Po kliknięciu "Dodaj produkt" do koszyka
document.querySelectorAll('.btn-add-product').forEach(btn => {
    btn.addEventListener('click', function() {
        const productName = this.dataset.productName;
        const productSku = this.dataset.productSku;
        const price = parseFloat(this.dataset.price);

        // Twój kod dodawania do koszyka...
        addProductToCart(productName, productSku, price);

        // Track dodania do koszyka
        if (typeof window.trackAddToCart === 'function') {
            window.trackAddToCart(productName, productSku, price, 1);
        }
    });
});

// Po SUBMIT formularza zamówienia (gdy zamówienie zostało złożone)
document.getElementById('submit-order-btn').addEventListener('click', function() {
    // AJAX submit zamówienia...

    fetch('/client/orders/new', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Track złożenia zamówienia
            if (typeof window.trackOrderPlaced === 'function') {
                window.trackOrderPlaced(
                    data.order_number,    // np. 'ST/00000123'
                    data.total_amount,    // np. 450.00
                    data.items_count,     // np. 3
                    'standard'            // typ: 'standard' lub 'exclusive'
                );
            }

            // Redirect na stronę potwierdzenia...
            window.location.href = `/client/orders/${data.order_id}`;
        }
    });
});

// ====================================================================
// PRZYKŁAD 3: Tracking zamówienia Exclusive (Guest Order)
// Lokalizacja: static/js/pages/exclusive/order-page.js
// ====================================================================

// Po złożeniu zamówienia przez gościa
document.getElementById('guest-order-form').addEventListener('submit', function(e) {
    e.preventDefault();

    const formData = new FormData(this);

    fetch(this.action, {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Track zamówienia gościa
            if (typeof window.trackGuestOrderPlaced === 'function') {
                window.trackGuestOrderPlaced(
                    data.order_number,
                    data.total_amount
                );
            }

            // Pokazanie strony "Dziękujemy"...
            showThankYouPage(data.order_number);
        }
    });
});

// Track wyświetlenia strony Exclusive (zaraz po załadowaniu)
document.addEventListener('DOMContentLoaded', function() {
    const exclusiveToken = document.body.dataset.exclusiveToken;
    const exclusiveName = document.body.dataset.exclusiveName;

    if (exclusiveToken && typeof window.trackExclusivePageView === 'function') {
        window.trackExclusivePageView(exclusiveToken, exclusiveName);
    }
});

// ====================================================================
// PRZYKŁAD 4: Tracking zlecenia wysyłki (Client - Shipping Request)
// Lokalizacja: static/js/pages/client/shipping-request.js
// ====================================================================

document.getElementById('shipping-request-form').addEventListener('submit', function(e) {
    e.preventDefault();

    const selectedOrders = document.querySelectorAll('input[name="orders"]:checked');
    const ordersCount = selectedOrders.length;

    // AJAX submit...
    fetch('/client/shipping/request', {
        method: 'POST',
        body: new FormData(this)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Track zlecenia wysyłki
            if (typeof window.trackShippingRequested === 'function') {
                window.trackShippingRequested(ordersCount);
            }

            // Pokazanie komunikatu sukcesu...
            showToast('Zlecenie wysyłki zostało wysłane', 'success');
        }
    });
});

// ====================================================================
// PRZYKŁAD 5: Tracking wyszukiwania (Global Search)
// Lokalizacja: static/js/components/global-search.js
// ====================================================================

const searchInput = document.getElementById('global-search-input');

// Debounce tracking (nie trackuj każdej litery)
let searchTimeout;
searchInput.addEventListener('input', function() {
    clearTimeout(searchTimeout);

    searchTimeout = setTimeout(() => {
        const searchTerm = this.value.trim();

        if (searchTerm.length >= 3) {
            // Track wyszukiwania
            if (typeof window.trackSearch === 'function') {
                window.trackSearch(searchTerm);
            }

            // Wykonaj wyszukiwanie...
            performSearch(searchTerm);
        }
    }, 500); // 500ms debounce
});

// ====================================================================
// PRZYKŁAD 6: Tracking kliknięć w ważne przyciski
// Lokalizacja: dowolne pliki JS
// ====================================================================

// Przycisk "Nowe zamówienie" w sidebar
document.getElementById('btn-new-order')?.addEventListener('click', function() {
    if (typeof window.trackButtonClick === 'function') {
        window.trackButtonClick('new_order', 'sidebar');
    }
});

// Przycisk "Export do CSV" na stronie statystyk
document.getElementById('btn-export-csv')?.addEventListener('click', function() {
    if (typeof window.trackButtonClick === 'function') {
        window.trackButtonClick('export_csv', 'statistics_page');
    }
});

// Przycisk "Zapisz szablon zamówienia"
document.getElementById('btn-save-template')?.addEventListener('click', function() {
    if (typeof window.trackButtonClick === 'function') {
        window.trackButtonClick('save_order_template', 'new_order_page');
    }
});

// ====================================================================
// PRZYKŁAD 7: Tracking wysłania formularzy (kontakt, itp.)
// Lokalizacja: formularze kontaktowe, feedback, itp.
// ====================================================================

document.getElementById('contact-form')?.addEventListener('submit', function(e) {
    // Track wysłania formularza
    if (typeof window.trackFormSubmit === 'function') {
        window.trackFormSubmit('contact_form');
    }

    // Normalny submit...
});

document.getElementById('feedback-form')?.addEventListener('submit', function(e) {
    if (typeof window.trackFormSubmit === 'function') {
        window.trackFormSubmit('feedback_form');
    }
});

// ====================================================================
// PRZYKŁAD 8: Custom eventy (dowolne akcje)
// ====================================================================

// Track otworzenia modala WMS
document.getElementById('btn-open-wms')?.addEventListener('click', function() {
    if (typeof window.trackEvent === 'function') {
        window.trackEvent('wms_mode_opened', {
            orders_count: selectedOrders.length
        });
    }
});

// Track zmiany statusu zamówienia (Admin)
function changeOrderStatus(orderId, oldStatus, newStatus) {
    // Twój kod zmiany statusu...

    // Track zmiany statusu
    if (typeof window.trackEvent === 'function') {
        window.trackEvent('order_status_changed', {
            order_id: orderId,
            old_status: oldStatus,
            new_status: newStatus
        });
    }
}

// Track dodania komentarza do zamówienia
function addOrderComment(orderId, commentText) {
    // Twój kod dodawania komentarza...

    // Track komentarza
    if (typeof window.trackEvent === 'function') {
        window.trackEvent('order_comment_added', {
            order_id: orderId,
            comment_length: commentText.length
        });
    }
}

// ====================================================================
// PRZYKŁAD 9: Tracking błędów (opcjonalnie)
// ====================================================================

// Track błędów JavaScript (global error handler)
window.addEventListener('error', function(e) {
    if (typeof window.trackEvent === 'function') {
        window.trackEvent('javascript_error', {
            error_message: e.message,
            error_file: e.filename,
            error_line: e.lineno,
            error_column: e.colno
        });
    }
});

// Track błędów AJAX/Fetch
fetch('/api/some-endpoint')
    .then(response => {
        if (!response.ok) {
            // Track błędu API
            if (typeof window.trackEvent === 'function') {
                window.trackEvent('api_error', {
                    endpoint: '/api/some-endpoint',
                    status_code: response.status,
                    status_text: response.statusText
                });
            }
        }
        return response.json();
    });

// ====================================================================
// PRZYKŁAD 10: Conditional tracking (sprawdzanie czy GA4 jest aktywne)
// ====================================================================

// Zawsze sprawdzaj czy funkcja istnieje przed użyciem
function safeTrack() {
    // Sposób 1: Prosty if
    if (typeof window.trackOrderPlaced === 'function') {
        window.trackOrderPlaced('ST/00000123', 450.00, 3, 'standard');
    }

    // Sposób 2: Optional chaining (ES2020+)
    window.trackOrderPlaced?.('ST/00000123', 450.00, 3, 'standard');

    // Sposób 3: Try-catch (jeśli nie ufasz że istnieje)
    try {
        window.trackOrderPlaced('ST/00000123', 450.00, 3, 'standard');
    } catch (error) {
        console.warn('GA4 tracking not available:', error);
    }
}

// ====================================================================
// BEST PRACTICES
// ====================================================================

/**
 * 1. ZAWSZE sprawdzaj czy funkcja istnieje przed użyciem
 *    (GA4 może być wyłączone w .env)
 *
 * 2. NIE trackuj wrażliwych danych (hasła, numery kart, itp.)
 *
 * 3. Używaj sensownych nazw eventów (lowercase_with_underscores)
 *
 * 4. Dodawaj kontekst w parametrach (order_id, user_role, etc.)
 *
 * 5. Nie trackuj za dużo - skup się na kluczowych akcjach:
 *    - Rejestracja / Logowanie
 *    - Złożenie zamówienia
 *    - Dodanie do koszyka
 *    - Zlecenie wysyłki
 *    - Kluczowe kliknięcia (CTA buttons)
 *
 * 6. Testuj lokalnie z console.log przed wdrożeniem:
 *    console.log('[GA4 Test] Would track:', eventName, params);
 *
 * 7. Sprawdź w GA4 Realtime czy eventy są wysyłane:
 *    Google Analytics → Reports → Realtime → Event count by Event name
 */

// ====================================================================
// UWAGA: Ten plik jest TYLKO przykładem!
// Skopiuj potrzebne fragmenty do swoich plików JS.
// ====================================================================
