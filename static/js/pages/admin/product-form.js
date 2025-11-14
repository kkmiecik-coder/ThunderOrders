/**
 * Product Form JavaScript
 * Multi-currency calculator, image upload, tab switching
 */

// ==========================================
// Submit Button State Management
// ==========================================
function setButtonLoading(loading = true) {
    const submitButton = document.getElementById('submitButton');
    if (!submitButton) return;

    const btnText = submitButton.querySelector('.btn-text');
    const btnSpinner = submitButton.querySelector('.btn-spinner');

    if (loading) {
        // Show spinner, hide text
        if (btnText) btnText.style.display = 'none';
        if (btnSpinner) btnSpinner.style.display = 'inline-flex';
        submitButton.disabled = true;
    } else {
        // Show text, hide spinner
        if (btnText) btnText.style.display = 'inline';
        if (btnSpinner) btnSpinner.style.display = 'none';
        submitButton.disabled = false;
    }
}

// ==========================================
// Tab Switching (Global function accessible from modal)
// ==========================================
window.switchTab = function(tabName) {
    // Hide all tab contents
    const tabContents = document.querySelectorAll('.tab-content');
    tabContents.forEach(content => {
        content.classList.remove('active');
    });

    // Deactivate all tab buttons
    const tabButtons = document.querySelectorAll('.tab-btn');
    tabButtons.forEach(btn => {
        btn.classList.remove('active');
    });

    // Show selected tab content
    const selectedContent = document.querySelector(`.tab-content[data-tab="${tabName}"]`);
    if (selectedContent) {
        selectedContent.classList.add('active');
    }

    // Activate selected tab button
    const selectedButton = document.querySelector(`.tab-btn[data-tab="${tabName}"]`);
    if (selectedButton) {
        selectedButton.classList.add('active');
    }
}

// Initialize tabs on page load (for full page form)
document.addEventListener('DOMContentLoaded', function() {
    // Only run if not in modal context
    if (!document.getElementById('productModal')) {
        // Set first tab as active by default
        switchTab('product');

        // Initialize currency calculator if we're editing a product
        initCurrencyCalculator();

        // Add form submit handler to update variant group input before submission
        const productForm = document.querySelector('.product-form');
        if (productForm) {
            productForm.addEventListener('submit', function(e) {
                // Update variant group input before form submits
                if (typeof updateVariantGroupInput === 'function') {
                    updateVariantGroupInput();
                }
                // Let form submit normally (no preventDefault)
            });
        }
    }
});

// ==========================================
// Multi-Currency Calculator
// ==========================================
let exchangeRates = {
    'PLN': 1.0,
    'KRW': null,
    'USD': null,
    'EUR': null
};

let isCalculating = false; // Prevent infinite loops
let isUpdatingFromMargin = false; // Prevent loops when updating from margin
let priceRoundingMode = 'full'; // Default rounding mode, loaded from settings

/**
 * Round price according to warehouse settings
 * @param {number} price - Price to round
 * @param {string} mode - Rounding mode ('full' or 'decimal')
 * @returns {number} - Rounded price
 */
function roundPrice(price, mode = null) {
    if (!price || price === 0) return 0.00;

    const roundingMode = mode || priceRoundingMode;

    if (roundingMode === 'full') {
        // Round to full złoty (e.g., 45.67 → 46.00, 45.23 → 45.00)
        return Math.round(price);
    } else if (roundingMode === 'decimal') {
        // Round to .49 or .99 (psychological pricing)
        // Examples:
        //   45.23 → 45.49
        //   45.67 → 45.99
        const whole = Math.floor(price);
        const decimal = price - whole;

        if (decimal < 0.50) {
            return parseFloat(`${whole}.49`);
        } else {
            return parseFloat(`${whole}.99`);
        }
    } else {
        // Fallback: no rounding
        return parseFloat(price.toFixed(2));
    }
}

/**
 * Load price rounding mode from warehouse settings
 */
async function loadPriceRoundingMode() {
    try {
        // Try to get rounding mode from a data attribute on the form
        const formElement = document.querySelector('.product-form');
        if (formElement && formElement.dataset.priceRounding) {
            priceRoundingMode = formElement.dataset.priceRounding;
            console.log('Price rounding mode loaded from form:', priceRoundingMode);
            return;
        }

        // Fallback: Fetch from API or assume 'full'
        // For now, default to 'full'
        priceRoundingMode = 'full';
        console.log('Price rounding mode defaulted to:', priceRoundingMode);
    } catch (error) {
        console.error('Error loading price rounding mode:', error);
        priceRoundingMode = 'full';
    }
}

