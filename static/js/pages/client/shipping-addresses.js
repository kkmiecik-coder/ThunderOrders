// ============================================
// SHIPPING ADDRESSES - JavaScript
// ============================================

// Current step tracker
let currentStep = 1;
let selectedDeliveryType = null;
let selectedCourier = null;

// ============================================
// MODAL MANAGEMENT
// ============================================

function openAddAddressModal() {
    document.getElementById('addAddressModal').classList.add('active');
    resetForm();
}

function closeAddAddressModal() {
    document.getElementById('addAddressModal').classList.remove('active');
    resetForm();
}

function resetForm() {
    document.getElementById('addAddressForm').reset();
    currentStep = 1;
    selectedDeliveryType = null;
    selectedCourier = null;

    // Reset all form steps
    document.querySelectorAll('.form-step').forEach(step => {
        step.classList.remove('active');
    });
    document.getElementById('step1').classList.add('active');

    // Reset step indicators
    updateStepIndicators(1);

    // Hide extra step indicator
    hideExtraStep();

    // Disable next buttons
    const inpostNextBtn = document.getElementById('inpostNextBtn');
    if (inpostNextBtn) {
        inpostNextBtn.disabled = true;
    }
    const orlenNextBtn = document.getElementById('orlenNextBtn');
    if (orlenNextBtn) {
        orlenNextBtn.disabled = true;
    }

    // Clear all form fields
    const allFields = ['inpost_point_id', 'inpost_address', 'inpost_postal_code', 'inpost_city',
                       'orlen_point_id', 'orlen_address', 'orlen_postal_code', 'orlen_city'];
    allFields.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });
}

// ============================================
// EXTRA STEP INDICATOR (4th step for pickup points)
// ============================================

function showExtraStep() {
    const extraElements = document.querySelectorAll('[data-extra]');
    extraElements.forEach(el => {
        el.classList.remove('hidden');
        // Trigger animation after removing hidden
        setTimeout(() => {
            el.classList.add('visible');
        }, 10);
    });
}

function hideExtraStep() {
    const extraElements = document.querySelectorAll('[data-extra]');
    extraElements.forEach(el => {
        el.classList.remove('visible');
        // Wait for animation to complete before hiding
        setTimeout(() => {
            el.classList.add('hidden');
        }, 300);
    });
}

function updateStepIndicators(step, totalSteps = 3) {
    const dots = document.querySelectorAll('.step-dot');
    const lines = document.querySelectorAll('.step-line');

    // Update dots
    dots.forEach((dot, index) => {
        // Skip extra step dot if not visible
        if (dot.hasAttribute('data-extra') && totalSteps < 4) {
            dot.classList.remove('active', 'completed');
            return;
        }

        dot.classList.remove('active', 'completed');
        if (index + 1 < step) {
            dot.classList.add('completed');
        } else if (index + 1 === step) {
            dot.classList.add('active');
        }
    });

    // Update lines (line before step N connects dot N-1 to dot N)
    lines.forEach((line, index) => {
        // Skip extra step line if not visible
        if (line.hasAttribute('data-extra') && totalSteps < 4) {
            line.classList.remove('completed');
            return;
        }

        line.classList.remove('completed');
        // Line at index N is completed if we're past step N+1
        if (index + 2 <= step) {
            line.classList.add('completed');
        }
    });
}

// ============================================
// PROGRESSIVE DISCLOSURE - STEPS NAVIGATION
// ============================================

function goToStep(stepNumber) {
    // Validate current step before moving
    if (!validateCurrentStep()) {
        return;
    }

    // Hide all steps
    document.querySelectorAll('.form-step').forEach(step => {
        step.classList.remove('active');
    });

    // Determine which step to show and total steps based on delivery type
    let targetStepId = null;
    let indicatorStep = stepNumber;
    let totalSteps = selectedDeliveryType === 'pickup_point' ? 4 : 3;

    if (stepNumber === 2) {
        if (selectedDeliveryType === 'pickup_point') {
            targetStepId = 'step2-pickup';
        } else {
            targetStepId = 'step2-home';
        }
    } else if (stepNumber === 3) {
        if (selectedCourier === 'InPost') {
            targetStepId = 'step3-inpost';
        } else if (selectedCourier === 'Orlen Paczka') {
            targetStepId = 'step3-orlen';
        }
    } else if (stepNumber === 4) {
        targetStepId = 'step4';
        indicatorStep = totalSteps; // Summary is the last dot
        generateSummary();
    } else {
        targetStepId = 'step1';
    }

    // Show target step
    if (targetStepId) {
        const targetStep = document.getElementById(targetStepId);
        targetStep.classList.add('active');
        currentStep = stepNumber;
        updateStepIndicators(indicatorStep, totalSteps);
    }
}

