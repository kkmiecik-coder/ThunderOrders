/**
 * Exclusive Page Builder
 * Handles drag & drop, auto-save, and section management
 */

let builderConfig = {
    pageId: null,
    csrfToken: null,
    pageToken: null
};

let autoSaveInterval = null;
let previewUpdateTimeout = null;
let isDirty = false;
let lastSaveTime = null;

/**
 * Initialize the builder
 */
function initExclusiveBuilder(config) {
    builderConfig = config;

    // Setup dropdown menu
    setupDropdownMenu();

    // Setup drag and drop
    setupDragAndDrop();

    // Setup checkbox toggles
    setupCheckboxToggles();

    // Setup preview header live update
    setupPreviewUpdates();

    // Setup auto-save (every 60 seconds)
    autoSaveInterval = setInterval(autoSave, 60000);

    // Mark dirty on any input change
    document.querySelectorAll('.builder-sidebar input, .builder-sidebar textarea, .section-card input, .section-card textarea, .section-card select').forEach(el => {
        el.addEventListener('change', markDirty);
        el.addEventListener('input', markDirty);
    });

    // Warn before leaving if dirty
    window.addEventListener('beforeunload', function(e) {
        if (isDirty) {
            e.preventDefault();
            e.returnValue = 'Masz niezapisane zmiany. Czy na pewno chcesz opuścić stronę?';
        }
    });

    // Initialize product dependencies management
    updateAllSetsButtons();
    updateProductDropdowns();
}

/**
 * Mark page as dirty (unsaved changes)
 */
function markDirty() {
    isDirty = true;
}

/**
 * Setup dropdown menu for adding sections
 */
function setupDropdownMenu() {
    const btn = document.getElementById('addSectionBtn');
    const menu = document.getElementById('addSectionMenu');

    if (!btn || !menu) return;

    btn.addEventListener('click', (e) => {
        e.stopPropagation();
        menu.classList.toggle('show');
    });

    document.addEventListener('click', () => {
        menu.classList.remove('show');
    });
}

/**
 * Setup drag and drop for sections
 */
function setupDragAndDrop() {
    const container = document.getElementById('sectionsContainer');
    if (!container) return;

    container.addEventListener('dragstart', handleDragStart);
    container.addEventListener('dragend', handleDragEnd);
    container.addEventListener('dragover', handleDragOver);
    container.addEventListener('drop', handleDrop);

    // Make sections draggable
    document.querySelectorAll('.section-card').forEach(section => {
        section.setAttribute('draggable', 'true');
    });
}

let draggedElement = null;

function handleDragStart(e) {
    if (!e.target.classList.contains('section-card')) return;

    draggedElement = e.target;
    e.target.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
}

function handleDragEnd(e) {
    if (draggedElement) {
        draggedElement.classList.remove('dragging');
        draggedElement = null;
    }

    document.querySelectorAll('.section-card').forEach(section => {
        section.classList.remove('drag-over');
    });

    markDirty();
}

function handleDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';

    const section = e.target.closest('.section-card');
    if (section && section !== draggedElement) {
        document.querySelectorAll('.section-card').forEach(s => s.classList.remove('drag-over'));
        section.classList.add('drag-over');
    }
}

function handleDrop(e) {
    e.preventDefault();

    const targetSection = e.target.closest('.section-card');
    if (!targetSection || !draggedElement || targetSection === draggedElement) return;

    const container = document.getElementById('sectionsContainer');
    const sections = [...container.querySelectorAll('.section-card')];
    const draggedIndex = sections.indexOf(draggedElement);
    const targetIndex = sections.indexOf(targetSection);

    if (draggedIndex < targetIndex) {
        targetSection.parentNode.insertBefore(draggedElement, targetSection.nextSibling);
    } else {
        targetSection.parentNode.insertBefore(draggedElement, targetSection);
    }

    targetSection.classList.remove('drag-over');
    markDirty();
}

/**
 * Setup live preview updates for name and description
 * Updates preview with 1 second debounce
 */
function setupPreviewUpdates() {
    const nameInput = document.getElementById('pageName');
    const descriptionInput = document.getElementById('pageDescription');
    const previewTitle = document.getElementById('previewTitle');
    const previewDescription = document.getElementById('previewDescription');

    if (!nameInput || !previewTitle) return;

    // Update preview function with debounce
    function updatePreview() {
        clearTimeout(previewUpdateTimeout);
        previewUpdateTimeout = setTimeout(() => {
            // Update title
            previewTitle.textContent = nameInput.value || '';

            // Update description
            if (previewDescription) {
                previewDescription.textContent = descriptionInput ? descriptionInput.value : '';
            }
        }, 1000); // 1 second debounce
    }

    // Listen for input events
    nameInput.addEventListener('input', updatePreview);
    if (descriptionInput) {
        descriptionInput.addEventListener('input', updatePreview);
    }
}

/**
 * Setup checkbox toggles for quantity inputs
 */
function setupCheckboxToggles() {
    document.querySelectorAll('.min-qty-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            const input = this.closest('.form-group').querySelector('.min-qty-input');
            input.disabled = !this.checked;
            if (!this.checked) input.value = '';
        });
    });

    document.querySelectorAll('.max-qty-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            const input = this.closest('.form-group').querySelector('.max-qty-input');
            input.disabled = !this.checked;
            if (!this.checked) input.value = '';
        });
    });
}

/**
 * Add a new section
 */
function addSection(type) {
    const container = document.getElementById('sectionsContainer');
    const emptyState = document.getElementById('emptySections');

    if (emptyState) {
        emptyState.style.display = 'none';
    }

    const sectionHtml = getSectionTemplate(type);
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = sectionHtml;
    const newSection = tempDiv.firstElementChild;

    container.appendChild(newSection);
    newSection.setAttribute('draggable', 'true');

    // Setup new section's checkboxes
    setupCheckboxToggles();

    // Close dropdown
    document.getElementById('addSectionMenu').classList.remove('show');

    // Update product dropdowns to reflect dependencies
    updateProductDropdowns();

    markDirty();
    showToast('Sekcja dodana', 'success');
}

