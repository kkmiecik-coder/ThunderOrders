/**
 * Mass Product Edit
 * Handles column selection, grid rendering, validation, and save flow
 */

// =============================================
// CSRF
// =============================================

function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.getAttribute('content');
    const input = document.querySelector('input[name="csrf_token"]');
    if (input) return input.value;
    return '';
}

// =============================================
// STATE
// =============================================

let productsData = [];
let selectOptions = {};
let maxImages = 5;
let selectedColumns = [];
let pendingImageUploads = {};
let pendingImageRemovals = []; // [{productId, slot}]

// Undo/Redo
const MAX_HISTORY = 50;
let undoStack = [];
let redoStack = [];

const COLUMN_GROUPS = [
    {
        name: 'Dane podstawowe',
        columns: [
            { key: 'sku', label: 'SKU', type: 'text', maxlength: 100 },
            { key: 'ean', label: 'EAN', type: 'text', maxlength: 13, pattern: '^[0-9]{13}$' },
            { key: 'description', label: 'Opis', type: 'textarea' },
            { key: 'tags', label: 'Tagi', type: 'text', placeholder: 'np. kpop, album, bts' },
            { key: 'sizes', label: 'Rozmiary', type: 'text', placeholder: 'np. S, M, L, XL, 42, 43' },
            { key: 'is_active', label: 'Aktywny', type: 'checkbox' }
        ]
    },
    {
        name: 'Taxonomia',
        columns: [
            { key: 'category_id', label: 'Kategoria', type: 'select', optionsKey: 'categories', autoCreate: true },
            { key: 'manufacturer_id', label: 'Producent', type: 'select', optionsKey: 'manufacturers', autoCreate: true },
            { key: 'series_id', label: 'Seria', type: 'select', optionsKey: 'series', autoCreate: true },
            { key: 'product_type_id', label: 'Typ produktu', type: 'select', optionsKey: 'product_types', autoCreate: true },
        ]
    },
    {
        name: 'Ceny',
        columns: [
            { key: 'sale_price', label: 'Cena sprzedaży', type: 'number', step: '0.01', min: '0', required: true },
            { key: 'purchase_price', label: 'Cena zakupu', type: 'number', step: '0.01', min: '0' },
            { key: 'purchase_currency', label: 'Waluta', type: 'select', optionsKey: 'currencies', autoCreate: false },
            { key: 'purchase_price_pln', label: 'Cena zakupu PLN', type: 'number', step: '0.01', min: '0' },
            { key: 'margin', label: 'Marża (%)', type: 'number', step: '0.01' },
        ]
    },
    {
        name: 'Magazyn',
        columns: [
            { key: 'quantity', label: 'Ilość', type: 'number', step: '1', min: '0' },
            { key: 'supplier_id', label: 'Dostawca', type: 'select', optionsKey: 'suppliers', autoCreate: true },
            { key: 'length', label: 'Długość (cm)', type: 'number', step: '0.01', min: '0' },
            { key: 'width', label: 'Szerokość (cm)', type: 'number', step: '0.01', min: '0' },
            { key: 'height', label: 'Wysokość (cm)', type: 'number', step: '0.01', min: '0' },
            { key: 'weight', label: 'Waga (kg)', type: 'number', step: '0.01', min: '0' },
        ]
    },
];

// =============================================
// INIT — Column Selection (Stage 1)
// =============================================

document.addEventListener('DOMContentLoaded', function() {
    renderColumnGroups();

    // Undo/Redo keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
            e.preventDefault();
            if (e.shiftKey) {
                redo();
            } else {
                undo();
            }
        }
    });
});

function renderColumnGroups() {
    const container = document.getElementById('columnGroups');
    let html = '';

    COLUMN_GROUPS.forEach((group, gi) => {
        html += renderGroupHtml(group, gi);
    });

    const imgCount = typeof INITIAL_MAX_IMAGES !== 'undefined' ? INITIAL_MAX_IMAGES : 10;
    let imgItems = '';
    for (let i = 1; i <= imgCount; i++) {
        imgItems += `<label><input type="checkbox" class="col-checkbox" data-col="image_${i}" data-group="img"> Zdjęcie ${i}</label>`;
    }
    html += `<div class="column-group">
        <div class="column-group-header" onclick="toggleGroup('img')">
            <input type="checkbox" id="group_img" onchange="toggleGroup('img')">
            <label for="group_img">Zdjęcia</label>
        </div>
        <div class="column-group-items" id="imageColumnsContainer">
            ${imgItems}
        </div>
    </div>`;

    container.innerHTML = html;
}

