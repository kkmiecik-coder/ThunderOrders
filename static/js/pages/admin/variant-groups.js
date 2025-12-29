/**
 * Variant Groups System
 * Handles multiple variant groups per product with search, add/remove functionality
 */

let variantGroups = [];
let currentProductId = null;
let searchDebounceTimer = null;
let existingGroupSearchTimer = null;
let selectedProducts = {}; // Track selected products per group: { groupTempId: Set<productId> }
let activeDropdownGroupId = null; // Track which group's dropdown is currently open

/**
 * Initialize the variant groups system
 * @param {number|null} productId - Current product ID (null for new products)
 * @param {Array} existingGroups - Existing variant groups from backend
 */
function initVariantGroupsSystem(productId, existingGroups) {
    console.log('[VARIANT GROUPS INIT] initVariantGroupsSystem called');
    console.log('[VARIANT GROUPS INIT] productId:', productId, 'type:', typeof productId);
    console.log('[VARIANT GROUPS INIT] existingGroups:', existingGroups);

    currentProductId = productId;
    console.log('[VARIANT GROUPS INIT] currentProductId set to:', currentProductId);

    variantGroups = existingGroups.map((group, index) => ({
        id: group.id,
        name: group.name,
        products: group.products || [],
        tempId: `temp_${Date.now()}_${index}` // Temporary ID for frontend tracking
    }));

    console.log('[VARIANT GROUPS INIT] variantGroups initialized:', variantGroups);
    renderAllGroups();

    // Setup global click handler to close dropdowns when clicking outside
    setupGlobalClickHandler();
}

/**
 * Setup global click handler to close search dropdowns
 */
function setupGlobalClickHandler() {
    // Remove existing listener if any
    document.removeEventListener('click', handleGlobalClick);

    // Add new listener
    document.addEventListener('click', handleGlobalClick);
}

/**
 * Handle global clicks to close dropdowns when clicking outside
 */
function handleGlobalClick(event) {
    // If there's no active dropdown, nothing to do
    if (!activeDropdownGroupId) return;

    const resultsContainer = document.getElementById(`searchResults_${activeDropdownGroupId}`);
    const searchInput = document.getElementById(`searchInput_${activeDropdownGroupId}`);

    if (!resultsContainer) return;

    // Check if click was inside the search input or results container
    const clickedInsideSearch = searchInput && searchInput.contains(event.target);
    const clickedInsideResults = resultsContainer.contains(event.target);

    // If click was outside both, hide the dropdown
    if (!clickedInsideSearch && !clickedInsideResults) {
        hideSearchResults(activeDropdownGroupId);
        activeDropdownGroupId = null;
    }
}

/**
 * Render all variant groups
 */
function renderAllGroups() {
    console.log('[RENDER ALL GROUPS] Called. variantGroups:', variantGroups);

    const container = document.getElementById('variantGroupsContainer');
    if (!container) {
        console.error('[RENDER ALL GROUPS] Container NOT FOUND!');
        return;
    }

    container.innerHTML = '';

    if (variantGroups.length === 0) {
        console.log('[RENDER ALL GROUPS] No groups to render');
        container.innerHTML = '<p class="text-muted">Brak grup wariantowych. Kliknij "Dodaj nową grupę wariantową" aby rozpocząć.</p>';
        return;
    }

    console.log('[RENDER ALL GROUPS] Rendering', variantGroups.length, 'groups');

    variantGroups.forEach((group, index) => {
        console.log('[RENDER ALL GROUPS] Rendering group', index, ':', group);
        const groupHtml = renderGroup(group, index);
        container.insertAdjacentHTML('beforeend', groupHtml);
    });

    console.log('[RENDER ALL GROUPS] All groups rendered');
}

/**
 * Render single variant group
 * @param {Object} group - Group data
 * @param {number} index - Group index
 * @returns {string} HTML string
 */