/**
 * Get HTML template for a section type
 */
function getSectionTemplate(type) {
    const productOptions = document.getElementById('productOptionTemplate').innerHTML;

    const templates = {
        heading: `
            <div class="section-card" data-section-type="heading">
                <div class="section-header">
                    <div class="section-drag-handle">
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                            <path d="M7 2a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zM7 5a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zM7 8a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm-3 3a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm-3 3a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0z"/>
                        </svg>
                    </div>
                    <span class="section-type-label">Nagłówek</span>
                    <button type="button" class="btn-delete-section" onclick="deleteSection(this)">
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                            <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/>
                            <path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/>
                        </svg>
                    </button>
                </div>
                <div class="section-body">
                    <input type="text" class="form-input section-content" placeholder="Treść nagłówka H2">
                </div>
            </div>
        `,
        paragraph: `
            <div class="section-card" data-section-type="paragraph">
                <div class="section-header">
                    <div class="section-drag-handle">
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                            <path d="M7 2a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zM7 5a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zM7 8a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm-3 3a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm-3 3a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0z"/>
                        </svg>
                    </div>
                    <span class="section-type-label">Paragraf</span>
                    <button type="button" class="btn-delete-section" onclick="deleteSection(this)">
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                            <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/>
                            <path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/>
                        </svg>
                    </button>
                </div>
                <div class="section-body">
                    <textarea class="form-textarea section-content" rows="3" placeholder="Treść paragrafu"></textarea>
                </div>
            </div>
        `,
        product: `
            <div class="section-card" data-section-type="product">
                <div class="section-header">
                    <div class="section-drag-handle">
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                            <path d="M7 2a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zM7 5a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zM7 8a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm-3 3a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm-3 3a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0z"/>
                        </svg>
                    </div>
                    <span class="section-type-label">Produkt</span>
                    <button type="button" class="btn-delete-section" onclick="deleteSection(this)">
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                            <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/>
                            <path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/>
                        </svg>
                    </button>
                </div>
                <div class="section-body">
                    <div class="product-section">
                        <div class="product-selection-row">
                            <div class="product-thumbnail">
                                <div class="no-thumbnail">
                                    <svg width="24" height="24" viewBox="0 0 16 16" fill="currentColor">
                                        <path d="M6.002 5.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z"/>
                                        <path d="M2.002 1a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V3a2 2 0 0 0-2-2h-12zm12 1a1 1 0 0 1 1 1v6.5l-3.777-1.947a.5.5 0 0 0-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 0 0-.63.062L1.002 12V3a1 1 0 0 1 1-1h12z"/>
                                    </svg>
                                </div>
                            </div>
                            <div class="product-select-wrapper">
                                <label>Produkt</label>
                                <select class="form-select product-select" onchange="updateProductThumbnail(this)">
                                    <option value="">Wybierz produkt...</option>
                                    ${productOptions}
                                </select>
                            </div>
                            <div class="qty-counters-inline">
                                <div class="qty-counter-group">
                                    <span class="qty-counter-label">Max</span>
                                    <div class="qty-counter">
                                        <button type="button" class="counter-btn counter-plus" onclick="adjustMaxQty(this, 1)">+</button>
                                        <span class="counter-value" data-value="0">0</span>
                                        <button type="button" class="counter-btn counter-minus" onclick="adjustMaxQty(this, -1)">−</button>
                                    </div>
                                    <input type="hidden" class="max-qty-value" value="0">
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `,
        set: `
            <div class="section-card" data-section-type="set">
                <div class="section-header">
                    <div class="section-drag-handle">
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                            <path d="M7 2a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zM7 5a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zM7 8a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm-3 3a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm-3 3a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0z"/>
                        </svg>
                    </div>
                    <span class="section-type-label">Set produktów</span>
                    <button type="button" class="btn-delete-section" onclick="deleteSection(this)">
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                            <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/>
                            <path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/>
                        </svg>
                    </button>
                </div>
                <div class="section-body">
                    <div class="set-section">
                        <div class="set-header-row">
                            <div class="set-name-group">
                                <label class="set-name-label">Nazwa setu:</label>
                                <input type="text" class="form-input set-name" placeholder="np. Karty BTS - komplet 8 szt">
                            </div>
                            <div class="set-header-buttons">
                                <button type="button" class="btn btn-outline btn-sm btn-set-image" onclick="this.closest('.set-header-buttons').querySelector('.set-image-input').click()">
                                    <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                                        <path d="M6.002 5.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z"/>
                                        <path d="M2.002 1a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V3a2 2 0 0 0-2-2h-12zm12 1a1 1 0 0 1 1 1v6.5l-3.777-1.947a.5.5 0 0 0-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 0 0-.63.062L1.002 12V3a1 1 0 0 1 1-1h12z"/>
                                    </svg>
                                    Dodaj tło seta
                                </button>
                                <input type="file" class="set-image-input" accept="image/*" onchange="uploadSetImageNew(this)" style="display:none;">
                                <input type="hidden" class="set-image-path" value="">
                                <div class="set-add-buttons">
                                    <button type="button" class="btn btn-outline btn-sm" onclick="addSetItem(this)">
                                        + Dodaj produkt
                                    </button>
                                    <button type="button" class="btn btn-outline btn-sm" onclick="addSetVariantGroup(this)">
                                        + Dodaj grupę wariantową
                                    </button>
                                </div>
                                <div class="set-max-counter">
                                    <span class="counter-label">Max</span>
                                    <div class="counter-controls">
                                        <button type="button" class="counter-btn counter-plus" onclick="adjustSetMaxSets(this, 1)">+</button>
                                        <span class="counter-value" data-value="0">0</span>
                                        <button type="button" class="counter-btn counter-minus" onclick="adjustSetMaxSets(this, -1)">−</button>
                                    </div>
                                    <input type="hidden" class="set-max-sets" value="0">
                                </div>
                            </div>
                        </div>
                        <div class="set-image-row hidden">
                            <div class="set-image-preview has-image"></div>
                            <button type="button" class="btn-remove-set-image" onclick="removeSetImageNew(this)">
                                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                                    <path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708z"/>
                                </svg>
                            </button>
                        </div>
                        <div class="set-items">
                            <label>Składniki setu:</label>
                            <div class="set-items-list">
                                <div class="set-items-empty">
                                    <svg width="48" height="48" viewBox="0 0 16 16" fill="currentColor">
                                        <path d="M8.186 1.113a.5.5 0 0 0-.372 0L1.846 3.5l2.404.961L10.404 2l-2.218-.887zm3.564 1.426L5.596 5 8 5.961 14.154 3.5l-2.404-.961zm3.25 1.7-6.5 2.6v7.922l6.5-2.6V4.24zM7.5 14.762V6.838L1 4.239v7.923l6.5 2.6zM7.443.184a1.5 1.5 0 0 1 1.114 0l7.129 2.852A.5.5 0 0 1 16 3.5v8.662a1 1 0 0 1-.629.928l-7.185 2.874a.5.5 0 0 1-.372 0L.63 13.09a1 1 0 0 1-.63-.928V3.5a.5.5 0 0 1 .314-.464L7.443.184z"/>
                                    </svg>
                                    <p>Brak produktów w secie</p>
                                    <span>Dodaj produkty lub grupy wariantowe używając przycisków powyżej</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `,
        variant_group: `
            <div class="section-card" data-section-type="variant_group">
                <div class="section-header">
                    <div class="section-drag-handle">
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                            <path d="M7 2a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zM7 5a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zM7 8a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm-3 3a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm-3 3a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0z"/>
                        </svg>
                    </div>
                    <span class="section-type-label">Grupa wariantowa</span>
                    <button type="button" class="btn-delete-section" onclick="deleteSection(this)">
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                            <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/>
                            <path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/>
                        </svg>
                    </button>
                </div>
                <div class="section-body">
                    <div class="variant-group-section">
                        <div class="variant-group-selection-row">
                            <div class="variant-group-select-wrapper">
                                <label>Grupa wariantowa</label>
                                <select class="form-select variant-group-select" data-variant-group-id="" onchange="updateVariantGroupPreview(this)">
                                    <option value="">Wybierz grupę wariantową...</option>
                                    ${document.getElementById('variantGroupOptionTemplate')?.innerHTML || ''}
                                </select>
                            </div>
                            <div class="qty-counters-inline">
                                <div class="qty-counter-group">
                                    <span class="qty-counter-label">Max</span>
                                    <div class="qty-counter">
                                        <button type="button" class="counter-btn counter-plus" onclick="adjustMaxQty(this, 1)">+</button>
                                        <span class="counter-value" data-value="0">0</span>
                                        <button type="button" class="counter-btn counter-minus" onclick="adjustMaxQty(this, -1)">−</button>
                                    </div>
                                    <input type="hidden" class="max-qty-value" value="0">
                                </div>
                            </div>
                        </div>
                        <div class="variant-group-preview">
                            <p class="text-muted">Wybierz grupę wariantową, aby zobaczyć dostępne produkty</p>
                        </div>
                    </div>
                </div>
            </div>
        `
    };

    return templates[type] || '';
}

