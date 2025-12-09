/**
 * Stock Orders - PROXY Tab Modal
 * Handles modal for adding new stock orders
 */

// Selected products storage
let selectedProducts = [];

// Debounce timer
let searchDebounceTimer = null;

/**
 * Open the new order modal
 */
function openNewOrderModal() {
    console.log('openNewOrderModal called');
    const modal = document.getElementById('newOrderModal');
    console.log('Modal element:', modal);
    if (modal) {
        console.log('Adding active class to modal');
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';

        // Reset modal state
        selectedProducts = [];
        updateSelectedProductsTable();
        document.getElementById('productSearch').value = '';
        document.getElementById('searchResults').innerHTML = '<p class="text-muted">Wpisz nazwę, SKU, EAN lub ID produktu</p>';
        console.log('Modal should be visible now');
    } else {
        console.error('Modal element not found!');
    }
}

/**
 * Close the new order modal with animation
 */
function closeNewOrderModal() {
    const modal = document.getElementById('newOrderModal');
    if (modal && modal.classList.contains('active')) {
        // Dodaj klasę closing dla animacji
        modal.classList.add('closing');

        // Po zakończeniu animacji usuń klasy
        setTimeout(() => {
            modal.classList.remove('active');
            modal.classList.remove('closing');
            document.body.style.overflow = '';
        }, 350); // 350ms = czas trwania animacji
    }
}

/**
 * Toggle filters panel visibility
 */
function toggleFilters() {
    const filtersPanel = document.getElementById('filtersPanel');

    if (filtersPanel.style.display === 'none' || filtersPanel.style.display === '') {
        filtersPanel.style.display = 'block';
    } else {
        filtersPanel.style.display = 'none';
    }
}

/**
 * Clear all filters and search
 */
function clearFilters() {
    // Reset all filter selects
    document.getElementById('filterCategory').value = '';
    document.getElementById('filterManufacturer').value = '';
    document.getElementById('filterSupplier').value = '';
    document.getElementById('filterSeries').value = '';

    // Clear tag filter (multi-select)
    const tagSelect = document.getElementById('filterTag');
    if (tagSelect) {
        tagSelect.selectedIndex = -1;
    }

    // Clear search input
    document.getElementById('productSearch').value = '';

    // Reset search results to initial state
    document.getElementById('searchResults').innerHTML = '<p class="text-muted">Wpisz nazwę, SKU, EAN lub ID produktu</p>';
}

/**
 * Search products with debouncing
 */
function searchProducts() {
    clearTimeout(searchDebounceTimer);

    searchDebounceTimer = setTimeout(() => {
        const searchQuery = document.getElementById('productSearch').value.trim();
        const categoryId = document.getElementById('filterCategory').value;
        const manufacturerId = document.getElementById('filterManufacturer').value;
        const supplierId = document.getElementById('filterSupplier').value;
        const seriesId = document.getElementById('filterSeries').value;
        const tagId = document.getElementById('filterTag').value;

        // Build query parameters
        const params = new URLSearchParams();
        if (searchQuery) params.append('q', searchQuery);
        if (categoryId) params.append('category_id', categoryId);
        if (manufacturerId) params.append('manufacturer_id', manufacturerId);
        if (supplierId) params.append('supplier_id', supplierId);
        if (seriesId) params.append('series_id', seriesId);
        if (tagId) params.append('tag_id', tagId);

        // Show loading state
        const searchResults = document.getElementById('searchResults');
        searchResults.innerHTML = '<p class="no-results">Szukam produktów...</p>';

        // Fetch results
        fetch(`/admin/products/api/search-products?${params.toString()}`)
            .then(response => response.json())
            .then(products => {
                displaySearchResults(products);
            })
            .catch(error => {
                console.error('Search error:', error);
                searchResults.innerHTML = '<p class="no-results error">Błąd podczas wyszukiwania. Spróbuj ponownie.</p>';
            });
    }, 300);
}

/**
 * Display search results as product cards
 */