function renderGroup(group, index) {
    console.log('[RENDER GROUP] Rendering group:', group);
    console.log('[RENDER GROUP] Group.products:', group.products);
    console.log('[RENDER GROUP] Products count:', group.products ? group.products.length : 0);

    const productsHtml = group.products.map(product => {
        console.log('[RENDER GROUP]   - Rendering product:', product);
        const price = product.price !== undefined ? parseFloat(product.price).toFixed(2) : '0.00';
        return `
        <div class="variant-product-tile" data-product-id="${product.id}">
            <button type="button" class="tile-remove-btn" onclick="removeProductFromGroup('${group.tempId}', ${product.id})" title="Usuń produkt">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708z"/>
                </svg>
            </button>
            <img src="${product.image_url}" alt="${product.name}" class="tile-image" onerror="this.src='/static/img/product-placeholder.svg'">
            <div class="tile-info">
                <div class="tile-name" title="${product.name}">${product.name}</div>
                <div class="tile-meta">${product.series} • ${product.type}</div>
                <div class="tile-price">${price} PLN</div>
            </div>
        </div>
    `;
    }).join('');

    console.log('[RENDER GROUP] Products HTML generated, length:', productsHtml.length);

    return `
        <div class="variant-group-card" data-group-id="${group.tempId}">
            <div class="group-header">
                <input type="text"
                       class="group-name-input"
                       value="${group.name}"
                       placeholder="Nazwa grupy (np. Grupa 1)"
                       onchange="updateGroupName('${group.tempId}', this.value)">
                <button type="button" class="btn-delete-group" onclick="deleteGroup('${group.tempId}')" title="Usuń całą grupę">
                    <svg width="18" height="18" viewBox="0 0 18 18" fill="currentColor">
                        <path d="M6 2a1 1 0 0 0-1 1v1H3a1 1 0 0 0 0 2h1v9a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2V6h1a1 1 0 1 0 0-2h-2V3a1 1 0 0 0-1-1H6zm1 2h4v1H7V4zm-1 3h8v8a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V7z"/>
                    </svg>
                </button>
            </div>

            <!-- Search Input -->
            <div class="group-search-container">
                <input type="text"
                       id="searchInput_${group.tempId}"
                       class="group-search-input"
                       placeholder="Wyszukaj produkt do dodania..."
                       oninput="handleSearch('${group.tempId}', this.value)"
                       onfocus="handleSearchFocus('${group.tempId}')"
                       onblur="handleSearchBlur('${group.tempId}')">
                <div class="search-results-dropdown" id="searchResults_${group.tempId}" style="display: none;">
                    <!-- Results will be inserted here -->
                </div>
            </div>

            <!-- Products Grid -->
            <div class="variants-products-grid">
                ${productsHtml || '<p class="text-muted">Brak produktów. Użyj wyszukiwarki powyżej aby dodać produkty.</p>'}
            </div>
        </div>
    `;
}

/**
 * Add new variant group
 */
function addNewVariantGroup() {
    const groupNumber = variantGroups.length + 1;
    const newGroup = {
        id: null, // New group, no DB id yet
        name: `Grupa ${groupNumber}`,
        products: [],
        tempId: `temp_${Date.now()}_${groupNumber}`
    };

    variantGroups.push(newGroup);
    renderAllGroups();
}

/**
 * Delete variant group
 * @param {string} tempId - Temporary group ID
 */
function deleteGroup(tempId) {
    if (!confirm('Czy na pewno chcesz usunąć tę grupę wariantową?')) {
        return;
    }

    variantGroups = variantGroups.filter(g => g.tempId !== tempId);
    renderAllGroups();
}

/**
 * Update group name
 * @param {string} tempId - Temporary group ID
 * @param {string} newName - New group name
 */
function updateGroupName(tempId, newName) {
    const group = variantGroups.find(g => g.tempId === tempId);
    if (group) {
        group.name = newName.trim() || `Grupa ${variantGroups.indexOf(group) + 1}`;
    }
}

/**
 * Handle search input with debounce
 * @param {string} groupTempId - Temporary group ID
 * @param {string} query - Search query
 */