/**
 * Delete a section
 */
function deleteSection(btn) {
    if (!confirm('Czy na pewno chcesz usunąć tę sekcję?')) return;

    const section = btn.closest('.section-card');
    section.remove();

    // Show empty state if no sections left
    const container = document.getElementById('sectionsContainer');
    if (container.children.length === 0) {
        let emptyState = document.getElementById('emptySections');
        if (emptyState) {
            emptyState.style.display = 'block';
        }
    }

    markDirty();
    showToast('Sekcja usunięta', 'info');
}

/**
 * Add item to set
 */
function addSetItem(btn) {
    const productOptions = document.getElementById('productOptionTemplate').innerHTML;
    const setItemsList = btn.closest('.set-section').querySelector('.set-items-list');

    // Usuń pustostan jeśli istnieje
    const emptyState = setItemsList.querySelector('.set-items-empty');
    if (emptyState) {
        emptyState.remove();
    }

    const itemHtml = `
        <div class="set-item" data-item-type="product">
            <div class="set-item-thumbnail">
                <div class="no-thumbnail-sm">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                        <path d="M6.002 5.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z"/>
                        <path d="M2.002 1a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V3a2 2 0 0 0-2-2h-12zm12 1a1 1 0 0 1 1 1v6.5l-3.777-1.947a.5.5 0 0 0-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 0 0-.63.062L1.002 12V3a1 1 0 0 1 1-1h12z"/>
                    </svg>
                </div>
            </div>
            <select class="form-select set-item-product" onchange="updateSetItemThumbnail(this); updateProductDropdowns(); updateSetButtons(this.closest('.section-card[data-section-type=\\'set\\']'));">
                <option value="">Wybierz produkt...</option>
                ${productOptions}
            </select>
            <span class="set-item-badge badge-product">Produkt</span>
            <button type="button" class="btn-remove-item" onclick="removeSetItem(this)">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708z"/>
                </svg>
            </button>
        </div>
    `;

    setItemsList.insertAdjacentHTML('beforeend', itemHtml);

    // Update set buttons state
    const setSection = btn.closest('.section-card[data-section-type="set"]');
    if (setSection) {
        updateSetButtons(setSection);
    }

    // Update product dropdowns
    updateProductDropdowns();

    markDirty();
}

/**
 * Remove item from set
 */
