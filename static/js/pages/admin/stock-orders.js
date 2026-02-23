/**
 * Stock Orders - Proxy & Poland tabs
 * Handles sorting, filtering, modals, and order management
 */

/**
 * Table sorting — universal for all tabs (Do zamówienia, Proxy, Polska)
 */
let currentSortColumn = null;
let currentSortDirection = 'asc';

// Map column names to data-attribute keys (camelCase for dataset API)
const COLUMN_TO_DATASET = {
    order_number: 'orderNumber',
    status: 'status',
    status_changed: 'statusChanged',
    date: 'date',
    amount: 'amount',
    quantity: 'toOrder',
    product_name: 'productName',
    sku: 'sku',
    payment_type: 'paymentType',
    purchase_price: 'purchasePrice',
    purchase_value: 'purchaseValue',
};

const NUMERIC_COLUMNS = new Set([
    'date', 'status_changed', 'amount', 'quantity',
    'purchase_price', 'purchase_value',
]);

function sortTable(column) {
    // Find the table that contains the clicked header
    const th = document.querySelector(`th.sortable[data-column="${column}"]`);
    if (!th) return;
    const table = th.closest('table');
    if (!table) return;

    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));

    if (currentSortColumn === column) {
        currentSortDirection = currentSortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        currentSortDirection = 'asc';
    }
    currentSortColumn = column;

    // Update header indicators (only within this table)
    table.querySelectorAll('th.sortable').forEach(h => {
        h.classList.remove('sorted-asc', 'sorted-desc');
        if (h.dataset.column === column) {
            h.classList.add(currentSortDirection === 'asc' ? 'sorted-asc' : 'sorted-desc');
        }
    });

    const dataKey = COLUMN_TO_DATASET[column] || column;
    const isNumeric = NUMERIC_COLUMNS.has(column);

    rows.sort((a, b) => {
        let aVal = a.dataset[dataKey] || '';
        let bVal = b.dataset[dataKey] || '';

        if (isNumeric) {
            aVal = parseFloat(aVal) || 0;
            bVal = parseFloat(bVal) || 0;
        } else {
            aVal = aVal.toLowerCase();
            bVal = bVal.toLowerCase();
        }

        if (aVal < bVal) return currentSortDirection === 'asc' ? -1 : 1;
        if (aVal > bVal) return currentSortDirection === 'asc' ? 1 : -1;
        return 0;
    });

    rows.forEach(row => tbody.appendChild(row));
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

// ============================================
// Poland Order Modal Functions
// ============================================

// Poland order data state
let polandOrderData = {
    proxyOrders: [],     // fetched proxy order details
    totalShipping: 0,    // total shipping cost declared
    items: []            // flat list of items with shipping costs
};

/**
 * Open Poland order modal - fetch proxy order details and display
 */
function openPolandOrderModal() {
    const checkedBoxes = document.querySelectorAll('.proxy-checkbox:checked');
    if (checkedBoxes.length === 0) {
        if (window.Toast) {
            window.Toast.show('Zaznacz zamówienia Proxy do wysłania do Polski', 'warning');
        }
        return;
    }

    const proxyOrderIds = Array.from(checkedBoxes).map(cb => parseInt(cb.value));

    // Show loading state
    const modal = document.getElementById('orderToPolandModal');
    const productsContainer = document.getElementById('polandProductsTable');
    productsContainer.innerHTML = '<p class="text-muted">Ładowanie danych zamówień...</p>';
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';

    // Reset state
    polandOrderData = {
        proxyOrders: [],
        totalShipping: 0,
        items: []
    };
    const totalInput = document.getElementById('totalShippingCost');
    totalInput.value = '';
    totalInput.oninput = calculateShippingCascade;
    document.getElementById('polandTrackingNumber').value = '';
    document.getElementById('polandOrderNote').value = '';
    document.getElementById('sumShippingCost').textContent = '0.00 PLN';
    document.getElementById('shippingDifference').textContent = '0.00 PLN';
    document.getElementById('shippingDifference').style.color = '#059669';

    // Fetch proxy order details
    fetch('/admin/products/api/get-proxy-orders-details', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify({ proxy_order_ids: proxyOrderIds })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            polandOrderData.proxyOrders = data.orders;
            renderPolandModal(data.orders);
        } else {
            productsContainer.innerHTML = '<p class="text-muted" style="color: #dc2626;">Błąd ładowania danych: ' + (data.error || 'Nieznany błąd') + '</p>';
        }
    })
    .catch(error => {
        console.error('Error fetching proxy orders:', error);
        productsContainer.innerHTML = '<p class="text-muted" style="color: #dc2626;">Błąd połączenia z serwerem</p>';
    });
}

/**
 * Render the Poland modal products table
 */
function renderPolandModal(orders) {
    const container = document.getElementById('polandProductsTable');
    polandOrderData.items = [];

    let html = '';

    orders.forEach((order, orderIndex) => {
        if (orderIndex > 0) {
            html += `<hr class="poland-package-separator">`;
        }
        html += `<div class="poland-package" data-order-id="${order.id}">`;
        html += `<div class="poland-package-header">`;
        html += `<span class="poland-package-title">Paczka: ${escapeHtml(order.order_number)}</span>`;
        html += `<div class="poland-package-shipping">`;
        html += `<label>Wysyłka:</label>`;
        html += `<input type="number" class="form-input package-shipping-input" `;
        html += `data-order-index="${orderIndex}" `;
        html += `placeholder="0,00" step="0.01" min="0" `;
        html += `oninput="handlePackageShippingChange(${orderIndex})">`;
        html += `<span class="input-suffix">PLN</span>`;
        html += `</div>`;
        html += `</div>`;

        html += `<table class="data-table poland-products-table">`;
        html += `<colgroup>`;
        html += `<col style="width: auto">`;
        html += `<col style="width: 110px">`;
        html += `<col style="width: 60px">`;
        html += `<col style="width: 110px">`;
        html += `</colgroup>`;
        html += `<thead><tr>`;
        html += `<th>Produkt</th>`;
        html += `<th>Cena/szt</th>`;
        html += `<th>Ilość</th>`;
        html += `<th>Wartość</th>`;
        html += `</tr></thead>`;
        html += `<tbody>`;

        order.items.forEach((item) => {
            const globalItemIndex = polandOrderData.items.length;

            polandOrderData.items.push({
                proxy_order_item_id: item.id,
                product_id: item.product.id,
                product_name: item.product.name,
                quantity: item.quantity,
                shipping_cost: 0,
                order_index: orderIndex
            });

            const hasRealImage = item.product.image_url && !item.product.image_url.includes('placeholder');
            const imageHTML = hasRealImage
                ? `<img src="${item.product.image_url}" alt="${escapeHtml(item.product.name)}" class="product-thumb-compact">`
                : `<div class="product-thumb-compact product-thumb-placeholder"><svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M6.002 5.5a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0z"></path><path d="M2.002 1a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V3a2 2 0 00-2-2h-12zm12 1a1 1 0 011 1v6.5l-3.777-1.947a.5.5 0 00-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 00-.63.062L1.002 12V3a1 1 0 011-1h12z"></path></svg></div>`;

            html += `<tr>`;
            html += `<td><div class="product-item-compact">${imageHTML}<span class="product-item-name">${escapeHtml(item.product.name)}</span></div></td>`;
            html += `<td>`;
            html += `<input type="number" class="form-input shipping-price-input" `;
            html += `data-item-index="${globalItemIndex}" `;
            html += `placeholder="0,00" step="0.01" min="0" `;
            html += `oninput="handleShippingPriceChange(${globalItemIndex})">`;
            html += `</td>`;
            html += `<td>${item.quantity} szt</td>`;
            html += `<td>`;
            html += `<input type="number" class="form-input shipping-value-input" `;
            html += `data-item-index="${globalItemIndex}" `;
            html += `placeholder="0,00" step="0.01" min="0" `;
            html += `oninput="handleShippingValueChange(${globalItemIndex})">`;
            html += `</td>`;
            html += `</tr>`;
        });

        html += `</tbody></table>`;
        html += `</div>`;
    });

    container.innerHTML = html;

    // Double-click on any shipping input: placeholder → value
    container.querySelectorAll('.shipping-price-input, .shipping-value-input, .package-shipping-input').forEach(input => {
        input.addEventListener('dblclick', function() {
            if (!this.value && this.placeholder && this.placeholder !== '0,00') {
                this.value = this.placeholder.replace(',', '.');
                this.dispatchEvent(new Event('input', { bubbles: true }));
            }
        });
        // Clear validation error on input
        input.addEventListener('input', function() {
            this.classList.remove('input-error');
        });
    });
}

/**
 * CASCADE DOWN: Total → Packages → Products (Wartość)
 * Distributes total shipping cost as PLACEHOLDER hints on Wartość inputs.
 * Also sets Cena/szt placeholder = wartość / ilość.
 */