function goBack() {
    // Determine which step to go back to based on current step
    const activeStep = document.querySelector('.form-step.active');
    if (!activeStep) return;

    const activeStepId = activeStep.id;

    // Hide all steps first
    document.querySelectorAll('.form-step').forEach(step => {
        step.classList.remove('active');
    });

    let targetStepId = null;
    let indicatorStep = 1;
    let totalSteps = selectedDeliveryType === 'pickup_point' ? 4 : 3;

    if (activeStepId === 'step2-pickup' || activeStepId === 'step2-home') {
        // Go back to step 1 - reset delivery type selection
        targetStepId = 'step1';
        indicatorStep = 1;
        currentStep = 1;
        totalSteps = 3; // Reset to default 3 steps

        // Reset delivery type radio buttons
        document.querySelectorAll('input[name="address_type"]').forEach(radio => {
            radio.checked = false;
        });
        selectedDeliveryType = null;

        // Hide extra step indicator when going back to step 1
        hideExtraStep();
    } else if (activeStepId === 'step3-inpost' || activeStepId === 'step3-orlen') {
        // Go back to step 2 (courier selection) - reset courier selection
        targetStepId = 'step2-pickup';
        indicatorStep = 2;
        currentStep = 2;

        // Reset courier radio buttons
        document.querySelectorAll('input[name="pickup_courier"]').forEach(radio => {
            radio.checked = false;
        });
        selectedCourier = null;
    } else if (activeStepId === 'step4') {
        // Go back to step 3 or step 2 depending on delivery type
        if (selectedDeliveryType === 'pickup_point') {
            if (selectedCourier === 'InPost') {
                targetStepId = 'step3-inpost';
            } else {
                targetStepId = 'step3-orlen';
            }
            indicatorStep = 3;
            currentStep = 3;
        } else {
            targetStepId = 'step2-home';
            indicatorStep = 2;
            currentStep = 2;
        }
    }

    if (targetStepId) {
        document.getElementById(targetStepId).classList.add('active');
        updateStepIndicators(indicatorStep, totalSteps);
    }
}

function goBackFromSummary() {
    goBack();
}

function validateCurrentStep() {
    if (currentStep === 1) {
        const radioChecked = document.querySelector('input[name="address_type"]:checked');
        if (radioChecked) {
            selectedDeliveryType = radioChecked.value;
        }
        return true;
    } else if (currentStep === 2) {
        if (selectedDeliveryType === 'pickup_point') {
            const courierRadio = document.querySelector('input[name="pickup_courier"]:checked');
            if (!courierRadio) {
                showToastNotification('Wybierz kuriera', 'warning');
                return false;
            }
            selectedCourier = courierRadio.value;
        } else {
            const homeFields = ['home_name', 'home_address', 'home_postal_code', 'home_city'];
            for (let fieldId of homeFields) {
                const field = document.getElementById(fieldId);
                if (field && !field.value.trim()) {
                    showToastNotification('Wypełnij wszystkie wymagane pola', 'warning');
                    field.focus();
                    return false;
                }
            }
        }
        return true;
    } else if (currentStep === 3) {
        if (selectedCourier === 'InPost') {
            const inpostFields = ['inpost_point_id', 'inpost_address', 'inpost_postal_code', 'inpost_city'];
            for (let fieldId of inpostFields) {
                const field = document.getElementById(fieldId);
                if (field && !field.value.trim()) {
                    showToastNotification('Wypełnij wszystkie wymagane pola', 'warning');
                    field.focus();
                    return false;
                }
            }
        } else if (selectedCourier === 'Orlen Paczka') {
            const orlenFields = ['orlen_point_id', 'orlen_address', 'orlen_postal_code', 'orlen_city'];
            for (let fieldId of orlenFields) {
                const field = document.getElementById(fieldId);
                if (field && !field.value.trim()) {
                    showToastNotification('Wypełnij wszystkie wymagane pola', 'warning');
                    field.focus();
                    return false;
                }
            }

            const orlenCode = document.getElementById('orlen_point_id').value;
            if (!/^[A-Za-z0-9]{1,6}$/.test(orlenCode)) {
                showToastNotification('Kod automatu może zawierać tylko litery i cyfry (max 6 znaków)', 'warning');
                return false;
            }
        }
        return true;
    }

    return true;
}

// ============================================
// FORM FIELD VALIDATION (Real-time)
// ============================================

function validateInPostFields() {
    const fields = ['inpost_point_id', 'inpost_address', 'inpost_postal_code', 'inpost_city'];
    const allFilled = fields.every(fieldId => {
        const field = document.getElementById(fieldId);
        return field && field.value.trim() !== '';
    });

    const nextBtn = document.getElementById('inpostNextBtn');
    if (nextBtn) {
        nextBtn.disabled = !allFilled;
    }
}