function renderGroupHtml(group, groupIndex) {
    let html = `<div class="column-group">
        <div class="column-group-header" onclick="toggleGroup(${groupIndex})">
            <input type="checkbox" id="group_${groupIndex}" onchange="toggleGroup(${groupIndex})">
            <label for="group_${groupIndex}">${group.name}</label>
        </div>
        <div class="column-group-items">`;

    group.columns.forEach(col => {
        html += `<label>
            <input type="checkbox" class="col-checkbox" data-col="${col.key}" data-group="${groupIndex}">
            ${col.label}
        </label>`;
    });

    html += '</div></div>';
    return html;
}

function toggleGroup(groupIndex) {
    const groupCheckbox = document.getElementById(`group_${groupIndex}`);
    const isChecked = groupCheckbox.checked;
    const items = document.querySelectorAll(`.col-checkbox[data-group="${groupIndex}"]`);
    items.forEach(cb => cb.checked = isChecked);
}

function getSelectedColumns() {
    const checked = document.querySelectorAll('.col-checkbox:checked');
    const cols = [];

    cols.push({ key: 'id', label: 'ID', type: 'readonly', width: '50px' });
    cols.push({ key: 'name', label: 'Nazwa', type: 'text', maxlength: 255, required: true, width: '200px' });

    checked.forEach(cb => {
        const key = cb.dataset.col;

        if (key.startsWith('image_')) {
            const slot = parseInt(key.split('_')[1]);
            cols.push({ key: key, label: `Zdjęcie ${slot}`, type: 'image', slot: slot, width: '90px' });
            return;
        }

        for (const group of COLUMN_GROUPS) {
            const found = group.columns.find(c => c.key === key);
            if (found) {
                cols.push(found);
                break;
            }
        }
    });

    return cols;
}

// =============================================
// STAGE TRANSITION
// =============================================

function startEditing() {
    // Capture selected columns BEFORE hiding stage 1
    selectedColumns = getSelectedColumns();

    if (selectedColumns.length <= 2) {
        if (typeof window.showToast === 'function') {
            window.showToast('Zaznacz przynajmniej jedną kolumnę do edycji.', 'error');
        }
        return;
    }

    document.getElementById('stageColumnSelect').classList.add('hidden');
    document.getElementById('loadingOverlay').classList.remove('hidden');

    const idsParam = PRODUCT_IDS.join(',');
    fetch(`${DATA_URL}?ids=${idsParam}`, {
        headers: { 'X-CSRFToken': getCsrfToken() }
    })
    .then(r => r.json())
    .then(data => {
        if (!data.success) throw new Error(data.error || 'Błąd ładowania danych');

        productsData = data.products;
        selectOptions = data.options;
        maxImages = data.settings.max_images || 5;

        // selectedColumns already captured before fetch — don't overwrite

        document.getElementById('loadingProgress').style.width = '100%';
        document.getElementById('loadingText').textContent = 'Gotowe!';

        setTimeout(() => {
            document.getElementById('loadingOverlay').classList.add('hidden');
            document.getElementById('stageEditGrid').classList.remove('hidden');
            document.getElementById('productCount').textContent = productsData.length;
            renderGrid();
        }, 300);
    })
    .catch(err => {
        document.getElementById('loadingOverlay').classList.add('hidden');
        document.getElementById('stageColumnSelect').classList.remove('hidden');
        if (typeof window.showToast === 'function') {
            window.showToast('Błąd: ' + err.message, 'error');
        }
    });
}

