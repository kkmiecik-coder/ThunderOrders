/**
 * Product Form Extended JavaScript
 * Tags system, image upload, variants search
 */

// ==========================================
// Tags System
// ==========================================
window.selectedTags = new Set();
window.linkedVariants = new Set();

window.initTagsSystem = function() {
    // IMPORTANT: Clear selectedTags set when initializing (for modal reuse)
    selectedTags.clear();

    // Clear any existing badges in the UI
    const tagsSelectedContainer = document.getElementById('tagsSelected');
    if (tagsSelectedContainer) {
        tagsSelectedContainer.innerHTML = '';
    }

    // Reset all tag options to be visible
    const allTagOptions = document.querySelectorAll('.tag-option');
    allTagOptions.forEach(option => {
        option.style.display = 'block';
    });

    // Pre-select already checked tags
    const checkboxes = document.querySelectorAll('input[name="tags"]');
    checkboxes.forEach(checkbox => {
        if (checkbox.checked) {
            const tagOption = document.querySelector(`[data-tag-id="${checkbox.value}"]`);
            if (tagOption) {
                const tagId = checkbox.value;
                const tagName = tagOption.getAttribute('data-tag-name');
                selectedTags.add(tagId);
                addTagBadge(tagId, tagName);
                // Hide this tag in dropdown since it's already selected
                tagOption.style.display = 'none';
            }
        }
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', function(e) {
        const tagsWrapper = document.querySelector('.tags-input-wrapper');
        const dropdown = document.getElementById('tagsDropdown');
        if (tagsWrapper && !tagsWrapper.contains(e.target)) {
            dropdown.style.display = 'none';
        }
    });
}

window.showTagsDropdown = function() {
    const dropdown = document.getElementById('tagsDropdown');
    dropdown.style.display = 'block';
}

window.filterTags = function(searchTerm) {
    const dropdown = document.getElementById('tagsDropdown');
    const options = dropdown.querySelectorAll('.tag-option');

    dropdown.style.display = 'block';

    searchTerm = searchTerm.toLowerCase();

    options.forEach(option => {
        const tagName = option.getAttribute('data-tag-name').toLowerCase();
        const tagId = option.getAttribute('data-tag-id');

        // Hide if already selected or doesn't match search
        if (selectedTags.has(tagId) || (searchTerm && !tagName.includes(searchTerm))) {
            option.style.display = 'none';
        } else {
            option.style.display = 'block';
        }
    });
}

window.selectTag = function(tagId, tagName) {
    if (selectedTags.has(tagId)) return;

    // Add to selected set
    selectedTags.add(tagId);

    // Check the hidden checkbox
    const checkbox = document.querySelector(`input[name="tags"][value="${tagId}"]`);
    if (checkbox) {
        checkbox.checked = true;
    }

    // Add badge
    addTagBadge(tagId, tagName);

    // Hide this tag from dropdown since it's now selected
    const tagOption = document.querySelector(`.tag-option[data-tag-id="${tagId}"]`);
    if (tagOption) {
        tagOption.style.display = 'none';
    }

    // Clear search input
    const searchInput = document.getElementById('tagsSearchInput');
    if (searchInput) {
        searchInput.value = '';
    }

    // Hide dropdown
    const dropdown = document.getElementById('tagsDropdown');
    if (dropdown) {
        dropdown.style.display = 'none';
    }
}

function addTagBadge(tagId, tagName) {
    const tagsSelectedContainer = document.getElementById('tagsSelected');

    const badge = document.createElement('div');
    badge.className = 'tag-badge';
    badge.setAttribute('data-tag-id', tagId);
    badge.innerHTML = `
        <span class="tag-badge-text">${tagName}</span>
        <button type="button" class="tag-badge-remove" onclick="removeTag('${tagId}')">✕</button>
    `;

    tagsSelectedContainer.appendChild(badge);
}

window.removeTag = function(tagId) {
    // Remove from selected set
    selectedTags.delete(tagId);

    // Uncheck the hidden checkbox
    const checkbox = document.querySelector(`input[name="tags"][value="${tagId}"]`);
    if (checkbox) {
        checkbox.checked = false;
    }

    // Remove badge
    const badge = document.querySelector(`.tag-badge[data-tag-id="${tagId}"]`);
    if (badge) {
        badge.remove();
    }

    // Show this tag back in dropdown since it's no longer selected
    const tagOption = document.querySelector(`.tag-option[data-tag-id="${tagId}"]`);
    if (tagOption) {
        tagOption.style.display = 'block';
    }
}

// ==========================================
// Image Upload System
// ==========================================
window.selectedImages = [];

