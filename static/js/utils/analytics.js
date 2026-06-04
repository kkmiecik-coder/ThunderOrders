/**
 * Google Analytics 4 (GA4) Helper — format GA4 Enhanced Ecommerce
 *
 * Pomocnicze funkcje do trackowania eventów w Google Analytics.
 * Eventy ecommerce (view_item, add_to_cart, begin_checkout, add_payment_info,
 * purchase) używają standaryzowanej tablicy `items`, dzięki czemu zasilają
 * raporty Monetyzacja / Ścieżka zakupowa w GA4.
 *
 * UWAGA: `gtag` jest definiowane synchronicznie w <head> (Consent Mode v2),
 * więc eventy nigdy nie giną — przed zgodą są wysyłane jako pingi cookieless,
 * po zgodzie pełne pomiary.
 */

/**
 * Track dowolny event w GA4.
 * @param {string} eventName - Nazwa eventu (np. 'purchase', 'add_to_cart')
 * @param {object} eventParams - Parametry eventu
 */
function trackEvent(eventName, eventParams = {}) {
    if (typeof window.gtag === 'function') {
        window.gtag('event', eventName, eventParams);
        console.log(`[GA4] Event: ${eventName}`, eventParams);
    } else {
        // Fallback: dopchnij bezpośrednio do dataLayer, jeśli stub gtag jeszcze nie istnieje
        window.dataLayer = window.dataLayer || [];
        window.dataLayer.push(['event', eventName, eventParams]);
        console.warn('[GA4] gtag niezaładowane — event w dataLayer:', eventName);
    }
}

/**
 * Normalizuje pojedynczą pozycję do formatu GA4 `items[]`.
 * @param {object} item - { item_id|id|sku, item_name|name, price, quantity }
 */
function normalizeItem(item) {
    return {
        item_id: String(item.item_id ?? item.id ?? item.product_id ?? item.sku ?? ''),
        item_name: item.item_name ?? item.name ?? '',
        price: Number(item.price ?? 0),
        quantity: Number(item.quantity ?? item.qty ?? 1),
    };
}

/**
 * Suma wartości pozycji (value) dla eventu ecommerce.
 */
function itemsValue(items) {
    return (items || []).reduce((sum, it) => sum + Number(it.price ?? 0) * Number(it.quantity ?? it.qty ?? 1), 0);
}

/**
 * GA4 `view_item_list` — wyświetlenie listy produktów (np. strona oferty).
 * @param {Array} items - Lista produktów
 * @param {string} listName - Nazwa listy (np. nazwa oferty)
 */
function trackViewItemList(items, listName = '') {
    trackEvent('view_item_list', {
        item_list_name: listName,
        items: (items || []).map(normalizeItem),
    });
}

/**
 * GA4 `view_item` — wyświetlenie pojedynczego produktu.
 * @param {object} item - Produkt
 */
function trackViewItem(item) {
    const norm = normalizeItem(item);
    trackEvent('view_item', {
        currency: 'PLN',
        value: norm.price * norm.quantity,
        items: [norm],
    });
}

/**
 * GA4 `add_to_cart` — dodanie produktu do koszyka.
 * Wstecznie kompatybilne: (productName, productId, price, quantity)
 * lub nowy wariant: (itemObject, quantity).
 */
function trackAddToCart(productNameOrItem, productId, price, quantity = 1) {
    let item;
    if (typeof productNameOrItem === 'object' && productNameOrItem !== null) {
        item = normalizeItem({ ...productNameOrItem, quantity: productId ?? productNameOrItem.quantity ?? 1 });
    } else {
        item = normalizeItem({ item_name: productNameOrItem, item_id: productId, price: price, quantity: quantity });
    }
    trackEvent('add_to_cart', {
        currency: 'PLN',
        value: item.price * item.quantity,
        items: [item],
    });
}

/**
 * GA4 `begin_checkout` — rozpoczęcie składania zamówienia (otwarcie koszyka/modala).
 * @param {Array} items - Pozycje koszyka
 * @param {number} value - Wartość koszyka (opcjonalnie, liczona z items)
 */
