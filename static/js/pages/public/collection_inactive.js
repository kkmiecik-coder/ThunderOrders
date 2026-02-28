/**
 * Kolekcja niedostępna - particle effect
 */
(function () {
    'use strict';

    // ==========================================
    // Particle System (reused from collection.js)
    // ==========================================

    function initParticles() {
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

        var canvas = document.getElementById('particleCanvas');
        if (!canvas) return;

        var ctx = canvas.getContext('2d');
        var particles = [];
        var particleCount = 35;
        var rafId = null;

        var colors = [
            { r: 240, g: 147, b: 251 },
            { r: 157, g: 78, b: 221 },
            { r: 255, g: 255, b: 255 }
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
                p.y = Math.random() * canvas.height;
                particles.push(p);
            }
        }

        function animate() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            for (var i = 0; i < particles.length; i++) {
                var p = particles[i];
                p.y += p.vy;
                p.sineOffset += p.sineSpeed;
                p.vx = Math.sin(p.sineOffset) * p.sineAmp;
                p.x += p.vx;

                if (p.y < -10) {
                    particles[i] = createParticle();
                    continue;
                }

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

        var resizeTimer = null;
        window.addEventListener('resize', function () {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(resize, 200);
        });

        document.addEventListener('visibilitychange', function () {
            if (document.hidden) {
                if (rafId) cancelAnimationFrame(rafId);
                rafId = null;
            } else {
                if (!rafId) animate();
            }
        });
    }

    initParticles();
})();
