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