function calculateShippingCascade() {
    const totalShipping = parseFloat(document.getElementById('totalShippingCost').value) || 0;
    polandOrderData.totalShipping = totalShipping;

    const orders = polandOrderData.proxyOrders;
    if (orders.length === 0) return;

    // Calculate: how much is manually entered in packages, how many are empty
    let enteredPackageSum = 0;
    let emptyPackageCount = 0;

    orders.forEach((order, orderIndex) => {
        const packageInput = document.querySelector(`.package-shipping-input[data-order-index="${orderIndex}"]`);
        if (packageInput && packageInput.value !== '') {
            enteredPackageSum += parseFloat(packageInput.value) || 0;
        } else {
            emptyPackageCount++;
        }
    });

    const remainingForEmpty = emptyPackageCount > 0 ? (totalShipping - enteredPackageSum) / emptyPackageCount : 0;

    orders.forEach((order, orderIndex) => {
        const packageInput = document.querySelector(`.package-shipping-input[data-order-index="${orderIndex}"]`);
        let packageCost;

        if (packageInput && packageInput.value !== '') {
            // Package has manual value — keep it, don't overwrite placeholder
            packageCost = parseFloat(packageInput.value) || 0;
        } else {
            // Package is empty — set placeholder to remaining share
            if (packageInput) {
                packageInput.placeholder = remainingForEmpty.toFixed(2).replace('.', ',');
            }
            packageCost = remainingForEmpty;
        }

        // Cascade down to products
        distributeToProducts(orderIndex, packageCost);
    });

    updateShippingSummary();
}

/**
 * Handle manual change to a package's shipping cost
 * CASCADE DOWN: Package → Products Wartość (placeholder hints)
 */
function handlePackageShippingChange(orderIndex) {
    // Mark this package as manually edited
    const thisInput = document.querySelector(`.package-shipping-input[data-order-index="${orderIndex}"]`);
    if (thisInput) {
        if (thisInput.value !== '') {
            thisInput.dataset.manual = 'true';
        } else {
            delete thisInput.dataset.manual;
        }
    }

    const totalShipping = parseFloat(document.getElementById('totalShippingCost').value) || 0;
    const orders = polandOrderData.proxyOrders;

    // Recalculate placeholders for OTHER packages
    let enteredSum = 0;
    let emptyPackageCount = 0;

    orders.forEach((order, idx) => {
        const inp = document.querySelector(`.package-shipping-input[data-order-index="${idx}"]`);
        if (inp && inp.value !== '') {
            enteredSum += parseFloat(inp.value) || 0;
        } else {
            emptyPackageCount++;
        }
    });

    const remainingForEmpty = emptyPackageCount > 0 ? (totalShipping - enteredSum) / emptyPackageCount : 0;

    orders.forEach((order, idx) => {
        const inp = document.querySelector(`.package-shipping-input[data-order-index="${idx}"]`);
        let packageCost;

        if (inp && inp.value !== '') {
            packageCost = parseFloat(inp.value) || 0;
        } else {
            if (inp) {
                inp.placeholder = remainingForEmpty.toFixed(2).replace('.', ',');
            }
            packageCost = remainingForEmpty;
        }

        // Cascade down to products for this package
        distributeToProducts(idx, packageCost);
    });

    updateShippingSummary();
}

/**
 * Distribute package cost to products, respecting manually entered values.
 * Products with manual Wartość keep their value; remaining cost is split among empty ones.
 */
function distributeToProducts(orderIndex, packageCost) {
    const itemsInPackage = polandOrderData.items.filter(item => item.order_index === orderIndex);
    if (itemsInPackage.length === 0) return;

    // Calculate how much is manually entered in product Wartość, how many are empty
    let enteredProductSum = 0;
    let emptyProductCount = 0;

    itemsInPackage.forEach(item => {
        const globalIndex = polandOrderData.items.indexOf(item);
        const valueInput = document.querySelector(`.shipping-value-input[data-item-index="${globalIndex}"]`);
        if (valueInput && valueInput.value !== '') {
            enteredProductSum += parseFloat(valueInput.value) || 0;
        } else {
            emptyProductCount++;
        }
    });

    const remainingForEmptyProducts = emptyProductCount > 0 ? (packageCost - enteredProductSum) / emptyProductCount : 0;

    itemsInPackage.forEach(item => {
        const globalIndex = polandOrderData.items.indexOf(item);
        const qty = item.quantity || 1;
        const valueInput = document.querySelector(`.shipping-value-input[data-item-index="${globalIndex}"]`);
        const priceInput = document.querySelector(`.shipping-price-input[data-item-index="${globalIndex}"]`);

        if (valueInput && valueInput.value !== '') {
            // Product has manual value — update Cena/szt placeholder only
            const manualValue = parseFloat(valueInput.value) || 0;
            if (priceInput && priceInput.value === '') {
                priceInput.placeholder = (manualValue / qty).toFixed(2).replace('.', ',');
            }
        } else {
            // Product is empty — set placeholder
            if (valueInput) {
                valueInput.placeholder = remainingForEmptyProducts.toFixed(2).replace('.', ',');
            }
            if (priceInput) {
                priceInput.placeholder = (remainingForEmptyProducts / qty).toFixed(2).replace('.', ',');
            }
        }
    });
}

/**
 * Handle manual change to Cena/szt (price per item)
 * AUTO: Cena × Ilość = Wartość
 */
function handleShippingPriceChange(itemIndex) {
    const item = polandOrderData.items[itemIndex];
    const qty = item.quantity || 1;

    const priceInput = document.querySelector(`.shipping-price-input[data-item-index="${itemIndex}"]`);
    const valueInput = document.querySelector(`.shipping-value-input[data-item-index="${itemIndex}"]`);

    const price = parseFloat(priceInput.value) || 0;
    const calculatedValue = price * qty;

    if (valueInput) {
        valueInput.value = calculatedValue.toFixed(2);
    }

    // SUM UP: update package
    sumUpToPackage(item.order_index);

    // Recalculate placeholders for OTHER products in this package
    const packageInput = document.querySelector(`.package-shipping-input[data-order-index="${item.order_index}"]`);
    const packageCost = packageInput ? (parseFloat(packageInput.value) || parseFloat(packageInput.placeholder.replace(',', '.')) || 0) : 0;
    distributeToProducts(item.order_index, packageCost);

    updateShippingSummary();
}

/**
 * Handle manual change to Wartość (total shipping for this row)
 * AUTO: Wartość / Ilość = Cena/szt (as placeholder)
 */
function handleShippingValueChange(itemIndex) {
    const item = polandOrderData.items[itemIndex];
    const qty = item.quantity || 1;

    const valueInput = document.querySelector(`.shipping-value-input[data-item-index="${itemIndex}"]`);
    const priceInput = document.querySelector(`.shipping-price-input[data-item-index="${itemIndex}"]`);

    const value = parseFloat(valueInput.value) || 0;
    const calculatedPrice = value / qty;

    if (priceInput) {
        priceInput.placeholder = calculatedPrice.toFixed(2).replace('.', ',');
        priceInput.value = '';
    }

    // SUM UP: update package
    sumUpToPackage(item.order_index);

    // Recalculate placeholders for OTHER products in this package
    const packageInput = document.querySelector(`.package-shipping-input[data-order-index="${item.order_index}"]`);
    const packageCost = packageInput ? (parseFloat(packageInput.value) || parseFloat(packageInput.placeholder.replace(',', '.')) || 0) : 0;
    distributeToProducts(item.order_index, packageCost);

    updateShippingSummary();
}

/**
 * SUM UP: Recalculate package cost from product Wartość inputs.
 * If package was manually edited (data-manual), do NOT overwrite its value.
 */
function sumUpToPackage(orderIndex) {
    const packageInput = document.querySelector(`.package-shipping-input[data-order-index="${orderIndex}"]`);
    if (!packageInput) return;

    // If package was manually set, don't overwrite
    if (packageInput.dataset.manual === 'true') return;

    const itemsInPackage = polandOrderData.items.filter(item => item.order_index === orderIndex);
    const packageSum = itemsInPackage.reduce((sum, item) => {
        const idx = polandOrderData.items.indexOf(item);
        const inp = document.querySelector(`.shipping-value-input[data-item-index="${idx}"]`);
        return sum + (inp ? (parseFloat(inp.value) || 0) : 0);
    }, 0);

    if (packageSum > 0) {
        packageInput.value = packageSum.toFixed(2);
    } else {
        packageInput.value = '';
    }
}

/**
 * Update the shipping summary (sum and difference)
 * Reads actual Wartość values from inputs (not placeholders)
 */
function updateShippingSummary() {
    const totalDeclared = parseFloat(document.getElementById('totalShippingCost').value) || 0;

    // Sum all Wartość inputs that have actual values entered
    let totalCalculated = 0;
    polandOrderData.items.forEach((item, idx) => {
        const input = document.querySelector(`.shipping-value-input[data-item-index="${idx}"]`);
        if (input) {
            totalCalculated += parseFloat(input.value) || 0;
        }
    });

    const difference = totalCalculated - totalDeclared;

    document.getElementById('sumShippingCost').textContent = totalCalculated.toFixed(2) + ' PLN';

    const diffElement = document.getElementById('shippingDifference');
    diffElement.textContent = difference.toFixed(2) + ' PLN';

    // Color: green if balanced or surplus, red if deficit
    if (difference < -0.01) {
        diffElement.style.color = '#dc2626'; // red - deficit
    } else {
        diffElement.style.color = '#059669'; // green - balanced or surplus
    }
}

/**
 * Close Poland order modal
 */
function closePolandModal() {
    const modal = document.getElementById('orderToPolandModal');
    if (modal) {
        modal.classList.add('closing');
        setTimeout(() => {
            modal.classList.remove('active');
            modal.classList.remove('closing');
            document.body.style.overflow = '';
        }, 350);
    }
}

/**
 * Confirm and create Poland order (with validation)
 */