function updateImageColumns() {
    const container = document.getElementById('imageColumnsContainer');
    if (!container) return;
    let html = '';
    for (let i = 1; i <= maxImages; i++) {
        html += `<label><input type="checkbox" class="col-checkbox" data-col="image_${i}" data-group="img"> Zdjęcie ${i}</label>`;
    }
    container.innerHTML = html;
}

// =============================================
// GRID RENDERING
// =============================================

function renderGrid() {
    const container = document.getElementById('gridBody');
    const colCount = selectedColumns.length;

    // Build one flat grid: header cells + all row cells
    const colWidths = selectedColumns.map(col => {
        if (col.width) return col.width;
        if (col.type === 'textarea') return '200px';
        if (col.type === 'select') return '160px';
        if (col.type === 'image') return '64px';
        if (col.type === 'checkbox') return '60px';
        return '130px';
    }).join(' ');

    // Calculate min-width to ensure horizontal scroll
    container.style.display = 'grid';
    container.style.gridTemplateColumns = colWidths;

    let html = '';

    // Header cells
    selectedColumns.forEach((col, i) => {
        const stickyClass = i === 0 ? 'sticky-col-0' : i === 1 ? 'sticky-col-1' : '';
        html += `<div class="grid-header-cell ${stickyClass}">${col.label}</div>`;
    });

    // Data rows
    productsData.forEach((product, rowIndex) => {
        const oddRow = rowIndex % 2 === 1 ? ' row-alt' : '';
        selectedColumns.forEach((col, colIndex) => {
            const stickyClass = colIndex === 0 ? 'sticky-col-0' : colIndex === 1 ? 'sticky-col-1' : '';
            const rowAttr = colIndex === 0 ? ` data-row-id="${product.id}"` : '';
            html += `<div class="grid-cell ${stickyClass}${oddRow}"${rowAttr}>`;
            html += renderCellInput(col, product, rowIndex);
            html += '</div>';
        });
    });

    container.innerHTML = html;

    // Hide the separate header div (we render header inside gridBody now)
    document.getElementById('gridHeader').style.display = 'none';

    attachInputListeners();
}

function renderCellInput(col, product, rowIndex) {
    const pid = product.id;

    if (col.type === 'readonly') {
        return `<span>${product[col.key]}</span>`;
    }

    if (col.type === 'checkbox') {
        const checked = product[col.key] ? 'checked' : '';
        return `<input type="checkbox" data-pid="${pid}" data-field="${col.key}" ${checked}>`;
    }

    if (col.type === 'image') {
        return renderImageCell(product, col.slot);
    }

    if (col.type === 'textarea') {
        const val = escapeAttr(product[col.key] || '');
        return `<textarea data-pid="${pid}" data-field="${col.key}">${val}</textarea>`;
    }

    if (col.type === 'select') {
        return renderSelectCell(col, product);
    }

    const val = product[col.key] !== null && product[col.key] !== undefined ? product[col.key] : '';
    const attrs = [];
    attrs.push(`type="${col.type}"`);
    attrs.push(`data-pid="${pid}"`);
    attrs.push(`data-field="${col.key}"`);
    attrs.push(`value="${escapeAttr(val)}"`);
    if (col.maxlength) attrs.push(`maxlength="${col.maxlength}"`);
    if (col.step) attrs.push(`step="${col.step}"`);
    if (col.min) attrs.push(`min="${col.min}"`);
    if (col.pattern) attrs.push(`pattern="${col.pattern}"`);
    if (col.required) attrs.push('required');
    if (col.placeholder) attrs.push(`placeholder="${escapeAttr(col.placeholder)}"`);

    return `<input ${attrs.join(' ')}>`;
}

function renderSelectCell(col, product) {
    const pid = product.id;
    const currentVal = product[col.key];

    if (col.optionsKey === 'currencies') {
        let html = `<select data-pid="${pid}" data-field="${col.key}">`;
        html += '<option value="">—</option>';
        selectOptions.currencies.forEach(c => {
            const selected = currentVal === c ? 'selected' : '';
            html += `<option value="${c}" ${selected}>${c}</option>`;
        });
        html += '</select>';
        return html;
    }

    const options = selectOptions[col.optionsKey] || [];
    let html = `<select data-pid="${pid}" data-field="${col.key}" data-auto-create="${col.autoCreate}" data-options-key="${col.optionsKey}">`;
    html += '<option value="">—</option>';
    options.forEach(opt => {
        const selected = currentVal === opt.id ? 'selected' : '';
        html += `<option value="${opt.id}" ${selected}>${escapeHtml(opt.name)}</option>`;
    });
    if (col.autoCreate) {
        html += '<option value="__create__">+ Dodaj...</option>';
    }
    html += '</select>';
    return html;
}

