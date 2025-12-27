/**
 * Google Analytics 4 (GA4) Helper
 *
 * Pomocnicze funkcje do trackowania custom events w Google Analytics.
 * Używane do śledzenia ważnych akcji użytkowników (zamówienia, rejestracja, itp.)
 */

/**
 * Track custom event w GA4
 * @param {string} eventName - Nazwa eventu (np. 'order_placed', 'user_registered')
 * @param {object} eventParams - Parametry eventu (opcjonalnie)
 */
function trackEvent(eventName, eventParams = {}) {
    // Sprawdź czy gtag jest dostępne (GA4 załadowane)
    if (typeof window.gtag === 'function') {
        window.gtag('event', eventName, eventParams);
        console.log(`[GA4] Event tracked: ${eventName}`, eventParams);
    } else {
        console.warn('[GA4] gtag not loaded - event not tracked:', eventName);
    }
}

/**
 * Track złożenia zamówienia
 * @param {string} orderNumber - Numer zamówienia (np. "ST/00000123")
 * @param {number} totalAmount - Łączna kwota zamówienia (PLN)
 * @param {number} itemsCount - Liczba produktów w zamówieniu
 * @param {string} orderType - Typ zamówienia ('standard' lub 'exclusive')
 */
function trackOrderPlaced(orderNumber, totalAmount, itemsCount, orderType = 'standard') {
    trackEvent('purchase', {
        transaction_id: orderNumber,
        value: totalAmount,
        currency: 'PLN',
        items_count: itemsCount,
        order_type: orderType
    });
}

/**
 * Track rejestracji użytkownika
 * @param {string} method - Metoda rejestracji (np. 'email', 'google')
 */
function trackUserRegistered(method = 'email') {
    trackEvent('sign_up', {
        method: method
    });
}

/**
 * Track logowania użytkownika
 * @param {string} method - Metoda logowania (np. 'email', 'google')
 */
function trackUserLogin(method = 'email') {
    trackEvent('login', {
        method: method
    });
}

/**
 * Track dodania produktu do koszyka (podczas tworzenia zamówienia)
 * @param {string} productName - Nazwa produktu
 * @param {string} productSku - SKU produktu
 * @param {number} price - Cena produktu
 * @param {number} quantity - Ilość
 */
function trackAddToCart(productName, productSku, price, quantity = 1) {
    trackEvent('add_to_cart', {
        item_name: productName,
        item_id: productSku,
        price: price,
        quantity: quantity,
        currency: 'PLN'
    });
}

/**
 * Track wysłania formularza (contact, shipping request, itp.)
 * @param {string} formName - Nazwa formularza
 */
function trackFormSubmit(formName) {
    trackEvent('form_submit', {
        form_name: formName
    });
}

/**
 * Track kliknięcia w ważny przycisk/link
 * @param {string} buttonName - Nazwa przycisku
 * @param {string} location - Gdzie znajduje się przycisk (np. 'header', 'sidebar')
 */
function trackButtonClick(buttonName, location = 'unknown') {
    trackEvent('button_click', {
        button_name: buttonName,
        location: location
    });
}

/**
 * Track wyświetlenia strony Exclusive
 * @param {string} exclusiveToken - Token strony exclusive
 * @param {string} exclusiveName - Nazwa strony exclusive
 */
function trackExclusivePageView(exclusiveToken, exclusiveName) {
    trackEvent('view_exclusive_page', {
        exclusive_token: exclusiveToken,
        exclusive_name: exclusiveName
    });
}

/**
 * Track złożenia zamówienia przez gościa (bez rejestracji)
 * @param {string} orderNumber - Numer zamówienia
 * @param {number} totalAmount - Łączna kwota
 */
function trackGuestOrderPlaced(orderNumber, totalAmount) {
    trackEvent('guest_order_placed', {
        transaction_id: orderNumber,
        value: totalAmount,
        currency: 'PLN',
        is_guest: true
    });
}

/**
 * Track zlecenia wysyłki przez klienta
 * @param {number} ordersCount - Liczba zamówień do wysłania
 */
function trackShippingRequested(ordersCount) {
    trackEvent('shipping_requested', {
        orders_count: ordersCount
    });
}

/**
 * Track wyszukiwania (global search)
 * @param {string} searchTerm - Wyszukiwana fraza
 */
function trackSearch(searchTerm) {
    trackEvent('search', {
        search_term: searchTerm
    });
}

// Expose functions globally
window.trackEvent = trackEvent;
window.trackOrderPlaced = trackOrderPlaced;
window.trackUserRegistered = trackUserRegistered;
window.trackUserLogin = trackUserLogin;
window.trackAddToCart = trackAddToCart;
window.trackFormSubmit = trackFormSubmit;
window.trackButtonClick = trackButtonClick;
window.trackExclusivePageView = trackExclusivePageView;
window.trackGuestOrderPlaced = trackGuestOrderPlaced;
window.trackShippingRequested = trackShippingRequested;
window.trackSearch = trackSearch;
