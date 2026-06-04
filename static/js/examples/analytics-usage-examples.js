/**
 * Google Analytics 4 (GA4) — przykłady użycia (Enhanced Ecommerce)
 *
 * ⚠️ NIE IMPORTUJ tego pliku w aplikacji — to wyłącznie dokumentacja/przykłady.
 *
 * Wszystkie helpery są dostępne globalnie (window.*) po załadowaniu
 * static/js/utils/analytics.js. Eventy ecommerce używają tablicy `items[]`
 * zgodnej z GA4 (item_id, item_name, price, quantity).
 *
 * Format pojedynczej pozycji `items[]`:
 *   { item_id: 'SKU-123', item_name: 'Nazwa', price: 199.99, quantity: 2 }
 */

// ============================================
// 1. Lejek zakupowy (ecommerce funnel)
// ============================================

// view_item_list — wyświetlenie listy produktów (np. strona oferty)
const offerItems = [
    { item_id: 'SKU-1', item_name: 'Bluza', price: 199.99, quantity: 1 },
    { item_id: 'SKU-2', item_name: 'Czapka', price: 79.99, quantity: 1 },
];
window.trackViewItemList(offerItems, 'Drop wiosna 2026');

// view_item — wyświetlenie pojedynczego produktu
window.trackViewItem({ item_id: 'SKU-1', item_name: 'Bluza', price: 199.99, quantity: 1 });

// add_to_cart — dodanie do koszyka (wariant 4-argumentowy, wstecznie kompatybilny)
window.trackAddToCart('Bluza', 'SKU-1', 199.99, 2);

// begin_checkout — rozpoczęcie składania zamówienia (otwarcie koszyka/checkout)
window.trackBeginCheckout(offerItems /*, opcjonalnie value */);

// add_payment_info — wybór sposobu/etapów płatności
window.trackAddPaymentInfo(offerItems, 459.98, 'stages_3');

// purchase — złożone zamówienie (items[] najlepiej z odpowiedzi backendu)
window.trackPurchase('ST/00000123', 459.98, offerItems, 'standard');
// alias wstecznie kompatybilny:
window.trackOrderPlaced('ST/00000123', 459.98, offerItems, 'exclusive');

// ============================================
// 2. Konto użytkownika
// ============================================
// Eventy login / sign_up są emitowane serwerowo (po redirectach) — patrz
// components/ga4_head.html + session['ga_pending_event']. Helpery JS poniżej
// są dostępne, gdyby gdzieś przydał się tracking po stronie klienta:
window.trackUserLogin('email');
window.trackUserRegistered('email');

// ============================================
// 3. Pozostałe akcje
// ============================================
window.trackShippingRequested(3);            // zlecenie wysyłki 3 zamówień
window.trackSearch('bluza');                 // wyszukiwanie
window.trackFormSubmit('contact_form');      // wysłanie formularza
window.trackButtonClick('cta_hero', 'home'); // kliknięcie przycisku

// Ogólny event (zawsze sprawdź dostępność helpera):
if (typeof window.trackEvent === 'function') {
    window.trackEvent('custom_event', { foo: 'bar' });
}

// ============================================
// BEST PRACTICES
// ============================================
// 1. ZAWSZE sprawdzaj `if (typeof window.trackX === 'function')` przed użyciem.
// 2. Eventy ecommerce MUSZĄ zawierać `items[]` — bez tego raporty Monetyzacji
//    i Ścieżki zakupowej w GA4 pozostają puste.
// 3. Dla `purchase` używaj items[] z odpowiedzi backendu (autorytatywne dane),
//    a nie z koszyka (koszyk bywa już wyczyszczony przy sukcesie).
// 4. NIE trackuj danych wrażliwych (hasła, dane osobowe, numery kart).
// 5. currency zawsze 'PLN'.
