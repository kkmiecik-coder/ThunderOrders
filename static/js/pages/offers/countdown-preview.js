// Podgląd oferty na countdownie — otwieranie/zamykanie modala (read-only)
(function () {
    const modal = document.getElementById('offerPreviewModal');
    if (!modal) return;

    window.openOfferPreview = function () {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    };

    window.closeOfferPreview = function () {
        modal.classList.remove('active');
        document.body.style.overflow = '';
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
