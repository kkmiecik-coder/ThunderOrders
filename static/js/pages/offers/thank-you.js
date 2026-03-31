/**
 * ThunderOrders - K-POP Thank You Page (OPTIMIZED)
 * Confetti, muzyka, easter eggs - zoptymalizowane! 🌟💜
 */

(function() {
    'use strict';

    // ============================================
    // CONFIG
    // ============================================
    const CONFIG = {
        audio: {
            volume: 0.4,
            fadeInDuration: 1500
        },
        confetti: {
            particleCount: 80,
            colors: ['#ff006e', '#8338ec', '#3a86ff', '#06ffa5', '#ffbe0b']
        },
        easterEgg: {
            clicksRequired: 3,
            megaConfettiCount: 200
        }
    };

    // ============================================
    // STATE
    // ============================================
    const state = {
        audioPlaying: false,
        audioElement: null,
        easterEggClicks: 0
    };

    // ============================================
    // LIGHTWEIGHT CONFETTI (Canvas-based)
    // ============================================
    class SimpleConfetti {
        constructor() {
            this.canvas = document.createElement('canvas');
            this.ctx = this.canvas.getContext('2d', { alpha: true });
            this.particles = [];
            this.rafId = null;

            this.canvas.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                pointer-events: none;
                z-index: 5;
            `;

            document.body.appendChild(this.canvas);
            this.resize();
            window.addEventListener('resize', () => this.resize());
        }

        resize() {
            this.canvas.width = window.innerWidth;
            this.canvas.height = window.innerHeight;
        }

        createParticle(x, y) {
            const angle = Math.random() * Math.PI * 2;
            const velocity = (15 + Math.random() * 15) / 3; // Slow down 3x
            const color = CONFIG.confetti.colors[Math.floor(Math.random() * CONFIG.confetti.colors.length)];

            return {
                x: x,
                y: y,
                vx: Math.cos(angle) * velocity,
                vy: Math.sin(angle) * velocity,
                color: color,
                size: 8 + Math.random() * 12, // Bigger size (was 4-10, now 8-20)
                rotation: Math.random() * 360,
                rotationSpeed: (Math.random() - 0.5) * 8 / 3, // Slow rotation 3x
                life: 360 // 3x longer life (was 120)
            };
        }

        burst(x, y, count = CONFIG.confetti.particleCount) {
            for (let i = 0; i < count; i++) {
                this.particles.push(this.createParticle(x, y));
            }

            if (!this.rafId) {
                this.animate();
            }
        }

        animate() {
            this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

            for (let i = this.particles.length - 1; i >= 0; i--) {
                const p = this.particles[i];

                // Physics (slower)
                p.x += p.vx;
                p.y += p.vy;
                p.vy += 0.27; // Gravity 3x slower (was 0.8)
                p.vx *= 0.993; // Less drag for smoother motion
                p.vy *= 0.993;
                p.rotation += p.rotationSpeed;
                p.life--;

                // Remove if dead or out of bounds
                if (p.life <= 0 || p.y > this.canvas.height + 20) {
                    this.particles.splice(i, 1);
                    continue;
                }

                // Draw
                this.ctx.save();
                this.ctx.translate(p.x, p.y);
                this.ctx.rotate(p.rotation * Math.PI / 180);
                this.ctx.globalAlpha = Math.max(0, p.life / 360); // Updated for new life value
                this.ctx.fillStyle = p.color;
                this.ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size);
                this.ctx.restore();
            }

            if (this.particles.length > 0) {
                this.rafId = requestAnimationFrame(() => this.animate());
            } else {
                this.rafId = null;
            }
        }

        destroy() {
            if (this.rafId) {
                cancelAnimationFrame(this.rafId);
            }
            if (this.canvas.parentNode) {
                this.canvas.parentNode.removeChild(this.canvas);
            }
        }
    }

    // ============================================
    // AUDIO CONTROLLER
    // ============================================
    function initAudio() {
        state.audioElement = document.getElementById('celebration-audio');
        if (!state.audioElement) return;

        // Start muted to bypass autoplay restrictions
        state.audioElement.volume = 0;
        state.audioElement.muted = true;

        // Try to play muted first
        state.audioElement.play().then(() => {
            // Success! Now unmute and fade in on first interaction
            state.audioPlaying = true;
            console.log('[ThunderOrders] Audio playing (muted, waiting for interaction to unmute)');
        }).catch(() => {
            console.log('[ThunderOrders] Autoplay blocked completely');
        });
    }

    function fadeInAudio() {
        if (!state.audioElement) return;

        const start = Date.now();
        const startVol = state.audioElement.volume;
        const targetVol = CONFIG.audio.volume;

        function fade() {
            const elapsed = Date.now() - start;
            const progress = Math.min(elapsed / CONFIG.audio.fadeInDuration, 1);
            state.audioElement.volume = startVol + (targetVol - startVol) * progress;

            if (progress < 1) {
                requestAnimationFrame(fade);
            }
        }

        fade();
    }

    function toggleAudio() {
        if (!state.audioElement) return;

        if (state.audioPlaying) {
            state.audioElement.pause();
            state.audioPlaying = false;
        } else {
            state.audioElement.play();
            state.audioPlaying = true;
            if (state.audioElement.volume === 0) {
                fadeInAudio();
            }
        }

        updateAudioButton(state.audioPlaying);
    }

    function updateAudioButton(isPlaying) {
        const btn = document.getElementById('audio-toggle');
        if (!btn) return;

        const icon = btn.querySelector('.audio-icon');
        if (icon) {
            icon.innerHTML = isPlaying
                ? '<path d="M11.536 14.01A8.473 8.473 0 0 0 14.026 8a8.473 8.473 0 0 0-2.49-6.01l-.708.707A7.476 7.476 0 0 1 13.025 8c0 2.071-.84 3.946-2.197 5.303l.708.707z"/><path d="M10.121 12.596A6.48 6.48 0 0 0 12.025 8a6.48 6.48 0 0 0-1.904-4.596l-.707.707A5.483 5.483 0 0 1 11.025 8a5.483 5.483 0 0 1-1.61 3.89l.706.706z"/><path d="M8.707 11.182A4.486 4.486 0 0 0 10.025 8a4.486 4.486 0 0 0-1.318-3.182L8 5.525A3.489 3.489 0 0 1 9.025 8 3.49 3.49 0 0 1 8 10.475l.707.707zM6.717 3.55A.5.5 0 0 1 7 4v8a.5.5 0 0 1-.812.39L3.825 10.5H1.5A.5.5 0 0 1 1 10V6a.5.5 0 0 1 .5-.5h2.325l2.363-1.89a.5.5 0 0 1 .529-.06z"/>'
                : '<path d="M6.717 3.55A.5.5 0 0 1 7 4v8a.5.5 0 0 1-.812.39L3.825 10.5H1.5A.5.5 0 0 1 1 10V6a.5.5 0 0 1 .5-.5h2.325l2.363-1.89a.5.5 0 0 1 .529-.06z"/><path d="M11.854 4.146a.5.5 0 0 1 0 .708L10.207 6.5l1.647 1.646a.5.5 0 0 1-.708.708L9.5 7.207 7.854 8.854a.5.5 0 1 1-.708-.708L8.793 6.5 7.146 4.854a.5.5 0 1 1 .708-.708L9.5 5.793l1.646-1.647a.5.5 0 0 1 .708 0z"/>';
        }

        btn.setAttribute('aria-label', isPlaying ? 'Wycisz muzykę' : 'Włącz muzykę');
        btn.classList.toggle('is-playing', isPlaying);
    }

    // ============================================
    // EASTER EGG - Click checkmark 3 times
    // ============================================
    function initEasterEgg(confetti) {
        const checkmark = document.getElementById('checkmark-icon');
        if (!checkmark) return;

        checkmark.style.cursor = 'pointer';
        checkmark.addEventListener('click', () => {
            state.easterEggClicks++;

            // Shake animation
            checkmark.classList.add('shake');
            setTimeout(() => checkmark.classList.remove('shake'), 400);

            // Normal burst
            const rect = checkmark.getBoundingClientRect();
            confetti.burst(
                rect.left + rect.width / 2,
                rect.top + rect.height / 2,
                CONFIG.confetti.particleCount / 2
            );

            // MEGA BURST on 3rd click!
            if (state.easterEggClicks === CONFIG.easterEgg.clicksRequired) {
                setTimeout(() => {
                    confetti.burst(
                        rect.left + rect.width / 2,
                        rect.top + rect.height / 2,
                        CONFIG.easterEgg.megaConfettiCount
                    );
                }, 200);

                // Reset counter
                state.easterEggClicks = 0;
            }
        });
    }

    // ============================================
    // MOUSE PARALLAX EFFECT
    // ============================================
    function initParallax() {
        const orbs = document.querySelectorAll('.orb');
        if (!orbs.length) return;

        let mouseX = 0;
        let mouseY = 0;
        let currentX = 0;
        let currentY = 0;

        // Track mouse position
        document.addEventListener('mousemove', (e) => {
            mouseX = (e.clientX / window.innerWidth - 0.5) * 2;
            mouseY = (e.clientY / window.innerHeight - 0.5) * 2;
        });

        // Smooth animation with RAF
        function animateParallax() {
            // Smooth interpolation (ease out)
            currentX += (mouseX - currentX) * 0.05;
            currentY += (mouseY - currentY) * 0.05;

            orbs.forEach((orb, index) => {
                // Different movement speeds for each orb
                const speed = (index + 1) * 15;
                const x = currentX * speed;
                const y = currentY * speed;

                orb.style.transform = `translate(${x}px, ${y}px)`;
            });

            requestAnimationFrame(animateParallax);
        }

        animateParallax();
    }

    // ============================================
    // INITIALIZATION
    // ============================================
    function init() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', setup);
        } else {
            setup();
        }
    }

    function setup() {
        // Initialize confetti engine
        const confetti = new SimpleConfetti();

        // Initialize audio
        initAudio();

        // Easter egg
        initEasterEgg(confetti);

        // Mouse parallax on orbs
        initParallax();

        // SYLWESTER! Multiple burst points around "GRATULACJE!" title
        const heroTitle = document.querySelector('.hero-title-wrapper');
        if (heroTitle) {
            // Define 5 different burst locations around the title
            const burstLocations = [
                { xPercent: 0.1, yPercent: 0.5 },   // Far left
                { xPercent: 0.3, yPercent: 0.3 },   // Left top
                { xPercent: 0.5, yPercent: 0.2 },   // Center top
                { xPercent: 0.7, yPercent: 0.3 },   // Right top
                { xPercent: 0.9, yPercent: 0.5 }    // Far right
            ];

            // Initial sequence - 20 bursts
            for (let i = 0; i < 20; i++) {
                setTimeout(() => {
                    const rect = heroTitle.getBoundingClientRect();
                    const location = burstLocations[Math.floor(Math.random() * burstLocations.length)];

                    confetti.burst(
                        rect.left + (rect.width * location.xPercent),
                        rect.top + (rect.height * location.yPercent),
                        30 // 30 particles per burst - SYLWESTER!
                    );
                }, 300 + (i * (200 + Math.random() * 300)));
            }

            // Continuous loop after initial sequence
            function continuousConfetti() {
                const rect = heroTitle.getBoundingClientRect();
                const location = burstLocations[Math.floor(Math.random() * burstLocations.length)];

                confetti.burst(
                    rect.left + (rect.width * location.xPercent),
                    rect.top + (rect.height * location.yPercent),
                    15 // Smaller bursts for loop (15 particles)
                );

                // Schedule next burst randomly between 800-1500ms
                setTimeout(continuousConfetti, 800 + Math.random() * 700);
            }

            // Start continuous loop after initial sequence finishes (after ~10 seconds)
            setTimeout(continuousConfetti, 10000);
        }

        // Audio toggle button
        const audioBtn = document.getElementById('audio-toggle');
        if (audioBtn) {
            audioBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                toggleAudio();
            });
        }

        // Unmute and fade in audio on first user interaction
        function handleFirstInteraction() {
            if (state.audioElement && state.audioElement.muted) {
                state.audioElement.muted = false;
                fadeInAudio();
                updateAudioButton(true);
                console.log('[ThunderOrders] Audio unmuted and fading in');
            }
        }

        // Listen for any user interaction to unmute audio
        document.addEventListener('click', handleFirstInteraction, { once: true });
        document.addEventListener('touchstart', handleFirstInteraction, { once: true });
        document.addEventListener('keydown', handleFirstInteraction, { once: true });

        // Cleanup on page unload
        window.addEventListener('beforeunload', () => {
            confetti.destroy();
            if (state.audioElement) {
                state.audioElement.pause();
            }
        });
    }

    // Start!
    init();

})();