function removeSetItem(btn) {
    // Obsługa zarówno .set-item jak i .set-item-variant-group-card
    const item = btn.closest('.set-item') || btn.closest('.set-item-variant-group-card');
    if (item) {
        const setItemsList = item.closest('.set-items-list');
        const setSection = item.closest('.section-card[data-section-type="set"]');

        item.remove();

        // Update set buttons state
        if (setSection) {
            updateSetButtons(setSection);
        }

        // Update product dropdowns
        updateProductDropdowns();

        markDirty();

        // Pokaż pustostan jeśli lista jest pusta
        const remainingItems = setItemsList.querySelectorAll('.set-item, .set-item-variant-group-card');
        if (remainingItems.length === 0) {
            setItemsList.innerHTML = `
                <div class="set-items-empty">
                    <svg width="48" height="48" viewBox="0 0 16 16" fill="currentColor">
                        <path d="M8.186 1.113a.5.5 0 0 0-.372 0L1.846 3.5l2.404.961L10.404 2l-2.218-.887zm3.564 1.426L5.596 5 8 5.961 14.154 3.5l-2.404-.961zm3.25 1.7-6.5 2.6v7.922l6.5-2.6V4.24zM7.5 14.762V6.838L1 4.239v7.923l6.5 2.6zM7.443.184a1.5 1.5 0 0 1 1.114 0l7.129 2.852A.5.5 0 0 1 16 3.5v8.662a1 1 0 0 1-.629.928l-7.185 2.874a.5.5 0 0 1-.372 0L.63 13.09a1 1 0 0 1-.63-.928V3.5a.5.5 0 0 1 .314-.464L7.443.184z"/>
                    </svg>
                    <p>Brak produktów w secie</p>
                    <span>Dodaj produkty lub grupy wariantowe używając przycisków powyżej</span>
                </div>
            `;
        }
    }
}

/**
 * Collect page data for saving
 */
function collectPageData() {
    const data = {
        name: document.getElementById('pageName').value,
        description: document.getElementById('pageDescription').value,
        starts_at: document.getElementById('startsAt').value || null,
        ends_at: document.getElementById('endsAt').value || null,
        sections: []
    };

    // Collect sections
    document.querySelectorAll('.section-card').forEach((section, index) => {
        const type = section.dataset.sectionType;
        const sectionData = {
            id: section.dataset.sectionId ? parseInt(section.dataset.sectionId) : null,
            type: type,
            sort_order: index
        };

        if (type === 'heading' || type === 'paragraph') {
            sectionData.content = section.querySelector('.section-content').value;
        } else if (type === 'product') {
            sectionData.product_id = parseInt(section.querySelector('.product-select').value) || null;
            const maxQtyInput = section.querySelector('.max-qty-value');
            const maxVal = maxQtyInput ? parseInt(maxQtyInput.value) : 0;
            sectionData.max_quantity = maxVal > 0 ? maxVal : null;
        } else if (type === 'set') {
            sectionData.set_name = section.querySelector('.set-name').value;
            sectionData.set_image = section.querySelector('.set-image-path')?.value || null;
            sectionData.set_min_sets = 1;
            const maxSetsInput = section.querySelector('.set-max-sets');
            const maxSetsVal = maxSetsInput ? parseInt(maxSetsInput.value) : 0;
            sectionData.set_max_sets = maxSetsVal > 0 ? maxSetsVal : null;
            // Also save as max_quantity for availability calculation
            sectionData.max_quantity = maxSetsVal > 0 ? maxSetsVal : null;
            sectionData.set_max_per_product = null;

            // Collect set items (products and variant groups)
            sectionData.set_items = [];
            // Wybierz zarówno .set-item jak i .set-item-variant-group-card
            section.querySelectorAll('.set-item, .set-item-variant-group-card').forEach((item) => {
                const itemType = item.dataset.itemType || 'product';

                if (itemType === 'variant_group') {
                    const variantGroupSelect = item.querySelector('.set-item-variant-group');
                    const variantGroupId = variantGroupSelect ? parseInt(variantGroupSelect.value) : null;
                    if (variantGroupId) {
                        sectionData.set_items.push({
                            variant_group_id: variantGroupId,
                            quantity_per_set: 1
                        });
                    }
                } else {
                    const productSelect = item.querySelector('.set-item-product');
                    const productId = productSelect ? parseInt(productSelect.value) : null;
                    if (productId) {
                        sectionData.set_items.push({
                            product_id: productId,
                            quantity_per_set: 1
                        });
                    }
                }
            });
        } else if (type === 'variant_group') {
            sectionData.variant_group_id = parseInt(section.querySelector('.variant-group-select').value) || null;
            const maxQtyInput = section.querySelector('.max-qty-value');
            const maxVal = maxQtyInput ? parseInt(maxQtyInput.value) : 0;
            sectionData.max_quantity = maxVal > 0 ? maxVal : null;
        }

        data.sections.push(sectionData);
    });

    return data;
}

/**
 * Save page (AJAX)
 */
async function savePage() {
    const data = collectPageData();

    try {
        const response = await fetch(`/admin/exclusive/${builderConfig.pageId}/save`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': builderConfig.csrfToken
            },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (result.success) {
            isDirty = false;
            lastSaveTime = new Date();
            document.getElementById('lastSaved').textContent = `Ostatni zapis: ${result.updated_at}`;
            showToast('Zapisano zmiany', 'success');
            return true;
        } else {
            showToast(result.error || 'Błąd zapisu', 'error');
            return false;
        }
    } catch (error) {
        console.error('Save error:', error);
        showToast('Błąd połączenia', 'error');
        return false;
    }
}

/**
 * Auto-save (called every 60 seconds)
 */
async function autoSave() {
    if (!isDirty) return;

    try {
        await savePage();
        showToast('Automatycznie zapisano', 'info');
    } catch (error) {
        console.error('Auto-save error:', error);
    }
}

/**
 * Change page status
 */
async function changeStatus(action) {
    // First save current changes
    if (isDirty) {
        const saved = await savePage();
        if (!saved) return;
    }

    try {
        const response = await fetch(`/admin/exclusive/${builderConfig.pageId}/status`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': builderConfig.csrfToken
            },
            body: JSON.stringify({ action: action })
        });

        const result = await response.json();

        if (result.success) {
            showToast(result.message, 'success');
            // Reload page to update UI
            setTimeout(() => window.location.reload(), 1000);
        } else {
            showToast(result.error || 'Błąd', 'error');
        }
    } catch (error) {
        console.error('Status change error:', error);
        showToast('Błąd połączenia', 'error');
    }
}

