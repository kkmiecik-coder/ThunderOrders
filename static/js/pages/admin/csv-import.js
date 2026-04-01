/**
 * CSV Import Module
 * Handles CSV file upload, column mapping, and import progress tracking
 */

// Global variables
let currentTempFilePath = null;
let currentTempFileId = null;
let currentFileName = null;
let currentColumns = [];
let currentPreviewRows = [];
let currentTotalRows = 0;
let currentDelimiter = ',';
let currentEncoding = 'utf-8';
let suggestedMapping = {};
let importPollingInterval = null;

// Polish translation map for column names
const columnNameTranslations = {
    // English names
    'name': 'Nazwa produktu',
    'sku': 'SKU (kod produktu)',
    'ean': 'EAN (kod kreskowy)',
    'category': 'Kategoria',
    'category_id': 'Kategoria',
    'manufacturer': 'Producent',
    'series': 'Seria produktowa',
    'product_type': 'Typ produktu',
    'sale_price': 'Cena sprzedaży (PLN)',
    'purchase_price': 'Cena zakupu',
    'purchase_price_pln': 'Cena zakupu (PLN)',
    'purchase_currency': 'Waluta zakupu',
    'margin': 'Marża (%)',
    'quantity': 'Ilość w magazynie',
    'length': 'Długość (cm)',
    'width': 'Szerokość (cm)',
    'height': 'Wysokość (cm)',
    'weight': 'Waga (kg)',
    'supplier': 'Dostawca',
    'supplier_id': 'Dostawca',
    'tags': 'Tagi',
    'description': 'Opis produktu',
    'is_active': 'Aktywny',
    'variant_group': 'Grupa wariantów',

    // Polish names (in case CSV has Polish headers)
    'nazwa': 'Nazwa produktu',
    'kategoria': 'Kategoria',
    'producent': 'Producent',
    'seria': 'Seria produktowa',
    'typ_produktu': 'Typ produktu',
    'cena': 'Cena sprzedaży (PLN)',
    'cena_sprzedazy': 'Cena sprzedaży (PLN)',
    'cena_zakupu': 'Cena zakupu',
    'cena_zakupu_pln': 'Cena zakupu (PLN)',
    'waluta_zakupu': 'Waluta zakupu',
    'marza': 'Marża (%)',
    'ilosc': 'Ilość w magazynie',
    'dlugosc': 'Długość (cm)',
    'szerokosc': 'Szerokość (cm)',
    'wysokosc': 'Wysokość (cm)',
    'waga': 'Waga (kg)',
    'dostawca': 'Dostawca',
    'tagi': 'Tagi',
    'opis': 'Opis produktu',
    'aktywny': 'Aktywny',
    'grupa_wariantow': 'Grupa wariantów'
};

/**
 * Translate column name to Polish
 */
function translateColumnName(columnName) {
    const normalized = columnName.toLowerCase().trim();
    return columnNameTranslations[normalized] || columnName;
}

// CSRF Token Helper
function getCsrfToken() {
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    if (metaTag) {
        return metaTag.getAttribute('content');
    }
    const csrfInput = document.querySelector('input[name="csrf_token"]');
    if (csrfInput) {
        return csrfInput.value;
    }
    return '';
}

// =============================================
// MODAL MANAGEMENT
// =============================================

/**
 * Open Import Modal
 */
function openImportModal() {
    const modal = document.getElementById('importModal');
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';

    // Reset upload area to initial state
    const uploadArea = document.getElementById('csvUploadArea');
    uploadArea.innerHTML = `
        <svg width="48" height="48" viewBox="0 0 16 16" fill="currentColor">
            <path d="M.5 9.9a.5.5 0 01.5.5v2.5a1 1 0 001 1h12a1 1 0 001-1v-2.5a.5.5 0 011 0v2.5a2 2 0 01-2 2H2a2 2 0 01-2-2v-2.5a.5.5 0 01.5-.5z"/>
            <path d="M7.646 1.146a.5.5 0 01.708 0l3 3a.5.5 0 01-.708.708L8.5 2.707V11.5a.5.5 0 01-1 0V2.707L5.354 4.854a.5.5 0 11-.708-.708l3-3z"/>
        </svg>
        <p>Kliknij lub przeciągnij plik CSV</p>
        <input type="file" id="csvFileInput" accept=".csv" style="display:none;">
        <button type="button" class="btn btn-secondary btn-sm" onclick="document.getElementById('csvFileInput').click()">
            Wybierz plik
        </button>
        <p class="upload-hint">
            <a href="/static/uploads/csv/templates/product_import_template.csv" download>
                Pobierz szablon CSV
            </a>
        </p>
    `;

    // Load import history
    loadImportHistory();

    // Setup drag and drop
    setupDragAndDrop();

    // Setup file input
    const fileInput = document.getElementById('csvFileInput');
    fileInput.addEventListener('change', handleFileSelect);
}

