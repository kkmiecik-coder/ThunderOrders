/**
 * Order Detail - Admin Panel
 * Handles auto-detect courier, refund modal, timeline auto-scroll
 */

(function() {
    'use strict';

    // ====================
    // COURIER AUTO-DETECT
    // ====================

    /**
     * Handle courier detection response from HTMX
     */
    document.body.addEventListener('htmx:afterSwap', function(evt) {
        if (evt.detail.target.id === 'courierSuggestion') {
            try {
                const response = JSON.parse(evt.detail.xhr.response);
                if (response.courier && response.confidence === 'high') {
                    showCourierSuggestion(response);
                }
            } catch (error) {
                console.error('Error parsing courier detection response:', error);
            }
        }
    });

    /**
     * Show courier suggestion with accept button
     */
    function showCourierSuggestion(data) {
        const container = document.getElementById('courierSuggestion');
        if (!container) return;

        container.innerHTML = `
            <div class="alert alert-info courier-alert">
                <p>Wykryto kurier: <strong>${data.courier}</strong></p>
                <button type="button"
                        class="btn btn-sm btn-primary"
                        onclick="acceptCourierSuggestion('${data.courier}')">
                    Ustaw ${data.courier}
                </button>
                <button type="button"
                        class="btn btn-sm btn-link"
                        onclick="dismissCourierSuggestion()">
                    Odrzuć
                </button>
            </div>
        `;
    }

    /**
     * Accept courier suggestion
     */
    window.acceptCourierSuggestion = function(courier) {
        const courierSelect = document.querySelector('select[name="courier"]');
        if (courierSelect) {
            courierSelect.value = courier;
        }
        dismissCourierSuggestion();
    };

    /**
     * Dismiss courier suggestion
     */
    window.dismissCourierSuggestion = function() {
        const container = document.getElementById('courierSuggestion');
        if (container) {
            container.innerHTML = '';
        }
    };

    // ====================
    // TIMELINE AUTO-SCROLL
    // ====================

    /**
     * Auto-scroll timeline after adding comment
     */
    document.body.addEventListener('htmx:afterSwap', function(evt) {
        if (evt.detail.target.id === 'timeline') {
            // Scroll to top of timeline (newest comment)
            const timeline = document.getElementById('timeline');
            if (timeline) {
                timeline.scrollTo({
                    top: 0,
                    behavior: 'smooth'
                });
            }

            // Clear comment form
            const commentForm = document.querySelector('.comment-form textarea');
            if (commentForm) {
                commentForm.value = '';
            }

            // Show success message
            showToast('Komentarz dodany', 'success');
        }
    });

    // ====================
    // DELETE ORDER CONFIRMATION
    // ====================

    /**
     * Confirm delete order (exposed globally)
     */
    window.confirmDeleteOrder = function(orderId, orderNumber) {
        const confirmation = confirm(
            `Czy na pewno chcesz usunąć zamówienie ${orderNumber}?\n\n` +
            'Ta operacja jest nieodwracalna!'
        );

        if (!confirmation) {
            return;
        }

        // Send DELETE request
        fetch(`/admin/orders/${orderId}/delete`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showToast(`Zamówienie ${orderNumber} zostało usunięte`, 'success');

                // Redirect to orders list after short delay
                setTimeout(() => {
                    window.location.href = '/admin/orders';
                }, 1000);
            } else {
                showToast('Nie udało się usunąć zamówienia', 'error');
            }
        })
        .catch(error => {
            console.error('Delete error:', error);
            showToast('Wystąpił błąd podczas usuwania', 'error');
        });
    };

    // ====================
    // HTMX ERROR HANDLING
    // ====================

    /**
     * Handle HTMX errors
     */
    document.body.addEventListener('htmx:responseError', function(evt) {
        console.error('HTMX error:', evt.detail);
        showToast('Wystąpił błąd podczas przetwarzania żądania', 'error');
    });

    /**
     * Show loading indicator for HTMX requests
     */
    document.body.addEventListener('htmx:beforeRequest', function(evt) {
        const target = evt.detail.target;
        if (target) {
            target.classList.add('htmx-loading');
        }
    });

    document.body.addEventListener('htmx:afterRequest', function(evt) {
        const target = evt.detail.target;
        if (target) {
            target.classList.remove('htmx-loading');
        }
    });

    // ====================
    // UTILITY FUNCTIONS
    // ====================

    /**
     * Get CSRF token
     */
    function getCSRFToken() {
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

    /**
     * Show toast notification
     */
    function showToast(message, type = 'info') {
        if (typeof window.showToast === 'function') {
            window.showToast(message, type);
        } else {
            // Fallback
            const alertClass = type === 'success' ? 'alert-success' :
                             type === 'error' ? 'alert-error' : 'alert-info';

            const toast = document.createElement('div');
            toast.className = `alert ${alertClass} toast-notification`;
            toast.textContent = message;
            toast.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 9999;
                padding: 12px 20px;
                border-radius: 6px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
                animation: slideInRight 0.3s ease-out;
            `;

            document.body.appendChild(toast);

            setTimeout(() => {
                toast.style.animation = 'slideOutRight 0.3s ease-in';
                setTimeout(() => toast.remove(), 300);
            }, 3000);
        }
    }

    // ====================
    // FORM VALIDATION
    // ====================

    /**
     * Validate comment form before submit
     */
    const commentForms = document.querySelectorAll('.comment-form');
    commentForms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const textarea = this.querySelector('textarea[name="comment"]');
            if (textarea && textarea.value.trim() === '') {
                e.preventDefault();
                showToast('Wpisz treść komentarza', 'error');
                textarea.focus();
            }
        });
    });

    /**
     * Validate refund form
     */
    const refundModal = document.getElementById('refundModal');
    const refundForm = refundModal?.querySelector('form');
    if (refundForm) {
        refundForm.addEventListener('submit', function(e) {
            const amountField = this.querySelector('input[name="amount"]');
            const reasonField = this.querySelector('textarea[name="reason"]');

            let isValid = true;

            if (!amountField || !amountField.value || parseFloat(amountField.value) <= 0) {
                isValid = false;
                showToast('Podaj prawidłową kwotę zwrotu', 'error');
            }

            if (!reasonField || reasonField.value.trim().length < 10) {
                isValid = false;
                showToast('Powód zwrotu musi mieć min. 10 znaków', 'error');
            }

            if (!isValid) {
                e.preventDefault();
            }
        });
    }

    // ====================
    // POSTAL CODE -> VOIVODESHIP AUTOCOMPLETE
    // ====================

    /**
     * Polish postal code to voivodeship mapping
     * First 2 digits of postal code determine the voivodeship
     */
    const postalCodeToVoivodeship = {
        // dolnośląskie (50-59)
        '50': 'dolnośląskie', '51': 'dolnośląskie', '52': 'dolnośląskie',
        '53': 'dolnośląskie', '54': 'dolnośląskie', '55': 'dolnośląskie',
        '56': 'dolnośląskie', '57': 'dolnośląskie', '58': 'dolnośląskie', '59': 'dolnośląskie',

        // kujawsko-pomorskie (85-89)
        '85': 'kujawsko-pomorskie', '86': 'kujawsko-pomorskie', '87': 'kujawsko-pomorskie',
        '88': 'kujawsko-pomorskie', '89': 'kujawsko-pomorskie',

        // lubelskie (20-24)
        '20': 'lubelskie', '21': 'lubelskie', '22': 'lubelskie', '23': 'lubelskie', '24': 'lubelskie',

        // lubuskie (65-69)
        '65': 'lubuskie', '66': 'lubuskie', '67': 'lubuskie', '68': 'lubuskie', '69': 'lubuskie',

        // łódzkie (90-99)
        '90': 'łódzkie', '91': 'łódzkie', '92': 'łódzkie', '93': 'łódzkie', '94': 'łódzkie',
        '95': 'łódzkie', '96': 'łódzkie', '97': 'łódzkie', '98': 'łódzkie', '99': 'łódzkie',

        // małopolskie (30-34)
        '30': 'małopolskie', '31': 'małopolskie', '32': 'małopolskie', '33': 'małopolskie', '34': 'małopolskie',

        // mazowieckie (00-09, 26-27)
        '00': 'mazowieckie', '01': 'mazowieckie', '02': 'mazowieckie', '03': 'mazowieckie', '04': 'mazowieckie',
        '05': 'mazowieckie', '06': 'mazowieckie', '07': 'mazowieckie', '08': 'mazowieckie', '09': 'mazowieckie',
        '26': 'mazowieckie', '27': 'mazowieckie',

        // opolskie (45-49)
        '45': 'opolskie', '46': 'opolskie', '47': 'opolskie', '48': 'opolskie', '49': 'opolskie',

        // podkarpackie (35-39)
        '35': 'podkarpackie', '36': 'podkarpackie', '37': 'podkarpackie', '38': 'podkarpackie', '39': 'podkarpackie',

        // podlaskie (15-19)
        '15': 'podlaskie', '16': 'podlaskie', '17': 'podlaskie', '18': 'podlaskie', '19': 'podlaskie',

        // pomorskie (80-84)
        '80': 'pomorskie', '81': 'pomorskie', '82': 'pomorskie', '83': 'pomorskie', '84': 'pomorskie',

        // śląskie (40-44)
        '40': 'śląskie', '41': 'śląskie', '42': 'śląskie', '43': 'śląskie', '44': 'śląskie',

        // świętokrzyskie (25, 28-29)
        '25': 'świętokrzyskie', '28': 'świętokrzyskie', '29': 'świętokrzyskie',

        // warmińsko-mazurskie (10-14)
        '10': 'warmińsko-mazurskie', '11': 'warmińsko-mazurskie', '12': 'warmińsko-mazurskie',
        '13': 'warmińsko-mazurskie', '14': 'warmińsko-mazurskie',

        // wielkopolskie (60-64)
        '60': 'wielkopolskie', '61': 'wielkopolskie', '62': 'wielkopolskie',
        '63': 'wielkopolskie', '64': 'wielkopolskie',

        // zachodniopomorskie (70-78)
        '70': 'zachodniopomorskie', '71': 'zachodniopomorskie', '72': 'zachodniopomorskie',
        '73': 'zachodniopomorskie', '74': 'zachodniopomorskie', '75': 'zachodniopomorskie',
        '76': 'zachodniopomorskie', '77': 'zachodniopomorskie', '78': 'zachodniopomorskie'
    };

    /**
     * Get voivodeship from postal code
     */
    function getVoivodeshipFromPostalCode(postalCode) {
        // Remove any non-digit characters and get first 2 digits
        const cleaned = postalCode.replace(/\D/g, '');
        if (cleaned.length >= 2) {
            const prefix = cleaned.substring(0, 2);
            return postalCodeToVoivodeship[prefix] || null;
        }
        return null;
    }

    /**
     * Initialize postal code autocomplete for shipping address
     */
    const shippingPostalCode = document.getElementById('shippingPostalCode');
    const shippingVoivodeship = document.getElementById('shippingVoivodeship');

    if (shippingPostalCode && shippingVoivodeship) {
        shippingPostalCode.addEventListener('input', function() {
            const voivodeship = getVoivodeshipFromPostalCode(this.value);
            if (voivodeship) {
                shippingVoivodeship.value = voivodeship;
                // Flash animation to indicate autocomplete
                shippingVoivodeship.classList.add('autocompleted');
                setTimeout(() => shippingVoivodeship.classList.remove('autocompleted'), 500);
            }
        });

        // Also check on blur for formatting like "00-000"
        shippingPostalCode.addEventListener('blur', function() {
            const voivodeship = getVoivodeshipFromPostalCode(this.value);
            if (voivodeship && !shippingVoivodeship.value) {
                shippingVoivodeship.value = voivodeship;
            }
        });
    }

    // ====================
    // SHIPMENTS MANAGEMENT
    // ====================

    /**
     * Courier display names mapping
     */
    const courierNames = {
        'inpost': 'InPost',
        'dpd': 'DPD',
        'dhl': 'DHL',
        'gls': 'GLS',
        'poczta_polska': 'Poczta Polska',
        'orlen': 'Orlen Paczka',
        'ups': 'UPS',
        'fedex': 'FedEx',
        'other': 'Inny'
    };

    /**
     * Add new shipment to order
     */
    window.addShipment = function(orderId) {
        const trackingInput = document.getElementById('newShipmentTracking');
        const courierSelect = document.getElementById('newShipmentCourier');

        const trackingNumber = trackingInput.value.trim();
        const courier = courierSelect.value;

        if (!trackingNumber) {
            showToast('Podaj numer przesyłki', 'error');
            trackingInput.focus();
            return;
        }

        if (!courier) {
            showToast('Wybierz kuriera', 'error');
            courierSelect.focus();
            return;
        }

        // Disable button during request
        const addButton = document.querySelector('.btn-add-shipment');
        if (addButton) {
            addButton.disabled = true;
        }

        fetch(`/admin/orders/${orderId}/shipments`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({
                tracking_number: trackingNumber,
                courier: courier
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Clear form
                trackingInput.value = '';
                courierSelect.value = '';

                // Remove empty state if exists
                const emptyState = document.getElementById('shipmentsEmpty');
                if (emptyState) {
                    emptyState.remove();
                }

                // Add new shipment to list
                const shipmentsList = document.getElementById('shipmentsList');
                const shipmentHtml = createShipmentItemHtml(orderId, data.shipment);
                shipmentsList.insertAdjacentHTML('afterbegin', shipmentHtml);

                // Update count badge
                updateShipmentsCount(1);

                showToast('Przesyłka została dodana', 'success');
            } else {
                showToast(data.message || 'Nie udało się dodać przesyłki', 'error');
            }
        })
        .catch(error => {
            console.error('Add shipment error:', error);
            showToast('Wystąpił błąd podczas dodawania przesyłki', 'error');
        })
        .finally(() => {
            if (addButton) {
                addButton.disabled = false;
            }
        });
    };

    /**
     * Delete shipment from order
     */
    window.deleteShipment = function(orderId, shipmentId) {
        if (!confirm('Czy na pewno chcesz usunąć tę przesyłkę?')) {
            return;
        }

        fetch(`/admin/orders/${orderId}/shipments/${shipmentId}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Remove shipment item from DOM
                const shipmentItem = document.querySelector(`.shipment-item[data-shipment-id="${shipmentId}"]`);
                if (shipmentItem) {
                    shipmentItem.style.opacity = '0';
                    shipmentItem.style.transform = 'translateX(20px)';
                    shipmentItem.style.transition = 'all 0.3s';
                    setTimeout(() => {
                        shipmentItem.remove();

                        // Show empty state if no more shipments
                        const shipmentsList = document.getElementById('shipmentsList');
                        if (shipmentsList && !shipmentsList.querySelector('.shipment-item')) {
                            shipmentsList.innerHTML = `
                                <div class="shipments-empty" id="shipmentsEmpty">
                                    <span class="text-muted">Brak przesyłek</span>
                                </div>
                            `;
                        }

                        // Update count badge
                        updateShipmentsCount(-1);
                    }, 300);
                }

                showToast('Przesyłka została usunięta', 'success');
            } else {
                showToast(data.message || 'Nie udało się usunąć przesyłki', 'error');
            }
        })
        .catch(error => {
            console.error('Delete shipment error:', error);
            showToast('Wystąpił błąd podczas usuwania przesyłki', 'error');
        });
    };

    /**
     * Create HTML for shipment item
     */
    function createShipmentItemHtml(orderId, shipment) {
        const courierName = courierNames[shipment.courier] || shipment.courier;
        const courierAbbr = courierName.substring(0, 2).toUpperCase();
        const hasTrackingUrl = shipment.tracking_url && shipment.tracking_url !== '#';

        // Build tracking number display - link if URL exists, plain text otherwise
        let trackingHtml;
        if (hasTrackingUrl) {
            trackingHtml = `
                <a href="${shipment.tracking_url}"
                   target="_blank"
                   rel="noopener noreferrer"
                   class="shipment-tracking-link"
                   title="Śledź przesyłkę">
                    ${shipment.tracking_number}
                    <svg width="12" height="12" fill="currentColor" viewBox="0 0 16 16">
                        <path fill-rule="evenodd" d="M8.636 3.5a.5.5 0 0 0-.5-.5H1.5A1.5 1.5 0 0 0 0 4.5v10A1.5 1.5 0 0 0 1.5 16h10a1.5 1.5 0 0 0 1.5-1.5V7.864a.5.5 0 0 0-1 0V14.5a.5.5 0 0 1-.5.5h-10a.5.5 0 0 1-.5-.5v-10a.5.5 0 0 1 .5-.5h6.636a.5.5 0 0 0 .5-.5z"/>
                        <path fill-rule="evenodd" d="M16 .5a.5.5 0 0 0-.5-.5h-5a.5.5 0 0 0 0 1h3.793L6.146 9.146a.5.5 0 1 0 .708.708L15 1.707V5.5a.5.5 0 0 0 1 0v-5z"/>
                    </svg>
                </a>`;
        } else {
            trackingHtml = `<span class="shipment-tracking-number">${shipment.tracking_number}</span>`;
        }

        return `
            <div class="shipment-item" data-shipment-id="${shipment.id}" style="animation: slideInLeft 0.3s ease-out;">
                <div class="shipment-courier-icon courier-${shipment.courier}">
                    ${courierAbbr}
                </div>
                <div class="shipment-info">
                    ${trackingHtml}
                    <span class="shipment-courier-name">${shipment.courier_name || courierName}</span>
                </div>
                <button type="button"
                        class="btn-delete-shipment"
                        onclick="deleteShipment(${orderId}, ${shipment.id})"
                        title="Usuń przesyłkę">
                    <svg width="14" height="14" fill="currentColor" viewBox="0 0 16 16">
                        <path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708z"/>
                    </svg>
                </button>
            </div>
        `;
    }

    /**
     * Update shipments count badge
     */
    function updateShipmentsCount(delta) {
        const countBadge = document.querySelector('.shipments-count');
        const cardHeader = document.querySelector('.shipments-card h3');

        if (countBadge) {
            const currentCount = parseInt(countBadge.textContent) || 0;
            const newCount = currentCount + delta;

            if (newCount <= 0) {
                countBadge.remove();
            } else {
                countBadge.textContent = newCount;
            }
        } else if (delta > 0 && cardHeader) {
            // Create badge if it doesn't exist
            const badge = document.createElement('span');
            badge.className = 'shipments-count';
            badge.textContent = '1';
            cardHeader.appendChild(badge);
        }
    }

    // ====================
    // CUSTOM STATUS DROPDOWN
    // ====================

    /**
     * Toggle status dropdown open/close
     */
    window.toggleStatusDropdown = function() {
        const dropdown = document.getElementById('statusDropdown');
        if (dropdown) {
            dropdown.classList.toggle('open');

            // Focus search input when opening
            if (dropdown.classList.contains('open')) {
                const searchInput = dropdown.querySelector('.status-search-input');
                if (searchInput) {
                    setTimeout(() => searchInput.focus(), 100);
                }
            }
        }
    };

    /**
     * Select a status from dropdown
     */
    window.selectStatus = function(slug, name, color) {
        const dropdown = document.getElementById('statusDropdown');
        const hiddenInput = document.getElementById('statusHiddenInput');
        const trigger = dropdown.querySelector('.status-dropdown-trigger');
        const colorBox = trigger.querySelector('.status-color-box');
        const nameSpan = trigger.querySelector('.status-name');

        // Update hidden input
        hiddenInput.value = slug;

        // Update trigger display
        colorBox.style.backgroundColor = color;
        nameSpan.textContent = name;

        // Update selected state in options
        const options = dropdown.querySelectorAll('.status-option');
        options.forEach(opt => {
            opt.classList.remove('selected');
            // Remove check icon if exists
            const existingCheck = opt.querySelector('.check-icon');
            if (existingCheck) {
                existingCheck.remove();
            }
        });

        // Add selected class and check icon to selected option
        const selectedOption = dropdown.querySelector(`.status-option[data-value="${slug}"]`);
        if (selectedOption) {
            selectedOption.classList.add('selected');
            // Add check icon
            const checkIcon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            checkIcon.setAttribute('class', 'check-icon');
            checkIcon.setAttribute('width', '14');
            checkIcon.setAttribute('height', '14');
            checkIcon.setAttribute('fill', 'currentColor');
            checkIcon.setAttribute('viewBox', '0 0 16 16');
            checkIcon.innerHTML = '<path d="M13.854 3.646a.5.5 0 0 1 0 .708l-7 7a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6.5 10.293l6.646-6.647a.5.5 0 0 1 .708 0z"/>';
            selectedOption.appendChild(checkIcon);
        }

        // Close dropdown
        dropdown.classList.remove('open');

        // Clear search
        const searchInput = dropdown.querySelector('.status-search-input');
        if (searchInput) {
            searchInput.value = '';
            filterStatuses('');
        }

        // Status will be submitted when user clicks "Zmień" button
    };

    /**
     * Filter statuses by search query
     */
    window.filterStatuses = function(query) {
        const dropdown = document.getElementById('statusDropdown');
        const options = dropdown.querySelectorAll('.status-option');
        const normalizedQuery = query.toLowerCase().trim();

        options.forEach(option => {
            const name = option.getAttribute('data-name').toLowerCase();
            if (normalizedQuery === '' || name.includes(normalizedQuery)) {
                option.classList.remove('hidden');
            } else {
                option.classList.add('hidden');
            }
        });
    };

    /**
     * Close dropdown when clicking outside
     */
    document.addEventListener('click', function(e) {
        const dropdown = document.getElementById('statusDropdown');
        if (dropdown && !dropdown.contains(e.target)) {
            dropdown.classList.remove('open');
        }
    });

    /**
     * Handle keyboard navigation in dropdown
     */
    document.addEventListener('keydown', function(e) {
        const dropdown = document.getElementById('statusDropdown');
        if (!dropdown || !dropdown.classList.contains('open')) return;

        if (e.key === 'Escape') {
            dropdown.classList.remove('open');
        }
    });

    console.log('Order detail JavaScript initialized');
})();