window.handleImageSelect = function(event) {
    const files = Array.from(event.target.files);
    const previewGrid = document.getElementById('imagesPreviewGrid');
    const uploadArea = document.getElementById('imageUploadArea');

    if (files.length === 0) return;

    // Validate files
    const validFiles = [];
    const maxSize = 5 * 1024 * 1024; // 5MB
    const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp'];

    files.forEach(file => {
        if (!allowedTypes.includes(file.type)) {
            alert(`Nieprawidłowy typ pliku: ${file.name}. Dozwolone: JPG, PNG, GIF, WEBP.`);
            return;
        }
        if (file.size > maxSize) {
            alert(`Plik ${file.name} jest za duży. Maksymalny rozmiar: 5MB.`);
            return;
        }
        validFiles.push(file);
    });

    if (validFiles.length === 0) return;

    // Add to selected images
    selectedImages.push(...validFiles);

    // Show preview grid
    previewGrid.style.display = 'grid';

    // Create previews
    validFiles.forEach((file, index) => {
        const reader = new FileReader();
        reader.onload = function(e) {
            const previewItem = document.createElement('div');
            previewItem.className = 'image-preview-item';
            previewItem.innerHTML = `
                <img src="${e.target.result}" alt="${file.name}" class="image-preview-thumb">
                <div class="image-preview-overlay">
                    <span class="image-preview-name">${file.name}</span>
                    <button type="button" class="btn-remove-image" onclick="removeImagePreview(${selectedImages.length - validFiles.length + index})">
                        ✕ Usuń
                    </button>
                </div>
            `;
            previewGrid.appendChild(previewItem);
        };
        reader.readAsDataURL(file);
    });
}

window.removeImagePreview = function(index) {
    selectedImages.splice(index, 1);

    // Rebuild preview grid
    const previewGrid = document.getElementById('imagesPreviewGrid');
    previewGrid.innerHTML = '';

    if (selectedImages.length === 0) {
        previewGrid.style.display = 'none';
        return;
    }

    selectedImages.forEach((file, idx) => {
        const reader = new FileReader();
        reader.onload = function(e) {
            const previewItem = document.createElement('div');
            previewItem.className = 'image-preview-item';
            previewItem.innerHTML = `
                <img src="${e.target.result}" alt="${file.name}" class="image-preview-thumb">
                <div class="image-preview-overlay">
                    <span class="image-preview-name">${file.name}</span>
                    <button type="button" class="btn-remove-image" onclick="removeImagePreview(${idx})">
                        ✕ Usuń
                    </button>
                </div>
            `;
            previewGrid.appendChild(previewItem);
        };
        reader.readAsDataURL(file);
    });
}

// ==========================================
// Variants Search System
// ==========================================
let variantSearchTimeout;

window.searchVariants = function(searchTerm) {
    clearTimeout(variantSearchTimeout);

    if (searchTerm.length < 2) {
        document.getElementById('variantSearchResults').style.display = 'none';
        return;
    }

    variantSearchTimeout = setTimeout(() => {
        fetch(`/api/products/search?q=${encodeURIComponent(searchTerm)}`)
            .then(response => response.json())
            .then(data => {
                console.log('API Response:', data);
                console.log('Products:', data.products);
                displayVariantSearchResults(data.products || []);
            })
            .catch(error => {
                console.error('Error searching products:', error);
            });
    }, 300);
}

function displayVariantSearchResults(products) {
    const resultsContainer = document.getElementById('variantSearchResults');
    console.log('displayVariantSearchResults called with', products.length, 'products');
    console.log('linkedVariants:', window.linkedVariants);

    if (products.length === 0) {
        resultsContainer.innerHTML = '<div class="variant-search-empty">Nie znaleziono produktów</div>';
        resultsContainer.style.display = 'block';
        return;
    }

    resultsContainer.innerHTML = '';
    let addedCount = 0;
    products.forEach(product => {
        console.log('Processing product:', product.id, product.name);

        // Skip if already linked or if it's the current product
        if (window.linkedVariants && window.linkedVariants.has(product.id)) {
            console.log('Skipping product', product.id, '- already linked');
            return;
        }

        const resultItem = document.createElement('div');
        resultItem.className = 'variant-search-result-item';
        resultItem.onclick = () => linkVariant(product);

        resultItem.innerHTML = `
            ${product.image_url ?
                `<img src="${product.image_url}" alt="${product.name}" class="variant-result-thumbnail">` :
                '<div class="variant-result-thumbnail-placeholder">📦</div>'
            }
            <div class="variant-result-info">
                <span class="variant-result-name">${product.name}</span>
                <span class="variant-result-sku">SKU: ${product.sku || '-'}</span>
            </div>
        `;

        resultsContainer.appendChild(resultItem);
        addedCount++;
        console.log('Added result item to container. Total added:', addedCount);
    });

    console.log('Total items added to container:', addedCount);
    console.log('Container children count:', resultsContainer.children.length);
    console.log('Setting display to block');
    resultsContainer.style.display = 'block';
    console.log('Container display style:', window.getComputedStyle(resultsContainer).display);
}