function validateOrlenFields() {
    const fields = ['orlen_point_id', 'orlen_address', 'orlen_postal_code', 'orlen_city'];
    const allFilled = fields.every(fieldId => {
        const field = document.getElementById(fieldId);
        return field && field.value.trim() !== '';
    });

    const nextBtn = document.getElementById('orlenNextBtn');
    if (nextBtn) {
        nextBtn.disabled = !allFilled;
    }
}

// ============================================
// SUMMARY GENERATION
// ============================================

function generateSummary() {
    const summaryContent = document.getElementById('summaryContent');
    let html = '';

    if (selectedDeliveryType === 'pickup_point') {
        if (selectedCourier === 'InPost') {
            html = `
                <div class="summary-row">
                    <span class="summary-label">Typ dostawy</span>
                    <span class="summary-value">Paczkomat® InPost</span>
                </div>
                <div class="summary-row">
                    <span class="summary-label">Kod paczkomatu</span>
                    <span class="summary-value">${document.getElementById('inpost_point_id').value}</span>
                </div>
                <div class="summary-row">
                    <span class="summary-label">Adres</span>
                    <span class="summary-value">${document.getElementById('inpost_address').value}</span>
                </div>
                <div class="summary-row">
                    <span class="summary-label">Miejscowość</span>
                    <span class="summary-value">${document.getElementById('inpost_postal_code').value} ${document.getElementById('inpost_city').value}</span>
                </div>
            `;
        } else if (selectedCourier === 'Orlen Paczka') {
            html = `
                <div class="summary-row">
                    <span class="summary-label">Typ dostawy</span>
                    <span class="summary-value">Orlen Paczka</span>
                </div>
                <div class="summary-row">
                    <span class="summary-label">Kod automatu</span>
                    <span class="summary-value">${document.getElementById('orlen_point_id').value}</span>
                </div>
                <div class="summary-row">
                    <span class="summary-label">Adres</span>
                    <span class="summary-value">${document.getElementById('orlen_address').value}</span>
                </div>
                <div class="summary-row">
                    <span class="summary-label">Miejscowość</span>
                    <span class="summary-value">${document.getElementById('orlen_postal_code').value} ${document.getElementById('orlen_city').value}</span>
                </div>
            `;
        }
    } else {
        const voivodeship = document.getElementById('home_voivodeship').value;
        html = `
            <div class="summary-row">
                <span class="summary-label">Typ dostawy</span>
                <span class="summary-value">Adres domowy</span>
            </div>
            <div class="summary-row">
                <span class="summary-label">Odbiorca</span>
                <span class="summary-value">${document.getElementById('home_name').value}</span>
            </div>
            <div class="summary-row">
                <span class="summary-label">Adres</span>
                <span class="summary-value">${document.getElementById('home_address').value}</span>
            </div>
            <div class="summary-row">
                <span class="summary-label">Miejscowość</span>
                <span class="summary-value">${document.getElementById('home_postal_code').value} ${document.getElementById('home_city').value}</span>
            </div>
            ${voivodeship ? `
            <div class="summary-row">
                <span class="summary-label">Województwo</span>
                <span class="summary-value">${voivodeship}</span>
            </div>
            ` : ''}
        `;
    }

    summaryContent.innerHTML = html;
}

// ============================================
// FORM SUBMISSION
// ============================================

document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('addAddressForm');
    if (form) {
        form.addEventListener('submit', handleFormSubmit);
    }

    // Auto-advance from step 1 when delivery type is selected
    const deliveryTypeRadios = document.querySelectorAll('input[name="address_type"]');
    deliveryTypeRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            selectedDeliveryType = this.value;

            // Show or hide extra step based on delivery type
            if (selectedDeliveryType === 'pickup_point') {
                showExtraStep();
            } else {
                hideExtraStep();
            }

            // Small delay for visual feedback
            setTimeout(() => {
                goToStep(2);
            }, 200);
        });
    });

    // Auto-advance from step 2 when courier is selected
    const courierRadios = document.querySelectorAll('input[name="pickup_courier"]');
    courierRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            selectedCourier = this.value;
            // Small delay for visual feedback
            setTimeout(() => {
                goToStep(3);
            }, 200);
        });
    });

    // InPost fields validation
    const inpostFields = ['inpost_point_id', 'inpost_address', 'inpost_postal_code', 'inpost_city'];
    inpostFields.forEach(fieldId => {
        const field = document.getElementById(fieldId);
        if (field) {
            field.addEventListener('input', validateInPostFields);
        }
    });

    // InPost code validation - uppercase
    const inpostCodeInput = document.getElementById('inpost_point_id');
    if (inpostCodeInput) {
        inpostCodeInput.addEventListener('input', function(e) {
            e.target.value = e.target.value.toUpperCase();
        });
    }

    // Orlen fields validation
    const orlenFields = ['orlen_point_id', 'orlen_address', 'orlen_postal_code', 'orlen_city'];
    orlenFields.forEach(fieldId => {
        const field = document.getElementById(fieldId);
        if (field) {
            field.addEventListener('input', validateOrlenFields);
        }
    });

    // Orlen code validation - uppercase and alphanumeric only
    const orlenInput = document.getElementById('orlen_point_id');
    if (orlenInput) {
        orlenInput.addEventListener('input', function(e) {
            let value = e.target.value.toUpperCase();
            value = value.replace(/[^A-Z0-9]/g, '');
            value = value.substring(0, 6);
            e.target.value = value;
            validateOrlenFields();
        });
    }

    // NOTE: Modal closing on outside click is intentionally DISABLED
    // Users must use the X button to close the modal
});