// Action handlers
function saveAsDraft() { savePage(); }
function saveAndSchedule() { savePage().then(() => changeStatus('schedule')); }
function publishNow() { changeStatus('publish'); }
function pauseSales() { changeStatus('pause'); }
function resumeSales() { changeStatus('resume'); }
function endSales() {
    if (confirm('Czy na pewno chcesz zakończyć sprzedaż? Ta akcja jest nieodwracalna.')) {
        changeStatus('end');
    }
}
function backToDraft() {
    if (confirm('Czy na pewno chcesz cofnąć stronę do wersji roboczej?')) {
        changeStatus('draft');
    }
}

/**
 * Copy page link to clipboard
 */
function copyPageLink() {
    const url = `${window.location.origin}/exclusive/${builderConfig.pageToken}`;
    navigator.clipboard.writeText(url).then(() => {
        showToast('Link skopiowany do schowka!', 'success');
    }).catch(err => {
        console.error('Failed to copy:', err);
        prompt('Skopiuj link:', url);
    });
}

/**
 * Show toast notification
 */
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;

    container.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 3000);
}

/**
 * Update product thumbnail when selection changes
 * @param {HTMLSelectElement} select - The product select element
 */
function updateProductThumbnail(select) {
    const selectedOption = select.options[select.selectedIndex];
    const imageUrl = selectedOption.getAttribute('data-image');
    const sectionCard = select.closest('.section-card');
    const thumbnailContainer = sectionCard.querySelector('.product-thumbnail');

    if (!thumbnailContainer) return;

    if (imageUrl) {
        thumbnailContainer.innerHTML = `<img src="${imageUrl}" alt="Produkt">`;
    } else {
        thumbnailContainer.innerHTML = `
            <div class="no-thumbnail">
                <svg width="24" height="24" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M6.002 5.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z"/>
                    <path d="M2.002 1a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V3a2 2 0 0 0-2-2h-12zm12 1a1 1 0 0 1 1 1v6.5l-3.777-1.947a.5.5 0 0 0-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 0 0-.63.062L1.002 12V3a1 1 0 0 1 1-1h12z"/>
                </svg>
            </div>
        `;
    }

    // Update product dropdowns
    updateProductDropdowns();

    markDirty();
}

/**
 * Update set item thumbnail when selection changes
 * @param {HTMLSelectElement} select - The set item product select element
 */
function updateSetItemThumbnail(select) {
    const selectedOption = select.options[select.selectedIndex];
    const imageUrl = selectedOption.getAttribute('data-image');
    const setItem = select.closest('.set-item');
    const thumbnailContainer = setItem.querySelector('.set-item-thumbnail');

    if (!thumbnailContainer) return;

    if (imageUrl) {
        thumbnailContainer.innerHTML = `<img src="${imageUrl}" alt="Produkt">`;
    } else {
        thumbnailContainer.innerHTML = `
            <div class="no-thumbnail-sm">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M6.002 5.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z"/>
                    <path d="M2.002 1a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V3a2 2 0 0 0-2-2h-12zm12 1a1 1 0 0 1 1 1v6.5l-3.777-1.947a.5.5 0 0 0-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 0 0-.63.062L1.002 12V3a1 1 0 0 1 1-1h12z"/>
                </svg>
            </div>
        `;
    }

    markDirty();
}

/**
 * Add variant group to set
 */
function addSetVariantGroup(btn) {
    const variantGroupOptions = document.getElementById('variantGroupOptionTemplate')?.innerHTML || '';
    const setItemsList = btn.closest('.set-section').querySelector('.set-items-list');

    // Usuń pustostan jeśli istnieje
    const emptyState = setItemsList.querySelector('.set-items-empty');
    if (emptyState) {
        emptyState.remove();
    }

    const itemHtml = `
        <div class="set-item-variant-group-card" data-item-type="variant_group">
            <div class="variant-group-header">
                <div class="variant-group-icon">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                        <path d="M1 2.5A1.5 1.5 0 0 1 2.5 1h3A1.5 1.5 0 0 1 7 2.5v3A1.5 1.5 0 0 1 5.5 7h-3A1.5 1.5 0 0 1 1 5.5v-3zM2.5 2a.5.5 0 0 0-.5.5v3a.5.5 0 0 0 .5.5h3a.5.5 0 0 0 .5-.5v-3a.5.5 0 0 0-.5-.5h-3zm6.5.5A1.5 1.5 0 0 1 10.5 1h3A1.5 1.5 0 0 1 15 2.5v3A1.5 1.5 0 0 1 13.5 7h-3A1.5 1.5 0 0 1 9 5.5v-3zm1.5-.5a.5.5 0 0 0-.5.5v3a.5.5 0 0 0 .5.5h3a.5.5 0 0 0 .5-.5v-3a.5.5 0 0 0-.5-.5h-3zM1 10.5A1.5 1.5 0 0 1 2.5 9h3A1.5 1.5 0 0 1 7 10.5v3A1.5 1.5 0 0 1 5.5 15h-3A1.5 1.5 0 0 1 1 13.5v-3zm1.5-.5a.5.5 0 0 0-.5.5v3a.5.5 0 0 0 .5.5h3a.5.5 0 0 0 .5-.5v-3a.5.5 0 0 0-.5-.5h-3zm6.5.5A1.5 1.5 0 0 1 10.5 9h3a1.5 1.5 0 0 1 1.5 1.5v3a1.5 1.5 0 0 1-1.5 1.5h-3A1.5 1.5 0 0 1 9 13.5v-3zm1.5-.5a.5.5 0 0 0-.5.5v3a.5.5 0 0 0 .5.5h3a.5.5 0 0 0 .5-.5v-3a.5.5 0 0 0-.5-.5h-3z"/>
                    </svg>
                </div>
                <select class="form-select variant-group-select set-item-variant-group" onchange="updateSetVariantGroupProducts(this)">
                    <option value="">Wybierz grupę...</option>
                    ${variantGroupOptions}
                </select>
                <span class="set-item-badge badge-variant">Grupa</span>
            </div>
            <div class="variant-group-products">
                <div class="variant-products-empty">Wybierz grupę wariantową</div>
            </div>
            <button type="button" class="btn-remove-item" onclick="removeSetItem(this)">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708z"/>
                </svg>
            </button>
        </div>
    `;

    setItemsList.insertAdjacentHTML('beforeend', itemHtml);

    // Update set buttons state
    const setSection = btn.closest('.section-card[data-section-type="set"]');
    if (setSection) {
        updateSetButtons(setSection);
    }

    markDirty();
}