function displaySearchResults(products) {
    const searchResults = document.getElementById('searchResults');

    if (!products || products.length === 0) {
        searchResults.innerHTML = '<p class="no-results">Nie znaleziono produktów</p>';
        return;
    }

    // Wrap products in a grid container
    const productsHTML = products.map(product => {
        // Check if product has a valid image URL (not placeholder SVG)
        const hasRealImage = product.image_url && !product.image_url.includes('placeholder');

        const imageHTML = hasRealImage
            ? `<img src="${product.image_url}" alt="${escapeHtml(product.name)}" class="product-card-image">`
            : `<div class="product-card-image product-thumbnail-placeholder">
                <svg width="48" height="48" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M6.002 5.5a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0z"></path>
                    <path d="M2.002 1a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V3a2 2 0 00-2-2h-12zm12 1a1 1 0 011 1v6.5l-3.777-1.947a.5.5 0 00-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 00-.63.062L1.002 12V3a1 1 0 011-1h12z"></path>
                </svg>
            </div>`;

        return `
        <div class="product-card" onclick="addProductToTable(${product.id}, '${escapeJs(product.name)}', '${escapeJs(product.sku)}', '${escapeJs(product.supplier_name)}', ${product.purchase_price}, '${product.purchase_currency}', ${product.purchase_price_pln}, '${escapeJs(product.image_url)}')">
            ${imageHTML}
            <div class="product-card-info">
                <h4>${escapeHtml(product.name)}</h4>
                <p class="product-sku">SKU: ${product.sku}</p>
                <p class="product-supplier">Dostawca: ${product.supplier_name}</p>
                <p class="product-price">
                    ${product.purchase_price.toFixed(2)} ${product.purchase_currency}
                    ${product.purchase_currency !== 'PLN' ? `(${product.purchase_price_pln.toFixed(2)} PLN)` : ''}
                </p>
            </div>
        </div>
    `}).join('');

    searchResults.innerHTML = `<div class="products-grid">${productsHTML}</div>`;
}

/**
 * Add product to selected products table
 */
function addProductToTable(id, name, sku, supplier, price, currency, pricePln, imageUrl) {
    console.log('Adding product to table:', { id, name, sku, supplier, price, currency, pricePln });

    // Check if product already in table
    const existingIndex = selectedProducts.findIndex(p => p.id === id);

    if (existingIndex >= 0) {
        // Increase quantity
        selectedProducts[existingIndex].quantity += 1;
        console.log('Product already exists, increased quantity');
    } else {
        // Add new product
        selectedProducts.push({
            id: id,
            name: name,
            sku: sku,
            supplier: supplier,
            price: price,
            currency: currency,
            pricePln: pricePln,
            imageUrl: imageUrl,
            quantity: 1
        });
        console.log('New product added to selectedProducts array');
    }

    console.log('Total selected products:', selectedProducts.length);
    updateSelectedProductsTable();
}

/**
 * Update the selected products table
 */
function updateSelectedProductsTable() {
    console.log('Updating selected products table, count:', selectedProducts.length);

    const tbody = document.getElementById('selectedProductsTableBody');
    const selectedSection = document.getElementById('selectedProductsSection');
    const submitBtn = document.getElementById('btnSubmitOrders');
    const orderCount = document.getElementById('orderCount');

    if (selectedProducts.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="no-products">Brak wybranych produktów</td></tr>';
        selectedSection.style.display = 'none';
        submitBtn.disabled = true;
        orderCount.textContent = '0';
        return;
    }

    // Show the selected products section
    selectedSection.style.display = 'block';
    submitBtn.disabled = false;
    orderCount.textContent = selectedProducts.length;

    tbody.innerHTML = selectedProducts.map((product, index) => {
        // Check if product has a valid image URL (not placeholder)
        const hasRealImage = product.imageUrl && !product.imageUrl.includes('placeholder');

        const imageHTML = hasRealImage
            ? `<img src="${product.imageUrl}" alt="${escapeHtml(product.name)}" class="table-product-image">`
            : `<div class="table-product-image product-thumbnail-placeholder">
                <svg width="24" height="24" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M6.002 5.5a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0z"></path>
                    <path d="M2.002 1a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V3a2 2 0 00-2-2h-12zm12 1a1 1 0 011 1v6.5l-3.777-1.947a.5.5 0 00-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 00-.63.062L1.002 12V3a1 1 0 011-1h12z"></path>
                </svg>
            </div>`;

        return `
        <tr>
            <td>${imageHTML}</td>
            <td>
                <strong>${escapeHtml(product.name)}</strong><br>
                <small>SKU: ${product.sku}</small>
            </td>
            <td>${product.sku}</td>
            <td>${product.supplier}</td>
            <td>
                ${product.price.toFixed(2)} ${product.currency}<br>
                ${product.currency !== 'PLN' ? `<small>${product.pricePln.toFixed(2)} PLN</small>` : ''}
            </td>
            <td>
                <div class="quantity-control">
                    <button type="button" class="qty-btn" onclick="changeQuantity(${index}, -1)">−</button>
                    <input type="number" value="${product.quantity}" min="1" onchange="setQuantity(${index}, this.value)" class="qty-input">
                    <button type="button" class="qty-btn" onclick="changeQuantity(${index}, 1)">+</button>
                </div>
            </td>
            <td>
                <strong>${(product.pricePln * product.quantity).toFixed(2)} PLN</strong>
            </td>
            <td>
                <button type="button" class="btn-remove" onclick="removeProduct(${index})" title="Usuń">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                        <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/>
                        <path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/>
                    </svg>
                </button>
            </td>
        </tr>
    `;
    }).join('');

    // Update total
    const total = selectedProducts.reduce((sum, p) => sum + (p.pricePln * p.quantity), 0);
    const totalElement = document.getElementById('totalAmount');
    if (totalElement) {
        totalElement.textContent = `${total.toFixed(2)} PLN`;
    }

    console.log('Total amount updated:', total.toFixed(2), 'PLN');
}