function confirmPolandOrder() {
    const trackingNum = document.getElementById('polandTrackingNumber').value.trim();
    const totalShipping = parseFloat(document.getElementById('totalShippingCost').value) || 0;
    const note = document.getElementById('polandOrderNote').value.trim();

    // --- Validation ---
    const errors = [];

    if (polandOrderData.items.length === 0) {
        errors.push('Brak produktów do zamówienia');
    }

    if (!trackingNum) {
        errors.push('Uzupełnij numer kfriday (KB88900-RS...)');
        document.getElementById('polandTrackingNumber').classList.add('input-error');
    } else {
        document.getElementById('polandTrackingNumber').classList.remove('input-error');
    }

    if (totalShipping <= 0) {
        errors.push('Wpisz całkowity koszt wysyłki');
        document.getElementById('totalShippingCost').classList.add('input-error');
    } else {
        document.getElementById('totalShippingCost').classList.remove('input-error');
    }

    // Check that every product has a Wartość filled in
    let allItemsHaveShipping = true;
    polandOrderData.items.forEach((item, idx) => {
        const input = document.querySelector(`.shipping-value-input[data-item-index="${idx}"]`);
        if (input) {
            const val = parseFloat(input.value) || 0;
            if (val <= 0) {
                allItemsHaveShipping = false;
                input.classList.add('input-error');
            } else {
                input.classList.remove('input-error');
            }
        }
    });

    if (!allItemsHaveShipping) {
        errors.push('Uzupełnij wartość wysyłki dla każdego produktu');
    }

    if (errors.length > 0) {
        if (window.Toast) {
            window.Toast.show(errors[0], 'error');
        }
        return;
    }

    const trackingNumber = 'KB88900-RS' + trackingNum;
    const proxyOrderIds = polandOrderData.proxyOrders.map(o => o.id);

    const itemsPayload = polandOrderData.items.map((item, idx) => {
        const input = document.querySelector(`.shipping-value-input[data-item-index="${idx}"]`);
        const shippingCost = input ? (parseFloat(input.value) || 0) : 0;
        return {
            proxy_order_item_id: item.proxy_order_item_id,
            shipping_cost: shippingCost
        };
    });

    // Disable button
    const btn = document.getElementById('btnConfirmPolandOrder');
    btn.disabled = true;
    btn.textContent = 'Tworzenie zamówienia...';

    fetch('/admin/products/api/create-poland-order', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify({
            proxy_order_ids: proxyOrderIds,
            shipping_cost_total: totalShipping,
            tracking_number: trackingNumber,
            items: itemsPayload,
            note: note
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            closePolandModal();
            if (window.Toast) {
                window.Toast.show(`Zamówienie do Polski utworzone! Numer: ${data.order_number}`, 'success');
            }
            // Redirect to POLSKA tab
            setTimeout(() => {
                window.location.href = '/admin/products/stock-orders?tab=polska';
            }, 1000);
        } else {
            if (window.Toast) {
                window.Toast.show('Błąd: ' + (data.error || 'Nieznany błąd'), 'error');
            }
            btn.disabled = false;
            btn.textContent = 'Potwierdz zamowienie';
        }
    })
    .catch(error => {
        console.error('Error creating Poland order:', error);
        if (window.Toast) {
            window.Toast.show('Wystąpił błąd podczas tworzenia zamówienia', 'error');
        }
        btn.disabled = false;
        btn.textContent = 'Potwierdz zamowienie';
    });
}

/**
 * Initialize event listeners
 */
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOMContentLoaded - Stock orders JS initialized');

    // Close Poland modal on overlay click
    const polandModal = document.getElementById('orderToPolandModal');
    if (polandModal) {
        polandModal.addEventListener('click', function(e) {
            if (e.target === polandModal) {
                closePolandModal();
            }
        });
    }

    // Clear validation error on input for tracking and total shipping
    ['polandTrackingNumber', 'totalShippingCost'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('input', function() {
                this.classList.remove('input-error');
            });
        }
    });

    // Customs VAT modal - close on overlay click
    const customsVatModal = document.getElementById('customsVatModal');
    if (customsVatModal) {
        customsVatModal.addEventListener('click', function(e) {
            if (e.target === customsVatModal) {
                closeCustomsVatModal();
            }
        });
    }
});


// ==========================================
// Cło/VAT Modal Functions
// ==========================================

let customsVatData = {
    isBulk: false,
    orders: []
};

/**
 * Open Customs/VAT modal for a single Poland order
 */
function openCustomsVatModal(orderId) {
    customsVatData.isBulk = false;
    customsVatData.orders = [];

    const modal = document.getElementById('customsVatModal');
    const title = document.getElementById('customsVatModalTitle');
    const globalSection = document.getElementById('customsVatGlobalSection');
    const container = document.getElementById('customsVatItemsContainer');

    title.textContent = 'Edycja Cło/VAT';
    globalSection.style.display = 'none';
    container.innerHTML = '<div class="loading-spinner">Ładowanie danych...</div>';

    modal.classList.add('active');
    document.body.style.overflow = 'hidden';

    fetch(`/admin/products/api/poland-order-customs/${orderId}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                customsVatData.orders = [{
                    order_id: data.order_id,
                    order_number: data.order_number,
                    items: data.items
                }];
                title.textContent = `Edycja Cło/VAT — ${data.order_number}`;
                renderCustomsVatItems();
            } else {
                container.innerHTML = `<div class="empty-state-small">Błąd: ${data.error}</div>`;
            }
        })
        .catch(err => {
            container.innerHTML = `<div class="empty-state-small">Błąd połączenia</div>`;
            console.error('Error fetching customs data:', err);
        });
}

/**
 * Open Customs/VAT modal for a single item within an order
 */
function openCustomsVatModalForItem(orderId, itemId) {
    customsVatData.isBulk = false;
    customsVatData.orders = [];

    const modal = document.getElementById('customsVatModal');
    const title = document.getElementById('customsVatModalTitle');
    const globalSection = document.getElementById('customsVatGlobalSection');
    const container = document.getElementById('customsVatItemsContainer');

    title.textContent = 'Edycja Cło/VAT';
    globalSection.style.display = 'none';
    container.innerHTML = '<div class="loading-spinner">Ładowanie danych...</div>';

    modal.classList.add('active');
    document.body.style.overflow = 'hidden';

    fetch(`/admin/products/api/poland-order-customs/${orderId}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                // Filter to only the target item
                const filteredItems = data.items.filter(item => item.id === itemId);
                customsVatData.orders = [{
                    order_id: data.order_id,
                    order_number: data.order_number,
                    items: filteredItems
                }];
                const itemName = filteredItems.length > 0 ? filteredItems[0].product_name : '';
                title.textContent = `Edycja Cło/VAT — ${itemName}`;
                renderCustomsVatItems();
            } else {
                container.innerHTML = `<div class="empty-state-small">Błąd: ${data.error}</div>`;
            }
        })
        .catch(err => {
            container.innerHTML = `<div class="empty-state-small">Błąd połączenia</div>`;
            console.error('Error fetching customs data:', err);
        });
}

/**
 * Open Customs/VAT modal for multiple selected Poland orders (bulk)
 */
function openBulkCustomsVatModal() {
    const checkedBoxes = document.querySelectorAll('.poland-checkbox:checked');
    if (checkedBoxes.length === 0) {
        if (window.Toast) window.Toast.show('Zaznacz zamówienia Polska', 'warning');
        return;
    }

    customsVatData.isBulk = true;
    customsVatData.orders = [];

    const orderIds = Array.from(checkedBoxes).map(cb => parseInt(cb.value));

    const modal = document.getElementById('customsVatModal');
    const title = document.getElementById('customsVatModalTitle');
    const globalSection = document.getElementById('customsVatGlobalSection');
    const container = document.getElementById('customsVatItemsContainer');

    title.textContent = `Edycja Cło/VAT — ${orderIds.length} zamówień`;
    globalSection.style.display = 'flex';
    document.getElementById('customsVatGlobalPercent').value = '';
    container.innerHTML = '<div class="loading-spinner">Ładowanie danych...</div>';

    modal.classList.add('active');
    document.body.style.overflow = 'hidden';

    fetch('/admin/products/api/poland-orders-customs-bulk', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify({ order_ids: orderIds })
    })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                customsVatData.orders = data.orders;
                renderCustomsVatItems();
            } else {
                container.innerHTML = `<div class="empty-state-small">Błąd: ${data.error}</div>`;
            }
        })
        .catch(err => {
            container.innerHTML = `<div class="empty-state-small">Błąd połączenia</div>`;
            console.error('Error fetching bulk customs data:', err);
        });
}

/**
 * Close Customs/VAT modal
 */
function closeCustomsVatModal() {
    const modal = document.getElementById('customsVatModal');
    if (modal && modal.classList.contains('active')) {
        modal.classList.add('closing');
        setTimeout(() => {
            modal.classList.remove('active', 'closing');
            document.body.style.overflow = '';
        }, 350);
    }
}

/**
 * Render items inside the Customs/VAT modal
 */
