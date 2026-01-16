/**
 * Feedback Builder
 * Handles drag & drop, auto-save, and question management
 */

let builderConfig = {
    surveyId: null,
    csrfToken: null,
    surveyToken: null
};

let autoSaveInterval = null;
let previewUpdateTimeout = null;
let isDirty = false;
let lastSaveTime = null;

/**
 * Initialize the builder
 */
function initFeedbackBuilder(config) {
    builderConfig = config;

    // Setup dropdown menu
    setupDropdownMenu();

    // Setup drag and drop
    setupDragAndDrop();

    // Setup preview header live update
    setupPreviewUpdates();

    // Setup auto-save (every 60 seconds)
    autoSaveInterval = setInterval(autoSave, 60000);

    // Mark dirty on any input change
    document.querySelectorAll('.builder-sidebar input, .builder-sidebar textarea, .question-card input, .question-card textarea').forEach(el => {
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
}

/**
 * Mark survey as dirty (unsaved changes)
 */
function markDirty() {
    isDirty = true;
}

/**
 * Setup dropdown menu for adding questions
 */
function setupDropdownMenu() {
    const btn = document.getElementById('addQuestionBtn');
    const menu = document.getElementById('addQuestionMenu');

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
 * Setup drag and drop for questions
 */
function setupDragAndDrop() {
    const container = document.getElementById('questionsContainer');
    if (!container) return;

    container.addEventListener('dragstart', handleDragStart);
    container.addEventListener('dragend', handleDragEnd);
    container.addEventListener('dragover', handleDragOver);
    container.addEventListener('drop', handleDrop);

    // Make questions draggable
    document.querySelectorAll('.question-card').forEach(question => {
        question.setAttribute('draggable', 'true');
    });
}

let draggedElement = null;

function handleDragStart(e) {
    if (!e.target.classList.contains('question-card')) return;

    draggedElement = e.target;
    e.target.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
}

function handleDragEnd(e) {
    if (draggedElement) {
        draggedElement.classList.remove('dragging');
        draggedElement = null;
    }

    document.querySelectorAll('.question-card').forEach(question => {
        question.classList.remove('drag-over');
    });

    markDirty();
}

function handleDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';

    const question = e.target.closest('.question-card');
    if (question && question !== draggedElement) {
        document.querySelectorAll('.question-card').forEach(q => q.classList.remove('drag-over'));
        question.classList.add('drag-over');
    }
}

function handleDrop(e) {
    e.preventDefault();

    const targetQuestion = e.target.closest('.question-card');
    if (!targetQuestion || !draggedElement || targetQuestion === draggedElement) return;

    const container = document.getElementById('questionsContainer');
    const questions = [...container.querySelectorAll('.question-card')];
    const draggedIndex = questions.indexOf(draggedElement);
    const targetIndex = questions.indexOf(targetQuestion);

    if (draggedIndex < targetIndex) {
        targetQuestion.parentNode.insertBefore(draggedElement, targetQuestion.nextSibling);
    } else {
        targetQuestion.parentNode.insertBefore(draggedElement, targetQuestion);
    }

    targetQuestion.classList.remove('drag-over');
    markDirty();
}

/**
 * Setup live preview updates for name and description
 */
function setupPreviewUpdates() {
    const nameInput = document.getElementById('surveyName');
    const descriptionInput = document.getElementById('surveyDescription');
    const previewTitle = document.getElementById('previewTitle');
    const previewDescription = document.getElementById('previewDescription');

    if (!nameInput || !previewTitle) return;

    function updatePreview() {
        clearTimeout(previewUpdateTimeout);
        previewUpdateTimeout = setTimeout(() => {
            previewTitle.textContent = nameInput.value || '';
            if (previewDescription) {
                previewDescription.textContent = descriptionInput ? descriptionInput.value : '';
            }
        }, 500);
    }

    nameInput.addEventListener('input', updatePreview);
    if (descriptionInput) {
        descriptionInput.addEventListener('input', updatePreview);
    }
}

/**
 * Toggle settings accordion on mobile
 */
function toggleSettingsAccordion(btn) {
    const accordion = btn.closest('.sidebar-settings-accordion');
    accordion.classList.toggle('expanded');
    btn.classList.toggle('expanded');
}

/**
 * Add a new question
 */
function addQuestion(type) {
    const container = document.getElementById('questionsContainer');
    const emptyState = document.getElementById('emptyQuestions');

    if (emptyState) {
        emptyState.style.display = 'none';
    }

    const questionHtml = getQuestionTemplate(type);
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = questionHtml;
    const newQuestion = tempDiv.firstElementChild;

    container.appendChild(newQuestion);
    newQuestion.setAttribute('draggable', 'true');

    // Close dropdown
    document.getElementById('addQuestionMenu').classList.remove('show');

    // Setup input listeners for new question
    newQuestion.querySelectorAll('input, textarea').forEach(el => {
        el.addEventListener('change', markDirty);
        el.addEventListener('input', markDirty);
    });

    markDirty();
    showToast('Pytanie dodane', 'success');
}

/**
 * Get HTML template for a question type
 */
function getQuestionTemplate(type) {
    const typeLabels = {
        'section_header': 'Nagłówek',
        'text': 'Tekst',
        'rating_scale': 'Ocena 1-5',
        'rating_10': 'Ocena 1-10',
        'emoji_rating': 'Emoji',
        'yes_no': 'Tak/Nie',
        'yes_no_comment': 'Tak/Nie + komentarz',
        'multiple_choice': 'Wybór jednokrotny',
        'checkbox_list': 'Wybór wielokrotny',
        'textarea': 'Odpowiedź tekstowa'
    };

    const isDisplayOnly = ['section_header', 'text'].includes(type);

    let bodyContent = '';

    if (type === 'section_header') {
        bodyContent = `
            <input type="text" class="form-input question-content" placeholder="Nagłówek sekcji (np. Sekcja 1: Zamówienia Exclusive)">
        `;
    } else if (type === 'text') {
        bodyContent = `
            <textarea class="form-textarea question-content" rows="2" placeholder="Tekst opisowy (np. instrukcje dla użytkownika)"></textarea>
        `;
    } else if (['multiple_choice', 'checkbox_list'].includes(type)) {
        const marker = type === 'multiple_choice' ? '&#9675;' : '&#9744;';
        bodyContent = `
            <input type="text" class="form-input question-content" placeholder="Treść pytania">
            <div class="options-editor">
                <label>Opcje wyboru:</label>
                <div class="options-list">
                    <div class="option-item">
                        <span class="option-marker">${marker}</span>
                        <input type="text" class="form-input option-input" value="Opcja 1" placeholder="Opcja">
                        <button type="button" class="btn-remove-option" onclick="removeOption(this)">
                            <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                                <path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708z"/>
                            </svg>
                        </button>
                    </div>
                    <div class="option-item">
                        <span class="option-marker">${marker}</span>
                        <input type="text" class="form-input option-input" value="Opcja 2" placeholder="Opcja">
                        <button type="button" class="btn-remove-option" onclick="removeOption(this)">
                            <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                                <path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708z"/>
                            </svg>
                        </button>
                    </div>
                </div>
                <button type="button" class="btn btn-sm btn-outline" onclick="addOption(this)">
                    + Dodaj opcję
                </button>
            </div>
        `;
    } else {
        // All other types with preview
        let previewHtml = '';

        if (type === 'rating_scale') {
            previewHtml = `
                <div class="preview-stars">
                    <span class="star">&#9733;</span>
                    <span class="star">&#9733;</span>
                    <span class="star">&#9733;</span>
                    <span class="star">&#9733;</span>
                    <span class="star">&#9733;</span>
                </div>
            `;
        } else if (type === 'rating_10') {
            let nums = '';
            for (let i = 1; i <= 10; i++) {
                nums += `<span class="rating-num">${i}</span>`;
            }
            previewHtml = `<div class="preview-rating-10">${nums}</div>`;
        } else if (type === 'emoji_rating') {
            previewHtml = `
                <div class="preview-emoji">
                    <span class="emoji">&#128577;</span>
                    <span class="emoji">&#128528;</span>
                    <span class="emoji">&#128578;</span>
                    <span class="emoji">&#128512;</span>
                    <span class="emoji">&#129321;</span>
                </div>
            `;
        } else if (type === 'yes_no') {
            previewHtml = `
                <div class="preview-yes-no">
                    <span class="btn-preview btn-yes">Tak</span>
                    <span class="btn-preview btn-no">Nie</span>
                </div>
            `;
        } else if (type === 'yes_no_comment') {
            previewHtml = `
                <div class="preview-yes-no-comment">
                    <div class="preview-yes-no">
                        <span class="btn-preview btn-yes">Tak</span>
                        <span class="btn-preview btn-no">Nie</span>
                    </div>
                    <div class="preview-comment-box">+ pole komentarza</div>
                </div>
            `;
        } else if (type === 'textarea') {
            previewHtml = `
                <div class="preview-textarea">
                    <div class="textarea-placeholder">Pole tekstowe dla odpowiedzi</div>
                </div>
            `;
        }

        bodyContent = `
            <input type="text" class="form-input question-content" placeholder="Treść pytania">
            <div class="question-preview">
                ${previewHtml}
            </div>
        `;
    }

    const requiredToggle = isDisplayOnly ? '' : `
        <label class="required-toggle" title="Pytanie wymagane">
            <input type="checkbox" class="question-required">
            <span class="required-label">Wymagane</span>
        </label>
    `;

    return `
        <div class="question-card" data-question-type="${type}">
            <div class="question-header">
                <div class="question-drag-handle">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                        <path d="M7 2a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zM7 5a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zM7 8a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm-3 3a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm-3 3a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0z"/>
                    </svg>
                </div>
                <span class="question-type-label">${typeLabels[type]}</span>
                ${requiredToggle}
                <button type="button" class="btn-delete-question" onclick="deleteQuestion(this)">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                        <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/>
                        <path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/>
                    </svg>
                </button>
            </div>
            <div class="question-body">
                ${bodyContent}
            </div>
        </div>
    `;
}

/**
 * Delete a question
 */
function deleteQuestion(btn) {
    const card = btn.closest('.question-card');
    card.remove();
    markDirty();
    showToast('Pytanie usunięte', 'info');

    // Show empty state if no questions
    const container = document.getElementById('questionsContainer');
    if (container.children.length === 0) {
        const emptyState = document.getElementById('emptyQuestions');
        if (emptyState) {
            emptyState.style.display = 'block';
        }
    }
}

/**
 * Add option to multiple choice / checkbox question
 */
function addOption(btn) {
    const editor = btn.closest('.options-editor');
    const list = editor.querySelector('.options-list');
    const questionCard = btn.closest('.question-card');
    const type = questionCard.dataset.questionType;
    const marker = type === 'multiple_choice' ? '&#9675;' : '&#9744;';

    const optionHtml = `
        <div class="option-item">
            <span class="option-marker">${marker}</span>
            <input type="text" class="form-input option-input" placeholder="Opcja">
            <button type="button" class="btn-remove-option" onclick="removeOption(this)">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708z"/>
                </svg>
            </button>
        </div>
    `;

    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = optionHtml;
    const newOption = tempDiv.firstElementChild;
    list.appendChild(newOption);

    // Focus new input
    newOption.querySelector('.option-input').focus();

    markDirty();
}

/**
 * Remove option from multiple choice / checkbox question
 */
function removeOption(btn) {
    const optionItem = btn.closest('.option-item');
    const list = optionItem.closest('.options-list');

    // Keep at least 2 options
    if (list.children.length <= 2) {
        showToast('Wymagane minimum 2 opcje', 'error');
        return;
    }

    optionItem.remove();
    markDirty();
}

/**
 * Collect survey data for saving
 */
function collectSurveyData() {
    const data = {
        name: document.getElementById('surveyName').value,
        description: document.getElementById('surveyDescription').value,
        closes_at: document.getElementById('closesAt').value || null,
        is_anonymous: document.getElementById('isAnonymous').checked,
        allow_multiple_responses: document.getElementById('allowMultiple').checked,
        questions: []
    };

    const questionCards = document.querySelectorAll('.question-card');
    questionCards.forEach((card, index) => {
        const questionData = {
            id: card.dataset.questionId || null,
            type: card.dataset.questionType,
            content: card.querySelector('.question-content')?.value || '',
            is_required: card.querySelector('.question-required')?.checked || false,
            options: null
        };

        // Collect options for multiple choice / checkbox
        if (['multiple_choice', 'checkbox_list'].includes(questionData.type)) {
            const optionInputs = card.querySelectorAll('.option-input');
            questionData.options = Array.from(optionInputs).map(input => input.value).filter(v => v.trim());
        }

        data.questions.push(questionData);
    });

    return data;
}

/**
 * Save survey
 */
async function saveSurvey() {
    const data = collectSurveyData();

    try {
        const response = await fetch(`/admin/feedback/${builderConfig.surveyId}/save`, {
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
            showToast('Ankieta zapisana', 'success');
        } else {
            showToast(`Błąd: ${result.error}`, 'error');
        }
    } catch (error) {
        console.error('Save error:', error);
        showToast('Błąd podczas zapisywania', 'error');
    }
}

/**
 * Auto-save if dirty
 */
async function autoSave() {
    if (isDirty) {
        await saveSurvey();
    }
}

/**
 * Change survey status
 */
async function changeStatus(action) {
    // Save first
    await saveSurvey();

    try {
        const response = await fetch(`/admin/feedback/${builderConfig.surveyId}/status`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': builderConfig.csrfToken
            },
            body: JSON.stringify({ action: action })
        });

        const result = await response.json();

        if (result.success) {
            // Reload page to update UI
            window.location.reload();
        } else {
            showToast(`Błąd: ${result.error}`, 'error');
        }
    } catch (error) {
        console.error('Status change error:', error);
        showToast('Błąd podczas zmiany statusu', 'error');
    }
}

/**
 * Activate survey
 */
function activateSurvey() {
    changeStatus('activate');
}

/**
 * Close survey
 */
function closeSurvey() {
    changeStatus('close');
}

/**
 * Reopen survey
 */
function reopenSurvey() {
    changeStatus('reopen');
}

/**
 * Copy survey link to clipboard
 */
function copySurveyLink() {
    const url = `${window.location.origin}/feedback/${builderConfig.surveyToken}`;

    navigator.clipboard.writeText(url).then(() => {
        showToast('Link skopiowany do schowka', 'success');
    }).catch(() => {
        // Fallback
        const input = document.createElement('input');
        input.value = url;
        document.body.appendChild(input);
        input.select();
        document.execCommand('copy');
        document.body.removeChild(input);
        showToast('Link skopiowany do schowka', 'success');
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