function handleSearch(groupTempId, query) {
    clearTimeout(searchDebounceTimer);

    if (query.trim().length < 2) {
        hideSearchResults(groupTempId);
        return;
    }

    searchDebounceTimer = setTimeout(() => {
        performSearch(groupTempId, query);
    }, 500); // 0.5 second debounce
}

/**
 * Perform actual search
 * @param {string} groupTempId - Temporary group ID
 * @param {string} query - Search query
 */
async function performSearch(groupTempId, query) {
    const group = variantGroups.find(g => g.tempId === groupTempId);
    if (!group) return;

    const resultsContainer = document.getElementById(`searchResults_${groupTempId}`);
    if (!resultsContainer) return;

    try {
        // Build query params
        const params = new URLSearchParams({
            q: query,
            exclude_group_id: group.id || '',
            product_id: currentProductId || ''
        });

        const response = await fetch(`/admin/products/search-variants?${params}`);
        const data = await response.json();

        if (!data.products || data.products.length === 0) {
            resultsContainer.innerHTML = '<div class="search-result-item no-results">Brak wyników</div>';
            resultsContainer.style.display = 'block';
            return;
        }

        // Filter out products already in THIS group
        const existingIds = group.products.map(p => p.id);
        const filteredProducts = data.products.filter(p => !existingIds.includes(p.id));

        if (filteredProducts.length === 0) {
            resultsContainer.innerHTML = '<div class="search-result-item no-results">Wszystkie wyniki już są w tej grupie</div>';
            resultsContainer.style.display = 'block';
            return;
        }

        // Initialize selected products set for this group if not exists
        if (!selectedProducts[groupTempId]) {
            selectedProducts[groupTempId] = new Set();
        }

        // Render results with checkboxes
        const selectAllChecked = selectedProducts[groupTempId].size === filteredProducts.length && filteredProducts.length > 0;

        let resultsHtml = `
            <div class="search-result-header">
                <label class="search-result-select-all">
                    <input type="checkbox"
                           id="selectAll_${groupTempId}"
                           ${selectAllChecked ? 'checked' : ''}
                           onchange="toggleSelectAll('${groupTempId}', this.checked)">
                    <span>Zaznacz wszystkie (${filteredProducts.length})</span>
                </label>
            </div>
        `;

        resultsHtml += filteredProducts.map(product => {
            const isChecked = selectedProducts[groupTempId].has(product.id);
            const productName = product.name.replace(/"/g, '&quot;');
            const productSeries = (product.series || '').replace(/"/g, '&quot;');
            const productType = (product.type || '').replace(/"/g, '&quot;');
            const productImage = product.image_url.replace(/"/g, '&quot;');
            const productPrice = product.price !== undefined ? product.price : 0.0;

            return `
            <div class="search-result-item"
                 data-product-id="${product.id}"
                 data-product-name="${productName}"
                 data-product-series="${productSeries}"
                 data-product-type="${productType}"
                 data-product-image="${productImage}"
                 data-product-price="${productPrice}">
                <input type="checkbox"
                       class="result-checkbox"
                       ${isChecked ? 'checked' : ''}
                       onchange="toggleProductSelection('${groupTempId}', ${product.id}, this.checked)"
                       onclick="event.stopPropagation()">
                <img src="${product.image_url}" alt="${productName}" class="result-thumbnail" onerror="this.src='/static/img/product-placeholder.svg'">
                <div class="result-info" onclick="addProductToGroupFromData('${groupTempId}', this.parentElement)">
                    <div class="result-name">${product.name}</div>
                    <div class="result-meta">${product.series} • ${product.type}</div>
                </div>
            </div>
        `}).join('');

        resultsContainer.innerHTML = resultsHtml;
        resultsContainer.style.display = 'block';

        // Mark this dropdown as active
        activeDropdownGroupId = groupTempId;

        // Update bulk add button visibility
        updateBulkAddButton(groupTempId, filteredProducts);

    } catch (error) {
        console.error('Search error:', error);
        resultsContainer.innerHTML = '<div class="search-result-item no-results">Błąd wyszukiwania</div>';
        resultsContainer.style.display = 'block';
    }
}

/**
 * Handle search input focus
 * @param {string} groupTempId - Temporary group ID
 */
function handleSearchFocus(groupTempId) {
    const resultsContainer = document.getElementById(`searchResults_${groupTempId}`);
    if (resultsContainer && resultsContainer.innerHTML.trim() !== '') {
        resultsContainer.style.display = 'block';
        activeDropdownGroupId = groupTempId;
    }
}

/**
 * Handle search input blur
 * @param {string} groupTempId - Temporary group ID
 */
function handleSearchBlur(groupTempId) {
    // Don't hide results - let user interact with checkboxes
    // Results will be hidden manually when needed (after adding products)
}

/**
 * Hide search results dropdown
 * @param {string} groupTempId - Temporary group ID
 */
function hideSearchResults(groupTempId) {
    const resultsContainer = document.getElementById(`searchResults_${groupTempId}`);
    if (resultsContainer) {
        resultsContainer.style.display = 'none';
    }

    // Clear active dropdown if it's this one
    if (activeDropdownGroupId === groupTempId) {
        activeDropdownGroupId = null;
    }
}

/**
 * Add product to group
 * @param {string} groupTempId - Temporary group ID
 * @param {Object} product - Product data
 */
function addProductToGroup(groupTempId, product) {
    const group = variantGroups.find(g => g.tempId === groupTempId);
    if (!group) return;

    // Check if product already in group
    if (group.products.some(p => p.id === product.id)) {
        return;
    }

    // Add product
    group.products.push(product);

    // Re-render this specific group
    renderAllGroups();

    // Clear search
    const searchInput = document.querySelector(`[oninput*="${groupTempId}"]`);
    if (searchInput) {
        searchInput.value = '';
    }
    hideSearchResults(groupTempId);
}

/**
 * Add product to group from data attributes
 * @param {string} groupTempId - Temporary group ID
 * @param {HTMLElement} itemElement - The search result item element
 */
function addProductToGroupFromData(groupTempId, itemElement) {
    const product = {
        id: parseInt(itemElement.getAttribute('data-product-id')),
        name: itemElement.getAttribute('data-product-name'),
        series: itemElement.getAttribute('data-product-series'),
        type: itemElement.getAttribute('data-product-type'),
        image_url: itemElement.getAttribute('data-product-image'),
        price: parseFloat(itemElement.getAttribute('data-product-price')) || 0.0
    };

    addProductToGroup(groupTempId, product);
}

/**
 * Remove product from group
 * @param {string} groupTempId - Temporary group ID
 * @param {number} productId - Product ID to remove
 */
function removeProductFromGroup(groupTempId, productId) {
    const group = variantGroups.find(g => g.tempId === groupTempId);
    if (!group) return;

    // Ask for confirmation first
    if (!confirm('Czy na pewno chcesz usunąć ten produkt z grupy wariantów?')) {
        return; // User clicked Cancel - do nothing
    }

    // Remove product from group
    group.products = group.products.filter(p => p.id !== productId);

    // If group is now empty, auto-delete it (no additional confirmation)
    if (group.products.length === 0) {
        deleteGroup(groupTempId);
        return;
    }

    renderAllGroups();
}

/**
 * Toggle product selection
 * @param {string} groupTempId - Temporary group ID
 * @param {number} productId - Product ID to toggle
 * @param {boolean} checked - Whether checkbox is checked
 */
function toggleProductSelection(groupTempId, productId, checked) {
    if (!selectedProducts[groupTempId]) {
        selectedProducts[groupTempId] = new Set();
    }

    if (checked) {
        selectedProducts[groupTempId].add(productId);
    } else {
        selectedProducts[groupTempId].delete(productId);
    }

    // Update select all checkbox
    const resultsContainer = document.getElementById(`searchResults_${groupTempId}`);
    if (resultsContainer) {
        const totalProducts = resultsContainer.querySelectorAll('.search-result-item[data-product-id]').length;
        const selectAllCheckbox = document.getElementById(`selectAll_${groupTempId}`);
        if (selectAllCheckbox) {
            selectAllCheckbox.checked = selectedProducts[groupTempId].size === totalProducts;
        }
    }

    // Update bulk add button
    updateBulkAddButton(groupTempId);
}

/**
 * Toggle select all products
 * @param {string} groupTempId - Temporary group ID
 * @param {boolean} checked - Whether to select all
 */
function toggleSelectAll(groupTempId, checked) {
    if (!selectedProducts[groupTempId]) {
        selectedProducts[groupTempId] = new Set();
    }

    const resultsContainer = document.getElementById(`searchResults_${groupTempId}`);
    if (!resultsContainer) return;

    const productItems = resultsContainer.querySelectorAll('.search-result-item[data-product-id]');

    if (checked) {
        // Select all
        productItems.forEach(item => {
            const productId = parseInt(item.getAttribute('data-product-id'));
            selectedProducts[groupTempId].add(productId);
            const checkbox = item.querySelector('.result-checkbox');
            if (checkbox) checkbox.checked = true;
        });
    } else {
        // Deselect all
        selectedProducts[groupTempId].clear();
        productItems.forEach(item => {
            const checkbox = item.querySelector('.result-checkbox');
            if (checkbox) checkbox.checked = false;
        });
    }

    // Update bulk add button
    updateBulkAddButton(groupTempId);
}

/**
 * Update bulk add button visibility and count
 * @param {string} groupTempId - Temporary group ID
 * @param {Array} products - Optional products array for data lookup
 */
function updateBulkAddButton(groupTempId, products = null) {
    const resultsContainer = document.getElementById(`searchResults_${groupTempId}`);
    if (!resultsContainer) return;

    const selectedCount = selectedProducts[groupTempId] ? selectedProducts[groupTempId].size : 0;

    // Remove existing button
    const existingButton = resultsContainer.querySelector('.bulk-add-button');
    if (existingButton) {
        existingButton.remove();
    }

    // Add new button if there are selected products
    if (selectedCount > 0) {
        const button = document.createElement('div');
        button.className = 'bulk-add-button';
        button.innerHTML = `
            <button type="button" class="btn btn-primary" onclick="addSelectedProducts('${groupTempId}')">
                ✓ Dodaj zaznaczone (${selectedCount})
            </button>
        `;
        resultsContainer.appendChild(button);
    }
}

/**
 * Add all selected products to group
 * @param {string} groupTempId - Temporary group ID
 */
async function addSelectedProducts(groupTempId) {
    if (!selectedProducts[groupTempId] || selectedProducts[groupTempId].size === 0) {
        return;
    }

    const group = variantGroups.find(g => g.tempId === groupTempId);
    if (!group) return;

    const resultsContainer = document.getElementById(`searchResults_${groupTempId}`);
    if (!resultsContainer) return;

    const selectedIds = Array.from(selectedProducts[groupTempId]);
    let addedCount = 0;

    // Fetch product data for each selected product
    for (const productId of selectedIds) {
        const productItem = resultsContainer.querySelector(`.search-result-item[data-product-id="${productId}"]`);
        if (!productItem) continue;

        // Extract product data from DOM
        const imgElement = productItem.querySelector('.result-thumbnail');
        const nameElement = productItem.querySelector('.result-name');
        const metaElement = productItem.querySelector('.result-meta');

        if (!nameElement) continue;

        const product = {
            id: productId,
            name: nameElement.textContent,
            image_url: imgElement ? imgElement.src : '/static/img/product-placeholder.svg',
            series: metaElement ? metaElement.textContent.split(' • ')[0] : '',
            type: metaElement ? metaElement.textContent.split(' • ')[1] : '',
            price: parseFloat(productItem.getAttribute('data-product-price')) || 0.0
        };

        // Check if product is already in group
        if (!group.products.some(p => p.id === product.id)) {
            group.products.push(product);
            addedCount++;
        }
    }

    // Clear selections
    selectedProducts[groupTempId].clear();

    // Hide search results and clear input
    hideSearchResults(groupTempId);
    const searchInput = document.querySelector(`#searchInput_${groupTempId}`);
    if (searchInput) {
        searchInput.value = '';
    }

    // Re-render group
    renderAllGroups();

    // Show success message
    if (window.showToast && addedCount > 0) {
        showToast(`Dodano ${addedCount} ${addedCount === 1 ? 'produkt' : 'produkty/ów'} do grupy`, 'success');
    }
}

/**
 * Save all variant groups (called on form submit)
 */
async function saveVariantGroups() {
    console.log('[VARIANT GROUPS] saveVariantGroups() called');
    console.log('[VARIANT GROUPS] currentProductId:', currentProductId);
    console.log('[VARIANT GROUPS] variantGroups:', variantGroups);

    if (!currentProductId) {
        console.log('[VARIANT GROUPS] No product ID yet, variant groups will be saved after product creation');
        return true;
    }

    try {
        // Prepare data (even if empty array - backend needs to know to delete all groups)
        const groupsData = variantGroups.map(group => ({
            id: group.id,
            name: group.name,
            product_ids: group.products.map(p => p.id)
        }));

        console.log('[VARIANT GROUPS] Sending data:', groupsData);
        console.log('[VARIANT GROUPS] URL:', `/admin/products/${currentProductId}/save-variant-groups`);

        const response = await fetch(`/admin/products/${currentProductId}/save-variant-groups`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ groups: groupsData })
        });

        console.log('[VARIANT GROUPS] Response status:', response.status);
        const data = await response.json();
        console.log('[VARIANT GROUPS] Response data:', data);

        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Błąd zapisu grup wariantowych');
        }

        console.log('[VARIANT GROUPS] Successfully saved variant groups');
        return true;

    } catch (error) {
        console.error('[VARIANT GROUPS] Error saving variant groups:', error);
        alert('Błąd zapisu grup wariantowych: ' + error.message);
        return false;
    }
}