function renderImageCell(product, slot) {
    const pid = product.id;
    const imgData = product.images && product.images[String(slot)];
    const fileInputId = `img-${pid}-${slot}`;

    if (imgData) {
        const imgSrc = imgData.path_compressed.startsWith('static/') ? '/' + imgData.path_compressed : '/static/' + imgData.path_compressed;
        return `<div class="image-slot has-image">
            <img src="${imgSrc}" alt="" onclick="document.getElementById('${fileInputId}').click()">
            <span class="image-remove" onclick="removeImage(${pid}, ${slot}, event)" title="Usuń zdjęcie">&times;</span>
            <input type="file" id="${fileInputId}" accept="image/*" style="display:none"
                   onchange="handleImageSelect(${pid}, ${slot}, this)">
        </div>`;
    }

    return `<div class="image-slot empty" onclick="document.getElementById('${fileInputId}').click()">
        +
        <input type="file" id="${fileInputId}" accept="image/*" style="display:none"
               onchange="handleImageSelect(${pid}, ${slot}, this)">
    </div>`;
}

// =============================================
// EVENT LISTENERS
// =============================================

function attachInputListeners() {
    document.querySelectorAll('#gridBody input, #gridBody textarea, #gridBody select').forEach(el => {
        if (el.type === 'file') return;

        // Save undo state when field gets focus (before any edits)
        el.addEventListener('focus', function() {
            saveUndoState();
        });

        el.addEventListener('blur', function() {
            validateCell(this);
        });

        el.addEventListener('change', function() {
            validateCell(this);
            updateProductData(this);

            if (this.tagName === 'SELECT' && this.value === '__create__') {
                handleAutoCreate(this);
            }
        });

        el.addEventListener('input', function() {
            updateProductData(this);

            const field = this.dataset.field;
            if (['sale_price', 'purchase_price_pln', 'margin'].includes(field)) {
                autoCalcPrices(this.dataset.pid, field);
            }
        });
    });
}

function saveUndoState() {
    undoStack.push(JSON.parse(JSON.stringify(productsData)));
    if (undoStack.length > MAX_HISTORY) undoStack.shift();
    redoStack = [];
}

function undo() {
    if (undoStack.length === 0) return;
    redoStack.push(JSON.parse(JSON.stringify(productsData)));
    productsData = undoStack.pop();
    renderGrid();
}

function redo() {
    if (redoStack.length === 0) return;
    undoStack.push(JSON.parse(JSON.stringify(productsData)));
    productsData = redoStack.pop();
    renderGrid();
}

function updateProductData(el) {
    const pid = parseInt(el.dataset.pid);
    const field = el.dataset.field;
    const product = productsData.find(p => p.id === pid);
    if (!product) return;

    if (el.type === 'checkbox') {
        product[field] = el.checked;
    } else if (el.type === 'number') {
        product[field] = el.value === '' ? null : parseFloat(el.value);
    } else if (el.tagName === 'SELECT') {
        const val = el.value;
        product[field] = val === '' ? null : (isNaN(val) ? val : parseInt(val));
    } else {
        product[field] = el.value;
    }
}

// =============================================
// AUTO-CREATE SELECT
// =============================================

function handleAutoCreate(selectEl) {
    const pid = selectEl.dataset.pid;
    const field = selectEl.dataset.field;
    const optionsKey = selectEl.dataset.optionsKey;

    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'inline-create-input';
    input.placeholder = 'Wpisz nazwę, Enter = potwierdź';
    input.dataset.pid = pid;
    input.dataset.field = field;
    input.dataset.optionsKey = optionsKey;

    selectEl.parentNode.replaceChild(input, selectEl);
    input.focus();

    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            confirmAutoCreate(this);
        } else if (e.key === 'Escape') {
            revertAutoCreate(this);
        }
    });

    input.addEventListener('blur', function() {
        if (this.value.trim()) {
            confirmAutoCreate(this);
        } else {
            revertAutoCreate(this);
        }
    });
}