function renderCustomsVatItems() {
    const container = document.getElementById('customsVatItemsContainer');
    let html = '';

    customsVatData.orders.forEach((order, orderIdx) => {
        if (customsVatData.isBulk || customsVatData.orders.length > 1) {
            html += `<div class="customs-vat-order-header">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M6 2L3 6v14a2 2 0 002 2h14a2 2 0 002-2V6l-3-4z"></path>
                    <line x1="3" y1="6" x2="21" y2="6"></line>
                    <path d="M16 10a4 4 0 01-8 0"></path>
                </svg>
                ${order.order_number}
            </div>`;
        }

        html += `<table class="customs-vat-table">
            <thead>
                <tr>
                    <th>Produkt</th>
                    <th class="text-right">Cena zakupu</th>
                    <th class="text-center">Ilość</th>
                    <th class="text-right">Wartość</th>
                    <th class="text-center">Cło/VAT %</th>
                    <th class="text-right">Kwota Cło/VAT</th>
                </tr>
            </thead>
            <tbody>`;

        order.items.forEach(item => {
            const productValue = item.product_value;
            const currentAmount = item.customs_vat_amount || 0;
            const currentPercent = item.customs_vat_percentage || 0;

            html += `<tr data-item-id="${item.id}" data-product-value="${productValue}">
                <td class="customs-vat-product-cell">
                    <div class="customs-vat-product">
                        ${item.product_image
                            ? `<img src="${item.product_image}" alt="${item.product_name}" class="product-thumb-compact">`
                            : `<div class="product-thumb-compact product-thumb-placeholder">
                                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                                    <path d="M6.002 5.5a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0z"></path>
                                    <path d="M2.002 1a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V3a2 2 0 00-2-2h-12zm12 1a1 1 0 011 1v6.5l-3.777-1.947a.5.5 0 00-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 00-.63.062L1.002 12V3a1 1 0 011-1h12z"></path>
                                </svg>
                              </div>`
                        }
                        <span class="customs-vat-product-name">${item.product_name}</span>
                    </div>
                </td>
                <td class="text-right text-nowrap">${item.purchase_price_pln.toFixed(2)} zł</td>
                <td class="text-center">${item.quantity}</td>
                <td class="text-right text-nowrap font-semibold">${productValue.toFixed(2)} zł</td>
                <td class="text-center">
                    <div class="customs-vat-percent-wrapper">
                        <input type="number" class="form-control customs-vat-percent-input"
                               data-item-id="${item.id}"
                               value="${currentPercent > 0 ? currentPercent : ''}"
                               min="0" max="100" step="0.01"
                               placeholder="0"
                               oninput="calculateCustomsAmount(this)">
                        <span class="input-suffix">%</span>
                    </div>
                </td>
                <td class="text-right text-nowrap customs-vat-amount-cell" data-item-id="${item.id}">
                    ${currentAmount.toFixed(2)} zł
                </td>
            </tr>`;
        });

        html += `</tbody></table>`;
    });

    container.innerHTML = html;
    updateCustomsVatTotal();
}

/**
 * Calculate customs amount when % input changes
 */
function calculateCustomsAmount(input) {
    const row = input.closest('tr');
    const productValue = parseFloat(row.dataset.productValue) || 0;
    const percentage = parseFloat(input.value) || 0;
    const amount = (productValue * percentage / 100);
    const amountCell = row.querySelector('.customs-vat-amount-cell');

    amountCell.textContent = amount.toFixed(2) + ' zł';
    updateCustomsVatTotal();
}

/**
 * Update total customs/VAT sum in modal footer
 */
function updateCustomsVatTotal() {
    let total = 0;
    document.querySelectorAll('#customsVatItemsContainer .customs-vat-amount-cell').forEach(cell => {
        total += parseFloat(cell.textContent) || 0;
    });
    document.getElementById('customsVatTotalAmount').textContent = total.toFixed(2) + ' zł';
}

/**
 * Apply global % to all products in the modal
 */
function applyGlobalCustomsPercentage() {
    const globalPercent = parseFloat(document.getElementById('customsVatGlobalPercent').value);
    if (isNaN(globalPercent) || globalPercent < 0) {
        if (window.Toast) window.Toast.show('Wpisz poprawny procent', 'warning');
        return;
    }

    document.querySelectorAll('#customsVatItemsContainer .customs-vat-percent-input').forEach(input => {
        input.value = globalPercent;
        calculateCustomsAmount(input);
    });
}

/**
 * Save customs/VAT data to backend
 */
function saveCustomsVat() {
    const items = [];
    document.querySelectorAll('#customsVatItemsContainer tr[data-item-id]').forEach(row => {
        const itemId = parseInt(row.dataset.itemId);
        const percentInput = row.querySelector('.customs-vat-percent-input');
        const percentage = parseFloat(percentInput.value) || 0;

        items.push({
            poland_order_item_id: itemId,
            customs_vat_percentage: percentage
        });
    });

    if (items.length === 0) {
        if (window.Toast) window.Toast.show('Brak danych do zapisania', 'warning');
        return;
    }

    fetch('/admin/products/api/update-poland-customs-vat', {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify({ items: items })
    })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                // Update DOM - per-item amounts in main table
                if (data.updated_items) {
                    data.updated_items.forEach(item => {
                        const amountSpan = document.querySelector(`.poland-item-customs-amount[data-item-id="${item.id}"]`);
                        if (amountSpan) {
                            amountSpan.textContent = item.customs_vat_amount.toFixed(2) + ' zł';
                        }
                    });
                }

                // Update DOM - order totals in main table
                if (data.updated_orders) {
                    data.updated_orders.forEach(order => {
                        const customsCell = document.querySelector(`.poland-customs-cost-cell[data-order-id="${order.order_id}"]`);
                        const productValueCell = document.querySelector(`.poland-product-value-cell[data-order-id="${order.order_id}"]`);
                        const totalCell = document.querySelector(`.poland-total-amount-cell[data-order-id="${order.order_id}"]`);

                        if (customsCell) customsCell.textContent = order.customs_cost.toFixed(2) + ' PLN';
                        if (productValueCell) productValueCell.textContent = order.product_value.toFixed(2) + ' PLN';
                        if (totalCell) totalCell.textContent = order.total_amount.toFixed(2) + ' PLN';

                        // Update data-amount attribute for sorting
                        const row = document.querySelector(`#poland-order-row-${order.order_id}`);
                        if (row) row.dataset.amount = order.total_amount;
                    });
                }

                closeCustomsVatModal();
                if (window.Toast) window.Toast.show('Cło/VAT zapisane pomyślnie', 'success');
            } else {
                if (window.Toast) window.Toast.show('Błąd: ' + data.error, 'error');
            }
        })
        .catch(err => {
            console.error('Error saving customs/VAT:', err);
            if (window.Toast) window.Toast.show('Błąd połączenia z serwerem', 'error');
        });
}

// ============================================
// Fetch helper with CSRF token and JSON handling
// ============================================

/**
 * Fetch helper with CSRF token and JSON handling
 */
async function apiFetch(url, { method = 'GET', body = null } = {}) {
    const headers = { 'Content-Type': 'application/json' };
    const csrfToken = getCsrfToken();
    if (csrfToken) headers['X-CSRFToken'] = csrfToken;
    const options = { method, headers };
    if (body) options.body = JSON.stringify(body);
    const response = await fetch(url, options);
    return response.json();
}

// ============================================
// TAB_CONFIG — shared configuration for Proxy & Polska tabs
// ============================================

const TAB_CONFIG = {
    proxy: {
        tableId: 'proxyOrdersTable',
        checkboxClass: 'order-checkbox',
        selectAllId: 'selectAllOrders',
        statusDropdownId: 'statusMultiSelect',
        statusTextId: 'statusSelectText',
        filterIds: {
            orderNumber: 'filterOrderNumber',
            dateFrom: 'filterDateFrom',
            dateTo: 'filterDateTo',
            tracking: null
        },
        rowIdPrefix: 'order-row',
        statusEndpoint: id => `/admin/products/proxy-orders/${id}/status`,
        deleteEndpoint: id => `/admin/products/proxy-orders/${id}/delete`,
        statusLabels: {
            zamowiono: 'Zamówiono',
            dostarczone_do_proxy: 'Dostarczone do Proxy',
            anulowane: 'Anulowane'
        },
        statusDropdownPrefix: 'status-dropdown',
        dateUpdateSelector: null,
        dateUpdateCellIndex: 4
    },
    polska: {
        tableId: 'polandOrdersTable',
        checkboxClass: 'poland-checkbox',
        selectAllId: 'selectAllPolandOrders',
        statusDropdownId: 'statusMultiSelectPoland',
        statusTextId: 'statusSelectTextPoland',
        filterIds: {
            orderNumber: 'filterOrderNumberPoland',
            dateFrom: 'filterDateFromPoland',
            dateTo: 'filterDateToPoland',
            tracking: 'filterTrackingPoland'
        },
        rowIdPrefix: 'poland-order-row',
        statusEndpoint: id => `/admin/products/poland-orders/${id}/status`,
        deleteEndpoint: id => `/admin/products/poland-orders/${id}/delete`,
        statusLabels: {
            zamowione: 'Zamówione',
            urzad_celny: 'Urząd celny',
            dostarczone_gom: 'Dostarczone GOM',
            anulowane: 'Anulowane'
        },
        statusDropdownPrefix: 'poland-status-dropdown',
        dateUpdateSelector: '.poland-date-secondary',
        dateUpdateCellIndex: null
    },
    archiwum: {
        tableId: 'archiwumOrdersTable',
        checkboxClass: 'archiwum-checkbox',
        selectAllId: 'selectAllArchiwumOrders',
        statusDropdownId: 'statusMultiSelectArchiwum',
        statusTextId: 'statusSelectTextArchiwum',
        filterIds: {
            orderNumber: 'filterOrderNumberArchiwum',
            dateFrom: 'filterDateFromArchiwum',
            dateTo: 'filterDateToArchiwum',
            tracking: 'filterTrackingArchiwum'
        },
        rowIdPrefix: 'archiwum-order-row',
        statusEndpoint: null,
        deleteEndpoint: null,
        statusLabels: {
            zamowione: 'Zamówione',
            urzad_celny: 'Urząd celny',
            dostarczone_gom: 'Dostarczone GOM',
            anulowane: 'Anulowane'
        },
        statusDropdownPrefix: null,
        dateUpdateSelector: '.poland-date-secondary',
        dateUpdateCellIndex: null
    }
};

