/**
 * ThunderOrders - Complete Profile (2-step wizard)
 * Krok 1: Dane osobowe (AJAX submit)
 * Krok 2: Wybór avatara (carousel + AJAX save)
 */

document.addEventListener('DOMContentLoaded', function() {
    initFloatingLabels();
    initPhoneInput();
    initStep1Form();
    initStep2Avatar();
    initBackButton();
});

// ============================================
// Floating labels
// ============================================
function initFloatingLabels() {
    document.querySelectorAll('.auth-input').forEach(input => {
        if (input.value) {
            input.classList.add('has-value');
        }
        input.addEventListener('input', function() {
            this.classList.toggle('has-value', this.value.length > 0);
        });
    });
}

// ============================================
// Phone prefix selector (reuse logiki z auth-unified.js)
// ============================================
function initPhoneInput() {
    const prefixBtn = document.getElementById('phone-prefix-btn');
    const dropdown = document.getElementById('phone-prefix-dropdown');
    const prefixInput = document.getElementById('phone_prefix');
    const selectedFlag = document.getElementById('selected-flag');
    const selectedPrefix = document.getElementById('selected-prefix');

    if (!prefixBtn || !dropdown) return;

    // Otwieranie/zamykanie dropdown
    prefixBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        dropdown.classList.toggle('open');
    });

    // Zamknij po kliknięciu poza
    document.addEventListener('click', function() {
        dropdown.classList.remove('open');
    });

    // Wybór opcji
    dropdown.querySelectorAll('.prefix-option').forEach(option => {
        option.addEventListener('click', function() {
            const prefix = this.dataset.prefix;
            const flag = this.dataset.flag;

            prefixInput.value = prefix;
            selectedFlag.textContent = flag;
            selectedPrefix.textContent = prefix;
            dropdown.classList.remove('open');
        });
    });
}

// ============================================
// Krok 1: Formularz danych osobowych
// ============================================
function initStep1Form() {
    const form = document.getElementById('complete-profile-form');
    if (!form) return;

    form.addEventListener('submit', function(e) {
        e.preventDefault();

        const btn = document.getElementById('step1-submit');
        btn.classList.add('loading');

        // Wyczyść poprzednie błędy
        document.querySelectorAll('.form-error').forEach(el => {
            el.style.display = 'none';
            el.textContent = '';
        });

        const formData = new FormData(form);

        fetch(window.CP_CONFIG.saveProfileUrl, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => response.json())
        .then(data => {
            btn.classList.remove('loading');

            if (data.success) {
                transitionToStep2();
            } else if (data.errors) {
                // Pokaż błędy walidacji
                for (const [field, message] of Object.entries(data.errors)) {
                    const errorEl = document.getElementById('error-' + field);
                    if (errorEl) {
                        errorEl.textContent = message;
                        errorEl.style.display = 'block';
                    }
                }
            }
        })
        .catch(error => {
            btn.classList.remove('loading');
            console.error('Błąd zapisu profilu:', error);
        });
    });
}

// ============================================
// Przejście do kroku 2
// ============================================
function transitionToStep2() {
    const step1Panel = document.getElementById('step-1');
    const step2Panel = document.getElementById('step-2');
    const stepDot1 = document.querySelector('.cp-step[data-step="1"]');
    const stepDot2 = document.querySelector('.cp-step[data-step="2"]');
    const stepLine = document.querySelector('.cp-step-line');

    // Animacja ukrycia kroku 1
    step1Panel.style.opacity = '0';
    step1Panel.style.transform = 'translateY(-15px)';
    step1Panel.style.transition = 'opacity 0.3s, transform 0.3s';

    setTimeout(() => {
        step1Panel.style.display = 'none';

        // Zaktualizuj step indicator
        stepDot1.classList.remove('active');
        stepDot1.classList.add('completed');
        stepLine.classList.add('active');
        stepDot2.classList.add('active');

        // Pokaż krok 2
        step2Panel.style.display = 'block';
        step2Panel.style.opacity = '0';
        step2Panel.style.transform = 'translateY(15px)';

        requestAnimationFrame(() => {
            step2Panel.style.transition = 'opacity 0.4s, transform 0.4s';
            step2Panel.style.opacity = '1';
            step2Panel.style.transform = 'translateY(0)';
        });

        // Inicjalizuj widoczność przycisków nawigacji carousel
        updateCarouselNavButtons();
    }, 300);
}

// ============================================
// Cofnięcie do kroku 1
// ============================================
function transitionToStep1() {
    const step1Panel = document.getElementById('step-1');
    const step2Panel = document.getElementById('step-2');
    const stepDot1 = document.querySelector('.cp-step[data-step="1"]');
    const stepDot2 = document.querySelector('.cp-step[data-step="2"]');
    const stepLine = document.querySelector('.cp-step-line');

    // Animacja ukrycia kroku 2
    step2Panel.style.opacity = '0';
    step2Panel.style.transform = 'translateY(15px)';
    step2Panel.style.transition = 'opacity 0.3s, transform 0.3s';

    setTimeout(() => {
        step2Panel.style.display = 'none';

        // Zaktualizuj step indicator
        stepDot2.classList.remove('active');
        stepLine.classList.remove('active');
        stepDot1.classList.remove('completed');
        stepDot1.classList.add('active');

        // Pokaż krok 1
        step1Panel.style.display = 'block';
        step1Panel.style.opacity = '0';
        step1Panel.style.transform = 'translateY(-15px)';

        requestAnimationFrame(() => {
            step1Panel.style.transition = 'opacity 0.4s, transform 0.4s';
            step1Panel.style.opacity = '1';
            step1Panel.style.transform = 'translateY(0)';
        });
    }, 300);
}

