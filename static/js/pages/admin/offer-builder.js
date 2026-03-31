/**
 * Offer Page Builder
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
function initOfferBuilder(config) {
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

    // Initialize auto-increase form
    initializeAutoIncreaseForm();

    // Setup payment stages toggle
    setupPaymentStagesToggle();
}

/**
 * Mark page as dirty (unsaved changes)
 */
function markDirty() {
    isDirty = true;
}

/**
 * Setup payment stages toggle (Proxy left / Polska right)
 * Proxy = 4 platnosci (unchecked/left), Polska = 3 platnosci (checked/right)
 */
function setupPaymentStagesToggle() {
    const toggle = document.getElementById('paymentStagesToggle');
    const hiddenInput = document.getElementById('paymentStages');
    const labelProxy = document.getElementById('labelProxy');
    const labelPolska = document.getElementById('labelPolska');

    if (!toggle || !hiddenInput) return;

    function updateActiveLabel() {
        if (toggle.checked) {
            // Polska (right) = 3
            if (labelProxy) labelProxy.classList.remove('active');
            if (labelPolska) labelPolska.classList.add('active');
        } else {
            // Proxy (left) = 4
            if (labelProxy) labelProxy.classList.add('active');
            if (labelPolska) labelPolska.classList.remove('active');
        }
    }

    toggle.addEventListener('change', function() {
        hiddenInput.value = this.checked ? 3 : 4;
        updateActiveLabel();
        markDirty();
    });

    // Initial state
    updateActiveLabel();
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
                        <!-- Top row - 4 columns: Nazwa | Tło button | Dodaj buttons (vertical) | Max counter -->
                        <div class="set-header-row">
                            <!-- Column 1: Nazwa setu -->
                            <div class="set-name-col">
                                <label class="set-name-label">Nazwa setu: <span style="color: red;">*</span></label>
                                <input type="text" class="form-input set-name" placeholder="np. Karty BTS - komplet 8 szt" required>
                            </div>

                            <!-- Column 2: Dodaj tło setu button -->
                            <div class="set-image-button-col">
                                <button type="button" class="btn btn-outline btn-sm btn-set-image" onclick="this.closest('.set-section').querySelector('.set-image-input').click()">
                                    <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                                        <path d="M6.002 5.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z"/>
                                        <path d="M2.002 1a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V3a2 2 0 0 0-2-2h-12zm12 1a1 1 0 0 1 1 1v6.5l-3.777-1.947a.5.5 0 0 0-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 0 0-.63.062L1.002 12V3a1 1 0 0 1 1-1h12z"/>
                                    </svg>
                                    Dodaj tło setu
                                </button>
                                <input type="file" class="set-image-input" accept="image/*" onchange="uploadSetImageNew(this)" style="display:none;">
                                <input type="hidden" class="set-image-path" value="">
                            </div>

                            <!-- Column 3: Dodaj produkt / Dodaj grupę (stacked vertically) -->
                            <div class="set-add-buttons-col">
                                <button type="button" class="btn btn-outline btn-sm" onclick="addSetItem(this)">
                                    + Dodaj produkt
                                </button>
                                <button type="button" class="btn btn-outline btn-sm" onclick="addSetVariantGroup(this)">
                                    + Dodaj grupę wariantową
                                </button>
                            </div>

                            <!-- Column 4: Max counter -->
                            <div class="qty-counter-group">
                                <span class="qty-counter-label">Max</span>
                                <div class="qty-counter">
                                    <button type="button" class="counter-btn counter-plus" onclick="adjustSetMaxSets(this, 1)">+</button>
                                    <span class="counter-value" data-value="0">0</span>
                                    <button type="button" class="counter-btn counter-minus" onclick="adjustSetMaxSets(this, -1)">−</button>
                                </div>
                                <input type="hidden" class="set-max-sets" value="0">
                            </div>
                        </div>

                        <!-- Separator -->
                        <hr class="set-separator">

                        <!-- Image preview section (full width, max 300px height, hidden by default) -->
                        <div class="set-image-preview-section hidden">
                            <div class="set-image-preview-wrapper">
                                <img class="set-image-preview" src="" alt="Tło seta">
                                <button type="button" class="btn-remove-set-image" onclick="removeSetImageNew(this)">
                                    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                                        <path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708z"/>
                                    </svg>
                                </button>
                            </div>
                        </div>

                        <!-- Bottom row - 70/30 split -->
                        <div class="set-bottom-row">
                            <!-- Left column 70%: Elementy setu -->
                            <div class="set-items-col">
                                <div class="set-items">
                                    <label>
                                        Elementy setu (pojedyncze produkty) <span style="color: red;">*</span>
                                        <small style="opacity: 0.7; display: block; margin-top: 4px;">Produkty widoczne na liście w secie</small>
                                    </label>
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

                            <!-- Right column 30%: Produkt-komplet -->
                            <div class="set-product-selection" style="display: none;">
                                <label>
                                    Produkt - komplet setu <span style="color: red;">*</span>
                                    <small style="opacity: 0.7; display: block; margin-top: 4px;">Dodawany przez "KUP PEŁNY SET"</small>
                                </label>
                                <div class="custom-select-wrapper">
                                    <select class="form-select set-product-select" onchange="markDirty(); updateSetProductPreview(this)">
                                        <option value="">Wybierz produkt...</option>
                                        ${productOptions}
                                    </select>
                                    <div class="custom-select-display">
                                        <span class="selected-text">Wybierz produkt...</span>
                                        <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
                                            <path d="M1.646 4.646a.5.5 0 0 1 .708 0L8 10.293l5.646-5.647a.5.5 0 0 1 .708.708l-6 6a.5.5 0 0 1-.708 0l-6-6a.5.5 0 0 1 0-.708z"/>
                                        </svg>
                                    </div>
                                </div>
                                <!-- Preview card (hidden by default, shown when product selected) -->
                                <div class="set-product-preview-card" style="display: none;">
                                    <div class="set-product-preview-image">
                                        <img src="" alt="">
                                    </div>
                                    <div class="set-product-preview-info">
                                        <span class="set-product-preview-name"></span>
                                        <span class="set-product-preview-price"></span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- ========== GRATISY (BONUSY) ========== -->
                        <hr class="set-separator">
                        <div class="set-bonuses-section">
                            <div class="set-bonuses-header">
                                <div class="set-bonuses-title">
                                    <svg class="set-bonuses-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                        <polyline points="20 12 20 22 4 22 4 12"></polyline>
                                        <rect x="2" y="7" width="20" height="5"></rect>
                                        <line x1="12" y1="22" x2="12" y2="7"></line>
                                        <path d="M12 7H7.5a2.5 2.5 0 0 1 0-5C11 2 12 7 12 7z"></path>
                                        <path d="M12 7h4.5a2.5 2.5 0 0 0 0-5C13 2 12 7 12 7z"></path>
                                    </svg>
                                    <div>
                                        <span class="set-bonuses-label">Gratisy</span>
                                        <small class="set-bonuses-desc">Darmowe produkty dodawane do zamówień po spełnieniu warunków</small>
                                    </div>
                                </div>
                                <button type="button" class="btn-add-bonus" onclick="addSetBonus(this)">
                                    <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                                        <path d="M8 4a.5.5 0 0 1 .5.5v3h3a.5.5 0 0 1 0 1h-3v3a.5.5 0 0 1-1 0v-3h-3a.5.5 0 0 1 0-1h3v-3A.5.5 0 0 1 8 4z"/>
                                    </svg>
                                    Dodaj gratis
                                </button>
                            </div>
                            <div class="set-bonuses-list">
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `,
        bonus: `
            <div class="section-card" data-section-type="bonus">
                <div class="section-header">
                    <div class="section-drag-handle">
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                            <path d="M7 2a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zM7 5a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zM7 8a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm-3 3a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm-3 3a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0z"/>
                        </svg>
                    </div>
                    <span class="section-type-label">Bonus (gratis)</span>
                    <button type="button" class="btn-delete-section" onclick="deleteSection(this)">
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                            <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/>
                            <path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/>
                        </svg>
                    </button>
                </div>
                <div class="section-body">
                    <div class="standalone-bonus-section">
                        <div class="bonus-columns">
                            <div class="bonus-col bonus-col-left">
                                <div class="bonus-block-label">Warunek</div>
                                <div class="bonus-field">
                                    <label>Typ warunku</label>
                                    <select class="form-select bonus-trigger-type" onchange="toggleBonusTriggerFields(this); markDirty()">
                                        <option value="buy_products">Kup produkty</option>
                                        <option value="price_threshold">Próg kwoty</option>
                                        <option value="quantity_threshold">Próg ilości</option>
                                    </select>
                                </div>
                                <div class="bonus-field bonus-threshold-row" style="display: none;">
                                    <label>Wartość progu</label>
                                    <input type="number" class="form-input bonus-threshold-value" step="0.01" min="0" onchange="markDirty()">
                                </div>
                                <div class="bonus-required-products">
                                    <label>Wymagane produkty <small>(wszystkie)</small></label>
                                    <div class="bonus-required-list"></div>
                                    <button type="button" class="btn-add-req-product" onclick="addBonusRequiredProduct(this)">+ Dodaj wymagany produkt</button>
                                </div>
                            </div>
                            <div class="bonus-col bonus-col-right">
                                <div class="bonus-block-label">Nagroda</div>
                                <div class="bonus-field">
                                    <label>Produkt gratisowy <span style="color: red;">*</span></label>
                                    <div class="bonus-product-search-wrapper">
                                        <input type="text" class="form-input bonus-product-search"
                                               placeholder="Szukaj produktu (nazwa lub SKU)..."
                                               oninput="searchBonusProduct(this)"
                                               onfocus="searchBonusProduct(this)"
                                               autocomplete="off">
                                        <input type="hidden" class="bonus-product-id" value="">
                                    </div>
                                </div>
                                <div class="bonus-field-row">
                                    <div class="bonus-field bonus-field-wide">
                                        <label>Ilość</label>
                                        <input type="number" class="form-input bonus-quantity" value="1" min="1" onchange="markDirty()">
                                    </div>
                                    <div class="bonus-field bonus-field-wide">
                                        <label>Limit</label>
                                        <input type="number" class="form-input bonus-max-available" min="1" placeholder="Bez" onchange="markDirty()">
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="bonus-options-row">
                            <label class="bonus-option">
                                <input type="checkbox" class="bonus-repeatable" onchange="markDirty()">
                                Wielokrotny próg
                            </label>
                            <div class="bonus-option">
                                <label>Po wyczerpaniu:</label>
                                <select class="form-select bonus-when-exhausted" onchange="markDirty()">
                                    <option value="hide">Ukryj</option>
                                    <option value="show_exhausted">Pokaż jako wyczerpany</option>
                                </select>
                            </div>
                            <label class="bonus-option">
                                <input type="checkbox" class="bonus-is-active" checked onchange="markDirty()">
                                Aktywny
                            </label>
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

        // Ukryj pole "Produkt - komplet setu" jeśli nie ma grup wariantowych
        if (setSection) {
            const hasVariantGroups = setSection.querySelectorAll('.set-item-variant-group-card').length > 0;
            const setProductSelection = setSection.querySelector('.set-product-selection');
            if (setProductSelection) {
                setProductSelection.style.display = hasVariantGroups ? 'block' : 'none';
            }
        }
    }
}