function trackBeginCheckout(items, value = null) {
    const norm = (items || []).map(normalizeItem);
    trackEvent('begin_checkout', {
        currency: 'PLN',
        value: value != null ? Number(value) : itemsValue(norm),
        items: norm,
    });
}

/**
 * GA4 `add_payment_info` — wybór sposobu/etapów płatności.
 * @param {Array} items - Pozycje koszyka
 * @param {number} value - Wartość
 * @param {string} paymentType - Typ płatności (np. 'stages_3')
 */
function trackAddPaymentInfo(items, value = null, paymentType = '') {
    const norm = (items || []).map(normalizeItem);
    trackEvent('add_payment_info', {
        currency: 'PLN',
        value: value != null ? Number(value) : itemsValue(norm),
        payment_type: paymentType,
        items: norm,
    });
}

/**
 * GA4 `purchase` — złożone zamówienie.
 * @param {string} orderNumber - Numer zamówienia → transaction_id
 * @param {number} totalAmount - Łączna kwota (PLN) → value
 * @param {Array} items - Pozycje zamówienia (item_id, item_name, price, quantity)
 * @param {string} orderType - 'standard' | 'exclusive' | 'preorder'
 */
function trackPurchase(orderNumber, totalAmount, items, orderType = 'standard') {
    const norm = (Array.isArray(items) ? items : []).map(normalizeItem);
    trackEvent('purchase', {
        transaction_id: orderNumber,
        value: Number(totalAmount ?? 0),
        currency: 'PLN',
        order_type: orderType,
        items: norm,
    });
}

/**
 * Alias wstecznie kompatybilny. UWAGA: 3. parametr to teraz tablica `items[]`,
 * a nie liczba pozycji — wszystkie wywołania zostały zaktualizowane.
 */
function trackOrderPlaced(orderNumber, totalAmount, items, orderType = 'standard') {
    trackPurchase(orderNumber, totalAmount, items, orderType);
}

/**
 * GA4 `sign_up` — rejestracja użytkownika.
 */
function trackUserRegistered(method = 'email') {
    trackEvent('sign_up', { method: method });
}

/**
 * GA4 `login` — logowanie użytkownika.
 */
function trackUserLogin(method = 'email') {
    trackEvent('login', { method: method });
}

/**
 * GA4 `form_submit` — wysłanie formularza.
 */
function trackFormSubmit(formName) {
    trackEvent('form_submit', { form_name: formName });
}

/**
 * Custom `button_click` — kliknięcie ważnego przycisku/linku.
 */
function trackButtonClick(buttonName, location = 'unknown') {
    trackEvent('button_click', { button_name: buttonName, location: location });
}

/**
 * Custom `view_offer_page` — wyświetlenie strony oferty (uzupełnienie do view_item_list).
 */
function trackOfferPageView(offerToken, offerName) {
    trackEvent('view_offer_page', { offer_token: offerToken, offer_name: offerName });
}

/**
 * Custom `shipping_requested` — zlecenie wysyłki przez klienta.
 */
function trackShippingRequested(ordersCount) {
    trackEvent('shipping_requested', { orders_count: ordersCount });
}

/**
 * GA4 `search` — wyszukiwanie.
 */
function trackSearch(searchTerm) {
    trackEvent('search', { search_term: searchTerm });
}

// Eksport globalny
window.trackEvent = trackEvent;
window.trackViewItemList = trackViewItemList;
window.trackViewItem = trackViewItem;
window.trackAddToCart = trackAddToCart;
window.trackBeginCheckout = trackBeginCheckout;
window.trackAddPaymentInfo = trackAddPaymentInfo;
window.trackPurchase = trackPurchase;
window.trackOrderPlaced = trackOrderPlaced;
window.trackUserRegistered = trackUserRegistered;
window.trackUserLogin = trackUserLogin;
window.trackFormSubmit = trackFormSubmit;
window.trackButtonClick = trackButtonClick;
window.trackOfferPageView = trackOfferPageView;
window.trackShippingRequested = trackShippingRequested;
window.trackSearch = trackSearch;