/**
 * Initialize currency calculator (Global function accessible from modal)
 */
window.initCurrencyCalculator = function() {
    console.log('=== initCurrencyCalculator called ===');

    // Load price rounding mode from settings
    loadPriceRoundingMode();

    // Try both normal IDs and modal IDs
    const purchasePriceInput = document.getElementById('purchase_price') || document.getElementById('purchase_price_modal');
    const purchaseCurrencySelect = document.getElementById('purchase_currency') || document.getElementById('purchase_currency_modal');
    const purchasePricePlnInput = document.getElementById('purchase_price_pln') || document.getElementById('purchase_price_pln_modal');
    const salePriceInput = document.querySelector('#sale_price, input[name="sale_price"]');
    const marginInput = document.getElementById('margin') || document.getElementById('margin_modal');
    const marginAmountInput = document.getElementById('margin_amount_modal');

    console.log('Found elements:', {
        purchasePriceInput: !!purchasePriceInput,
        purchaseCurrencySelect: !!purchaseCurrencySelect,
        purchasePricePlnInput: !!purchasePricePlnInput,
        salePriceInput: !!salePriceInput,
        marginInput: !!marginInput,
        marginAmountInput: !!marginAmountInput
    });

    if (!purchasePriceInput || !purchaseCurrencySelect) {
        console.warn('Currency calculator elements not found, exiting');
        return; // Not on a page with these fields
    }

    // Remove any existing listeners to avoid duplication
    const newPurchasePriceInput = purchasePriceInput.cloneNode(true);
    purchasePriceInput.parentNode.replaceChild(newPurchasePriceInput, purchasePriceInput);

    const newPurchaseCurrencySelect = purchaseCurrencySelect.cloneNode(true);
    purchaseCurrencySelect.parentNode.replaceChild(newPurchaseCurrencySelect, purchaseCurrencySelect);

    // Listen to changes on purchase price and currency
    console.log('Adding event listeners...');
    newPurchasePriceInput.addEventListener('input', debounce(calculatePricePLN, 300));
    newPurchaseCurrencySelect.addEventListener('change', calculatePricePLN);
    console.log('Event listeners added');

    // Listen to changes on sale price to recalculate margin
    if (salePriceInput) {
        const newSalePriceInput = salePriceInput.cloneNode(true);
        salePriceInput.parentNode.replaceChild(newSalePriceInput, salePriceInput);
        newSalePriceInput.addEventListener('input', debounce(calculateMargin, 300));
        console.log('Sale price listener added');
    }

    // Listen to changes on margin % to recalculate sale price
    if (marginInput) {
        const newMarginInput = marginInput.cloneNode(true);
        marginInput.parentNode.replaceChild(newMarginInput, marginInput);
        newMarginInput.addEventListener('input', debounce(calculateSalePriceFromMarginPercent, 300));
        console.log('Margin % listener added');
    }

    // Listen to changes on margin amount to recalculate sale price
    if (marginAmountInput) {
        const newMarginAmountInput = marginAmountInput.cloneNode(true);
        marginAmountInput.parentNode.replaceChild(newMarginAmountInput, marginAmountInput);
        newMarginAmountInput.addEventListener('input', debounce(calculateSalePriceFromMarginAmount, 300));
        console.log('Margin amount listener added');
    }

    // If editing existing product, fetch current rates
    const currentCurrency = newPurchaseCurrencySelect.value;
    console.log('Current currency:', currentCurrency);
    if (currentCurrency && currentCurrency !== 'PLN') {
        console.log('Fetching exchange rate for:', currentCurrency);
        fetchExchangeRate(currentCurrency);
    }
}

/**
 * Fetch exchange rate from API
 */