/**
 * Close Import Modal
 */
function closeImportModal() {
    const modal = document.getElementById('importModal');
    modal.classList.remove('active');
    document.body.style.overflow = '';

    // Reset file input (only if it exists)
    const fileInput = document.getElementById('csvFileInput');
    if (fileInput) {
        fileInput.value = '';
    }
}

/**
 * Open Mapping Modal
 */
function openMappingModal() {
    const modal = document.getElementById('mappingModal');
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
}

/**
 * Close Mapping Modal
 */
function closeMappingModal() {
    const modal = document.getElementById('mappingModal');
    modal.classList.remove('active');
    document.body.style.overflow = '';
}

/**
 * Open Progress Modal
 */
function openProgressModal() {
    const modal = document.getElementById('progressModal');
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
}

/**
 * Close Progress Modal
 */
function closeProgressModal() {
    const modal = document.getElementById('progressModal');
    modal.classList.remove('active');
    document.body.style.overflow = '';
}

// =============================================
// DRAG AND DROP
// =============================================

/**
 * Setup Drag and Drop for CSV Upload
 */
function setupDragAndDrop() {
    const uploadArea = document.getElementById('csvUploadArea');

    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });

    uploadArea.addEventListener('dragleave', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
    });

    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('dragover');

        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFileUpload(files[0]);
        }
    });

    // Click to upload
    uploadArea.addEventListener('click', (e) => {
        if (e.target === uploadArea || e.target.tagName === 'P' || e.target.tagName === 'SVG' || e.target.tagName === 'PATH') {
            document.getElementById('csvFileInput').click();
        }
    });
}

/**
 * Handle File Select from Input
 */
function handleFileSelect(event) {
    const file = event.target.files[0];
    if (file) {
        handleFileUpload(file);
    }
}

// =============================================
// FILE UPLOAD
// =============================================

/**
 * Handle CSV File Upload
 */
