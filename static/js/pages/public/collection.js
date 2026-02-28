/**
 * Publiczna kolekcja - karuzela, particle effect, staggered animations, CTA bar
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

        var widthBased = (containerWidth - 4 * gap) / 4.1;

        var containerTop = container.getBoundingClientRect().top + window.scrollY;
        var availableHeight = window.innerHeight - containerTop + window.scrollY - 16;
        var usableHeight = availableHeight - 90;
        var heightBased = (usableHeight - 55) * 0.75;

        var cardWidth = Math.max(160, Math.min(380, Math.round(Math.min(widthBased, heightBased))));

        var prevOffset = Math.round(cardWidth * 0.925 + gap);
        var farOffset = Math.round(prevOffset + cardWidth * 0.775 + gap);

        var trackHeight = Math.round(cardWidth * (4 / 3) + 55);

        track.style.setProperty('--slide-width', cardWidth + 'px');
        track.style.setProperty('--prev-offset', prevOffset + 'px');
        track.style.setProperty('--prev-offset-neg', '-' + prevOffset + 'px');
        track.style.setProperty('--far-offset', farOffset + 'px');
        track.style.setProperty('--far-offset-neg', '-' + farOffset + 'px');
        track.style.setProperty('--track-height', trackHeight + 'px');
    }

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

    var posClasses = ['active', 'prev', 'next', 'far-prev', 'far-next'];
    var posMap = { 0: 'active', '-1': 'prev', 1: 'next', '-2': 'far-prev', 2: 'far-next' };

    function applyPos(slide, cls) {
        posClasses.forEach(function (c) {
            slide.classList.remove(c);
        });
        if (cls) slide.classList.add(cls);
    }

    function updateCarousel() {
        if (slides.length === 0) return;

        var totalSlides = slides.length;

        slides.forEach(function (slide, index) {
            if (slide._fadeTimer) {
                clearTimeout(slide._fadeTimer);
                slide._fadeTimer = null;
            }

            var wasVisible = posClasses.some(function (cls) { return slide.classList.contains(cls); });

            var diff = index - currentIndex;
            if (diff > totalSlides / 2) diff -= totalSlides;
            if (diff < -totalSlides / 2) diff += totalSlides;

            var willBeVisible = (diff >= -2 && diff <= 2);
            var targetCls = posMap[diff] || null;

            if (!wasVisible && willBeVisible) {
                slide.classList.add('no-transition');
                applyPos(slide, targetCls);
                slide.style.opacity = '0';
                void slide.offsetHeight;
                slide.classList.remove('no-transition');
                slide.style.opacity = '';

            } else if (wasVisible && !willBeVisible) {
                slide.style.opacity = '0';
                slide._fadeTimer = setTimeout(function () {
                    slide.classList.add('no-transition');
                    applyPos(slide, null);
                    void slide.offsetHeight;
                    slide.classList.remove('no-transition');
                    slide._fadeTimer = null;
                }, 400);

            } else if (wasVisible && willBeVisible) {
                applyPos(slide, targetCls);
                slide.style.opacity = '';

            } else {
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
    // Particle System
    // ==========================================

    function initParticles() {
        // Respect prefers-reduced-motion
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

        var canvas = document.getElementById('particleCanvas');
        if (!canvas) return;

        var ctx = canvas.getContext('2d');
        var particles = [];
        var particleCount = 50;
        var rafId = null;

        var colors = [
            { r: 240, g: 147, b: 251 },  // pink #f093fb
            { r: 157, g: 78, b: 221 },   // purple #9d4edd
            { r: 255, g: 255, b: 255 }   // white
        ];

        function resize() {
            var page = canvas.parentElement;
            if (!page) return;
            canvas.width = page.offsetWidth;
            canvas.height = page.offsetHeight;
        }

        function createParticle() {
            var color = colors[Math.floor(Math.random() * colors.length)];
            var isWhite = color.r === 255 && color.g === 255 && color.b === 255;
            return {
                x: Math.random() * canvas.width,
                y: canvas.height + Math.random() * 50,
                radius: 1 + Math.random() * 1.5,
                opacity: isWhite ? 0.1 + Math.random() * 0.2 : 0.15 + Math.random() * 0.4,
                color: color,
                vy: -(0.2 + Math.random() * 0.6),
                vx: 0,
                sineOffset: Math.random() * Math.PI * 2,
                sineSpeed: 0.01 + Math.random() * 0.02,
                sineAmp: 0.3 + Math.random() * 0.4
            };
        }

        function initAllParticles() {
            particles = [];
            for (var i = 0; i < particleCount; i++) {
                var p = createParticle();
                // Distribute across full height on init
                p.y = Math.random() * canvas.height;
                particles.push(p);
            }
        }

        function animate() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            for (var i = 0; i < particles.length; i++) {
                var p = particles[i];

                // Move upward
                p.y += p.vy;
                // Sine wave drift
                p.sineOffset += p.sineSpeed;
                p.vx = Math.sin(p.sineOffset) * p.sineAmp;
                p.x += p.vx;

                // Respawn at bottom when past top
                if (p.y < -10) {
                    particles[i] = createParticle();
                    continue;
                }

                // Draw
                ctx.beginPath();
                ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
                ctx.fillStyle = 'rgba(' + p.color.r + ',' + p.color.g + ',' + p.color.b + ',' + p.opacity + ')';
                ctx.fill();
            }

            rafId = requestAnimationFrame(animate);
        }

        resize();
        initAllParticles();
        animate();

        // Handle resize
        var resizeParticleTimer = null;
        window.addEventListener('resize', function () {
            clearTimeout(resizeParticleTimer);
            resizeParticleTimer = setTimeout(function () {
                resize();
            }, 200);
        });

        // Cleanup on page hide
        document.addEventListener('visibilitychange', function () {
            if (document.hidden) {
                if (rafId) cancelAnimationFrame(rafId);
                rafId = null;
            } else {
                if (!rafId) animate();
            }
        });
    }

    // ==========================================
    // Staggered card fade-in (IntersectionObserver)
    // ==========================================

    function initCardAnimations() {
        var cards = document.querySelectorAll('.public-card[data-index]');
        if (!cards.length) return;

        // Reduced motion: show all immediately
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
            cards.forEach(function (card) {
                card.classList.add('visible');
            });
            return;
        }

        if ('IntersectionObserver' in window) {
            var observer = new IntersectionObserver(function (entries) {
                entries.forEach(function (entry) {
                    if (entry.isIntersecting) {
                        var card = entry.target;
                        var index = parseInt(card.getAttribute('data-index'), 10) || 0;
                        card.style.animationDelay = (index * 0.05) + 's';
                        card.classList.add('visible');
                        observer.unobserve(card);
                    }
                });
            }, { threshold: 0.1 });

            cards.forEach(function (card) {
                observer.observe(card);
            });
        } else {
            // Fallback: show all
            cards.forEach(function (card) {
                card.classList.add('visible');
            });
        }
    }

    // ==========================================
    // Sticky CTA Bar
    // ==========================================

    function initCtaBar() {
        var ctaBar = document.getElementById('ctaBar');
        if (!ctaBar) return;

        // Slide in after 1s delay
        setTimeout(function () {
            ctaBar.classList.add('visible');
        }, 1000);
    }

    // ==========================================
    // Inicjalizacja
    // ==========================================

    computeCarouselLayout();
    updateCarousel();
    initParticles();
    initCardAnimations();
    initCtaBar();
})();