async function fetchExchangeRate(currency) {
    console.log('=== fetchExchangeRate called ===', currency);

    if (currency === 'PLN') {
        console.log('Currency is PLN, no conversion needed');
        exchangeRates['PLN'] = 1.0;
        updateExchangeRateInfo(currency, 1.0, false, null);
        return 1.0;
    }

    try {
        console.log('Fetching from API:', `/api/exchange-rate?currency=${currency}`);
        const response = await fetch(`/api/exchange-rate?currency=${currency}`);
        console.log('API Response status:', response.status);

        const data = await response.json();
        console.log('API Response data:', data);

        if (data.success) {
            exchangeRates[currency] = data.rate;
            console.log('Exchange rate cached:', exchangeRates);
            updateExchangeRateInfo(currency, data.rate, data.cached, data.cached_at);
            return data.rate;
        } else {
            console.error('API returned error:', data.message);
            window.showToast(`Błąd pobierania kursu: ${data.message}`, 'error');
            return null;
        }
    } catch (error) {
        console.error('Error fetching exchange rate:', error);
        window.showToast('Nie udało się pobrać kursu waluty. Sprawdź połączenie z internetem.', 'error');
        return null;
    }
}

/**
 * Calculate purchase price in PLN
 */
async function calculatePricePLN() {
    console.log('=== calculatePricePLN called ===');

    if (isCalculating) {
        console.log('Already calculating, skipping');
        return;
    }
    isCalculating = true;

    const purchasePriceInput = document.getElementById('purchase_price') || document.getElementById('purchase_price_modal');
    const purchaseCurrencySelect = document.getElementById('purchase_currency') || document.getElementById('purchase_currency_modal');
    const purchasePricePlnInput = document.getElementById('purchase_price_pln') || document.getElementById('purchase_price_pln_modal');
    const currencyUnitSpan = document.getElementById('currency_unit') || document.getElementById('currency_unit_modal');

    console.log('Rechecked elements:', {
        purchasePriceInput: !!purchasePriceInput,
        purchaseCurrencySelect: !!purchaseCurrencySelect,
        purchasePricePlnInput: !!purchasePricePlnInput
    });

    if (!purchasePriceInput || !purchaseCurrencySelect || !purchasePricePlnInput) {
        console.warn('Missing elements in calculatePricePLN');
        isCalculating = false;
        return;
    }

    const purchasePrice = parseFloat(purchasePriceInput.value);
    const currency = purchaseCurrencySelect.value;

    console.log('Values:', { purchasePrice, currency });

    // Update currency unit display
    if (currencyUnitSpan) {
        currencyUnitSpan.textContent = currency;
        console.log('Updated currency unit to:', currency);
    }

    if (!purchasePrice || isNaN(purchasePrice)) {
        console.log('No valid purchase price');
        purchasePricePlnInput.value = '';
        isCalculating = false;
        calculateMargin(); // Recalculate margin even if empty
        return;
    }

    if (currency === 'PLN') {
        console.log('Currency is PLN, no conversion needed');
        // No conversion needed
        purchasePricePlnInput.value = purchasePrice.toFixed(2);
        isCalculating = false;
        calculateMargin();
        return;
    }

    // Fetch exchange rate if not cached
    let rate = exchangeRates[currency];
    console.log('Cached rate:', rate);

    if (!rate) {
        console.log('Rate not cached, fetching...');
        rate = await fetchExchangeRate(currency);
        if (!rate) {
            console.error('Failed to fetch exchange rate');
            isCalculating = false;
            return;
        }
    }

    // Calculate PLN price
    const pricePLN = purchasePrice * rate;
    console.log('Calculated PLN price:', pricePLN, '=', purchasePrice, 'x', rate);
    purchasePricePlnInput.value = pricePLN.toFixed(2);

    isCalculating = false;
    calculateMargin();
}

/**
 * Calculate margin percentage and amount from sale and purchase prices
 */