/**
 * Handle search for existing groups with debounce
 * @param {string} query - Search query
 */
function handleExistingGroupSearch(query) {
    clearTimeout(existingGroupSearchTimer);

    if (query.trim().length < 2) {
        hideExistingGroupSearchResults();
        return;
    }

    existingGroupSearchTimer = setTimeout(() => {
        performExistingGroupSearch(query);
    }, 500);
}

/**
 * Perform search for existing variant groups
 * @param {string} query - Search query
 */
async function performExistingGroupSearch(query) {
    const resultsContainer = document.getElementById('existingGroupsSearchResults');
    if (!resultsContainer) return;

    try {
        // Build query params - exclude groups that this product is already in
        const existingGroupIds = variantGroups.map(g => g.id).filter(id => id !== null);
        const params = new URLSearchParams({
            q: query,
            exclude_ids: existingGroupIds.join(',')
        });

        const response = await fetch(`/admin/products/search-variant-groups?${params}`);
        const data = await response.json();

        if (!data.groups || data.groups.length === 0) {
            resultsContainer.innerHTML = '<div class="search-result-item no-results">Brak grup o tej nazwie</div>';
            resultsContainer.style.display = 'block';
            return;
        }

        // Render results
        const resultsHtml = data.groups.map(group => `
            <div class="search-result-item" onclick="addProductToExistingGroup(${JSON.stringify(group).replace(/"/g, '&quot;')})">
                <div class="result-info" style="width: 100%;">
                    <div class="result-name">${group.name}</div>
                    <div class="result-meta">${group.product_count} produktów w grupie</div>
                </div>
            </div>
        `).join('');

        resultsContainer.innerHTML = resultsHtml;
        resultsContainer.style.display = 'block';

    } catch (error) {
        console.error('Existing group search error:', error);
        resultsContainer.innerHTML = '<div class="search-result-item no-results">Błąd wyszukiwania</div>';
        resultsContainer.style.display = 'block';
    }
}