// ============================================
// Unified Filter Functions
// ============================================

let selectedStatusesByTab = { proxy: [], polska: [], archiwum: [] };

function _toggleStatusMultiSelect(tab) {
    const config = TAB_CONFIG[tab];
    const dropdown = document.getElementById(config.statusDropdownId);
    dropdown.style.display = dropdown.style.display === 'none' ? 'block' : 'none';
}

function toggleStatusMultiSelect() { _toggleStatusMultiSelect('proxy'); }
function toggleStatusMultiSelectPoland() { _toggleStatusMultiSelect('polska'); }

function _updateStatusFilter(tab) {
    const config = TAB_CONFIG[tab];
    const checkboxes = document.querySelectorAll(`#${config.statusDropdownId} input[type="checkbox"]:checked`);
    selectedStatusesByTab[tab] = Array.from(checkboxes).map(cb => cb.value);

    const statusText = document.getElementById(config.statusTextId);
    const count = selectedStatusesByTab[tab].length;
    statusText.textContent = count === 0 ? 'Wszystkie statusy' : count === 1 ? '1 status' : `${count} statusy`;

    _applyFilters(tab);
}

function updateStatusFilter() { _updateStatusFilter('proxy'); }
function updateStatusFilterPoland() { _updateStatusFilter('polska'); }

function _applyFilters(tab) {
    const config = TAB_CONFIG[tab];
    const f = config.filterIds;
    const orderNumberFilter = document.getElementById(f.orderNumber).value.toLowerCase().trim();
    const dateFrom = document.getElementById(f.dateFrom).value;
    const dateTo = document.getElementById(f.dateTo).value;
    const trackingFilter = f.tracking ? document.getElementById(f.tracking).value.toLowerCase().trim() : '';

    const table = document.getElementById(config.tableId);
    if (!table) return;
    const rows = table.querySelectorAll('tbody tr');

    rows.forEach(row => {
        let show = true;

        if (orderNumberFilter) {
            const num = (row.dataset.orderNumber || '').toLowerCase();
            if (!num.includes(orderNumberFilter)) show = false;
        }

        if (trackingFilter && f.tracking) {
            const tracking = (row.dataset.tracking || '').toLowerCase();
            if (!tracking.includes(trackingFilter)) show = false;
        }

        if (dateFrom || dateTo) {
            if (tab === 'proxy') {
                const rowDate = row.dataset.dateFormatted;
                if (rowDate) {
                    if (dateFrom && rowDate < dateFrom) show = false;
                    if (dateTo && rowDate > dateTo) show = false;
                }
            } else {
                const ts = parseFloat(row.dataset.date) || 0;
                const rowDateStr = new Date(ts * 1000).toISOString().split('T')[0];
                if (dateFrom && rowDateStr < dateFrom) show = false;
                if (dateTo && rowDateStr > dateTo) show = false;
            }
        }

        if (selectedStatusesByTab[tab].length > 0) {
            if (!selectedStatusesByTab[tab].includes(row.dataset.status)) show = false;
        }

        row.style.display = show ? '' : 'none';
    });

    _updateSelectAllState(tab);
}

function applyFilters() { _applyFilters('proxy'); }
function applyFiltersPoland() { _applyFilters('polska'); }

function _clearAllFilters(tab) {
    const config = TAB_CONFIG[tab];
    const f = config.filterIds;

    document.getElementById(f.orderNumber).value = '';
    document.getElementById(f.dateFrom).value = '';
    document.getElementById(f.dateTo).value = '';
    if (f.tracking) document.getElementById(f.tracking).value = '';

    document.querySelectorAll(`#${config.statusDropdownId} input[type="checkbox"]`).forEach(cb => { cb.checked = false; });
    selectedStatusesByTab[tab] = [];
    document.getElementById(config.statusTextId).textContent = 'Wszystkie statusy';

    const table = document.getElementById(config.tableId);
    if (table) {
        table.querySelectorAll('tbody tr').forEach(row => { row.style.display = ''; });
    }

    _updateSelectAllState(tab);
}

function clearAllFilters() { _clearAllFilters('proxy'); }
function clearAllFiltersPoland() { _clearAllFilters('polska'); }

// ============================================
// Unified Checkbox & Select All Functions
// ============================================

function _toggleSelectAll(tab, selectAllCheckbox) {
    const config = TAB_CONFIG[tab];
    const table = document.getElementById(config.tableId);
    if (!table) return;
    const visibleRows = table.querySelectorAll('tbody tr:not([style*="display: none"])');

    visibleRows.forEach(row => {
        const cb = row.querySelector(`.${config.checkboxClass}`);
        if (cb) {
            cb.checked = selectAllCheckbox.checked;
            row.classList.toggle('selected', selectAllCheckbox.checked);
        }
    });

    updateBulkActionsModal();
}

function toggleSelectAll(selectAllCheckbox) { _toggleSelectAll('proxy', selectAllCheckbox); }
function toggleSelectAllPoland(selectAllCheckbox) { _toggleSelectAll('polska', selectAllCheckbox); }

function _handleCheckboxChange(tab) {
    const checkbox = event.target;
    const row = checkbox.closest('tr');
    row.classList.toggle('selected', checkbox.checked);

    _updateSelectAllState(tab);
    updateBulkActionsModal();
}

function handleCheckboxChange() { _handleCheckboxChange('proxy'); }
function handleCheckboxChangePoland() { _handleCheckboxChange('polska'); }

function _updateSelectAllState(tab) {
    const config = TAB_CONFIG[tab];
    const selectAll = document.getElementById(config.selectAllId);
    if (!selectAll) return;

    const table = document.getElementById(config.tableId);
    if (!table) return;
    const visibleRows = table.querySelectorAll('tbody tr:not([style*="display: none"])');
    const checkboxes = Array.from(visibleRows).map(row => row.querySelector(`.${config.checkboxClass}`)).filter(cb => cb);

    const allChecked = checkboxes.length > 0 && checkboxes.every(cb => cb.checked);
    const someChecked = checkboxes.some(cb => cb.checked);

    selectAll.checked = allChecked;
    selectAll.indeterminate = someChecked && !allChecked;
}

function updateSelectAllState() { _updateSelectAllState('proxy'); }
function updateSelectAllStatePoland() { _updateSelectAllState('polska'); }

// ============================================
// Unified Status Dropdown Functions
// ============================================

function _toggleStatusDropdown(tab, orderId) {
    const config = TAB_CONFIG[tab];
    const prefix = config.statusDropdownPrefix;
    const dropdownId = `${prefix}-${orderId}`;

    const allDropdowns = document.querySelectorAll(`[id^="${prefix}-"]`);
    allDropdowns.forEach(d => {
        if (d.id !== dropdownId) d.style.display = 'none';
    });

    const dropdown = document.getElementById(dropdownId);
    if (!dropdown) return;

    const fnName = tab === 'proxy' ? 'toggleStatusDropdown' : 'togglePolandStatusDropdown';
    const button = document.querySelector(`[onclick="${fnName}(${orderId})"]`);
    if (!button) return;

    if (dropdown.style.display === 'none' || !dropdown.style.display) {
        if (dropdown.parentElement !== document.body) {
            document.body.appendChild(dropdown);
        }

        const rect = button.getBoundingClientRect();
        const dropdownHeight = 280;
        const viewportHeight = window.innerHeight;
        const viewportWidth = window.innerWidth;

        let top = (rect.bottom + dropdownHeight > viewportHeight) ? rect.top - dropdownHeight - 4 : rect.bottom + 4;
        let left = rect.left;
        if (left + 180 > viewportWidth) left = viewportWidth - 180 - 16;

        dropdown.style.position = 'fixed';
        dropdown.style.top = `${top}px`;
        dropdown.style.left = `${left}px`;
        dropdown.style.display = 'block';
    } else {
        dropdown.style.display = 'none';
    }
}

function toggleStatusDropdown(orderId) { _toggleStatusDropdown('proxy', orderId); }
function togglePolandStatusDropdown(orderId) { _toggleStatusDropdown('polska', orderId); }

// ============================================
// Unified Status Change Function
// ============================================