function calculateMargin() {
    console.log('=== calculateMargin called ===');

    if (isCalculating || isUpdatingFromMargin) {
        console.log('Currently calculating or updating from margin, skipping');
        return;
    }

    const salePriceInput = document.querySelector('#sale_price, input[name="sale_price"]');
    const purchasePricePlnInput = document.getElementById('purchase_price_pln') || document.getElementById('purchase_price_pln_modal');
    const marginInput = document.getElementById('margin') || document.getElementById('margin_modal');
    const marginAmountInput = document.getElementById('margin_amount_modal');

    console.log('Margin calculation elements:', {
        salePriceInput: !!salePriceInput,
        purchasePricePlnInput: !!purchasePricePlnInput,
        marginInput: !!marginInput,
        marginAmountInput: !!marginAmountInput
    });

    if (!salePriceInput || !purchasePricePlnInput || !marginInput) {
        console.warn('Missing elements for margin calculation');
        return;
    }

    const salePrice = parseFloat(salePriceInput.value);
    const purchasePricePLN = parseFloat(purchasePricePlnInput.value);

    console.log('Margin values:', { salePrice, purchasePricePLN });

    if (!salePrice || !purchasePricePLN || isNaN(salePrice) || isNaN(purchasePricePLN)) {
        console.log('Invalid prices for margin calculation');
        marginInput.value = '';
        if (marginAmountInput) {
            marginAmountInput.value = '';
        }
        return;
    }

    if (purchasePricePLN === 0) {
        console.log('Purchase price is 0, cannot calculate margin');
        marginInput.value = '';
        if (marginAmountInput) {
            marginAmountInput.value = '';
        }
        return;
    }

    // Calculate margin percentage: ((sale - purchase) / purchase) * 100
    const marginPercent = ((salePrice - purchasePricePLN) / purchasePricePLN) * 100;

    // Calculate margin amount: sale - purchase
    const marginAmount = salePrice - purchasePricePLN;

    console.log('Calculated margin:', marginPercent.toFixed(2) + '%', '(' + marginAmount.toFixed(2) + ' PLN)');

    marginInput.value = marginPercent.toFixed(2);
    if (marginAmountInput) {
        marginAmountInput.value = marginAmount.toFixed(2);
    }
}

/**
 * Calculate sale price from margin percentage
 * Formula: sale_price = purchase_price_pln * (1 + margin_percent / 100)
 */
function calculateSalePriceFromMarginPercent() {
    console.log('=== calculateSalePriceFromMarginPercent called ===');

    if (isCalculating) {
        console.log('Currently calculating, skipping');
        return;
    }

    isUpdatingFromMargin = true;

    const marginInput = document.getElementById('margin') || document.getElementById('margin_modal');
    const purchasePricePlnInput = document.getElementById('purchase_price_pln') || document.getElementById('purchase_price_pln_modal');
    const salePriceInput = document.querySelector('#sale_price, input[name="sale_price"]');
    const marginAmountInput = document.getElementById('margin_amount_modal');

    if (!marginInput || !purchasePricePlnInput || !salePriceInput) {
        console.warn('Missing elements for sale price calculation from margin %');
        isUpdatingFromMargin = false;
        return;
    }

    const marginPercent = parseFloat(marginInput.value);
    const purchasePricePLN = parseFloat(purchasePricePlnInput.value);

    console.log('Values:', { marginPercent, purchasePricePLN });

    if (isNaN(marginPercent) || !purchasePricePLN || isNaN(purchasePricePLN) || purchasePricePLN === 0) {
        console.log('Invalid values for calculation');
        isUpdatingFromMargin = false;
        return;
    }

    // Calculate sale price: purchase * (1 + margin% / 100)
    let salePrice = purchasePricePLN * (1 + marginPercent / 100);

    // Apply price rounding according to warehouse settings
    salePrice = roundPrice(salePrice);

    const marginAmount = salePrice - purchasePricePLN;

    console.log('Calculated sale price (before rounding):', (purchasePricePLN * (1 + marginPercent / 100)).toFixed(2), 'PLN');
    console.log('Calculated sale price (after rounding):', salePrice.toFixed(2), 'PLN');

    salePriceInput.value = salePrice.toFixed(2);

    // Update margin amount
    if (marginAmountInput) {
        marginAmountInput.value = marginAmount.toFixed(2);
    }

    isUpdatingFromMargin = false;
}

/**
 * Calculate sale price from margin amount
 * Formula: sale_price = purchase_price_pln + margin_amount
 */