function handleFileUpload(file) {
    // Validate file type
    if (!file.name.endsWith('.csv')) {
        showToast('Wybierz plik w formacie CSV', 'error');
        return;
    }

    // Validate file size (max 5MB)
    if (file.size > 5 * 1024 * 1024) {
        showToast('Plik jest za duży. Maksymalny rozmiar to 5MB', 'error');
        return;
    }

    // Show loading state
    const uploadArea = document.getElementById('csvUploadArea');
    uploadArea.innerHTML = '<p>Przesyłanie pliku...</p>';

    // Create FormData
    const formData = new FormData();
    formData.append('file', file);

    // Upload file
    fetch('/admin/imports/csv/upload', {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCsrfToken()
        },
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Store data
            currentTempFilePath = data.temp_path;
            currentTempFileId = data.temp_file_id;
            currentFileName = file.name;
            currentColumns = data.columns;
            currentPreviewRows = data.preview_rows;
            currentTotalRows = data.total_rows;
            currentDelimiter = data.delimiter;
            currentEncoding = data.encoding;
            suggestedMapping = data.suggested_mapping;

            // Close import modal
            closeImportModal();

            // Open mapping modal
            openMappingModal();

            // Populate mapping modal
            populateMappingModal();
        } else {
            showToast(data.error || 'Błąd podczas przesyłania pliku', 'error');
            // Reset upload area
            uploadArea.innerHTML = `
                <svg width="48" height="48" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M.5 9.9a.5.5 0 01.5.5v2.5a1 1 0 001 1h12a1 1 0 001-1v-2.5a.5.5 0 011 0v2.5a2 2 0 01-2 2H2a2 2 0 01-2-2v-2.5a.5.5 0 01.5-.5z"/>
                    <path d="M7.646 1.146a.5.5 0 01.708 0l3 3a.5.5 0 01-.708.708L8.5 2.707V11.5a.5.5 0 01-1 0V2.707L5.354 4.854a.5.5 0 11-.708-.708l3-3z"/>
                </svg>
                <p>Kliknij lub przeciągnij plik CSV</p>
                <input type="file" id="csvFileInput" accept=".csv" style="display:none;">
                <button type="button" class="btn btn-secondary btn-sm" onclick="document.getElementById('csvFileInput').click()">
                    Wybierz plik
                </button>
                <p class="upload-hint">
                    <a href="/static/uploads/csv/templates/product_import_template.csv" download>
                        Pobierz szablon CSV
                    </a>
                </p>
            `;
            // Re-setup drag and drop
            setupDragAndDrop();
            const fileInput = document.getElementById('csvFileInput');
            fileInput.addEventListener('change', handleFileSelect);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Wystąpił błąd podczas przesyłania pliku', 'error');
        // Reset upload area
        uploadArea.innerHTML = `
            <svg width="48" height="48" viewBox="0 0 16 16" fill="currentColor">
                <path d="M.5 9.9a.5.5 0 01.5.5v2.5a1 1 0 001 1h12a1 1 0 001-1v-2.5a.5.5 0 011 0v2.5a2 2 0 01-2 2H2a2 2 0 01-2-2v-2.5a.5.5 0 01.5-.5z"/>
                <path d="M7.646 1.146a.5.5 0 01.708 0l3 3a.5.5 0 01-.708.708L8.5 2.707V11.5a.5.5 0 01-1 0V2.707L5.354 4.854a.5.5 0 11-.708-.708l3-3z"/>
            </svg>
            <p>Kliknij lub przeciągnij plik CSV</p>
            <input type="file" id="csvFileInput" accept=".csv" style="display:none;">
            <button type="button" class="btn btn-secondary btn-sm" onclick="document.getElementById('csvFileInput').click()">
                Wybierz plik
            </button>
            <p class="upload-hint">
                <a href="/static/uploads/csv/templates/product_import_template.csv" download>
                    Pobierz szablon CSV
                </a>
            </p>
        `;
        // Re-setup drag and drop
        setupDragAndDrop();
        const fileInput = document.getElementById('csvFileInput');
        fileInput.addEventListener('change', handleFileSelect);
    });
}

// =============================================
// MAPPING MODAL POPULATION
// =============================================

/**
 * Populate Mapping Modal with CSV Data
 */
function populateMappingModal() {
    // Just populate preview table with column mapping dropdowns
    populatePreviewTable();

    // Setup event listener for "Pomiń pierwszy wiersz" checkbox
    const hasHeadersCheckbox = document.getElementById('csvHasHeaders');
    if (hasHeadersCheckbox) {
        hasHeadersCheckbox.addEventListener('change', function() {
            toggleFirstRowStyle();
        });
    }

    // Setup event listener for "Kolumna główna" dropdown
    const matchColumnSelect = document.getElementById('matchColumn');
    if (matchColumnSelect) {
        matchColumnSelect.addEventListener('change', function() {
            highlightMatchColumn();
        });
    }

    // Setup event listeners for column mapping dropdowns (re-highlight on change)
    const mappingSelects = document.querySelectorAll('.column-mapping-select');
    mappingSelects.forEach(select => {
        select.addEventListener('change', function() {
            highlightMatchColumn();
        });
    });
}

/**
 * Generate mapping select options HTML
 */
function getMappingOptions(suggestedField) {
    const fields = [
        ['', '-- Pomiń --'],
        ['name', 'Nazwa produktu'],
        ['sku', 'SKU'],
        ['ean', 'EAN'],
        ['category_id', 'Kategoria'],
        ['manufacturer', 'Producent'],
        ['series', 'Seria'],
        ['product_type', 'Typ produktu'],
        ['sale_price', 'Cena sprzedaży'],
        ['purchase_price', 'Cena zakupu'],
        ['purchase_price_pln', 'Cena zakupu (PLN)'],
        ['purchase_currency', 'Waluta'],
        ['margin', 'Marża (%)'],
        ['quantity', 'Ilość'],
        ['length', 'Długość'],
        ['width', 'Szerokość'],
        ['height', 'Wysokość'],
        ['weight', 'Waga'],
        ['supplier_id', 'Dostawca'],
        ['tags', 'Tagi'],
        ['description', 'Opis'],
        ['is_active', 'Aktywny'],
        ['variant_group', 'Grupa wariantów']
    ];
    return fields.map(([val, label]) =>
        `<option value="${val}" ${suggestedField === val ? 'selected' : ''}>${label}</option>`
    ).join('');
}