window.linkVariant = function(product) {
    // Add to linked variants set
    if (!window.linkedVariants) {
        window.linkedVariants = new Set();
    }
    window.linkedVariants.add(product.id);

    // Hide "no variants" message if present
    const noVariantsMessage = document.getElementById('noVariantsMessage');
    if (noVariantsMessage) {
        noVariantsMessage.style.display = 'none';
    }

    // Add to linked variants list
    const linkedList = document.getElementById('linkedVariantsList');
    const variantItem = document.createElement('div');
    variantItem.className = 'linked-variant-item';
    variantItem.setAttribute('data-variant-id', product.id);

    variantItem.innerHTML = `
        ${product.image_url ?
            `<img src="${product.image_url}" alt="${product.name}" class="variant-thumbnail">` :
            '<div class="variant-thumbnail-placeholder">📦</div>'
        }
        <div class="variant-info">
            <span class="variant-name">${product.name}</span>
            <span class="variant-sku">SKU: ${product.sku || '-'}</span>
        </div>
        <button type="button" class="btn-remove-variant" onclick="unlinkVariant(${product.id})">
            ✕
        </button>
    `;

    linkedList.appendChild(variantItem);

    // Clear search
    document.getElementById('variantSearchInput').value = '';
    document.getElementById('variantSearchResults').style.display = 'none';

    // Show variant group name input section (with animation)
    showVariantGroupNameSection();

    // Update hidden variant_group input (will be generated on server on save)
    updateVariantGroupInput();
}

function showVariantGroupNameSection() {
    const nameSection = document.getElementById('variantGroupNameSection');
    if (nameSection && nameSection.style.display === 'none') {
        nameSection.style.display = 'block';
        // Add slide-down animation
        nameSection.style.opacity = '0';
        nameSection.style.transform = 'translateY(-10px)';
        nameSection.style.transition = 'opacity 0.3s ease, transform 0.3s ease';

        setTimeout(() => {
            nameSection.style.opacity = '1';
            nameSection.style.transform = 'translateY(0)';
        }, 10);
    }
}

function hideVariantGroupNameSection() {
    const nameSection = document.getElementById('variantGroupNameSection');
    if (nameSection) {
        nameSection.style.opacity = '0';
        nameSection.style.transform = 'translateY(-10px)';

        setTimeout(() => {
            nameSection.style.display = 'none';
        }, 300);
    }
}

window.unlinkVariant = function(variantId) {
    // Remove from linked variants set
    if (window.linkedVariants) {
        window.linkedVariants.delete(variantId);
    }

    // Remove from DOM
    const variantItem = document.querySelector(`.linked-variant-item[data-variant-id="${variantId}"]`);
    if (variantItem) {
        variantItem.remove();
    }

    // Show "no variants" message if no variants left
    const linkedList = document.getElementById('linkedVariantsList');
    const variantItems = linkedList.querySelectorAll('.linked-variant-item');

    if (variantItems.length === 0) {
        let noVariantsMessage = document.getElementById('noVariantsMessage');
        if (!noVariantsMessage) {
            noVariantsMessage = document.createElement('p');
            noVariantsMessage.className = 'text-muted';
            noVariantsMessage.id = 'noVariantsMessage';
            noVariantsMessage.textContent = 'Brak powiązanych produktów';
            linkedList.appendChild(noVariantsMessage);
        }
        noVariantsMessage.style.display = 'block';

        // Hide variant group name section when all variants removed
        hideVariantGroupNameSection();
    }

    updateVariantGroupInput();
}

window.updateVariantGroupInput = function() {
    // This will be handled on server side when saving
    // We just need to pass the linked variant IDs
    const variantGroupInput = document.getElementById('variantGroupInput');
    if (variantGroupInput && window.linkedVariants) {
        // Convert Set to Array and join with commas
        variantGroupInput.value = Array.from(window.linkedVariants).join(',');
        console.log('Updated variant group input:', variantGroupInput.value);
    }
}

// ==========================================
// Variants System Initialization
// ==========================================
window.initVariantsSystem = function() {
    // Clear linkedVariants set when initializing (for modal reuse)
    linkedVariants.clear();

    // Pre-populate linkedVariants set from existing linked variants in DOM
    const linkedVariantItems = document.querySelectorAll('.linked-variant-item[data-variant-id]');
    linkedVariantItems.forEach(item => {
        const variantId = item.getAttribute('data-variant-id');
        if (variantId) {
            linkedVariants.add(parseInt(variantId));
        }
    });

    console.log('Variants system initialized. Linked variants:', Array.from(linkedVariants));
}

// Close dropdowns when clicking outside
document.addEventListener('click', function(e) {
    // Close variant search results
    const variantSearch = document.getElementById('variantSearchInput');
    const variantResults = document.getElementById('variantSearchResults');
    if (variantResults && variantSearch && !variantSearch.contains(e.target) && !variantResults.contains(e.target)) {
        variantResults.style.display = 'none';
    }
});