function calculateSalePriceFromMarginAmount() {
    console.log('=== calculateSalePriceFromMarginAmount called ===');

    if (isCalculating) {
        console.log('Currently calculating, skipping');
        return;
    }

    isUpdatingFromMargin = true;

    const marginAmountInput = document.getElementById('margin_amount_modal');
    const purchasePricePlnInput = document.getElementById('purchase_price_pln') || document.getElementById('purchase_price_pln_modal');
    const salePriceInput = document.querySelector('#sale_price, input[name="sale_price"]');
    const marginInput = document.getElementById('margin') || document.getElementById('margin_modal');

    if (!marginAmountInput || !purchasePricePlnInput || !salePriceInput) {
        console.warn('Missing elements for sale price calculation from margin amount');
        isUpdatingFromMargin = false;
        return;
    }

    const marginAmount = parseFloat(marginAmountInput.value);
    const purchasePricePLN = parseFloat(purchasePricePlnInput.value);

    console.log('Values:', { marginAmount, purchasePricePLN });

    if (isNaN(marginAmount) || !purchasePricePLN || isNaN(purchasePricePLN) || purchasePricePLN === 0) {
        console.log('Invalid values for calculation');
        isUpdatingFromMargin = false;
        return;
    }

    // Calculate sale price: purchase + margin_amount
    let salePrice = purchasePricePLN + marginAmount;

    // Apply price rounding according to warehouse settings
    salePrice = roundPrice(salePrice);

    const marginPercent = (marginAmount / purchasePricePLN) * 100;

    console.log('Calculated sale price (before rounding):', (purchasePricePLN + marginAmount).toFixed(2), 'PLN');
    console.log('Calculated sale price (after rounding):', salePrice.toFixed(2), 'PLN');

    salePriceInput.value = salePrice.toFixed(2);

    // Update margin percentage
    if (marginInput) {
        marginInput.value = marginPercent.toFixed(2);
    }

    isUpdatingFromMargin = false;
}

/**
 * Initialize form submission handler for AJAX
 */
window.initFormSubmission = function() {
    console.log('=== initFormSubmission called ===');

    const form = document.getElementById('productFormModal');
    if (!form) {
        console.log('Form not found');
        return;
    }

    console.log('Form found, attaching submit listener');

    form.addEventListener('submit', async function(e) {
        e.preventDefault();

        console.log('[FORM] Form submission intercepted');

        // Save variant groups first (if exists)
        if (typeof window.saveVariantGroups === 'function') {
            console.log('[FORM] Calling saveVariantGroups...');
            const variantsSaved = await window.saveVariantGroups();
            if (!variantsSaved) {
                console.error('[FORM] Failed to save variant groups');
                alert('Nie udało się zapisać grup wariantowych. Sprawdź konsolę.');
                return; // Stop submission if variant groups failed to save
            }
            console.log('[FORM] Variant groups saved successfully');
        } else {
            console.log('[FORM] saveVariantGroups function not found (may not be loaded yet)');
        }

        console.log('[FORM] Proceeding with form submission...');

        const formData = new FormData(form);

        // Manually add checked tags (hidden checkboxes may not be sent)
        const tagCheckboxes = form.querySelectorAll('input[name="tags"]:checked');
        formData.delete('tags'); // Remove any existing tags entries
        tagCheckboxes.forEach(checkbox => {
            formData.append('tags', checkbox.value);
        });

        // Set button to loading state
        setButtonLoading(true);

        try {
            console.log('Sending POST to:', form.action);
            console.log('Headers being sent:', {
                'X-Requested-With': 'XMLHttpRequest'
            });

            const response = await fetch(form.action, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            console.log('Response status:', response.status);
            console.log('Response headers:', Array.from(response.headers.entries()));

            // Check if response is JSON
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                const data = await response.json();
                console.log('JSON response:', data);

                if (data.success) {
                    // Show success message
                    if (typeof window.showToast === 'function') {
                        window.showToast(data.message, 'success');
                    } else {
                        alert(data.message);
                    }

                    console.log('[FORM] Product saved successfully. Refreshing products list...');

                    // Close modal and refresh list after 1.5 seconds (time to read toast)
                    setTimeout(() => {
                        // Close modal
                        if (typeof closeProductModal === 'function') {
                            closeProductModal();
                        }

                        // Refresh products list (instead of full page reload)
                        if (typeof refreshProductsList === 'function') {
                            refreshProductsList();
                        } else {
                            // Fallback to full page reload if function not available
                            console.log('[FORM] refreshProductsList not available, falling back to page reload');
                            if (data.redirect) {
                                window.location.href = data.redirect;
                            } else {
                                window.location.reload();
                            }
                        }
                    }, 1500);
                } else {
                    // Show error message
                    if (typeof window.showToast === 'function') {
                        window.showToast(data.error || 'Wystąpił błąd podczas zapisywania produktu.', 'error');
                    } else {
                        alert(data.error || 'Wystąpił błąd podczas zapisywania produktu.');
                    }

                    // Re-enable submit button
                    setButtonLoading(false);
                }
            } else {
                // Response is HTML (probably validation errors), reload the form
                const html = await response.text();
                console.log('HTML response received (validation errors)');

                // Parse HTML to extract validation errors
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, 'text/html');
                const errorElements = doc.querySelectorAll('.form-error');

                // Collect all error messages
                const errors = [];
                errorElements.forEach(el => {
                    const errorText = el.textContent.trim();
                    if (errorText && !errors.includes(errorText)) {
                        errors.push(errorText);
                    }
                });

                // Show toast with errors
                if (errors.length > 0 && typeof window.showToast === 'function') {
                    const errorMessage = errors.length === 1
                        ? errors[0]
                        : `Formularz zawiera błędy:\n• ${errors.join('\n• ')}`;
                    window.showToast(errorMessage, 'error');
                }

                // Replace modal body with new form (with validation errors)
                const modalBody = document.getElementById('modalBody');
                if (modalBody) {
                    modalBody.innerHTML = html;

                    // Re-initialize after replacing content
                    if (typeof initCurrencyCalculator === 'function') {
                        initCurrencyCalculator();
                    }
                    if (typeof initTagsSystem === 'function') {
                        initTagsSystem();
                    }
                    if (typeof initFormSubmission === 'function') {
                        initFormSubmission();
                    }
                }

                // Re-enable submit button
                setButtonLoading(false);
            }
        } catch (error) {
            console.error('Error submitting form:', error);

            if (typeof window.showToast === 'function') {
                window.showToast('Wystąpił błąd podczas zapisywania produktu.', 'error');
            } else {
                alert('Wystąpił błąd podczas zapisywania produktu.');
            }

            // Re-enable submit button
            setButtonLoading(false);
        }
    });

    console.log('Form submit listener attached');
}

