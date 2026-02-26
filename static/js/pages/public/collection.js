/**
 * Publiczna kolekcja - karuzela i przełączanie widoków
 */
(function () {
    'use strict';

    // ==========================================
    // Przełączanie widoków (grid / carousel)
    // ==========================================

    const publicGrid = document.getElementById('publicGrid');
    const publicCarousel = document.getElementById('publicCarousel');
    const viewToggleBtns = document.querySelectorAll('.view-toggle-btn');

    /**
     * Ustawia aktywny widok (grid lub carousel)
     * Aktualizuje URL bez przeładowania strony
     * @param {string} view - 'grid' lub 'carousel'
     */
    window.setPublicView = function (view) {
        if (!publicGrid || !publicCarousel) return;

        if (view === 'grid') {
            publicGrid.classList.remove('hidden');
            publicCarousel.classList.add('hidden');
        } else {
            publicGrid.classList.add('hidden');
            publicCarousel.classList.remove('hidden');
            updateCarousel();
        }

        // Aktualizacja aktywnego przycisku
        viewToggleBtns.forEach(function (btn) {
            if (btn.dataset.view === view) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });

        // Aktualizacja parametru URL bez przeładowania
        var url = new URL(window.location.href);
        url.searchParams.set('view', view);
        history.replaceState(null, '', url.toString());
    };

    // Obsługa kliknięć przycisków przełączania widoku
    viewToggleBtns.forEach(function (btn) {
        btn.addEventListener('click', function () {
            var view = this.dataset.view;
            if (view) {
                window.setPublicView(view);
            }
        });
    });

    // ==========================================
    // Logika karuzeli
    // ==========================================

    var slides = document.querySelectorAll('.carousel-slide');
    var currentIndex = 0;

    // Klasy pozycji slajdów
    var positionClasses = ['active', 'prev', 'next', 'far-prev', 'far-next', 'hidden'];

    /**
     * Aktualizuje pozycje slajdów w karuzeli
     * Środkowy slajd dostaje klasę .active,
     * sąsiednie slajdy dostają odpowiednie klasy pozycji
     */
    function updateCarousel() {
        if (slides.length === 0) return;

        var totalSlides = slides.length;

        slides.forEach(function (slide, index) {
            // Usunięcie wszystkich klas pozycji
            positionClasses.forEach(function (cls) {
                slide.classList.remove(cls);
            });

            // Obliczenie względnej pozycji slajdu
            var diff = index - currentIndex;

            // Obsługa zawijania (wrap around)
            if (diff > totalSlides / 2) {
                diff -= totalSlides;
            } else if (diff < -totalSlides / 2) {
                diff += totalSlides;
            }

            // Przypisanie odpowiedniej klasy pozycji
            if (diff === 0) {
                slide.classList.add('active');
            } else if (diff === -1) {
                slide.classList.add('prev');
            } else if (diff === 1) {
                slide.classList.add('next');
            } else if (diff === -2) {
                slide.classList.add('far-prev');
            } else if (diff === 2) {
                slide.classList.add('far-next');
            } else {
                slide.classList.add('hidden');
            }
        });
    }

    // ==========================================
    // Przyciski nawigacji karuzeli
    // ==========================================

    var prevBtn = document.getElementById('carouselPrev');
    var nextBtn = document.getElementById('carouselNext');

    if (prevBtn) {
        prevBtn.addEventListener('click', function () {
            if (slides.length === 0) return;
            currentIndex = (currentIndex - 1 + slides.length) % slides.length;
            updateCarousel();
        });
    }

    if (nextBtn) {
        nextBtn.addEventListener('click', function () {
            if (slides.length === 0) return;
            currentIndex = (currentIndex + 1) % slides.length;
            updateCarousel();
        });
    }

    // ==========================================
    // Obsługa gestów dotykowych (swipe)
    // ==========================================

    var carouselContainer = publicCarousel;
    var touchStartX = 0;

    if (carouselContainer) {
        carouselContainer.addEventListener('touchstart', function (e) {
            touchStartX = e.changedTouches[0].clientX;
        }, { passive: true });

        carouselContainer.addEventListener('touchend', function (e) {
            if (slides.length === 0) return;

            var touchEndX = e.changedTouches[0].clientX;
            var deltaX = touchEndX - touchStartX;

            // Minimalny próg przesunięcia: 50px
            if (Math.abs(deltaX) > 50) {
                if (deltaX < 0) {
                    // Przesunięcie w lewo → następny slajd
                    currentIndex = (currentIndex + 1) % slides.length;
                } else {
                    // Przesunięcie w prawo → poprzedni slajd
                    currentIndex = (currentIndex - 1 + slides.length) % slides.length;
                }
                updateCarousel();
            }
        }, { passive: true });
    }

    // ==========================================
    // Inicjalizacja
    // ==========================================

    // Ustawienie karuzeli przy załadowaniu strony
    updateCarousel();
})();
