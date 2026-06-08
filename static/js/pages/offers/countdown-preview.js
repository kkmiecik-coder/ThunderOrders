// Podgląd oferty na countdownie — otwieranie/zamykanie modala (read-only)
(function () {
    const modal = document.getElementById('offerPreviewModal');
    if (!modal) return;

    window.openOfferPreview = function () {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
        const closeBtn = modal.querySelector('.modal-close');
        if (closeBtn) closeBtn.focus();
    };

    window.closeOfferPreview = function () {
        if (!modal.classList.contains('active') || modal.classList.contains('closing')) return;
        modal.classList.add('closing');
        setTimeout(function () {
            modal.classList.remove('active', 'closing');
            document.body.style.overflow = '';
        }, 350);
    };

    // Klik w tło zamyka
    modal.addEventListener('click', function (e) {
        if (e.target === modal) window.closeOfferPreview();
    });

    // ESC zamyka
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && modal.classList.contains('active')) {
            window.closeOfferPreview();
        }
    });
})();