function initBackButton() {
    const backBtn = document.getElementById('back-to-step1');
    if (backBtn) {
        backBtn.addEventListener('click', transitionToStep1);
    }

    // Klikniecie w step indicator "1" na kroku 2 też cofa
    const stepDot1 = document.querySelector('.cp-step[data-step="1"]');
    if (stepDot1) {
        stepDot1.style.cursor = 'pointer';
        stepDot1.addEventListener('click', function() {
            const step2Panel = document.getElementById('step-2');
            if (step2Panel && step2Panel.style.display !== 'none') {
                transitionToStep1();
            }
        });
    }
}

// ============================================
// Krok 2: Avatar carousel
// ============================================
let selectedAvatarId = null;

function initStep2Avatar() {
    const avatarContainer = document.getElementById('step-2');
    if (!avatarContainer) return;

    // Sprawdź czy jest już wybrany avatar
    const hiddenInput = document.getElementById('selectedAvatarId');
    if (hiddenInput && hiddenInput.value) {
        selectedAvatarId = parseInt(hiddenInput.value);
    }

    // Kliknięcie w avatar
    avatarContainer.querySelectorAll('.avatar-option').forEach(option => {
        option.addEventListener('click', function() {
            selectAvatar(parseInt(this.dataset.avatarId), this);
        });
    });

    // Nawigacja carousel
    avatarContainer.querySelectorAll('.carousel-nav-prev').forEach(btn => {
        btn.addEventListener('click', function() {
            scrollCarousel(this, -1);
        });
    });

    avatarContainer.querySelectorAll('.carousel-nav-next').forEach(btn => {
        btn.addEventListener('click', function() {
            scrollCarousel(this, 1);
        });
    });

    // Scroll listeners
    avatarContainer.querySelectorAll('.avatar-carousel').forEach(carousel => {
        carousel.addEventListener('scroll', updateCarouselNavButtons);
    });

    // Przycisk zapisu
    const saveBtn = document.getElementById('save-avatar-btn');
    if (saveBtn) {
        // Włącz jeśli avatar już wybrany
        if (selectedAvatarId) {
            saveBtn.disabled = false;
        }

        saveBtn.addEventListener('click', saveAvatarAndFinish);
    }

    // Początkowa widoczność nav buttons
    setTimeout(updateCarouselNavButtons, 100);
    window.addEventListener('load', updateCarouselNavButtons);
}

function selectAvatar(avatarId, element) {
    // Usuń poprzedni wybór
    document.querySelectorAll('.avatar-option.selected').forEach(el => {
        el.classList.remove('selected');
    });

    // Zaznacz kliknięty
    element.classList.add('selected');
    selectedAvatarId = avatarId;

    // Zaktualizuj hidden input
    const hiddenInput = document.getElementById('selectedAvatarId');
    if (hiddenInput) {
        hiddenInput.value = avatarId;
    }

    // Włącz przycisk zapisu
    const saveBtn = document.getElementById('save-avatar-btn');
    if (saveBtn) {
        saveBtn.disabled = false;
    }
}

function scrollCarousel(button, direction) {
    const wrapper = button.closest('.avatar-carousel-wrapper');
    const carousel = wrapper.querySelector('.avatar-carousel');
    const scrollAmount = 250;

    if (carousel) {
        carousel.scrollBy({
            left: direction * scrollAmount,
            behavior: 'smooth'
        });
    }
}

function updateCarouselNavButtons() {
    document.querySelectorAll('.avatar-carousel-wrapper').forEach(wrapper => {
        const carousel = wrapper.querySelector('.avatar-carousel');
        const prevBtn = wrapper.querySelector('.carousel-nav-prev');
        const nextBtn = wrapper.querySelector('.carousel-nav-next');

        if (!carousel || !prevBtn || !nextBtn) return;

        const isAtStart = carousel.scrollLeft <= 10;
        const isAtEnd = carousel.scrollLeft >= carousel.scrollWidth - carousel.clientWidth - 10;

        prevBtn.classList.toggle('hidden', isAtStart);
        nextBtn.classList.toggle('hidden', isAtEnd);
    });
}

// ============================================
// Zapis avatara i zakończenie
// ============================================
function saveAvatarAndFinish() {
    if (!selectedAvatarId) return;

    const btn = document.getElementById('save-avatar-btn');
    btn.classList.add('loading');

    const formData = new FormData();
    formData.append('csrf_token', window.CP_CONFIG.csrfToken);
    formData.append('avatar_id', selectedAvatarId);

    fetch(window.CP_CONFIG.saveAvatarUrl, {
        method: 'POST',
        body: formData,
        headers: {
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success && data.redirect_url) {
            window.location.href = data.redirect_url;
        } else {
            btn.classList.remove('loading');
            console.error('Błąd zapisu avatara:', data.error);
        }
    })
    .catch(error => {
        btn.classList.remove('loading');
        console.error('Błąd zapisu avatara:', error);
    });
}