function confirmAutoCreate(input) {
    const name = input.value.trim();
    if (!name) { revertAutoCreate(input); return; }

    const pid = parseInt(input.dataset.pid);
    const field = input.dataset.field;
    const optionsKey = input.dataset.optionsKey;

    const product = productsData.find(p => p.id === pid);
    if (product) product[field] = name;

    if (!selectOptions[optionsKey].find(o => o.name.toLowerCase() === name.toLowerCase())) {
        selectOptions[optionsKey].push({ id: name, name: name });
    }

    const col = selectedColumns.find(c => c.key === field);
    if (col) {
        const parentCell = input.parentNode;
        const tempProduct = { ...product };
        tempProduct[field] = name;
        parentCell.innerHTML = renderSelectCell(col, tempProduct);

        const newSelect = parentCell.querySelector('select');
        if (newSelect) {
            for (const opt of newSelect.options) {
                if (opt.text === name) { opt.selected = true; break; }
            }
        }
        attachInputListeners();
    }
}

function revertAutoCreate(input) {
    const pid = parseInt(input.dataset.pid);
    const field = input.dataset.field;
    const product = productsData.find(p => p.id === pid);
    const col = selectedColumns.find(c => c.key === field);

    if (col && product) {
        product[field] = null;
        const parentCell = input.parentNode;
        parentCell.innerHTML = renderSelectCell(col, product);
        attachInputListeners();
    }
}

// =============================================
// IMAGE HANDLING
// =============================================

function handleImageSelect(productId, slot, input) {
    if (!input.files || !input.files[0]) return;

    const file = input.files[0];

    if (!pendingImageUploads[productId]) pendingImageUploads[productId] = {};
    pendingImageUploads[productId][slot] = file;

    // Remove from pending removals if it was marked for deletion
    pendingImageRemovals = pendingImageRemovals.filter(
        r => !(r.productId === productId && r.slot === slot)
    );

    const reader = new FileReader();
    reader.onload = function(e) {
        const slotDiv = input.parentNode;
        slotDiv.className = 'image-slot has-image';
        slotDiv.innerHTML = `<img src="${e.target.result}" alt="" onclick="document.getElementById('img-${productId}-${slot}').click()">
            <span class="image-remove" onclick="removeImage(${productId}, ${slot}, event)" title="Usuń zdjęcie">&times;</span>
            <input type="file" id="img-${productId}-${slot}" accept="image/*" style="display:none"
                   onchange="handleImageSelect(${productId}, ${slot}, this)">`;
    };
    reader.readAsDataURL(file);
}

function removeImage(productId, slot, event) {
    event.stopPropagation();

    // Mark for removal on save
    if (!pendingImageRemovals.find(r => r.productId === productId && r.slot === slot)) {
        pendingImageRemovals.push({ productId, slot });
    }

    // Remove from pending uploads if it was a new file
    if (pendingImageUploads[productId]) {
        delete pendingImageUploads[productId][slot];
    }

    // Remove from local product data
    const product = productsData.find(p => p.id === productId);
    if (product && product.images) {
        delete product.images[String(slot)];
    }

    // Replace with empty slot
    const fileInputId = `img-${productId}-${slot}`;
    const slotDiv = event.target.closest('.image-slot');
    slotDiv.className = 'image-slot empty';
    slotDiv.setAttribute('onclick', `document.getElementById('${fileInputId}').click()`);
    slotDiv.innerHTML = `+
        <input type="file" id="${fileInputId}" accept="image/*" style="display:none"
               onchange="handleImageSelect(${productId}, ${slot}, this)">`;
}

// =============================================
// VALIDATION
// =============================================