/**
 * Change product quantity
 */
function changeQuantity(index, delta) {
    if (selectedProducts[index]) {
        selectedProducts[index].quantity = Math.max(1, selectedProducts[index].quantity + delta);
        updateSelectedProductsTable();
    }
}

/**
 * Set product quantity directly
 */
function setQuantity(index, value) {
    const qty = parseInt(value);
    if (selectedProducts[index] && qty > 0) {
        selectedProducts[index].quantity = qty;
        updateSelectedProductsTable();
    }
}

/**
 * Remove product from table
 */
function removeProduct(index) {
    selectedProducts.splice(index, 1);
    updateSelectedProductsTable();
}

/**
 * Submit stock orders (one per product)
 */
function submitStockOrders() {
    if (selectedProducts.length === 0) {
        alert('Dodaj produkty do zamówienia');
        return;
    }

    // Show loading state
    const submitBtn = document.querySelector('#newOrderModal .btn-primary');
    const originalText = submitBtn.textContent;
    submitBtn.disabled = true;
    submitBtn.textContent = 'Tworzenie zamówień...';

    // Send to backend
    fetch('/admin/products/api/create-stock-orders', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify({
            order_type: 'proxy',
            products: selectedProducts.map(p => ({
                product_id: p.id,
                quantity: p.quantity,
                unit_price: p.pricePln,
                currency: p.currency
            }))
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert(`Utworzono ${data.orders_created} zamówień PROXY`);
            closeNewOrderModal();
            location.reload(); // Reload to show new orders
        } else {
            alert('Błąd: ' + (data.error || 'Nie udało się utworzyć zamówień'));
        }
    })
    .catch(error => {
        console.error('Submit error:', error);
        alert('Błąd podczas tworzenia zamówień. Spróbuj ponownie.');
    })
    .finally(() => {
        submitBtn.disabled = false;
        submitBtn.textContent = originalText;
    });
}

/**
 * Get CSRF token from meta tag or cookie
 */
function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.getAttribute('content');

    // Fallback to cookie
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
        const [name, value] = cookie.trim().split('=');
        if (name === 'csrf_token') return value;
    }
    return '';
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Escape string for use in JavaScript/onclick attributes
 */
function escapeJs(text) {
    if (!text) return '';
    return text.replace(/\\/g, '\\\\')
               .replace(/'/g, "\\'")
               .replace(/"/g, '\\"')
               .replace(/\n/g, '\\n')
               .replace(/\r/g, '\\r');
}

/**
 * Initialize event listeners
 */
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOMContentLoaded - Stock orders JS initialized');

    // New order button (primary)
    const btnNewOrder = document.getElementById('btnNewOrder');
    console.log('btnNewOrder element:', btnNewOrder);
    if (btnNewOrder) {
        console.log('Attaching click event to btnNewOrder');
        btnNewOrder.addEventListener('click', openNewOrderModal);
    } else {
        console.warn('btnNewOrder not found');
    }

    // New order button (empty state)
    const btnNewOrderEmpty = document.getElementById('btnNewOrderEmpty');
    console.log('btnNewOrderEmpty element:', btnNewOrderEmpty);
    if (btnNewOrderEmpty) {
        console.log('Attaching click event to btnNewOrderEmpty');
        btnNewOrderEmpty.addEventListener('click', openNewOrderModal);
    } else {
        console.warn('btnNewOrderEmpty not found (this is normal if there are existing orders)');
    }

    // Close modal on overlay click
    const modal = document.getElementById('newOrderModal');
    if (modal) {
        modal.addEventListener('click', function(e) {
            // Close only if clicking on the overlay itself (not the modal content)
            if (e.target === modal) {
                closeNewOrderModal();
            }
        });
    }

    // Search input with debounce
    const searchInput = document.getElementById('productSearch');
    if (searchInput) {
        searchInput.addEventListener('input', searchProducts);
    }

    // Filter selects
    const filterSelects = ['filterCategory', 'filterManufacturer', 'filterSupplier', 'filterSeries', 'filterTag'];
    filterSelects.forEach(id => {
        const select = document.getElementById(id);
        if (select) {
            select.addEventListener('change', searchProducts);
        }
    });
});