/**
 * Collect page data for saving
 */
function collectPageData() {
    const paymentStagesInput = document.getElementById('paymentStages');
    const data = {
        name: document.getElementById('pageName').value,
        description: document.getElementById('pageDescription').value,
        starts_at: document.getElementById('startsAt').value || null,
        ends_at: document.getElementById('endsAt').value || null,
        payment_stages: paymentStagesInput ? parseInt(paymentStagesInput.value) || 4 : 4,
        notify_clients_on_publish: document.getElementById('notifyClientsOnPublish')?.checked || false,
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
            const maxSetsInput = section.querySelector('.set-max-sets');
            const maxSetsVal = maxSetsInput ? parseInt(maxSetsInput.value) : 0;
            sectionData.set_max_sets = maxSetsVal > 0 ? maxSetsVal : null;
            // Also save as max_quantity for availability calculation
            sectionData.max_quantity = maxSetsVal > 0 ? maxSetsVal : null;
            sectionData.set_max_per_product = null;

            // NOWE: Zbierz set_product_id (produkt-komplet)
            const setProductSelect = section.querySelector('.set-product-select');
            sectionData.set_product_id = setProductSelect ? (parseInt(setProductSelect.value) || null) : null;

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

            // Collect bonuses (gratisy)
            sectionData.bonuses = [];
            section.querySelectorAll('.set-bonus-item').forEach((bonusEl) => {
                const triggerType = bonusEl.querySelector('.bonus-trigger-type')?.value;
                const bonusProductId = parseInt(bonusEl.querySelector('.bonus-product-id')?.value) || null;
                if (!bonusProductId) return;

                const bonusData = {
                    trigger_type: triggerType,
                    threshold_value: parseFloat(bonusEl.querySelector('.bonus-threshold-value')?.value) || null,
                    bonus_product_id: bonusProductId,
                    bonus_quantity: parseInt(bonusEl.querySelector('.bonus-quantity')?.value) || 1,
                    max_available: parseInt(bonusEl.querySelector('.bonus-max-available')?.value) || null,
                    when_exhausted: bonusEl.querySelector('.bonus-when-exhausted')?.value || 'hide',
                    count_full_set: bonusEl.querySelector('.bonus-count-full-set')?.checked || false,
                    repeatable: bonusEl.querySelector('.bonus-repeatable')?.checked || false,
                    is_active: bonusEl.querySelector('.bonus-is-active')?.checked ?? true,
                    required_products: [],
                };

                if (triggerType === 'buy_products') {
                    bonusEl.querySelectorAll('.bonus-required-item').forEach((rpEl) => {
                        const rpProductId = parseInt(rpEl.querySelector('.bonus-req-product')?.value) || null;
                        if (rpProductId) {
                            bonusData.required_products.push({
                                product_id: rpProductId,
                                min_quantity: parseInt(rpEl.querySelector('.bonus-req-min-qty')?.value) || 1,
                            });
                        }
                    });
                }

                sectionData.bonuses.push(bonusData);
            });
        } else if (type === 'variant_group') {
            sectionData.variant_group_id = parseInt(section.querySelector('.variant-group-select').value) || null;
            const maxQtyInput = section.querySelector('.max-qty-value');
            const maxVal = maxQtyInput ? parseInt(maxQtyInput.value) : 0;
            sectionData.max_quantity = maxVal > 0 ? maxVal : null;
        } else if (type === 'bonus') {
            sectionData.bonus_trigger_type = section.querySelector('.bonus-trigger-type')?.value || 'buy_products';
            sectionData.bonus_threshold_value = parseFloat(section.querySelector('.bonus-threshold-value')?.value) || null;
            sectionData.bonus_product_id = parseInt(section.querySelector('.bonus-product-id')?.value) || null;
            sectionData.bonus_quantity = parseInt(section.querySelector('.bonus-quantity')?.value) || 1;
            sectionData.bonus_max_available = parseInt(section.querySelector('.bonus-max-available')?.value) || null;
            sectionData.bonus_when_exhausted = section.querySelector('.bonus-when-exhausted')?.value || 'hide';
            sectionData.bonus_repeatable = section.querySelector('.bonus-repeatable')?.checked || false;
            sectionData.bonus_is_active = section.querySelector('.bonus-is-active')?.checked ?? true;

            // Required products (for buy_products trigger)
            sectionData.bonus_required_products = [];
            section.querySelectorAll('.bonus-required-item').forEach((rpEl) => {
                const rpProductId = parseInt(rpEl.querySelector('.bonus-req-product')?.value) || null;
                if (rpProductId) {
                    sectionData.bonus_required_products.push({
                        product_id: rpProductId,
                        min_quantity: parseInt(rpEl.querySelector('.bonus-req-min-qty')?.value) || 1,
                    });
                }
            });
        }

        data.sections.push(sectionData);
    });

    return data;
}