/**
 * Populate CSV Preview Table with column mapping dropdowns
 */
function populatePreviewTable() {
    const container = document.getElementById('csvPreviewTable');

    // === Desktop: Table view ===
    let html = '<table class="csv-preview-table">';
    html += '<thead>';
    html += '<tr class="csv-column-names-row">';
    currentColumns.forEach(column => {
        html += `<th>${column}</th>`;
    });
    html += '</tr>';
    html += '<tr class="column-mapping-row">';
    currentColumns.forEach((column, index) => {
        const suggestedField = suggestedMapping[column] || '';
        html += `<th>
            <select class="column-mapping-select" id="mapping_${index}" data-csv-column="${column}">
                ${getMappingOptions(suggestedField)}
            </select>
        </th>`;
    });
    html += '</tr>';
    html += '</thead>';
    html += '<tbody>';
    currentPreviewRows.forEach((row, rowIndex) => {
        const rowClass = rowIndex === 0 ? 'first-row-header' : '';
        html += `<tr class="${rowClass}">`;
        currentColumns.forEach((column, colIndex) => {
            const value = row[column] || '';
            html += `<td data-col-index="${colIndex}">${value}</td>`;
        });
        html += '</tr>';
    });
    html += '</tbody>';
    html += '</table>';

    // === Mobile: Card view ===
    html += '<div class="csv-preview-cards">';
    currentColumns.forEach((column, index) => {
        const suggestedField = suggestedMapping[column] || '';
        const values = currentPreviewRows.map(row => row[column] || '').filter(v => v);
        html += `<div class="csv-column-card">
            <div class="csv-column-card-header">${column}</div>
            <select class="column-mapping-select csv-card-select" id="mapping_card_${index}" data-csv-column="${column}"
                    onchange="syncMappingSelect(${index}, this.value, 'card')">
                ${getMappingOptions(suggestedField)}
            </select>
            <div class="csv-column-card-preview">
                ${values.slice(0, 3).map(v => `<span class="csv-card-value">${v}</span>`).join('')}
            </div>
        </div>`;
    });
    html += '</div>';

    container.innerHTML = html;

    // Sync desktop selects with card selects on change
    container.querySelectorAll('table .column-mapping-select').forEach((sel, index) => {
        sel.addEventListener('change', function() {
            syncMappingSelect(index, this.value, 'table');
        });
    });

    // Apply initial styling based on checkbox state
    toggleFirstRowStyle();

    // Highlight match column
    highlightMatchColumn();
}

/**
 * Keep table and card mapping selects in sync
 */
function syncMappingSelect(index, value, source) {
    const tableSelect = document.getElementById(`mapping_${index}`);
    const cardSelect = document.getElementById(`mapping_card_${index}`);
    if (source === 'card' && tableSelect) tableSelect.value = value;
    if (source === 'table' && cardSelect) cardSelect.value = value;
    highlightMatchColumn();
}

/**
 * Toggle first row styling based on "Pomiń pierwszy wiersz" checkbox
 */
function toggleFirstRowStyle() {
    const hasHeadersCheckbox = document.getElementById('csvHasHeaders');
    const firstRow = document.querySelector('.csv-preview-table tbody tr.first-row-header');

    if (!firstRow) return;

    if (hasHeadersCheckbox && hasHeadersCheckbox.checked) {
        // Add "skipped" class to show it will be ignored
        firstRow.classList.add('row-skipped');
    } else {
        // Remove "skipped" class - it will be imported
        firstRow.classList.remove('row-skipped');
    }
}

/**
 * Highlight the match column (SKU/ID/EAN) in orange
 */