function _changeOrderStatus(tab, orderId, newStatus) {
    const config = TAB_CONFIG[tab];

    const dropdown = document.getElementById(`${config.statusDropdownPrefix}-${orderId}`);
    if (dropdown) dropdown.style.display = 'none';

    fetch(config.statusEndpoint(orderId), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
        body: JSON.stringify({ status: newStatus })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            const row = document.getElementById(`${config.rowIdPrefix}-${orderId}`);
            if (row) {
                const button = row.querySelector('.status-badge-button');
                if (button) {
                    button.className = `status-badge-button badge-${newStatus}`;
                    button.childNodes[0].textContent = (config.statusLabels[newStatus] || newStatus) + ' ';
                }
                row.dataset.status = newStatus;

                // Update date display
                const now = new Date();
                const formattedDate = `${String(now.getDate()).padStart(2,'0')}.${String(now.getMonth()+1).padStart(2,'0')}.${now.getFullYear()} ${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;

                if (config.dateUpdateSelector) {
                    const dateEl = row.querySelector(config.dateUpdateSelector);
                    if (dateEl) {
                        dateEl.textContent = formattedDate;
                        dateEl.style.transition = 'background-color 0.3s';
                        dateEl.style.backgroundColor = 'rgba(249, 115, 22, 0.15)';
                        setTimeout(() => { dateEl.style.backgroundColor = ''; }, 1000);
                    }
                } else if (config.dateUpdateCellIndex !== null) {
                    const cells = row.querySelectorAll('td');
                    const cell = cells[config.dateUpdateCellIndex];
                    if (cell) {
                        cell.textContent = formattedDate;
                        cell.className = 'text-muted';
                        cell.style.transition = 'background-color 0.3s';
                        cell.style.backgroundColor = 'rgba(90, 24, 154, 0.15)';
                        setTimeout(() => { cell.style.backgroundColor = ''; }, 1000);
                    }
                }

                row.dataset.statusChanged = Math.floor(now.getTime() / 1000);
            }

            if (window.Toast) {
                window.Toast.show(data.message || 'Status zamówienia zmieniony', 'success');
            }
        } else {
            if (window.Toast) window.Toast.show('Błąd: ' + data.error, 'error');
        }
    })
    .catch(error => {
        console.error('Status change error:', error);
        if (window.Toast) window.Toast.show('Wystąpił błąd podczas zmiany statusu', 'error');
    });
}

function changeOrderStatus(orderId, newStatus) { _changeOrderStatus('proxy', orderId, newStatus); }
function changePolandOrderStatus(orderId, newStatus) { _changeOrderStatus('polska', orderId, newStatus); }

// ============================================
// Unified Delete Functions
// ============================================

function _deleteOrder(tab, orderId) {
    const config = TAB_CONFIG[tab];
    const label = tab === 'polska' ? 'POLSKA' : '';
    if (!confirm(`Czy na pewno chcesz usunąć to zamówienie${label ? ' ' + label : ''}?\n\nTa operacja jest nieodwracalna.`)) return;

    fetch(config.deleteEndpoint(orderId), {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            if (window.Toast) window.Toast.show(`Zamówienie${label ? ' ' + label : ''} zostało usunięte`, 'success');
            setTimeout(() => { window.location.reload(); }, 500);
        } else {
            if (window.Toast) window.Toast.show('Błąd: ' + data.error, 'error');
        }
    })
    .catch(error => {
        console.error('Delete error:', error);
        if (window.Toast) window.Toast.show('Wystąpił błąd podczas usuwania zamówienia', 'error');
    });
}

function deleteOrder(orderId) { _deleteOrder('proxy', orderId); }
function deletePolandOrder(orderId) { _deleteOrder('polska', orderId); }

function _bulkDeleteOrders(tab) {
    const config = TAB_CONFIG[tab];
    const label = tab === 'polska' ? ' POLSKA' : '';
    const orderIds = getSelectedOrderIds();
    if (orderIds.length === 0) return;

    if (!confirm(`Czy na pewno chcesz usunąć ${orderIds.length} zamówień${label}?\n\nTa operacja jest nieodwracalna.`)) return;

    let completed = 0, errors = 0;

    orderIds.forEach(orderId => {
        fetch(config.deleteEndpoint(orderId), {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() }
        })
        .then(response => response.json())
        .then(data => {
            completed++;
            if (!data.success) errors++;
            if (completed === orderIds.length) {
                if (errors === 0) {
                    if (window.Toast) window.Toast.show(`Usunięto ${orderIds.length} zamówień`, 'success');
                } else {
                    if (window.Toast) window.Toast.show(`Usunięto ${completed - errors} zamówień, ${errors} błędów`, 'warning');
                }
                setTimeout(() => { window.location.reload(); }, 500);
            }
        })
        .catch(error => {
            console.error('Bulk delete error:', error);
            errors++; completed++;
            if (completed === orderIds.length) setTimeout(() => { window.location.reload(); }, 500);
        });
    });
}

function bulkDeleteOrders() { _bulkDeleteOrders('proxy'); }
function bulkDeletePolandOrders() { _bulkDeleteOrders('polska'); }

// ============================================
// Unified Bulk Move Function
// ============================================

function _bulkMove(targetTab) {
    const orderIds = getSelectedOrderIds();
    if (orderIds.length === 0) return;

    const targetLabel = targetTab.toUpperCase();
    if (!confirm(`Czy na pewno chcesz przenieść ${orderIds.length} zamówień do zakładki ${targetLabel}?`)) return;

    let completed = 0, errors = 0;
    const successfulMoves = [];
    const direction = targetTab === 'polska' ? '50px' : '-50px';

    orderIds.forEach(orderId => {
        fetch(`/admin/products/proxy-orders/${orderId}/move`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({ order_type: targetTab })
        })
        .then(response => response.json())
        .then(data => {
            completed++;
            if (data.success) {
                successfulMoves.push(orderId);
                const row = document.getElementById(`order-row-${orderId}`);
                if (row) {
                    row.style.transition = 'opacity 0.3s, transform 0.3s';
                    row.style.opacity = '0';
                    row.style.transform = `translateX(${direction})`;
                }
            } else {
                errors++;
            }

            if (completed === orderIds.length) {
                const modal = document.getElementById('bulkActionsModal');
                if (modal) modal.classList.remove('visible');

                const fromTab = targetTab === 'polska' ? 'proxy' : 'polska';
                updateTabBadges(fromTab, targetTab, successfulMoves.length);
                updateSelectAllState();

                if (errors === 0) {
                    if (window.Toast) window.Toast.show(`Przeniesiono ${successfulMoves.length} zamówień do zakładki ${targetLabel}`, 'success');
                } else {
                    if (window.Toast) window.Toast.show(`Przeniesiono ${completed - errors} zamówień, ${errors} błędów`, 'warning');
                }

                setTimeout(() => {
                    successfulMoves.forEach(id => {
                        const row = document.getElementById(`order-row-${id}`);
                        if (row) row.remove();
                    });
                    const tbody = document.querySelector('.data-table tbody');
                    if (tbody && tbody.children.length === 0) showEmptyState();
                }, 350);
            }
        })
        .catch(error => {
            console.error('Bulk move error:', error);
            errors++; completed++;
        });
    });
}

function bulkMoveToPolska() { _bulkMove('polska'); }
function bulkMoveToProxy() { _bulkMove('proxy'); }

// Close multi-select and status dropdowns when clicking outside
document.addEventListener('click', function(event) {
    if (!event.target.closest('.multi-select-wrapper')) {
        ['statusMultiSelect', 'statusMultiSelectPoland', 'statusMultiSelectArchiwum'].forEach(id => {
            const d = document.getElementById(id);
            if (d) d.style.display = 'none';
        });
    }
    if (!event.target.closest('.status-dropdown-wrapper') && !event.target.closest('.status-dropdown')) {
        document.querySelectorAll('.status-dropdown, [id^="poland-status-dropdown-"]').forEach(d => {
            d.style.display = 'none';
        });
    }
});

// ============================================
// Checkbox & Bulk Actions Functions
// ============================================

/**
 * Update bulk actions modal visibility
 */
function updateBulkActionsModal() {
    const activeTab = (window.STOCK_ORDERS_CONFIG && window.STOCK_ORDERS_CONFIG.activeTab) || 'proxy';
    const config = TAB_CONFIG[activeTab];
    const checkboxClass = config ? config.checkboxClass : 'order-checkbox';
    const checkedBoxes = document.querySelectorAll(`.${checkboxClass}:checked`);
    const modal = document.getElementById('bulkActionsModal');
    const countSpan = document.getElementById('selectedCount');

    if (checkedBoxes.length > 0) {
        modal.classList.remove('hidden');
        countSpan.textContent = checkedBoxes.length;
    } else {
        modal.classList.add('hidden');
        hideBulkStatusDropdown();
    }
}

/**
 * Get selected order IDs
 */
function getSelectedOrderIds() {
    const activeTab = (window.STOCK_ORDERS_CONFIG && window.STOCK_ORDERS_CONFIG.activeTab) || 'proxy';
    const config = TAB_CONFIG[activeTab];
    const checkboxClass = config ? config.checkboxClass : 'order-checkbox';
    return Array.from(document.querySelectorAll(`.${checkboxClass}:checked`)).map(cb => cb.value);
}

/**
 * Open bulk status change dropdown
 */
function openBulkStatusChange() {
    const dropdown = document.getElementById('bulkStatusDropdown');
    if (dropdown.style.display === 'none') {
        dropdown.style.display = 'block';
    } else {
        dropdown.style.display = 'none';
    }
}

/**
 * Hide bulk status dropdown
 */
function hideBulkStatusDropdown() {
    const dropdown = document.getElementById('bulkStatusDropdown');
    if (dropdown) dropdown.style.display = 'none';
}

/**
 * Apply bulk status change
 */
function applyBulkStatus(newStatus) {
    const orderIds = getSelectedOrderIds();
    if (orderIds.length === 0) return;

    const activeTab = (window.STOCK_ORDERS_CONFIG && window.STOCK_ORDERS_CONFIG.activeTab) || 'proxy';

    const statusLabelsProxy = {
        'zamowiono': 'Zamówiono',
        'dostarczone_do_proxy': 'Dostarczone do Proxy',
        'anulowane': 'Anulowane'
    };
    const statusLabelsPoland = {
        'zamowione': 'Zamówione',
        'urzad_celny': 'Urząd celny',
        'dostarczone_gom': 'Dostarczone GOM',
        'anulowane': 'Anulowane'
    };
    const statusLabels = activeTab === 'polska' ? statusLabelsPoland : statusLabelsProxy;
    const rowPrefix = activeTab === 'polska' ? 'poland-order-row' : 'order-row';

    let completed = 0;
    let errors = 0;

    orderIds.forEach(orderId => {
        const endpoint = activeTab === 'polska'
            ? `/admin/products/poland-orders/${orderId}/status`
            : `/admin/products/proxy-orders/${orderId}/status`;

        fetch(endpoint, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({ status: newStatus })
        })
        .then(response => response.json())
        .then(data => {
            completed++;

            if (data.success) {
                const row = document.getElementById(`${rowPrefix}-${orderId}`);

                if (row) {
                    const button = row.querySelector('.status-badge-button');
                    if (button) {
                        button.className = `status-badge-button badge-${newStatus}`;
                        button.childNodes[0].textContent = (statusLabels[newStatus] || newStatus) + ' ';
                    }
                    row.dataset.status = newStatus;

                    const checkbox = row.querySelector('.order-checkbox');
                    if (checkbox) {
                        checkbox.checked = false;
                        row.classList.remove('selected');
                    }
                }
            } else {
                errors++;
            }

            if (completed === orderIds.length) {
                hideBulkStatusDropdown();
                updateBulkActionsModal();
                _updateSelectAllState(activeTab);

                if (errors === 0) {
                    if (window.Toast) {
                        window.Toast.show(`Status ${orderIds.length} zamówień został zmieniony`, 'success');
                    }
                } else {
                    if (window.Toast) {
                        window.Toast.show(`Zmieniono status ${completed - errors} zamówień, ${errors} błędów`, 'warning');
                    }
                }
            }
        })
        .catch(error => {
            console.error('Bulk status change error:', error);
            errors++;
            completed++;
        });
    });
}

/**
 * Update tab badges after moving orders
 */
function updateTabBadges(fromTab, toTab, count) {
    const proxyBadge = document.getElementById('proxyCountBadge');
    const polskaBadge = document.getElementById('polskaCountBadge');

    if (fromTab === 'proxy' && proxyBadge) {
        let currentCount = parseInt(proxyBadge.textContent) || 0;
        let newCount = Math.max(0, currentCount - count);
        proxyBadge.textContent = newCount;
        proxyBadge.style.display = newCount > 0 ? '' : 'none';
    }

    if (fromTab === 'polska' && polskaBadge) {
        let currentCount = parseInt(polskaBadge.textContent) || 0;
        let newCount = Math.max(0, currentCount - count);
        polskaBadge.textContent = newCount;
        polskaBadge.style.display = newCount > 0 ? '' : 'none';
    }

    if (toTab === 'proxy' && proxyBadge) {
        let currentCount = parseInt(proxyBadge.textContent) || 0;
        let newCount = currentCount + count;
        proxyBadge.textContent = newCount;
        proxyBadge.style.display = newCount > 0 ? '' : 'none';
    }

    if (toTab === 'polska' && polskaBadge) {
        let currentCount = parseInt(polskaBadge.textContent) || 0;
        let newCount = currentCount + count;
        polskaBadge.textContent = newCount;
        polskaBadge.style.display = newCount > 0 ? '' : 'none';
    }
}

// Close bulk status dropdown when clicking outside
document.addEventListener('click', function(event) {
    if (!event.target.closest('.bulk-action-status') && !event.target.closest('.bulk-status-dropdown')) {
        hideBulkStatusDropdown();
    }
});

/**
 * Re-position dropdowns on scroll (for fixed position)
 */
const tableResponsive = document.querySelector('.table-responsive');
if (tableResponsive) {
    tableResponsive.addEventListener('scroll', function() {
        // Close all dropdowns on scroll
        document.querySelectorAll('.status-dropdown, [id^="poland-status-dropdown-"]').forEach(d => {
            d.style.display = 'none';
        });
    });
}

/**
 * Toggle hidden products in Poland tab
 */
function togglePolandProducts(toggleEl) {
    const container = toggleEl.closest('.poland-products-cell') || toggleEl.closest('.products-cell');
    const hiddenItems = container.querySelectorAll('.poland-product-hidden');
    const isExpanded = toggleEl.dataset.expanded === 'true';

    hiddenItems.forEach(item => {
        item.style.display = isExpanded ? 'none' : '';
    });

    if (isExpanded) {
        toggleEl.textContent = `Pokaż więcej (${hiddenItems.length})`;
        toggleEl.dataset.expanded = 'false';
    } else {
        toggleEl.textContent = 'Pokaż mniej';
        toggleEl.dataset.expanded = 'true';
    }
}

/**
 * Show empty state when table becomes empty
 */
function showEmptyState() {
    // Hide the filters section
    const filtersSection = document.querySelector('.orders-filters');
    if (filtersSection) {
        filtersSection.style.display = 'none';
    }

    const tableResponsive = document.querySelector('.table-responsive');
    if (tableResponsive) {
        tableResponsive.remove();
    }

    const ordersList = document.querySelector('.orders-list');
    if (ordersList) {
        const activeTab = (window.STOCK_ORDERS_CONFIG && window.STOCK_ORDERS_CONFIG.activeTab) || 'proxy';
        let emptyStateHTML = `
            <div class="empty-state">
                <svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="1" y="4" width="22" height="16" rx="2" ry="2"></rect>
                    <line x1="1" y1="10" x2="23" y2="10"></line>
                </svg>
                <h3>Brak zamówień</h3>
        `;

        if (activeTab === 'proxy') {
            emptyStateHTML += `
                <p>Nie znaleziono żadnych zamówień dla kategorii PROXY</p>
            `;
        } else {
            emptyStateHTML += `
                <p>Zamówienia pojawią się tutaj po zmianie statusu na "Dostarczone GOM" w zakładce PROXY</p>
                <a href="${(window.STOCK_ORDERS_CONFIG && window.STOCK_ORDERS_CONFIG.proxyTabUrl) || '/admin/products/stock-orders?tab=proxy'}" class="btn btn-primary">
                    Przejdź do PROXY
                </a>
            `;
        }

        emptyStateHTML += '</div>';
        ordersList.innerHTML = emptyStateHTML;
    }
}

// ============================================
// DO ZAMÓWIENIA Tab Functions
// ============================================

/**
 * Filter rows in DO ZAMÓWIENIA tab
 */
function applyToOrderFilters() {
    const productFilter = document.getElementById('filterToOrderProduct').value.toLowerCase().trim();
    const paymentFilter = document.getElementById('filterToOrderPayment').value;
    const rows = document.querySelectorAll('#toOrderTable tbody .to-order-row');

    rows.forEach(row => {
        const productName = (row.dataset.productName || '').toLowerCase();
        const paymentType = row.dataset.paymentType || '';

        const matchProduct = !productFilter || productName.includes(productFilter);
        const matchPayment = !paymentFilter || paymentType === paymentFilter;

        row.style.display = (matchProduct && matchPayment) ? '' : 'none';
    });

    // Update select all checkbox state after filter change
    handleToOrderCheckboxChange();
}

/**
 * Toggle select all products in DO ZAMÓWIENIA tab
 */
function toggleSelectAllToOrder(checkbox) {
    const checkboxes = document.querySelectorAll('.to-order-checkbox');
    checkboxes.forEach(cb => {
        const row = cb.closest('tr');
        const isVisible = row.style.display !== 'none';
        if (isVisible) {
            cb.checked = checkbox.checked;
            if (checkbox.checked) {
                row.classList.add('selected');
            } else {
                row.classList.remove('selected');
            }
        }
    });
    handleToOrderCheckboxChange();
}

/**
 * Handle checkbox change in DO ZAMÓWIENIA tab
 */
function handleToOrderCheckboxChange() {
    const allCheckboxes = document.querySelectorAll('.to-order-checkbox');
    const visibleCheckboxes = [...allCheckboxes].filter(cb => cb.closest('tr').style.display !== 'none');
    const visibleChecked = visibleCheckboxes.filter(cb => cb.checked);

    const bulkToolbar = document.getElementById('toOrderBulkToolbar');
    const selectedCount = document.getElementById('toOrderSelectedCount');

    // Count all checked (visible + hidden) for toolbar
    const totalChecked = document.querySelectorAll('.to-order-checkbox:checked').length;
    if (totalChecked > 0) {
        bulkToolbar.classList.remove('hidden');
        selectedCount.textContent = totalChecked;
    } else {
        bulkToolbar.classList.add('hidden');
    }

    // Update select all checkbox state based on visible rows only
    const selectAllCheckbox = document.getElementById('selectAllToOrder');
    if (selectAllCheckbox) {
        selectAllCheckbox.checked = visibleCheckboxes.length > 0 && visibleChecked.length === visibleCheckboxes.length;
        selectAllCheckbox.indeterminate = visibleChecked.length > 0 && visibleChecked.length < visibleCheckboxes.length;
    }
}

/**
 * Clear selection in DO ZAMÓWIENIA tab
 */
function clearToOrderSelection() {
    const checkboxes = document.querySelectorAll('.to-order-checkbox');
    checkboxes.forEach(cb => {
        cb.checked = false;
        cb.closest('tr').classList.remove('selected');
    });
    const selectAllCheckbox = document.getElementById('selectAllToOrder');
    if (selectAllCheckbox) {
        selectAllCheckbox.checked = false;
        selectAllCheckbox.indeterminate = false;
    }
    document.getElementById('toOrderBulkToolbar').classList.add('hidden');
}

/**
 * Suppliers data for the modal dropdown
 */

// suppliersData is declared in the HTML template (Jinja2 data bridge)

// Zamknij modal grupowy po kliknięciu na overlay
(function() {
    const groupModal = document.getElementById('groupOrderModal');
    if (groupModal) {
        groupModal.addEventListener('click', function(e) {
            if (e.target === groupModal) {
                closeGroupOrderModal();
            }
        });
    }
})();

// Podświetlanie zaznaczonych wierszy w tabeli DO ZAMÓWIENIA
document.querySelectorAll('.to-order-checkbox').forEach(box => {
    box.addEventListener('change', function() {
        const row = this.closest('tr');
        if (this.checked) {
            row.classList.add('selected');
        } else {
            row.classList.remove('selected');
        }
    });
});

/**
 * Otwórz modal zamówienia grupowego z walidacją typów płatności
 */
function openOrderProductsModal() {
    const checkboxes = document.querySelectorAll('.to-order-checkbox:checked');
    if (checkboxes.length === 0) {
        if (window.Toast) {
            window.Toast.show('Zaznacz produkty do zamówienia', 'warning');
        }
        return;
    }

    // Sprawdź typy płatności (Proxy vs Polska)
    const paymentTypes = new Set();
    checkboxes.forEach(box => {
        paymentTypes.add(box.dataset.paymentType);
    });

    // WALIDACJA: NIE można mieszać Proxy + Polska
    if (paymentTypes.size > 1) {
        if (window.Toast) {
            window.Toast.show('Nie można złożyć zamówienia grupowego łączącego produkty Proxy i Polska. Zaznacz produkty tylko jednego typu.', 'error');
        } else {
            alert('Nie można złożyć zamówienia grupowego łączącego produkty Proxy i Polska. Zaznacz produkty tylko jednego typu.');
        }
        return;
    }

    const orderType = Array.from(paymentTypes)[0]; // 'proxy' lub 'polska'
    const orderTypeLabel = orderType === 'proxy' ? 'Proxy' : 'Polska';

    // Uzupełnij dane w modalu
    document.getElementById('groupOrderCount').textContent = checkboxes.length;
    document.getElementById('groupOrderType').textContent = orderTypeLabel;

    // Wypełnij tabelę produktów
    const tbody = document.getElementById('groupOrderTableBody');
    tbody.innerHTML = '';
    let total = 0;

    checkboxes.forEach(checkbox => {
        const row = checkbox.closest('tr');
        const productName = row.dataset.productName;
        const toOrder = parseInt(row.dataset.toOrder);
        const purchasePrice = parseFloat(row.dataset.purchasePrice) || 0;
        const rowTotal = toOrder * purchasePrice;
        total += rowTotal;

        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${escapeHtml(productName)}</td>
            <td class="text-center">${toOrder}</td>
            <td class="text-right">${purchasePrice.toFixed(2)} PLN</td>
            <td class="text-right font-semibold">${rowTotal.toFixed(2)} PLN</td>
        `;
        tbody.appendChild(tr);
    });

    document.getElementById('groupOrderTotal').textContent = total.toFixed(2) + ' PLN';

    // Pokaż modal
    document.getElementById('groupOrderModal').classList.add('active');
    document.body.style.overflow = 'hidden';
}