/**
 * Handle search input focus for existing groups
 */
function handleExistingGroupSearchFocus() {
    const resultsContainer = document.getElementById('existingGroupsSearchResults');
    if (resultsContainer && resultsContainer.innerHTML.trim() !== '') {
        resultsContainer.style.display = 'block';
    }
}

/**
 * Handle search input blur for existing groups
 */
function handleExistingGroupSearchBlur() {
    setTimeout(() => {
        hideExistingGroupSearchResults();
    }, 200);
}

/**
 * Hide existing groups search results
 */
function hideExistingGroupSearchResults() {
    const resultsContainer = document.getElementById('existingGroupsSearchResults');
    if (resultsContainer) {
        resultsContainer.style.display = 'none';
    }
}

/**
 * Add current product to an existing variant group
 * @param {Object} group - Group data from search
 */
async function addProductToExistingGroup(group) {
    if (!currentProductId) {
        alert('Zapisz produkt przed dodaniem do grupy.');
        return;
    }

    // Check if group already in variantGroups
    if (variantGroups.some(g => g.id === group.id)) {
        alert('Ten produkt już należy do tej grupy.');
        return;
    }

    try {
        // Fetch full group data with products
        const response = await fetch(`/admin/products/variant-group/${group.id}`);
        const data = await response.json();

        if (!data.success) {
            throw new Error(data.error || 'Błąd pobierania danych grupy');
        }

        // Add group to variantGroups
        const fullGroup = {
            id: data.group.id,
            name: data.group.name,
            products: data.group.products || [],
            tempId: `temp_${Date.now()}_${variantGroups.length}`
        };

        // Add current product to the group if not already there
        if (!fullGroup.products.some(p => p.id === currentProductId)) {
            // We need to fetch current product data
            const currentProductData = await fetchCurrentProductData();
            if (currentProductData) {
                fullGroup.products.push(currentProductData);
            }
        }

        variantGroups.push(fullGroup);
        renderAllGroups();

        // Clear search
        const searchInput = document.getElementById('searchExistingGroupsInput');
        if (searchInput) {
            searchInput.value = '';
        }
        hideExistingGroupSearchResults();

        // Show success message
        if (window.showToast) {
            showToast(`Produkt dodany do grupy "${group.name}"`, 'success');
        }

    } catch (error) {
        console.error('Error adding to existing group:', error);
        alert('Błąd dodawania do grupy: ' + error.message);
    }
}