/**
 * Update variant group products list in set item card
 */
async function updateSetVariantGroupProducts(select) {
    const card = select.closest('.set-item-variant-group-card');
    const productsContainer = card.querySelector('.variant-group-products');
    const variantGroupId = select.value;

    if (!variantGroupId) {
        productsContainer.innerHTML = '<div class="variant-products-empty">Wybierz grupę wariantową</div>';
        markDirty();
        return;
    }

    productsContainer.innerHTML = '<div class="variant-products-empty">Ładowanie...</div>';

    try {
        const response = await fetch(`/admin/exclusive/api/variant-group/${variantGroupId}`);
        const data = await response.json();

        if (data.products && data.products.length > 0) {
            let html = '';
            data.products.forEach(product => {
                html += `
                    <div class="variant-product-item">
                        ${product.image
                            ? `<img src="${product.image}" alt="${product.name}">`
                            : `<div class="no-thumb"><svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor"><path d="M6.002 5.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z"/><path d="M2.002 1a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V3a2 2 0 0 0-2-2h-12zm12 1a1 1 0 0 1 1 1v6.5l-3.777-1.947a.5.5 0 0 0-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 0 0-.63.062L1.002 12V3a1 1 0 0 1 1-1h12z"/></svg></div>`
                        }
                        <span class="product-name">${product.name}</span>
                    </div>
                `;
            });
            productsContainer.innerHTML = html;
        } else {
            productsContainer.innerHTML = '<div class="variant-products-empty">Brak produktów w grupie</div>';
        }
    } catch (error) {
        console.error('Error fetching variant group products:', error);
        productsContainer.innerHTML = '<div class="variant-products-empty">Błąd ładowania</div>';
    }

    markDirty();
}

/**
 * Upload set image (for new sections)
 */
async function uploadSetImageNew(input) {
    const file = input.files[0];
    if (!file) return;

    const setSection = input.closest('.set-section');
    const imageRow = setSection.querySelector('.set-image-row');
    const previewContainer = imageRow.querySelector('.set-image-preview');
    const hiddenInput = input.nextElementSibling;
    const imageBtn = setSection.querySelector('.btn-set-image');

    // Show loading
    imageRow.classList.remove('hidden');
    previewContainer.innerHTML = '<div class="set-image-loading">Przesyłanie...</div>';

    try {
        const formData = new FormData();
        formData.append('image', file);
        formData.append('type', 'set_image');

        const response = await fetch('/admin/exclusive/api/upload-image', {
            method: 'POST',
            headers: {
                'X-CSRFToken': builderConfig.csrfToken
            },
            body: formData
        });

        const result = await response.json();

        if (result.success) {
            previewContainer.classList.add('has-image');
            previewContainer.innerHTML = `<img src="${result.url}" alt="Tło setu">`;
            hiddenInput.value = result.path;
            // Update button text and add has-image class for purple styling
            imageBtn.classList.add('has-image');
            imageBtn.innerHTML = `
                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M6.002 5.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z"/>
                    <path d="M2.002 1a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V3a2 2 0 0 0-2-2h-12zm12 1a1 1 0 0 1 1 1v6.5l-3.777-1.947a.5.5 0 0 0-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 0 0-.63.062L1.002 12V3a1 1 0 0 1 1-1h12z"/>
                </svg>
                Zmień tło seta
            `;
            markDirty();
            showToast('Zdjęcie przesłane', 'success');
        } else {
            imageRow.classList.add('hidden');
            previewContainer.innerHTML = '';
            showToast(result.error || 'Błąd przesyłania', 'error');
        }
    } catch (error) {
        console.error('Upload error:', error);
        imageRow.classList.add('hidden');
        previewContainer.innerHTML = '';
        showToast('Błąd przesyłania pliku', 'error');
    }
}

/**
 * Remove set image (for new sections)
 */
function removeSetImageNew(btn) {
    const imageRow = btn.closest('.set-image-row');
    const setSection = btn.closest('.set-section');
    const previewContainer = imageRow.querySelector('.set-image-preview');
    const hiddenInput = setSection.querySelector('.set-image-path');
    const imageBtn = setSection.querySelector('.btn-set-image');

    // Hide the image row
    imageRow.classList.add('hidden');
    previewContainer.innerHTML = '';
    hiddenInput.value = '';

    // Reset button text and remove purple styling
    imageBtn.classList.remove('has-image');
    imageBtn.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
            <path d="M6.002 5.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z"/>
            <path d="M2.002 1a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V3a2 2 0 0 0-2-2h-12zm12 1a1 1 0 0 1 1 1v6.5l-3.777-1.947a.5.5 0 0 0-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 0 0-.63.062L1.002 12V3a1 1 0 0 1 1-1h12z"/>
        </svg>
        Dodaj tło seta
    `;
    markDirty();
}

/**
 * Remove set image (for existing sections)
 */
function removeSetImage(btn, sectionId) {
    const imageRow = document.getElementById(`setImageRow-${sectionId}`);
    const previewContainer = document.getElementById(`setImagePreview-${sectionId}`);
    const setSection = btn.closest('.set-section');
    const hiddenInput = setSection.querySelector('.set-image-path');
    const imageBtn = setSection.querySelector('.btn-set-image');

    // Hide the image row
    imageRow.classList.add('hidden');
    previewContainer.innerHTML = '';
    hiddenInput.value = '';

    // Reset button text and remove purple styling
    imageBtn.classList.remove('has-image');
    imageBtn.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
            <path d="M6.002 5.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z"/>
            <path d="M2.002 1a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V3a2 2 0 0 0-2-2h-12zm12 1a1 1 0 0 1 1 1v6.5l-3.777-1.947a.5.5 0 0 0-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 0 0-.63.062L1.002 12V3a1 1 0 0 1 1-1h12z"/>
        </svg>
        Dodaj tło seta
    `;
    markDirty();
}

/**
 * Upload set image (for existing sections)
 */
async function uploadSetImage(input, sectionId) {
    const file = input.files[0];
    if (!file) return;

    const imageRow = document.getElementById(`setImageRow-${sectionId}`);
    const previewContainer = document.getElementById(`setImagePreview-${sectionId}`);
    const hiddenInput = input.nextElementSibling;
    const setSection = input.closest('.set-section');
    const imageBtn = setSection.querySelector('.btn-set-image');

    // Show loading
    imageRow.classList.remove('hidden');
    previewContainer.innerHTML = '<div class="set-image-loading">Przesyłanie...</div>';

    try {
        const formData = new FormData();
        formData.append('image', file);
        formData.append('type', 'set_image');
        formData.append('section_id', sectionId);

        const response = await fetch('/admin/exclusive/api/upload-image', {
            method: 'POST',
            headers: {
                'X-CSRFToken': builderConfig.csrfToken
            },
            body: formData
        });

        const result = await response.json();

        if (result.success) {
            previewContainer.classList.add('has-image');
            previewContainer.innerHTML = `<img src="${result.url}" alt="Tło setu">`;
            hiddenInput.value = result.path;
            // Update button text and add has-image class for purple styling
            imageBtn.classList.add('has-image');
            imageBtn.innerHTML = `
                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M6.002 5.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z"/>
                    <path d="M2.002 1a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V3a2 2 0 0 0-2-2h-12zm12 1a1 1 0 0 1 1 1v6.5l-3.777-1.947a.5.5 0 0 0-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 0 0-.63.062L1.002 12V3a1 1 0 0 1 1-1h12z"/>
                </svg>
                Zmień tło seta
            `;
            markDirty();
            showToast('Zdjęcie przesłane', 'success');
        } else {
            showToast(result.error || 'Błąd przesyłania', 'error');
        }
    } catch (error) {
        console.error('Upload error:', error);
        showToast('Błąd przesyłania pliku', 'error');
    }
}

/**
 * Adjust max sets counter for set sections
 * @param {HTMLButtonElement} btn - The +/- button clicked
 * @param {number} delta - Amount to add (1 or -1)
 */
function adjustSetMaxSets(btn, delta) {
    const counter = btn.closest('.set-max-counter');
    const valueSpan = counter.querySelector('.counter-value');
    const hiddenInput = counter.querySelector('.set-max-sets');

    let currentValue = parseInt(valueSpan.dataset.value) || 0;
    let newValue = currentValue + delta;

    // Ensure non-negative
    if (newValue < 0) newValue = 0;

    // Update display and hidden input
    valueSpan.textContent = newValue;
    valueSpan.dataset.value = newValue;
    hiddenInput.value = newValue;

    markDirty();
}

/**
 * Adjust min quantity counter for product/variant_group sections
 * @param {HTMLButtonElement} btn - The +/- button clicked
 * @param {number} delta - Amount to add (1 or -1)
 */
function adjustMinQty(btn, delta) {
    const group = btn.closest('.qty-counter-group');
    const counter = group.querySelector('.qty-counter');
    const valueSpan = counter.querySelector('.counter-value');
    const hiddenInput = group.querySelector('.min-qty-value');

    let currentValue = parseInt(valueSpan.dataset.value) || 0;
    let newValue = currentValue + delta;

    // Ensure non-negative
    if (newValue < 0) newValue = 0;

    // Update display and hidden input
    valueSpan.textContent = newValue;
    valueSpan.dataset.value = newValue;
    hiddenInput.value = newValue;

    markDirty();
}

/**
 * Adjust max quantity counter for product/variant_group sections
 * @param {HTMLButtonElement} btn - The +/- button clicked
 * @param {number} delta - Amount to add (1 or -1)
 */
function adjustMaxQty(btn, delta) {
    const group = btn.closest('.qty-counter-group');
    const counter = group.querySelector('.qty-counter');
    const valueSpan = counter.querySelector('.counter-value');
    const hiddenInput = group.querySelector('.max-qty-value');

    let currentValue = parseInt(valueSpan.dataset.value) || 0;
    let newValue = currentValue + delta;

    // Ensure non-negative
    if (newValue < 0) newValue = 0;

    // Update display and hidden input
    valueSpan.textContent = newValue;
    valueSpan.dataset.value = newValue;
    hiddenInput.value = newValue;

    markDirty();
}

/**
 * Update variant group preview when selection changes
 * @param {HTMLSelectElement} select - The variant group select element
 */
async function updateVariantGroupPreview(select) {
    const sectionCard = select.closest('.section-card');
    const previewContainer = sectionCard.querySelector('.variant-group-preview');
    const variantGroupId = select.value;

    if (!variantGroupId) {
        previewContainer.innerHTML = '<p class="text-muted">Wybierz grupę wariantową, aby zobaczyć dostępne produkty</p>';
        select.setAttribute('data-variant-group-id', '');
        markDirty();
        return;
    }

    // Show loading
    previewContainer.innerHTML = '<p class="text-muted">Ładowanie produktów...</p>';

    try {
        const response = await fetch(`/admin/exclusive/api/variant-groups`);
        const variantGroups = await response.json();

        // Find selected group
        const selectedGroup = variantGroups.find(vg => vg.id == variantGroupId);

        if (!selectedGroup || !selectedGroup.products || selectedGroup.products.length === 0) {
            previewContainer.innerHTML = '<p class="text-muted">Brak produktów w tej grupie wariantowej</p>';
            return;
        }

        // Render products grid
        let html = '<div class="variant-products-grid">';
        selectedGroup.products.forEach(product => {
            html += `
                <div class="variant-product-item">
                    <div class="variant-product-thumb">
                        ${product.image
                            ? `<img src="${product.image}" alt="${product.name}">`
                            : `<div class="no-thumbnail-sm">
                                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                                    <path d="M6.002 5.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z"/>
                                    <path d="M2.002 1a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V3a2 2 0 0 0-2-2h-12zm12 1a1 1 0 0 1 1 1v6.5l-3.777-1.947a.5.5 0 0 0-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 0 0-.63.062L1.002 12V3a1 1 0 0 1 1-1h12z"/>
                                </svg>
                               </div>`
                        }
                    </div>
                    <div class="variant-product-info">
                        <span class="variant-product-name">${product.name}</span>
                        <span class="variant-product-price">${product.price.toFixed(2)} PLN</span>
                    </div>
                </div>
            `;
        });
        html += '</div>';
        html += `<p class="variant-group-count">${selectedGroup.products.length} produktów w grupie</p>`;

        previewContainer.innerHTML = html;
        select.setAttribute('data-variant-group-id', variantGroupId);

    } catch (error) {
        console.error('Error fetching variant group:', error);
        previewContainer.innerHTML = '<p class="text-error">Błąd ładowania produktów</p>';
    }

    markDirty();
}

/**
 * ========================================
 * Product Dependencies Management
 * ========================================
 */

/**
 * Get all selected product IDs across all sections
 * @returns {Object} Object with productSections (array) and setProducts (object)
 */
function getAllSelectedProducts() {
    const result = {
        productSections: [], // Product IDs from "Produkt" sections
        setProducts: {}      // Set ID -> array of product IDs
    };

    // Get products from "Produkt" sections
    document.querySelectorAll('.section-card[data-section-type="product"]').forEach(section => {
        const select = section.querySelector('.product-select');
        const productId = select ? parseInt(select.value) : null;
        if (productId) {
            result.productSections.push(productId);
        }
    });

    // Get products from "Set" sections
    document.querySelectorAll('.section-card[data-section-type="set"]').forEach(section => {
        const setId = section.dataset.sectionId || section.getAttribute('data-temp-id') || Math.random().toString();
        result.setProducts[setId] = [];

        section.querySelectorAll('.set-item[data-item-type="product"]').forEach(item => {
            const select = item.querySelector('.set-item-product');
            const productId = select ? parseInt(select.value) : null;
            if (productId) {
                result.setProducts[setId].push(productId);
            }
        });
    });

    return result;
}

/**
 * Update all product dropdowns to hide/show options based on selections
 */
function updateProductDropdowns() {
    const selected = getAllSelectedProducts();

    // Update "Produkt" section dropdowns
    document.querySelectorAll('.section-card[data-section-type="product"]').forEach(section => {
        const select = section.querySelector('.product-select');
        if (!select) return;

        const currentValue = select.value;
        const options = select.querySelectorAll('option');

        options.forEach(option => {
            const productId = parseInt(option.value);
            if (!productId) return; // Skip empty option

            // Hide if selected in another "Produkt" section
            if (selected.productSections.includes(productId) && productId !== parseInt(currentValue)) {
                option.disabled = true;
                option.style.display = 'none';
            } else {
                option.disabled = false;
                option.style.display = '';
            }
        });
    });

    // Update "Set" section product dropdowns
    document.querySelectorAll('.section-card[data-section-type="set"]').forEach(section => {
        const setId = section.dataset.sectionId || section.getAttribute('data-temp-id') || Math.random().toString();
        const setProductIds = selected.setProducts[setId] || [];

        section.querySelectorAll('.set-item[data-item-type="product"]').forEach(item => {
            const select = item.querySelector('.set-item-product');
            if (!select) return;

            const currentValue = select.value;
            const options = select.querySelectorAll('option');

            options.forEach(option => {
                const productId = parseInt(option.value);
                if (!productId) return; // Skip empty option

                // Hide if selected in this set
                if (setProductIds.includes(productId) && productId !== parseInt(currentValue)) {
                    option.disabled = true;
                    option.style.display = 'none';
                } else {
                    option.disabled = false;
                    option.style.display = '';
                }
            });
        });
    });
}

/**
 * Check if set has variant group added
 * @param {HTMLElement} setSection - The set section element
 * @returns {boolean}
 */
function setHasVariantGroup(setSection) {
    return setSection.querySelector('.set-item-variant-group-card') !== null;
}

/**
 * Check if set has products added
 * @param {HTMLElement} setSection - The set section element
 * @returns {boolean}
 */
function setHasProducts(setSection) {
    return setSection.querySelector('.set-item[data-item-type="product"]') !== null;
}

/**
 * Update set buttons state (enable/disable based on content)
 * @param {HTMLElement} setSection - The set section element
 */
function updateSetButtons(setSection) {
    const addProductBtn = setSection.querySelector('[onclick*="addSetItem"]');
    const addVariantGroupBtn = setSection.querySelector('[onclick*="addSetVariantGroup"]');

    if (!addProductBtn || !addVariantGroupBtn) return;

    const hasVariantGroup = setHasVariantGroup(setSection);
    const hasProducts = setHasProducts(setSection);

    if (hasVariantGroup) {
        // Disable both buttons if variant group is added
        addProductBtn.disabled = true;
        addVariantGroupBtn.disabled = true;
        addProductBtn.style.opacity = '0.5';
        addVariantGroupBtn.style.opacity = '0.5';
        addProductBtn.style.cursor = 'not-allowed';
        addVariantGroupBtn.style.cursor = 'not-allowed';
    } else if (hasProducts) {
        // If products added, disable only variant group button
        addProductBtn.disabled = false;
        addVariantGroupBtn.disabled = true;
        addProductBtn.style.opacity = '1';
        addVariantGroupBtn.style.opacity = '0.5';
        addProductBtn.style.cursor = 'pointer';
        addVariantGroupBtn.style.cursor = 'not-allowed';
    } else {
        // Enable both if nothing is added
        addProductBtn.disabled = false;
        addVariantGroupBtn.disabled = false;
        addProductBtn.style.opacity = '1';
        addVariantGroupBtn.style.opacity = '1';
        addProductBtn.style.cursor = 'pointer';
        addVariantGroupBtn.style.cursor = 'pointer';
    }
}

/**
 * Update all sets buttons state
 */
function updateAllSetsButtons() {
    document.querySelectorAll('.section-card[data-section-type="set"]').forEach(setSection => {
        updateSetButtons(setSection);
    });
}
