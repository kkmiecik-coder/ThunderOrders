/**
 * Variant Groups System
 * Handles multiple variant groups per product with search, add/remove functionality
 */

let variantGroups = [];
let currentProductId = null;
let searchDebounceTimer = null;

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

        // Render results
        const resultsHtml = filteredProducts.map(product => `
            <div class="search-result-item" onclick="addProductToGroup('${groupTempId}', ${JSON.stringify(product).replace(/"/g, '&quot;')})">
                <img src="${product.image_url}" alt="${product.name}" class="result-thumbnail" onerror="this.src='/static/img/product-placeholder.svg'">
                <div class="result-info">
                    <div class="result-name">${product.name}</div>
                    <div class="result-meta">${product.series} • ${product.type}</div>
                </div>
            </div>
        `).join('');

        resultsContainer.innerHTML = resultsHtml;
        resultsContainer.style.display = 'block';

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
    }
}

/**
 * Handle search input blur
 * @param {string} groupTempId - Temporary group ID
 */
function handleSearchBlur(groupTempId) {
    // Delay to allow click on results
    setTimeout(() => {
        hideSearchResults(groupTempId);
    }, 200);
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

// Expose functions globally
window.initVariantGroupsSystem = initVariantGroupsSystem;
window.addNewVariantGroup = addNewVariantGroup;
window.deleteGroup = deleteGroup;
window.updateGroupName = updateGroupName;
window.handleSearch = handleSearch;
window.handleSearchFocus = handleSearchFocus;
window.handleSearchBlur = handleSearchBlur;
window.addProductToGroup = addProductToGroup;
window.removeProductFromGroup = removeProductFromGroup;
window.saveVariantGroups = saveVariantGroups;