function validateCell(el) {
    if (el.type === 'file' || el.type === 'checkbox') return true;

    const field = el.dataset.field;
    const value = el.value.trim();
    let error = '';

    if (el.required && !value) {
        error = 'Pole wymagane';
    }

    if (field === 'ean' && value && (!/^\d{13}$/.test(value))) {
        error = 'EAN: dokładnie 13 cyfr';
    }

    if (el.type === 'number' && value && el.min !== '' && parseFloat(value) < parseFloat(el.min)) {
        error = `Minimum: ${el.min}`;
    }

    el.classList.toggle('input-error', !!error);

    const existing = el.parentNode.querySelector('.cell-error-msg');
    if (existing) existing.remove();

    if (error) {
        const msg = document.createElement('div');
        msg.className = 'cell-error-msg';
        msg.textContent = error;
        el.parentNode.appendChild(msg);
    }

    return !error;
}

function validateAll() {
    let valid = true;
    document.querySelectorAll('#gridBody input:not([type="file"]):not([type="checkbox"]), #gridBody textarea, #gridBody select').forEach(el => {
        if (!validateCell(el)) valid = false;
    });
    return valid;
}

// =============================================
// AUTO-CALC PRICES
// =============================================

function autoCalcPrices(productId, changedField) {
    const pid = parseInt(productId);
    const product = productsData.find(p => p.id === pid);
    if (!product) return;

    const saleEl = document.querySelector(`input[data-pid="${pid}"][data-field="sale_price"]`);
    const plnEl = document.querySelector(`input[data-pid="${pid}"][data-field="purchase_price_pln"]`);
    const marginEl = document.querySelector(`input[data-pid="${pid}"][data-field="margin"]`);

    const sale = saleEl ? parseFloat(saleEl.value) : null;
    const pln = plnEl ? parseFloat(plnEl.value) : null;
    const margin = marginEl ? parseFloat(marginEl.value) : null;

    if (changedField === 'sale_price' || changedField === 'purchase_price_pln') {
        if (sale && pln && pln > 0 && marginEl) {
            const calc = ((sale - pln) / pln) * 100;
            marginEl.value = calc.toFixed(2);
            product.margin = calc;
        }
    } else if (changedField === 'margin') {
        if (margin !== null && !isNaN(margin)) {
            if (pln && pln > 0 && saleEl) {
                const calc = pln * (1 + margin / 100);
                saleEl.value = calc.toFixed(2);
                product.sale_price = calc;
            } else if (sale && sale > 0 && plnEl) {
                const calc = sale / (1 + margin / 100);
                plnEl.value = calc.toFixed(2);
                product.purchase_price_pln = calc;
            }
        }
    }
}

// =============================================
// SAVE
// =============================================