/**
 * Update exchange rate info text
 */
function updateExchangeRateInfo(currency, rate, cached, cachedAt) {
    const infoElement = document.getElementById('exchange-rate-info') || document.getElementById('exchange-rate-info-modal');
    if (!infoElement) return;

    if (currency === 'PLN') {
        infoElement.textContent = '';
        return;
    }

    let infoText = `1 ${currency} = ${rate.toFixed(4)} PLN`;

    if (cached && cachedAt) {
        const cacheDate = new Date(cachedAt);
        const now = new Date();
        const diffHours = Math.round((now - cacheDate) / 1000 / 60 / 60);
        infoText += ` (cache: ${diffHours}h temu)`;
    }

    infoElement.textContent = infoText;
}

/**
 * Debounce function to limit API calls
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// ==========================================
// Image Upload
// ==========================================
async function uploadImages() {
    const fileInput = document.getElementById('image-upload');
    const files = fileInput.files;

    if (!files || files.length === 0) {
        window.showToast('Nie wybrano żadnych plików.', 'warning');
        return;
    }

    // Validate file types
    const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp'];
    for (let file of files) {
        if (!allowedTypes.includes(file.type)) {
            window.showToast(`Nieprawidłowy typ pliku: ${file.name}. Dozwolone: JPG, PNG, GIF, WEBP.`, 'error');
            return;
        }
    }

    // Get product ID from URL
    const pathParts = window.location.pathname.split('/');
    const productId = pathParts[pathParts.indexOf('products') + 1];

    if (!productId || productId === 'create') {
        window.showToast('Najpierw zapisz produkt, a następnie dodaj zdjęcia.', 'error');
        return;
    }

    // Prepare FormData
    const formData = new FormData();
    for (let file of files) {
        formData.append('images', file);
    }

    try {
        const response = await fetch(`/admin/products/${productId}/images/upload`, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        const data = await response.json();

        if (data.success) {
            window.showToast(data.message, 'success');

            // Add uploaded images to grid
            for (let image of data.images) {
                addImageToGrid(image);
            }

            // Clear file input
            fileInput.value = '';
        } else {
            window.showToast(data.error || 'Nie udało się przesłać zdjęć.', 'error');
        }
    } catch (error) {
        console.error('Error uploading images:', error);
        window.showToast('Wystąpił błąd podczas przesyłania zdjęć.', 'error');
    }
}

/**
 * Add image to grid after upload
 */