function highlightMatchColumn() {
    const matchColumnSelect = document.getElementById('matchColumn');
    if (!matchColumnSelect) return;

    const matchField = matchColumnSelect.value; // 'id', 'sku', or 'ean'

    // Remove previous highlights
    document.querySelectorAll('.csv-preview-table th, .csv-preview-table td').forEach(cell => {
        cell.classList.remove('match-column-highlight');
    });

    // Find which column index has the match field mapped
    const mappingSelects = document.querySelectorAll('.column-mapping-select');
    let matchColIndex = -1;

    mappingSelects.forEach((select, index) => {
        if (select.value === matchField) {
            matchColIndex = index;
        }
    });

    if (matchColIndex === -1) return;

    // Highlight the column (header rows + data cells)
    // Header row 1 (CSV column names)
    const headerRow1 = document.querySelector('.csv-column-names-row');
    if (headerRow1) {
        const headerCells1 = headerRow1.querySelectorAll('th');
        if (headerCells1[matchColIndex]) {
            headerCells1[matchColIndex].classList.add('match-column-highlight');
        }
    }

    // Header row 2 (mapping dropdowns)
    const headerRow2 = document.querySelector('.column-mapping-row');
    if (headerRow2) {
        const headerCells2 = headerRow2.querySelectorAll('th');
        if (headerCells2[matchColIndex]) {
            headerCells2[matchColIndex].classList.add('match-column-highlight');
        }
    }

    // Data cells
    document.querySelectorAll(`.csv-preview-table tbody td[data-col-index="${matchColIndex}"]`).forEach(cell => {
        cell.classList.add('match-column-highlight');
    });
}

// =============================================
// START IMPORT
// =============================================

/**
 * Start CSV Import
 */
