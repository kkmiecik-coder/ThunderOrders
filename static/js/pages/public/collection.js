/**
 * Publiczna kolekcja - karuzela z dynamicznym rozmiarem i przełączanie widoków
 */
(function () {
    'use strict';

    // ==========================================
    // Przełączanie widoków (grid / carousel)
    // ==========================================

    var publicGrid = document.getElementById('publicGrid');
    var publicCarousel = document.getElementById('publicCarousel');
    var viewToggleBtns = document.querySelectorAll('.view-toggle-btn');

    /**
     * Ustawia aktywny widok (grid lub carousel)
     * Aktualizuje URL bez przeładowania strony
     */
    window.setPublicView = function (view) {
        if (!publicGrid || !publicCarousel) return;

        if (view === 'grid') {
            publicGrid.classList.remove('hidden');
            publicCarousel.classList.add('hidden');
        } else {
            publicGrid.classList.add('hidden');
            publicCarousel.classList.remove('hidden');
            computeCarouselLayout();
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
    // Dynamiczny rozmiar karuzeli
    // ==========================================

    var resizeTimer = null;

    /**
     * Oblicza dynamiczny layout karuzeli na podstawie dostępnego miejsca.
     * Ustawia CSS custom properties na .carousel-track.
     */
    function computeCarouselLayout() {
        var track = document.querySelector('.carousel-track');
        var container = publicCarousel;
        if (!track || !container) return;

        var containerWidth = container.clientWidth;
        var gap = 12;

        // Szerokość karty na podstawie dostępnej szerokości (5 kart widocznych)
        var widthBased = (containerWidth - 4 * gap) / 4.1;

        // Rzeczywista pozycja karuzeli na stronie
        var containerTop = container.getBoundingClientRect().top + window.scrollY;
        var availableHeight = window.innerHeight - containerTop + window.scrollY - 16;
        var usableHeight = availableHeight - 90; // padding karuzeli: 20px góra + 70px dół
        var heightBased = (usableHeight - 55) * 0.75; // karta: 4:3 + 55px tekst

        // Wybierz mniejszą z dwóch wartości, ogranicz zakresem 160-380px
        var cardWidth = Math.max(160, Math.min(380, Math.round(Math.min(widthBased, heightBased))));

        // Oblicz offsety pozycji
        var prevOffset = Math.round(cardWidth * 0.925 + gap);
        var farOffset = Math.round(prevOffset + cardWidth * 0.775 + gap);

        // Wysokość tracka: proporcja 4:3 karty + padding na tekst i przyciski
        var trackHeight = Math.round(cardWidth * (4 / 3) + 55);

        // Ustaw CSS custom properties
        track.style.setProperty('--slide-width', cardWidth + 'px');
        track.style.setProperty('--prev-offset', prevOffset + 'px');
        track.style.setProperty('--prev-offset-neg', '-' + prevOffset + 'px');
        track.style.setProperty('--far-offset', farOffset + 'px');
        track.style.setProperty('--far-offset-neg', '-' + farOffset + 'px');
        track.style.setProperty('--track-height', trackHeight + 'px');
    }

    // Przelicz layout przy zmianie rozmiaru okna (debounce)
    window.addEventListener('resize', function () {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function () {
            if (publicCarousel && !publicCarousel.classList.contains('hidden')) {
                computeCarouselLayout();
            }
        }, 150);
    });

    // ==========================================
    // Logika karuzeli
    // ==========================================

    var slides = document.querySelectorAll('.carousel-slide');
    var currentIndex = 0;

    // Klasy pozycji slajdów
    var posClasses = ['active', 'prev', 'next', 'far-prev', 'far-next'];
    var posMap = { 0: 'active', '-1': 'prev', 1: 'next', '-2': 'far-prev', 2: 'far-next' };

    /**
     * Pomocnicza - ustawia klasę pozycji na slajdzie
     */
    function applyPos(slide, cls) {
        posClasses.forEach(function (c) {
            slide.classList.remove(c);
        });
        if (cls) slide.classList.add(cls);
    }

    /**
     * Aktualizuje pozycje slajdów z logiką fade dla skrajnych kart.
     * 4 przypadki:
     *   1) Pojawienie (ukryty → widoczny): teleport bez animacji, potem fade in
     *   2) Znikanie (widoczny → ukryty): fade out 0.4s, potem ukryj
     *   3) Przesunięcie (widoczny → widoczny): normalna tranzycja CSS
     *   4) Ukryty → ukryty: natychmiast, bez animacji
     */
    function updateCarousel() {
        if (slides.length === 0) return;

        var totalSlides = slides.length;

        slides.forEach(function (slide, index) {
            // Anuluj wcześniejszy timer fade jeśli istnieje
            if (slide._fadeTimer) {
                clearTimeout(slide._fadeTimer);
                slide._fadeTimer = null;
            }

            // Sprawdź czy slajd był widoczny przed aktualizacją
            var wasVisible = posClasses.some(function (cls) { return slide.classList.contains(cls); });

            // Obliczenie względnej pozycji slajdu z obsługą zawijania
            var diff = index - currentIndex;
            if (diff > totalSlides / 2) diff -= totalSlides;
            if (diff < -totalSlides / 2) diff += totalSlides;

            var willBeVisible = (diff >= -2 && diff <= 2);
            var targetCls = posMap[diff] || null;

            if (!wasVisible && willBeVisible) {
                // --- Pojawienie: teleport na pozycję + fade in ---
                slide.classList.add('no-transition');
                applyPos(slide, targetCls);
                slide.style.opacity = '0';
                void slide.offsetHeight; // wymuszenie reflow
                slide.classList.remove('no-transition');
                slide.style.opacity = '';

            } else if (wasVisible && !willBeVisible) {
                // --- Znikanie: fade out 0.4s, potem ukryj ---
                slide.style.opacity = '0';
                slide._fadeTimer = setTimeout(function () {
                    slide.classList.add('no-transition');
                    applyPos(slide, null);
                    void slide.offsetHeight;
                    slide.classList.remove('no-transition');
                    slide._fadeTimer = null;
                }, 400);

            } else if (wasVisible && willBeVisible) {
                // --- Przesunięcie: normalna tranzycja CSS ---
                applyPos(slide, targetCls);
                slide.style.opacity = '';

            } else {
                // --- Ukryty → ukryty: natychmiast ---
                slide.classList.add('no-transition');
                applyPos(slide, null);
                slide.style.opacity = '0';
                void slide.offsetHeight;
                slide.classList.remove('no-transition');
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
                    currentIndex = (currentIndex + 1) % slides.length;
                } else {
                    currentIndex = (currentIndex - 1 + slides.length) % slides.length;
                }
                updateCarousel();
            }
        }, { passive: true });
    }

    // ==========================================
    // Inicjalizacja
    // ==========================================

    computeCarouselLayout();
    updateCarousel();
})();