function addImageToGrid(image) {
    const imagesGrid = document.querySelector('.images-grid');
    if (!imagesGrid) return;

    // Remove placeholder if this is the first image
    const placeholder = imagesGrid.querySelector('.image-upload-placeholder');

    // Create image item
    const imageItem = document.createElement('div');
    imageItem.className = 'image-item';
    imageItem.dataset.imageId = image.id;

    imageItem.innerHTML = `
        <img src="/${image.path_compressed}" alt="${image.filename}" class="image-preview">
        <div class="image-overlay">
            ${!image.is_primary ? `<button type="button" class="btn-icon-small btn-set-primary" onclick="setPrimaryImage(${image.id})">Ustaw jako główne</button>` : '<span class="badge-primary">Główne zdjęcie</span>'}
            <button type="button" class="btn-icon-small btn-delete-image" onclick="deleteImage(${image.id})">Usuń</button>
        </div>
    `;

    // Insert before placeholder
    if (placeholder) {
        imagesGrid.insertBefore(imageItem, placeholder);
    } else {
        imagesGrid.appendChild(imageItem);
    }
}

/**
 * Delete image
 */
async function deleteImage(imageId) {
    if (!confirm('Czy na pewno chcesz usunąć to zdjęcie?')) {
        return;
    }

    // Get product ID from URL
    const pathParts = window.location.pathname.split('/');
    const productId = pathParts[pathParts.indexOf('products') + 1];

    try {
        const response = await fetch(`/admin/products/${productId}/images/${imageId}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        const data = await response.json();

        if (data.success) {
            window.showToast(data.message, 'success');

            // Remove image from grid
            const imageItem = document.querySelector(`[data-image-id="${imageId}"]`);
            if (imageItem) {
                imageItem.remove();
            }

            // If this was primary image, reload page to update primary status
            if (data.new_primary_id) {
                setTimeout(() => {
                    location.reload();
                }, 1000);
            }
        } else {
            window.showToast(data.error || 'Nie udało się usunąć zdjęcia.', 'error');
        }
    } catch (error) {
        console.error('Error deleting image:', error);
        window.showToast('Wystąpił błąd podczas usuwania zdjęcia.', 'error');
    }
}

/**
 * Set image as primary
 */
async function setPrimaryImage(imageId) {
    // Get product ID from URL
    const pathParts = window.location.pathname.split('/');
    const productId = pathParts[pathParts.indexOf('products') + 1];

    try {
        const response = await fetch(`/admin/products/${productId}/images/${imageId}/set-primary`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        const data = await response.json();

        if (data.success) {
            window.showToast(data.message, 'success');

            // Reload page to update UI
            setTimeout(() => {
                location.reload();
            }, 500);
        } else {
            window.showToast(data.error || 'Nie udało się ustawić głównego zdjęcia.', 'error');
        }
    } catch (error) {
        console.error('Error setting primary image:', error);
        window.showToast('Wystąpił błąd podczas ustawiania głównego zdjęcia.', 'error');
    }
}

// ==========================================
// Toast Notifications
// ==========================================
// Removed local showToast function - using global window.showToast instead

// Add CSS animations
if (!document.getElementById('toast-animations')) {
    const style = document.createElement('style');
    style.id = 'toast-animations';
    style.textContent = `
        @keyframes slideIn {
            from {
                transform: translateX(400px);
                opacity: 0;
            }
            to {
                transform: translateX(0);
                opacity: 1;
            }
        }
        @keyframes slideOut {
            from {
                transform: translateX(0);
                opacity: 1;
            }
            to {
                transform: translateX(400px);
                opacity: 0;
            }
        }
    `;
    document.head.appendChild(style);
}

// ==========================================
// Image Slots Management
// ==========================================
window.handleSlotImageSelect = function(slotNumber, event) {
    const file = event.target.files[0];
    if (!file) return;

    // Validate file type
    const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp'];
    if (!allowedTypes.includes(file.type)) {
        window.showToast('Nieprawidłowy typ pliku. Dozwolone: JPG, PNG, GIF, WEBP.', 'error');
        return;
    }

    // Validate file size (max 5MB)
    const maxSize = 5 * 1024 * 1024;
    if (file.size > maxSize) {
        window.showToast('Plik jest za duży. Maksymalny rozmiar: 5MB.', 'error');
        return;
    }

    // Read and display preview
    const reader = new FileReader();
    reader.onload = function(e) {
        const uploadLabel = document.getElementById(`uploadLabel${slotNumber}`);
        const preview = document.getElementById(`preview${slotNumber}`);
        const previewImg = document.getElementById(`previewImg${slotNumber}`);

        if (uploadLabel && preview && previewImg) {
            previewImg.src = e.target.result;
            uploadLabel.style.display = 'none';
            preview.style.display = 'block';
        }
    };
    reader.readAsDataURL(file);
};

window.removeSlotImage = function(slotNumber, imageId) {
    const input = document.getElementById(`imageInput${slotNumber}`);
    const uploadLabel = document.getElementById(`uploadLabel${slotNumber}`);
    const preview = document.getElementById(`preview${slotNumber}`);
    const previewImg = document.getElementById(`previewImg${slotNumber}`);

    // If imageId is provided, this is an existing image - delete from server
    if (imageId) {
        // Get product_id from form action URL
        const form = document.getElementById('productFormModal');
        const actionUrl = form.getAttribute('action');
        const productIdMatch = actionUrl.match(/\/products\/(\d+)\//);

        if (productIdMatch) {
            const productId = productIdMatch[1];

            if (confirm('Czy na pewno chcesz usunąć to zdjęcie?')) {
                // Get CSRF token from form
                const csrfToken = form.querySelector('input[name="csrf_token"]').value;

                // Delete from server
                fetch(`/admin/products/${productId}/images/${imageId}`, {
                    method: 'DELETE',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                        'X-CSRFToken': csrfToken
                    }
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        // Clear the slot
                        if (input) input.value = '';
                        if (previewImg) previewImg.src = '';
                        if (preview) preview.style.display = 'none';
                        if (uploadLabel) uploadLabel.style.display = 'flex';

                        if (typeof window.showToast === 'function') {
                            window.showToast('Zdjęcie zostało usunięte.', 'success');
                        }
                    } else {
                        if (typeof window.showToast === 'function') {
                            window.showToast(data.error || 'Błąd podczas usuwania zdjęcia.', 'error');
                        }
                    }
                })
                .catch(error => {
                    console.error('Error deleting image:', error);
                    if (typeof window.showToast === 'function') {
                        window.showToast('Błąd podczas usuwania zdjęcia.', 'error');
                    }
                });
            }
        }
    } else {
        // This is a newly selected image (not yet saved) - just clear the preview
        if (input) input.value = '';
        if (previewImg) previewImg.src = '';
        if (preview) preview.style.display = 'none';
        if (uploadLabel) uploadLabel.style.display = 'flex';
    }
};

// ==========================================
// Product Type Toggle Bar
// ==========================================
function initProductTypeToggle() {
    const toggleButtons = document.querySelectorAll('.toggle-option');
    const hiddenSelect = document.querySelector('select[name="product_type_id"]');
    const toggleSlider = document.querySelector('.toggle-slider');

    if (!toggleButtons.length || !hiddenSelect || !toggleSlider) {
        return; // Exit if elements not found
    }

    // Handle toggle button clicks
    toggleButtons.forEach((button, index) => {
        button.addEventListener('click', function(e) {
            e.preventDefault();

            // Remove active class from all buttons
            toggleButtons.forEach(btn => btn.classList.remove('active'));

            // Add active class to clicked button
            this.classList.add('active');

            // Update hidden select value
            const typeId = this.getAttribute('data-type-id');
            hiddenSelect.value = typeId;

            // Move slider based on which button was clicked
            const typeSlug = this.getAttribute('data-type-slug');
            if (typeSlug === 'pre-order') {
                toggleSlider.style.left = '4px';
            } else if (typeSlug === 'on-hand') {
                toggleSlider.style.left = 'calc(33.333% + 1px)';
            } else if (typeSlug === 'exclusive') {
                toggleSlider.style.left = 'calc(66.666% - 2px)';
            }
        });
    });

    // Set initial slider position based on current selection
    const activeButton = document.querySelector('.toggle-option.active');
    if (activeButton) {
        const typeSlug = activeButton.getAttribute('data-type-slug');
        const typeId = activeButton.getAttribute('data-type-id');

        // Update hidden select value
        hiddenSelect.value = typeId;

        // Set slider position
        if (typeSlug === 'pre-order') {
            toggleSlider.style.left = '4px';
        } else if (typeSlug === 'on-hand') {
            toggleSlider.style.left = 'calc(33.333% + 1px)';
        } else if (typeSlug === 'exclusive') {
            toggleSlider.style.left = 'calc(66.666% - 2px)';
        }
    }
}

// Initialize product type toggle on page load
document.addEventListener('DOMContentLoaded', function() {
    initProductTypeToggle();
});

// Also initialize when modal is shown (for modal context)
window.initProductTypeToggle = initProductTypeToggle;