function startCsvImport() {
    // Get has_headers
    const hasHeaders = document.getElementById('csvHasHeaders').checked;

    // Get skip_empty_values
    const skipEmptyValues = document.getElementById('skipEmptyValues').checked;

    // Get match_column
    const matchColumn = document.getElementById('matchColumn').value;

    // Get column mapping
    const columnMapping = {};
    const mappingSelects = document.querySelectorAll('[id^="mapping_"]');

    mappingSelects.forEach(select => {
        const csvColumn = select.getAttribute('data-csv-column');
        const productField = select.value;

        if (productField) {
            columnMapping[csvColumn] = productField;
        }
    });

    // Validate: name is required
    const hasName = Object.values(columnMapping).includes('name');
    if (!hasName) {
        showToast('Pole "Nazwa" jest wymagane. Zmapuj przynajmniej jedną kolumnę na pole "name".', 'error');
        return;
    }

    // Validate: no duplicate field mappings
    const fieldValues = Object.values(columnMapping);
    const seen = {};
    const duplicates = [];
    fieldValues.forEach(v => {
        if (seen[v]) duplicates.push(v);
        else seen[v] = true;
    });
    if (duplicates.length > 0) {
        const dupNames = [...new Set(duplicates)].map(d => translateColumnName(d)).join(', ');
        showToast(`Zduplikowane mapowanie pól: ${dupNames}. Każde pole może być przypisane tylko raz.`, 'error');
        return;
    }

    // Close mapping modal
    closeMappingModal();

    // Open progress modal
    openProgressModal();

    // Send start import request
    fetch('/admin/imports/csv/start', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify({
            temp_file_path: currentTempFilePath,
            has_headers: hasHeaders,
            skip_empty_values: skipEmptyValues,
            match_column: matchColumn,
            column_mapping: columnMapping,
            total_rows: currentTotalRows,
            filename: currentFileName
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Start polling for progress
            startProgressPolling(data.import_id);
        } else {
            showToast(data.error || 'Błąd podczas rozpoczynania importu', 'error');
            closeProgressModal();
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Wystąpił błąd podczas rozpoczynania importu', 'error');
        closeProgressModal();
    });
}

// =============================================
// PROGRESS POLLING
// =============================================

/**
 * Start Progress Polling
 */
function startProgressPolling(importId) {
    // Poll every 1 second
    importPollingInterval = setInterval(() => {
        pollImportProgress(importId);
    }, 1000);
}

/**
 * Poll Import Progress
 */
function pollImportProgress(importId) {
    fetch(`/admin/imports/csv/status/${importId}`, {
        method: 'GET',
        headers: {
            'X-CSRFToken': getCsrfToken()
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            const importData = data;

            // Update progress UI
            updateProgressUI(importData);

            // Check if import is finished
            if (importData.status === 'completed' || importData.status === 'partial' || importData.status === 'failed') {
                // Stop polling
                clearInterval(importPollingInterval);

                // Show final message
                setTimeout(() => {
                    closeProgressModal();

                    if (importData.status === 'completed') {
                        showToast(`Import zakończony! Zaimportowano ${importData.successful_rows} produktów.`, 'success');
                        // Refresh products list
                        if (typeof refreshProductsList === 'function') {
                            refreshProductsList();
                        } else {
                            window.location.reload();
                        }
                    } else if (importData.status === 'partial') {
                        showToast(`Import częściowy: ${importData.successful_rows} OK, ${importData.failed_rows} błędów. Sprawdź historię importów.`, 'warning');
                        // Open import modal to show history
                        openImportModal();
                        loadImportHistory();
                    } else {
                        // Failed - show error details
                        showToast(`Import nieudany: ${importData.failed_rows}/${importData.total_rows} wierszy z błędami. Sprawdź historię importów.`, 'error');
                        // Open import modal to show history
                        openImportModal();
                        loadImportHistory();
                    }
                }, 1000);
            }
        } else {
            clearInterval(importPollingInterval);
            showToast(data.error || 'Błąd podczas pobierania statusu importu', 'error');
            closeProgressModal();
        }
    })
    .catch(error => {
        console.error('Error:', error);
        clearInterval(importPollingInterval);
        showToast('Wystąpił błąd podczas sprawdzania statusu importu', 'error');
        closeProgressModal();
    });
}

/**
 * Update Progress UI
 */
function updateProgressUI(importData) {
    const progressText = document.getElementById('progressText');
    const progressBar = document.getElementById('progressBar');
    const progressPercent = document.getElementById('progressPercent');

    progressText.textContent = `Przetwarzanie: ${importData.processed_rows} / ${importData.total_rows}`;
    progressBar.style.width = `${importData.progress_percent}%`;
    progressPercent.textContent = `${importData.progress_percent}%`;
}

// =============================================
// IMPORT HISTORY
// =============================================

/**
 * Load Import History
 */
function loadImportHistory() {
    const container = document.getElementById('importHistoryTable');
    container.innerHTML = '<p class="text-muted">Ładowanie...</p>';

    fetch('/admin/imports/csv/history', {
        method: 'GET',
        headers: {
            'X-CSRFToken': getCsrfToken()
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            if (data.imports.length === 0) {
                container.innerHTML = '<p class="text-muted">Brak historii importów</p>';
            } else {
                renderImportHistory(data.imports);
            }
        } else {
            container.innerHTML = '<p class="text-danger">Błąd podczas ładowania historii</p>';
        }
    })
    .catch(error => {
        console.error('Error:', error);
        container.innerHTML = '<p class="text-danger">Błąd podczas ładowania historii</p>';
    });
}

/**
 * Render Import History Table
 */
function renderImportHistory(imports) {
    const container = document.getElementById('importHistoryTable');

    function getStatus(imp) {
        const statusClass = imp.status === 'completed' ? 'status-success' :
                           imp.status === 'partial' ? 'status-warning' :
                           imp.status === 'failed' ? 'status-error' : 'status-info';
        const statusText = imp.status === 'completed' ? 'Zakończony' :
                          imp.status === 'partial' ? 'Częściowy' :
                          imp.status === 'failed' ? 'Błąd' :
                          imp.status === 'processing' ? 'W toku' : 'Oczekuje';
        return { statusClass, statusText };
    }

    // Desktop: Table
    let html = '<table class="import-history-table">';
    html += '<thead><tr>';
    html += '<th>Nazwa pliku</th>';
    html += '<th>Produkty</th>';
    html += '<th>Status</th>';
    html += '<th>Data</th>';
    html += '<th></th>';
    html += '</tr></thead>';
    html += '<tbody>';
    imports.forEach(imp => {
        const { statusClass, statusText } = getStatus(imp);
        const hasErrors = imp.failed_rows > 0 && imp.error_log && imp.error_log.length > 0;
        html += `<tr>`;
        html += `<td>${imp.filename}</td>`;
        html += `<td>${imp.successful_rows} / ${imp.total_rows}</td>`;
        html += `<td><span class="status-badge ${statusClass}">${statusText}</span></td>`;
        html += `<td>${formatDate(imp.created_at)}</td>`;
        html += `<td>${hasErrors ? `<button class="btn-error-details" onclick="toggleErrorDetails(${imp.id})">Błędy (${imp.failed_rows})</button>` : ''}</td>`;
        html += `</tr>`;
        if (hasErrors) {
            html += `<tr class="error-details-row" id="error-details-${imp.id}" style="display:none;">`;
            html += `<td colspan="5">${renderErrorLog(imp.error_log)}</td>`;
            html += `</tr>`;
        }
    });
    html += '</tbody></table>';

    // Mobile: Cards
    html += '<div class="import-history-cards">';
    imports.forEach(imp => {
        const { statusClass, statusText } = getStatus(imp);
        const hasErrors = imp.failed_rows > 0 && imp.error_log && imp.error_log.length > 0;
        html += `<div class="import-history-card">
            <div class="import-card-top">
                <span class="import-card-filename">${imp.filename}</span>
                <span class="status-badge ${statusClass}">${statusText}</span>
            </div>
            <div class="import-card-bottom">
                <span class="import-card-count">${imp.successful_rows} / ${imp.total_rows} produktów</span>
                <span class="import-card-date">${formatDate(imp.created_at)}</span>
            </div>
            ${hasErrors ? `
                <button class="btn-error-details" onclick="toggleErrorDetails(${imp.id}, true)">Pokaż błędy (${imp.failed_rows})</button>
                <div class="error-details-card" id="error-details-card-${imp.id}" style="display:none;">
                    ${renderErrorLog(imp.error_log)}
                </div>
            ` : ''}
        </div>`;
    });
    html += '</div>';

    container.innerHTML = html;
}

/**
 * Format Date
 */
function formatDate(isoString) {
    if (!isoString) return '-';
    const date = new Date(isoString);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${year}-${month}-${day} ${hours}:${minutes}`;
}

// =============================================
// UTILITY
// =============================================

/**
 * Show Toast Notification - delegates to global showToast from toast.js
 */
function showToast(message, type = 'info') {
    if (typeof window.showToast === 'function' && window.showToast !== showToast) {
        window.showToast(message, type);
        return;
    }

    // Fallback: create toast element if global not available
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        bottom: 24px;
        right: 24px;
        background: ${type === 'success' ? '#4CAF50' : type === 'error' ? '#f44336' : type === 'warning' ? '#FF9800' : '#2196F3'};
        color: white;
        padding: 12px 20px;
        border-radius: 4px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        z-index: 10002;
        font-size: 14px;
        font-weight: 500;
        max-width: 400px;
    `;

    document.body.appendChild(toast);

    // Auto-remove after 4 seconds
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s';
        setTimeout(() => {
            document.body.removeChild(toast);
        }, 300);
    }, 4000);
}