async function handleFormSubmit(e) {
    e.preventDefault();

    const data = {
        address_type: selectedDeliveryType,
        is_default: document.getElementById('is_default').checked
    };

    if (selectedDeliveryType === 'pickup_point') {
        data.pickup_courier = selectedCourier;

        if (selectedCourier === 'InPost') {
            data.pickup_point_id = document.getElementById('inpost_point_id').value;
            data.pickup_address = document.getElementById('inpost_address').value;
            data.pickup_postal_code = document.getElementById('inpost_postal_code').value;
            data.pickup_city = document.getElementById('inpost_city').value;
        } else if (selectedCourier === 'Orlen Paczka') {
            data.pickup_point_id = document.getElementById('orlen_point_id').value;
            data.pickup_address = document.getElementById('orlen_address').value;
            data.pickup_postal_code = document.getElementById('orlen_postal_code').value;
            data.pickup_city = document.getElementById('orlen_city').value;
        }
    } else {
        data.shipping_name = document.getElementById('home_name').value;
        data.shipping_address = document.getElementById('home_address').value;
        data.shipping_postal_code = document.getElementById('home_postal_code').value;
        data.shipping_city = document.getElementById('home_city').value;
        data.shipping_voivodeship = document.getElementById('home_voivodeship').value;
        data.shipping_country = 'Polska';
    }

    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');

    try {
        const response = await fetch('/client/shipping/addresses/add', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken || ''
            },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (result.success) {
            showToastNotification(result.message || 'Adres został zapisany', 'success');
            setTimeout(() => {
                window.location.reload();
            }, 500);
        } else {
            showToastNotification(result.message || 'Wystąpił błąd', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showToastNotification('Wystąpił błąd podczas zapisywania adresu', 'error');
    }
}

// ============================================
// ADDRESS CARD ACTIONS
// ============================================

async function setDefaultAddress(addressId) {
    if (!confirm('Czy na pewno chcesz ustawić ten adres jako domyślny?')) {
        return;
    }

    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');

    try {
        const response = await fetch(`/client/shipping/addresses/${addressId}/set-default`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken || ''
            }
        });

        const result = await response.json();

        if (result.success) {
            showToastNotification(result.message || 'Adres został ustawiony jako domyślny', 'success');
            window.location.reload();
        } else {
            showToastNotification(result.message || 'Wystąpił błąd', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showToastNotification('Wystąpił błąd', 'error');
    }
}

async function deleteAddress(addressId) {
    if (!confirm('Czy na pewno chcesz usunąć ten adres?')) {
        return;
    }

    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');

    try {
        const response = await fetch(`/client/shipping/addresses/${addressId}/delete`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken || ''
            }
        });

        const result = await response.json();

        if (result.success) {
            // Smooth removal animation
            const card = document.querySelector(`[data-address-id="${addressId}"]`);
            card.style.opacity = '0';
            card.style.transform = 'scale(0.95)';
            card.style.transition = 'all 0.3s ease';

            setTimeout(() => {
                card.remove();

                // Check if empty
                const remainingCards = document.querySelectorAll('.address-card');
                if (remainingCards.length === 0) {
                    window.location.reload();
                }
            }, 300);

            showToastNotification(result.message || 'Adres został usunięty', 'success');
        } else {
            showToastNotification(result.message || 'Wystąpił błąd', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showToastNotification('Wystąpił błąd', 'error');
    }
}

// ============================================
// HELPER: Toast notification (fallback)
// ============================================

function showToastNotification(message, type) {
    // Check if global showToast exists (from main.js or toast component)
    if (typeof window.showToast === 'function') {
        window.showToast(message, type);
    } else if (typeof window.showFlashMessage === 'function') {
        window.showFlashMessage(message, type);
    } else {
        // Fallback to alert
        alert(message);
    }
}