/**
 * Validate page data before saving
 */
function validatePageData(data) {
    // Check all set sections have a name
    const setSections = document.querySelectorAll('.section-card[data-section-type="set"]');
    for (let section of setSections) {
        const setNameInput = section.querySelector('.set-name');
        const setName = setNameInput ? setNameInput.value.trim() : '';

        if (!setName) {
            // Highlight the input
            setNameInput.classList.add('input-error');
            setNameInput.focus();

            // Scroll to the section
            section.scrollIntoView({ behavior: 'smooth', block: 'center' });

            showToast('Nazwa setu jest wymagana', 'error');

            // Remove error class after 3 seconds
            setTimeout(() => setNameInput.classList.remove('input-error'), 3000);

            return false;
        }
    }

    return true;
}

/**
 * Save page (AJAX)
 */
async function savePage() {
    const data = collectPageData();

    // Validate before saving
    if (!validatePageData(data)) {
        return false;
    }

    try {
        const response = await fetch(`/admin/offers/${builderConfig.pageId}/save`, {
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
        const response = await fetch(`/admin/offers/${builderConfig.pageId}/status`, {
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
    const url = `${window.location.origin}/offer/${builderConfig.pageToken}`;
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

        // Pokaż pole "Produkt - komplet setu" po dodaniu grupy wariantowej
        const setProductSelection = setSection.querySelector('.set-product-selection');
        if (setProductSelection) {
            setProductSelection.style.display = 'block';
        }
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
        const response = await fetch(`/admin/offers/api/variant-group/${variantGroupId}`);
        const data = await response.json();

        if (data.products && data.products.length > 0) {
            let html = '<div class="variant-products-grid">';
            data.products.forEach(product => {
                html += `
                    <div class="variant-product-card">
                        <div class="variant-product-image">
                            ${product.image
                                ? `<img src="${product.image}" alt="${product.name}">`
                                : `<div class="no-thumb"><svg width="20" height="20" viewBox="0 0 16 16" fill="currentColor"><path d="M6.002 5.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z"/><path d="M2.002 1a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V3a2 2 0 0 0-2-2h-12zm12 1a1 1 0 0 1 1 1v6.5l-3.777-1.947a.5.5 0 0 0-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 0 0-.63.062L1.002 12V3a1 1 0 0 1 1-1h12z"/></svg></div>`
                            }
                        </div>
                        <div class="variant-product-info">
                            <span class="variant-product-name">${product.name}</span>
                            <span class="variant-product-price">${parseFloat(product.price).toFixed(2)} PLN</span>
                        </div>
                    </div>
                `;
            });
            html += '</div>';
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
    const imagePreviewSection = setSection.querySelector('.set-image-preview-section');
    const previewImg = imagePreviewSection.querySelector('.set-image-preview');
    const hiddenInput = input.nextElementSibling;
    const imageBtn = setSection.querySelector('.btn-set-image');

    // Show loading
    imagePreviewSection.classList.remove('hidden');
    previewImg.src = '';
    previewImg.alt = 'Ładowanie...';

    try {
        const formData = new FormData();
        formData.append('image', file);
        formData.append('type', 'set_image');

        const response = await fetch('/admin/offers/api/upload-image', {
            method: 'POST',
            headers: {
                'X-CSRFToken': builderConfig.csrfToken
            },
            body: formData
        });

        const result = await response.json();

        if (result.success) {
            previewImg.src = result.url;
            previewImg.alt = 'Tło seta';
            hiddenInput.value = result.path;
            // Update button text and add has-image class for purple styling
            imageBtn.classList.add('has-image');
            imageBtn.innerHTML = `
                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M6.002 5.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z"/>
                    <path d="M2.002 1a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V3a2 2 0 0 0-2-2h-12zm12 1a1 1 0 0 1 1 1v6.5l-3.777-1.947a.5.5 0 0 0-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 0 0-.63.062L1.002 12V3a1 1 0 0 1 1-1h12z"/>
                </svg>
                Zmień tło setu
            `;
            markDirty();
            showToast('Zdjęcie przesłane', 'success');
        } else {
            imagePreviewSection.classList.add('hidden');
            previewImg.src = '';
            showToast(result.error || 'Błąd przesyłania', 'error');
        }
    } catch (error) {
        console.error('Upload error:', error);
        imagePreviewSection.classList.add('hidden');
        previewImg.src = '';
        showToast('Błąd przesyłania pliku', 'error');
    }
}

/**
 * Remove set image (for new sections)
 */
function removeSetImageNew(btn) {
    const imagePreviewSection = btn.closest('.set-image-preview-section');
    const setSection = btn.closest('.set-section');
    const previewImg = imagePreviewSection.querySelector('.set-image-preview');
    const hiddenInput = setSection.querySelector('.set-image-path');
    const imageBtn = setSection.querySelector('.btn-set-image');

    // Hide the image preview section
    imagePreviewSection.classList.add('hidden');
    previewImg.src = '';
    hiddenInput.value = '';

    // Reset button text and remove purple styling
    imageBtn.classList.remove('has-image');
    imageBtn.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
            <path d="M6.002 5.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z"/>
            <path d="M2.002 1a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V3a2 2 0 0 0-2-2h-12zm12 1a1 1 0 0 1 1 1v6.5l-3.777-1.947a.5.5 0 0 0-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 0 0-.63.062L1.002 12V3a1 1 0 0 1 1-1h12z"/>
        </svg>
        Dodaj tło setu
    `;
    markDirty();
}

/**
 * Remove set image (for existing sections)
 */
function removeSetImage(btn, sectionId) {
    const imagePreviewSection = document.getElementById(`setImagePreviewSection-${sectionId}`);
    const previewImg = document.getElementById(`setImagePreview-${sectionId}`);
    const setSection = btn.closest('.set-section');
    const hiddenInput = setSection.querySelector('.set-image-path');
    const imageBtn = setSection.querySelector('.btn-set-image');

    // Hide the image preview section
    imagePreviewSection.classList.add('hidden');
    previewImg.src = '';
    hiddenInput.value = '';

    // Reset button text and remove purple styling
    imageBtn.classList.remove('has-image');
    imageBtn.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
            <path d="M6.002 5.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z"/>
            <path d="M2.002 1a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V3a2 2 0 0 0-2-2h-12zm12 1a1 1 0 0 1 1 1v6.5l-3.777-1.947a.5.5 0 0 0-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 0 0-.63.062L1.002 12V3a1 1 0 0 1 1-1h12z"/>
        </svg>
        Dodaj tło setu
    `;
    markDirty();
}

/**
 * Upload set image (for existing sections)
 */
async function uploadSetImage(input, sectionId) {
    const file = input.files[0];
    if (!file) return;

    const imagePreviewSection = document.getElementById(`setImagePreviewSection-${sectionId}`);
    const previewImg = document.getElementById(`setImagePreview-${sectionId}`);
    const hiddenInput = input.nextElementSibling;
    const setSection = input.closest('.set-section');
    const imageBtn = setSection.querySelector('.btn-set-image');

    // Show loading
    imagePreviewSection.classList.remove('hidden');
    previewImg.src = '';
    previewImg.alt = 'Ładowanie...';

    try {
        const formData = new FormData();
        formData.append('image', file);
        formData.append('type', 'set_image');
        formData.append('section_id', sectionId);

        const response = await fetch('/admin/offers/api/upload-image', {
            method: 'POST',
            headers: {
                'X-CSRFToken': builderConfig.csrfToken
            },
            body: formData
        });

        const result = await response.json();

        if (result.success) {
            previewImg.src = result.url;
            previewImg.alt = 'Tło seta';
            hiddenInput.value = result.path;
            // Update button text and add has-image class for purple styling
            imageBtn.classList.add('has-image');
            imageBtn.innerHTML = `
                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M6.002 5.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z"/>
                    <path d="M2.002 1a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V3a2 2 0 0 0-2-2h-12zm12 1a1 1 0 0 1 1 1v6.5l-3.777-1.947a.5.5 0 0 0-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 0 0-.63.062L1.002 12V3a1 1 0 0 1 1-1h12z"/>
                </svg>
                Zmień tło setu
            `;
            markDirty();
            showToast('Zdjęcie przesłane', 'success');
        } else {
            imagePreviewSection.classList.add('hidden');
            previewImg.src = '';
            showToast(result.error || 'Błąd przesyłania', 'error');
        }
    } catch (error) {
        console.error('Upload error:', error);
        imagePreviewSection.classList.add('hidden');
        previewImg.src = '';
        showToast('Błąd przesyłania pliku', 'error');
    }
}

/**
 * Adjust max sets counter for set sections
 * @param {HTMLButtonElement} btn - The +/- button clicked
 * @param {number} delta - Amount to add (1 or -1)
 */
function adjustSetMaxSets(btn, delta) {
    const counterGroup = btn.closest('.qty-counter-group');
    const valueSpan = counterGroup.querySelector('.counter-value');
    const hiddenInput = counterGroup.querySelector('.set-max-sets');

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
        const response = await fetch(`/admin/offers/api/variant-groups`);
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

/**
 * Update custom select display
 */
function updateCustomSelect(select) {
    const wrapper = select.closest('.custom-select-wrapper');
    if (!wrapper) return;

    const display = wrapper.querySelector('.custom-select-display .selected-text');
    if (!display) return;

    const selectedOption = select.options[select.selectedIndex];
    display.textContent = selectedOption ? selectedOption.text : 'Set produktów';
}

/**
 * Update set product preview card when product is selected
 */
function updateSetProductPreview(select) {
    const selectedOption = select.options[select.selectedIndex];
    const productSelection = select.closest('.set-product-selection');

    if (!productSelection) return;

    const previewCard = productSelection.querySelector('.set-product-preview-card');
    const display = productSelection.querySelector('.custom-select-display .selected-text');

    if (!previewCard) return;

    // Update custom select display text
    if (display) {
        display.textContent = selectedOption && selectedOption.value ? selectedOption.text : 'Wybierz produkt...';
    }

    // If no product selected, hide preview
    if (!selectedOption || !selectedOption.value) {
        previewCard.style.display = 'none';
        return;
    }

    // Get product data from option attributes
    const productName = selectedOption.dataset.name || selectedOption.text;
    const productPrice = selectedOption.dataset.price;
    const productImage = selectedOption.dataset.image;

    // Update preview card
    const nameEl = previewCard.querySelector('.set-product-preview-name');
    const priceEl = previewCard.querySelector('.set-product-preview-price');
    const imageContainer = previewCard.querySelector('.set-product-preview-image');

    if (nameEl) nameEl.textContent = productName;
    if (priceEl) priceEl.textContent = productPrice ? `${productPrice} PLN` : '';

    // Update image
    if (imageContainer) {
        if (productImage) {
            imageContainer.innerHTML = `<img src="${productImage}" alt="${productName}">`;
        } else {
            // Show placeholder
            imageContainer.innerHTML = `
                <div class="no-thumb">
                    <svg width="24" height="24" viewBox="0 0 16 16" fill="currentColor">
                        <path d="M6.002 5.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z"/>
                        <path d="M2.002 1a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V3a2 2 0 0 0-2-2h-12zm12 1a1 1 0 0 1 1 1v6.5l-3.777-1.947a.5.5 0 0 0-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 0 0-.63.062L1.002 12V3a1 1 0 0 1 1-1h12z"/>
                    </svg>
                </div>
            `;
        }
    }

    // Show preview card
    previewCard.style.display = 'flex';
}

/**
 * Initialize Auto-increase Form
 * Handles the auto-increase settings form in the sidebar
 */
function initializeAutoIncreaseForm() {
    const form = document.getElementById('auto-increase-form');
    if (!form) return;

    const saveBtn = document.getElementById('save_auto_increase_btn');
    const enabledCheckbox = document.getElementById('auto_increase_enabled');
    const productThreshold = document.getElementById('auto_increase_product_threshold');
    const setThreshold = document.getElementById('auto_increase_set_threshold');
    const amount = document.getElementById('auto_increase_amount');

    // Store initial values
    const initialValues = {
        enabled: enabledCheckbox.checked,
        product_threshold: productThreshold.value,
        set_threshold: setThreshold.value,
        amount: amount.value
    };

    // Function to check for changes
    function checkForChanges() {
        const currentValues = {
            enabled: enabledCheckbox.checked,
            product_threshold: productThreshold.value,
            set_threshold: setThreshold.value,
            amount: amount.value
        };

        const hasChanges = JSON.stringify(initialValues) !== JSON.stringify(currentValues);
        saveBtn.disabled = !hasChanges;
    }

    // Add event listeners
    enabledCheckbox.addEventListener('change', checkForChanges);
    productThreshold.addEventListener('input', checkForChanges);
    setThreshold.addEventListener('input', checkForChanges);
    amount.addEventListener('input', checkForChanges);

    // Handle form submission
    form.addEventListener('submit', function(e) {
        e.preventDefault();

        // Disable button during submission
        saveBtn.disabled = true;
        const originalText = saveBtn.innerHTML;
        saveBtn.innerHTML = '<span class="spinner"></span> Zapisywanie...';

        // Prepare form data
        const formData = new FormData();
        formData.append('csrf_token', form.querySelector('input[name="csrf_token"]').value);
        formData.append('auto_increase_enabled', enabledCheckbox.checked ? 'true' : 'false');
        formData.append('auto_increase_product_threshold', productThreshold.value);
        formData.append('auto_increase_set_threshold', setThreshold.value);
        formData.append('auto_increase_amount', amount.value);

        // Submit via AJAX
        fetch(form.action, {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Update initial values
                initialValues.enabled = enabledCheckbox.checked;
                initialValues.product_threshold = productThreshold.value;
                initialValues.set_threshold = setThreshold.value;
                initialValues.amount = amount.value;

                // Show success message
                showToast(data.message || 'Ustawienia auto-zwiększania zostały zapisane.', 'success');

                // Reset button
                saveBtn.innerHTML = originalText;
                saveBtn.disabled = true;

                // Mark as not dirty since we just saved
                isDirty = false;
            } else {
                throw new Error(data.error || 'Wystąpił błąd podczas zapisywania.');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showToast(error.message || 'Wystąpił błąd podczas zapisywania.', 'error');
            saveBtn.innerHTML = originalText;
            checkForChanges(); // Re-enable button if there are still changes
        });
    });
}

/**
 * Toggle Settings Accordion (Mobile)
 * Expands/collapses the settings section on mobile devices
 */
function toggleSettingsAccordion(btn) {
    const accordion = btn.closest('.sidebar-settings-accordion');
    const isExpanded = accordion.classList.contains('expanded');

    if (isExpanded) {
        accordion.classList.remove('expanded');
        btn.classList.remove('expanded');
    } else {
        accordion.classList.add('expanded');
        btn.classList.add('expanded');
    }
}


// ============================================
// BONUS (GRATIS) MANAGEMENT
// ============================================

/**
 * Add a new bonus card to the set section
 */
function addSetBonus(btn) {
    const bonusesList = btn.closest('.set-bonuses-section').querySelector('.set-bonuses-list');
    const bonusIndex = bonusesList.querySelectorAll('.set-bonus-item').length + 1;

    const bonusHtml = `
    <div class="set-bonus-item">
        <div class="bonus-header-row">
            <span class="bonus-badge">GRATIS #${bonusIndex}</span>
            <label class="bonus-active-toggle">
                <input type="checkbox" class="bonus-is-active" checked onchange="markDirty()">
                Aktywny
            </label>
            <button type="button" class="btn-remove-bonus" onclick="removeSetBonus(this)" title="Usuń gratis">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708z"/></svg>
            </button>
        </div>

        <div class="bonus-columns">
            <div class="bonus-col bonus-col-left">
                <div class="bonus-block-label">Warunek</div>
                <div class="bonus-field">
                    <label>Typ warunku</label>
                    <select class="form-select bonus-trigger-type" onchange="onBonusTriggerTypeChange(this); markDirty()">
                        <option value="buy_products">Kup produkty</option>
                        <option value="price_threshold">Próg kwoty</option>
                        <option value="quantity_threshold">Próg ilości</option>
                    </select>
                </div>
                <div class="bonus-field bonus-threshold-field" style="display: none;">
                    <label>Wartość progu</label>
                    <input type="number" class="form-input bonus-threshold-value" step="0.01" min="0" onchange="markDirty()">
                </div>
                <div class="bonus-required-products">
                    <label>Wymagane produkty <small>(wszystkie)</small></label>
                    <div class="bonus-required-list"></div>
                    <button type="button" class="btn-add-req-product" onclick="addBonusRequiredProduct(this)">+ Dodaj wymagany produkt</button>
                </div>
            </div>
            <div class="bonus-col bonus-col-right">
                <div class="bonus-block-label">Nagroda</div>
                <div class="bonus-field">
                    <label>Produkt gratisowy <span style="color: red;">*</span></label>
                    <div class="bonus-product-search-wrapper">
                        <input type="text" class="form-input bonus-product-search"
                               placeholder="Szukaj produktu (nazwa lub SKU)..."
                               oninput="searchBonusProduct(this)"
                               onfocus="searchBonusProduct(this)"
                               autocomplete="off">
                        <input type="hidden" class="bonus-product-id" value="">
                    </div>
                </div>
                <div class="bonus-field-row">
                    <div class="bonus-field bonus-field-wide">
                        <label>Ilość</label>
                        <input type="number" class="form-input bonus-quantity" value="1" min="1" onchange="markDirty()">
                    </div>
                    <div class="bonus-field bonus-field-wide">
                        <label>Limit</label>
                        <input type="number" class="form-input bonus-max-available" min="1" placeholder="Bez" onchange="markDirty()">
                    </div>
                </div>
            </div>
        </div>

        <div class="bonus-options-row">
            <label class="bonus-option">
                <input type="checkbox" class="bonus-count-full-set" onchange="markDirty()">
                Pełny set liczy się do progu
            </label>
            <label class="bonus-option">
                <input type="checkbox" class="bonus-repeatable" onchange="markDirty()">
                Wielokrotny próg
            </label>
            <div class="bonus-option">
                <label>Po wyczerpaniu:</label>
                <select class="form-select bonus-when-exhausted" onchange="markDirty()">
                    <option value="hide">Ukryj</option>
                    <option value="show_exhausted">Pokaż jako wyczerpany</option>
                </select>
            </div>
        </div>
    </div>`;

    bonusesList.insertAdjacentHTML('beforeend', bonusHtml);
    markDirty();
}

/**
 * Remove a bonus card
 */
function removeSetBonus(btn) {
    if (!confirm('Czy na pewno chcesz usunąć ten gratis?')) return;
    const bonusItem = btn.closest('.set-bonus-item');
    const container = bonusItem.parentElement;
    bonusItem.remove();

    // Przelicz numerację pozostałych bonusów w tym kontenerze
    const remainingBonuses = container.querySelectorAll('.set-bonus-item');
    remainingBonuses.forEach((item, index) => {
        const badge = item.querySelector('.bonus-badge');
        if (badge) {
            badge.textContent = `GRATIS #${index + 1}`;
        }
    });

    markDirty();
}

/**
 * Search for bonus product (offer type only)
 * Dropdown is appended to document.body to escape overflow:hidden containers.
 */
let _bonusSearchTimeout = null;
let _bonusDropdown = null; // single shared dropdown element
let _bonusDropdownOwner = null; // the input that owns the current dropdown

function _getBonusDropdown() {
    if (!_bonusDropdown) {
        _bonusDropdown = document.createElement('div');
        _bonusDropdown.className = 'bonus-product-results';
        _bonusDropdown.style.display = 'none';
        document.body.appendChild(_bonusDropdown);
    }
    return _bonusDropdown;
}

function _positionBonusDropdown(input) {
    const dd = _getBonusDropdown();
    const rect = input.getBoundingClientRect();
    const maxH = 240;
    const spaceBelow = window.innerHeight - rect.bottom - 4;
    const spaceAbove = rect.top - 4;
    const fitsBelow = spaceBelow >= maxH;

    dd.style.position = 'fixed';
    dd.style.left = rect.left + 'px';
    dd.style.width = rect.width + 'px';

    if (fitsBelow) {
        dd.style.top = (rect.bottom + 2) + 'px';
        dd.style.bottom = 'auto';
        dd.style.maxHeight = maxH + 'px';
    } else {
        dd.style.top = 'auto';
        dd.style.bottom = (window.innerHeight - rect.top + 2) + 'px';
        dd.style.maxHeight = Math.min(maxH, spaceAbove) + 'px';
    }
}

function searchBonusProduct(input) {
    clearTimeout(_bonusSearchTimeout);
    const dd = _getBonusDropdown();
    _bonusDropdownOwner = input;
    const query = input.value.trim();

    if (query.length < 2) {
        dd.innerHTML = '';
        dd.style.display = 'none';
        return;
    }

    _positionBonusDropdown(input);

    _bonusSearchTimeout = setTimeout(() => {
        const pageType = document.querySelector('.builder-page')?.dataset?.pageType || 'exclusive';
        fetch(`/admin/offers/api/products?q=${encodeURIComponent(query)}&page_type=${pageType}`)
            .then(r => r.json())
            .then(products => {
                if (!products.length) {
                    dd.innerHTML = '<div class="bonus-product-no-results">Brak wyników</div>';
                    dd.style.display = 'block';
                    return;
                }
                dd.innerHTML = products.map(p => `
                    <div class="bonus-product-result-item" data-product-id="${p.id}" data-product-name="${p.name.replace(/"/g, '&quot;')}">
                        ${p.image ? `<img src="${p.image}" class="bonus-product-result-img" alt="">` : '<div class="bonus-product-result-img-placeholder"></div>'}
                        <div class="bonus-product-result-info">
                            <span class="bonus-product-result-name">${p.name}</span>
                            <span class="bonus-product-result-sku">${p.sku || ''} &middot; ${p.price.toFixed(2)} PLN</span>
                        </div>
                    </div>
                `).join('');
                dd.style.display = 'block';
                _positionBonusDropdown(input);
            })
            .catch(() => {
                dd.innerHTML = '<div class="bonus-product-no-results">Błąd wyszukiwania</div>';
                dd.style.display = 'block';
            });
    }, 300);
}

// Delegate click on dropdown items (dropdown lives in body, not in wrapper)
document.addEventListener('click', function(e) {
    const item = e.target.closest('.bonus-product-result-item');
    if (item && _bonusDropdownOwner) {
        const productId = item.dataset.productId;
        const productName = item.dataset.productName;
        selectBonusProduct(_bonusDropdownOwner, productId, productName);
        return;
    }
    // Close dropdown when clicking outside
    if (!e.target.closest('.bonus-product-search-wrapper') && _bonusDropdown) {
        _bonusDropdown.style.display = 'none';
    }
});

function selectBonusProduct(input, productId, productName) {
    const wrapper = input.closest('.bonus-product-search-wrapper');
    const hiddenInput = wrapper.querySelector('.bonus-product-id');

    hiddenInput.value = productId;
    input.value = productName;

    if (_bonusDropdown) {
        _bonusDropdown.innerHTML = '';
        _bonusDropdown.style.display = 'none';
    }

    // Show selected badge
    let selectedDiv = wrapper.querySelector('.bonus-product-selected');
    if (!selectedDiv) {
        selectedDiv = document.createElement('div');
        selectedDiv.className = 'bonus-product-selected';
        wrapper.appendChild(selectedDiv);
    }
    selectedDiv.innerHTML = `
        <span class="bonus-product-selected-name">${productName}</span>
        <button type="button" class="bonus-product-clear" onclick="clearBonusProduct(this)">&times;</button>
    `;

    markDirty();
}

function clearBonusProduct(btn) {
    const wrapper = btn.closest('.bonus-product-search-wrapper');
    wrapper.querySelector('.bonus-product-id').value = '';
    wrapper.querySelector('.bonus-product-search').value = '';
    const selectedDiv = wrapper.querySelector('.bonus-product-selected');
    if (selectedDiv) selectedDiv.remove();
    markDirty();
}

/**
 * Handle trigger type change - show/hide conditional fields
 */
function onBonusTriggerTypeChange(select) {
    const bonusItem = select.closest('.set-bonus-item');
    const triggerType = select.value;

    const thresholdField = bonusItem.querySelector('.bonus-threshold-field');
    const requiredProducts = bonusItem.querySelector('.bonus-required-products');

    if (triggerType === 'buy_products') {
        thresholdField.style.display = 'none';
        requiredProducts.style.display = 'block';
    } else {
        thresholdField.style.display = 'block';
        requiredProducts.style.display = 'none';
    }
}

/**
 * Toggle threshold / required products fields for standalone bonus sections
 */
function toggleBonusTriggerFields(select) {
    const card = select.closest('.section-card[data-section-type="bonus"]');
    if (!card) return; // not a standalone bonus section
    const thresholdRow = card.querySelector('.bonus-threshold-row');
    const requiredRow = card.querySelector('.bonus-required-products');
    const triggerType = select.value;

    if (thresholdRow) thresholdRow.style.display = (triggerType === 'price_threshold' || triggerType === 'quantity_threshold') ? '' : 'none';
    if (requiredRow) requiredRow.style.display = triggerType === 'buy_products' ? '' : 'none';
    markDirty();
}

/**
 * Add a required product row to a buy_products bonus
 */
function addBonusRequiredProduct(btn) {
    const productOptions = document.getElementById('productOptionTemplate').innerHTML;
    const list = btn.closest('.bonus-required-products').querySelector('.bonus-required-list');

    const html = `
    <div class="bonus-required-item">
        <select class="form-select bonus-req-product" onchange="markDirty()">
            <option value="">Wybierz...</option>
            ${productOptions}
        </select>
        <input type="number" class="form-input bonus-req-min-qty" value="1" min="1" style="width: 60px;" onchange="markDirty()">
        <button type="button" class="btn-remove-req-product" onclick="removeBonusRequiredProduct(this)">
            <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor"><path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708z"/></svg>
        </button>
    </div>`;

    list.insertAdjacentHTML('beforeend', html);
    markDirty();
}

/**
 * Remove a required product row
 */
function removeBonusRequiredProduct(btn) {
    btn.closest('.bonus-required-item').remove();
    markDirty();
}