// =============================================
// ERROR DETAILS
// =============================================

/**
 * Render Error Log as HTML table
 */
function renderErrorLog(errorLog) {
    if (!errorLog || errorLog.length === 0) return '';

    let html = '<div class="error-log-container">';
    html += '<table class="error-log-table">';
    html += '<thead><tr><th>Wiersz</th><th>Błąd</th><th>Dane</th></tr></thead>';
    html += '<tbody>';
    errorLog.forEach(entry => {
        const rowData = entry.data || {};
        // Show first 3 non-empty values as context
        const dataPreview = Object.entries(rowData)
            .filter(([, v]) => v && String(v).trim())
            .slice(0, 3)
            .map(([k, v]) => `${k}: ${String(v).substring(0, 30)}`)
            .join(', ');
        html += `<tr>`;
        html += `<td class="error-row-num">${entry.row}</td>`;
        html += `<td class="error-message">${escapeHtml(entry.error)}</td>`;
        html += `<td class="error-data">${escapeHtml(dataPreview)}</td>`;
        html += `</tr>`;
    });
    html += '</tbody></table>';
    html += '</div>';
    return html;
}

/**
 * Toggle Error Details visibility
 */
function toggleErrorDetails(importId, isCard = false) {
    if (isCard) {
        const el = document.getElementById(`error-details-card-${importId}`);
        if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
    } else {
        const el = document.getElementById(`error-details-${importId}`);
        if (el) el.style.display = el.style.display === 'none' ? 'table-row' : 'none';
    }
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

console.log('[CSV IMPORT] Module loaded successfully');
