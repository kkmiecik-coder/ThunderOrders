/**
 * ThunderOrders - Modal Component
 * System modalnych okien
 */

window.showModal = function(title, body, footer = '') {
    const overlay = document.getElementById('modal-overlay');
    const modalContent = document.getElementById('modal-content');

    if (!overlay || !modalContent) return;

    modalContent.innerHTML = `
        <div class="modal-header">
            <h3 class="modal-title">${title}</h3>
            <button class="modal-close" onclick="window.hideModal()">×</button>
        </div>
        <div class="modal-body">
            ${body}
        </div>
        ${footer ? `<div class="modal-footer">${footer}</div>` : ''}
    `;

    overlay.classList.add('active');
};

window.hideModal = function() {
    const overlay = document.getElementById('modal-overlay');
    if (overlay && overlay.classList.contains('active')) {
        // Dodaj klasę closing dla animacji
        overlay.classList.add('closing');

        // Po zakończeniu animacji usuń klasy
        setTimeout(() => {
            overlay.classList.remove('active');
            overlay.classList.remove('closing');
        }, 350); // 350ms = czas trwania animacji
    }
};

// Close modal on overlay click
document.addEventListener('DOMContentLoaded', function() {
    const overlay = document.getElementById('modal-overlay');
    if (overlay) {
        overlay.addEventListener('click', function(e) {
            if (e.target === overlay) {
                window.hideModal();
            }
        });
    }
});

// Close modal on Escape key
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        window.hideModal();
    }
});