/**
 * Fetch current product data for adding to group
 */
async function fetchCurrentProductData() {
    if (!currentProductId) return null;

    try {
        const response = await fetch(`/admin/products/${currentProductId}/data`);
        const data = await response.json();

        if (data.success) {
            return data.product;
        }
        return null;
    } catch (error) {
        console.error('Error fetching current product data:', error);
        return null;
    }
}

// Expose functions globally
window.initVariantGroupsSystem = initVariantGroupsSystem;
window.addNewVariantGroup = addNewVariantGroup;
window.deleteGroup = deleteGroup;
window.updateGroupName = updateGroupName;
window.handleSearch = handleSearch;
window.handleSearchFocus = handleSearchFocus;
window.handleSearchBlur = handleSearchBlur;
window.addProductToGroup = addProductToGroup;
window.addProductToGroupFromData = addProductToGroupFromData;
window.removeProductFromGroup = removeProductFromGroup;
window.saveVariantGroups = saveVariantGroups;
window.handleExistingGroupSearch = handleExistingGroupSearch;
window.handleExistingGroupSearchFocus = handleExistingGroupSearchFocus;
window.handleExistingGroupSearchBlur = handleExistingGroupSearchBlur;
window.addProductToExistingGroup = addProductToExistingGroup;
window.toggleProductSelection = toggleProductSelection;
window.toggleSelectAll = toggleSelectAll;
window.addSelectedProducts = addSelectedProducts;