/**
 * Zamknij modal zamówienia grupowego
 */
function closeGroupOrderModal() {
    const modal = document.getElementById('groupOrderModal');
    if (modal) {
        modal.classList.add('closing');
        setTimeout(() => {
            modal.classList.remove('active');
            modal.classList.remove('closing');
            document.body.style.overflow = '';
            document.getElementById('groupOrderNote').value = '';
        }, 350);
    }
}

/**
 * Potwierdź i utwórz zamówienie grupowe
 */
function confirmGroupOrder() {
    const checkboxes = document.querySelectorAll('.to-order-checkbox:checked');
    if (checkboxes.length === 0) return;

    const note = document.getElementById('groupOrderNote').value.trim();
    const orderType = checkboxes[0].dataset.paymentType;

    // Zbierz dane produktów
    const products = [];
    checkboxes.forEach(checkbox => {
        const row = checkbox.closest('tr');
        products.push({
            product_id: parseInt(checkbox.value),
            supplier_id: row.dataset.supplierId ? parseInt(row.dataset.supplierId) : null,
            quantity: parseInt(row.dataset.toOrder),
            unit_price: parseFloat(row.dataset.purchasePrice) || 0
        });
    });

    // Wyłącz przycisk
    const btn = document.getElementById('btnConfirmGroupOrder');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-small"></span> Tworzenie...';

    // AJAX: Utwórz zamówienie grupowe
    fetch('/admin/products/api/create-group-proxy-order', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify({
            products: products,
            order_type: orderType,
            note: note
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            closeGroupOrderModal();
            if (window.Toast) {
                window.Toast.show(`Zamówienie grupowe utworzone! Numer: ${data.order_number}`, 'success');
            }
            // Przekieruj do odpowiedniej zakładki
            setTimeout(() => {
                window.location.href = `/admin/products/stock-orders?tab=${orderType}`;
            }, 1000);
        } else {
            if (window.Toast) {
                window.Toast.show('Błąd: ' + (data.error || 'Nieznany błąd'), 'error');
            }
            btn.disabled = false;
            btn.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M6 2L3 6v14a2 2 0 002 2h14a2 2 0 002-2V6l-3-4z"></path>
                    <line x1="3" y1="6" x2="21" y2="6"></line>
                    <path d="M16 10a4 4 0 01-8 0"></path>
                </svg>
                Potwierdź zamówienie
            `;
        }
    })
    .catch(error => {
        console.error('Error:', error);
        if (window.Toast) {
            window.Toast.show('Wystąpił błąd podczas tworzenia zamówienia', 'error');
        }
        btn.disabled = false;
        btn.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M6 2L3 6v14a2 2 0 002 2h14a2 2 0 002-2V6l-3-4z"></path>
                <line x1="3" y1="6" x2="21" y2="6"></line>
                <path d="M16 10a4 4 0 01-8 0"></path>
            </svg>
            Potwierdź zamówienie
        `;
    });
}

// ============================================
// ARCHIWUM — Archive / Unarchive Poland Orders
// ============================================

function toggleSelectAllArchiwum(selectAllCheckbox) {
    _toggleSelectAll('archiwum', selectAllCheckbox);
}

function handleCheckboxChangeArchiwum() {
    _updateSelectAllState('archiwum');
    updateArchiwumBulkToolbar();
}

function updateArchiwumBulkToolbar() {
    const checkedBoxes = document.querySelectorAll('.archiwum-checkbox:checked');
    const toolbar = document.getElementById('archiwumBulkToolbar');
    const countEl = document.getElementById('archiwumSelectedCount');
    if (!toolbar) return;

    if (checkedBoxes.length > 0) {
        toolbar.classList.remove('hidden');
        if (countEl) countEl.textContent = checkedBoxes.length;
    } else {
        toolbar.classList.add('hidden');
    }
}

function getSelectedArchiwumIds() {
    return Array.from(document.querySelectorAll('.archiwum-checkbox:checked')).map(cb => cb.value);
}

function bulkArchivePolandOrders() {
    const orderIds = getSelectedOrderIds();
    if (orderIds.length === 0) {
        if (window.Toast) window.Toast.show('Zaznacz zamówienia do archiwizacji', 'warning');
        return;
    }

    if (!confirm(`Czy na pewno chcesz przenieść ${orderIds.length} zamówień do archiwum?`)) return;

    fetch('/admin/products/poland-orders/bulk-archive', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify({ order_ids: orderIds.map(Number), archive: true })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            if (window.Toast) window.Toast.show(data.message, 'success');
            setTimeout(() => location.reload(), 500);
        } else {
            if (window.Toast) window.Toast.show(data.error || 'Błąd archiwizacji', 'error');
        }
    })
    .catch(err => {
        console.error('Error:', err);
        if (window.Toast) window.Toast.show('Wystąpił błąd', 'error');
    });
}

function bulkUnarchivePolandOrders() {
    const orderIds = getSelectedArchiwumIds();
    if (orderIds.length === 0) {
        if (window.Toast) window.Toast.show('Zaznacz zamówienia do przywrócenia', 'warning');
        return;
    }

    if (!confirm(`Czy na pewno chcesz przywrócić ${orderIds.length} zamówień z archiwum?`)) return;

    fetch('/admin/products/poland-orders/bulk-archive', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify({ order_ids: orderIds.map(Number), archive: false })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            if (window.Toast) window.Toast.show(data.message, 'success');
            setTimeout(() => location.reload(), 500);
        } else {
            if (window.Toast) window.Toast.show(data.error || 'Błąd przywracania', 'error');
        }
    })
    .catch(err => {
        console.error('Error:', err);
        if (window.Toast) window.Toast.show('Wystąpił błąd', 'error');
    });
}

// Archiwum filter wrapper functions
function toggleStatusMultiSelectArchiwum() { _toggleStatusMultiSelect('archiwum'); }
function updateStatusFilterArchiwum() { _updateStatusFilter('archiwum'); }
function applyFiltersArchiwum() { _applyFilters('archiwum'); }
function clearAllFiltersArchiwum() { _clearAllFilters('archiwum'); }