function saveAll() {
    if (!validateAll()) {
        if (typeof window.showToast === 'function') {
            window.showToast('Popraw błędy walidacji przed zapisaniem.', 'error');
        }
        return;
    }

    const saveOverlay = document.getElementById('saveOverlay');
    const saveProgress = document.getElementById('saveProgress');
    const saveText = document.getElementById('saveText');
    const saveDetail = document.getElementById('saveDetail');

    saveOverlay.classList.remove('hidden');
    saveText.textContent = 'Zapisywanie danych...';
    saveProgress.style.width = '0%';

    fetch(SAVE_URL, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify({ products: productsData })
    })
    .then(r => r.json())
    .then(data => {
        if (!data.success) throw new Error(data.error || 'Błąd zapisu');

        const results = data.results;
        saveProgress.style.width = '30%';

        // Step 2: Delete removed images
        if (pendingImageRemovals.length > 0) {
            saveText.textContent = 'Usuwanie zdjęć...';
        }

        let removeIdx = 0;
        const processRemovals = () => {
            if (removeIdx >= pendingImageRemovals.length) {
                saveProgress.style.width = '50%';
                processUploads();
                return;
            }

            const rem = pendingImageRemovals[removeIdx];
            saveDetail.textContent = `Usuwanie ${removeIdx + 1} / ${pendingImageRemovals.length}`;

            fetch(IMAGE_DELETE_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify({ product_id: rem.productId, slot: rem.slot })
            })
            .then(r => r.json())
            .then(() => { removeIdx++; processRemovals(); })
            .catch(() => { removeIdx++; processRemovals(); });
        };

        // Step 3: Upload new images
        const processUploads = () => {
            const imageUploads = [];
            for (const [pid, slots] of Object.entries(pendingImageUploads)) {
                for (const [slot, file] of Object.entries(slots)) {
                    imageUploads.push({ productId: parseInt(pid), slot: parseInt(slot), file: file });
                }
            }

            if (imageUploads.length === 0 && pendingImageRemovals.length === 0) {
                finishSave(results);
                return;
            }

            if (imageUploads.length === 0) {
                finishSave(results);
                return;
            }

            saveText.textContent = 'Przesyłanie zdjęć...';
            let uploaded = 0;

            const uploadNext = () => {
                if (uploaded >= imageUploads.length) {
                    finishSave(results);
                    return;
                }

                const item = imageUploads[uploaded];
                saveDetail.textContent = `Zdjęcie ${uploaded + 1} / ${imageUploads.length}`;

                const formData = new FormData();
                formData.append('product_id', item.productId);
                formData.append('slot', item.slot);
                formData.append('image', item.file);

                fetch(IMAGE_UPLOAD_URL, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': getCsrfToken() },
                    body: formData
                })
                .then(r => r.json())
                .then(imgData => {
                    if (!imgData.success) {
                        results.errors.push({
                            product_id: item.productId,
                            name: `Zdjęcie ${item.slot}`,
                            error: imgData.error
                        });
                        results.failed++;
                    }
                    uploaded++;
                    saveProgress.style.width = (50 + (uploaded / imageUploads.length) * 50) + '%';
                    uploadNext();
                })
                .catch(err => {
                    results.errors.push({
                        product_id: item.productId,
                        name: `Zdjęcie ${item.slot}`,
                        error: err.message
                    });
                    results.failed++;
                    uploaded++;
                    uploadNext();
                });
            };

            uploadNext();
        };

        processRemovals();
    })
    .catch(err => {
        saveOverlay.classList.add('hidden');
        if (typeof window.showToast === 'function') {
            window.showToast('Błąd: ' + err.message, 'error');
        }
    });
}

function finishSave(results) {
    const saveOverlay = document.getElementById('saveOverlay');
    saveOverlay.classList.add('hidden');
    pendingImageUploads = {};

    if (results.failed === 0) {
        if (typeof window.showToast === 'function') {
            window.showToast(`Zapisano ${results.success} produktów.`, 'success');
        }
        setTimeout(() => { window.location.href = PRODUCTS_LIST_URL; }, 1000);
    } else if (results.success > 0) {
        if (typeof window.showToast === 'function') {
            window.showToast(`Zapisano ${results.success}, błędy: ${results.failed}. Popraw i zapisz ponownie.`, 'warning');
        }
        highlightErrors(results.errors);
    } else {
        if (typeof window.showToast === 'function') {
            window.showToast(`Błąd zapisu wszystkich produktów.`, 'error');
        }
        highlightErrors(results.errors);
    }
}

function highlightErrors(errors) {
    // Clear previous error highlights
    document.querySelectorAll('.grid-cell.cell-row-error').forEach(c => c.classList.remove('cell-row-error'));

    errors.forEach(err => {
        // Find all cells for this product and highlight them
        const cells = document.querySelectorAll(`[data-row-id="${err.product_id}"]`);
        if (cells.length > 0) {
            // Highlight the first cell (ID column) of the row
            const firstCell = cells[0];
            firstCell.classList.add('cell-row-error');
            firstCell.title = `${err.name}: ${err.error}`;
        }
        // Also highlight all inputs for this product
        document.querySelectorAll(`[data-pid="${err.product_id}"]`).forEach(input => {
            input.classList.add('input-error');
        });
    });

    // Show summary toast with all errors
    if (errors.length > 0 && typeof window.showToast === 'function') {
        const summary = errors.map(e => `${e.name}: ${e.error}`).join('\n');
        console.error('Save errors:', summary);
    }
}

// =============================================
// UTILS
// =============================================

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

function escapeAttr(text) {
    if (text === null || text === undefined) return '';
    return String(text).replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
