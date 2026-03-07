/**
 * Countdown Page - Particles, Lightning, Beams, Timer
 */
(function() {
    'use strict';

    // ==========================================
    // Countdown Timer (per-digit crossfade)
    // ==========================================
    var TARGET = new Date('2026-04-01T20:00:00').getTime();

    function updateValue(id, value) {
        var container = document.getElementById(id);
        if (!container) return;
        var digits = container.querySelectorAll('.digit');
        var valueStr = String(value).padStart(2, '0');

        for (var i = 0; i < digits.length; i++) {
            (function(digit, newChar) {
                var inner = digit.querySelector('.digit-inner');
                var currentChar = inner.textContent;

                if (currentChar !== newChar) {
                    // Create fading-out clone of old digit
                    var oldClone = document.createElement('span');
                    oldClone.className = 'digit-old';
                    oldClone.textContent = currentChar;
                    digit.appendChild(oldClone);

                    // Hide inner, update content
                    inner.classList.add('digit-hidden');
                    inner.textContent = newChar;

                    // Delay new digit animation to create proper crossfade
                    setTimeout(function() {
                        inner.classList.remove('digit-hidden');
                        inner.classList.add('digit-in');
                    }, 200);

                    // Cleanup after animation
                    setTimeout(function() {
                        if (oldClone.parentNode) oldClone.remove();
                        inner.classList.remove('digit-in');
                    }, 600);
                }
            })(digits[i], valueStr[i]);
        }
    }

    function updateCountdown() {
        var now = Date.now();
        var diff = Math.max(0, TARGET - now);

        if (diff <= 0) {
            window.location.reload();
            return;
        }

        var d = Math.floor(diff / 86400000);
        var h = Math.floor((diff % 86400000) / 3600000);
        var m = Math.floor((diff % 3600000) / 60000);
        var s = Math.floor((diff % 60000) / 1000);

        updateValue('days', d);
        updateValue('hours', h);
        updateValue('minutes', m);
        updateValue('seconds', s);
    }

    updateCountdown();
    setInterval(updateCountdown, 1000);

    // ==========================================
    // Particle Systems (ambient + embers)
    // ==========================================
    function initParticles() {
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

        var canvas = document.getElementById('particleCanvas');
        if (!canvas) return;

        var ctx = canvas.getContext('2d');
        var rafId = null;

        function resize() {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
        }

        // ---- Ambient (slow drifting dots) ----
        var AMBIENT_COUNT = 45;
        var ambientColors = [
            { r: 240, g: 147, b: 251 },
            { r: 123, g: 44, b: 191 },
            { r: 157, g: 78, b: 221 },
            { r: 255, g: 255, b: 255 }
        ];
        var ambient = [];

        function makeAmbient(fullHeight) {
            var c = ambientColors[Math.floor(Math.random() * ambientColors.length)];
            var w = c.r === 255 && c.g === 255 && c.b === 255;
            return {
                x: Math.random() * canvas.width,
                y: fullHeight ? Math.random() * canvas.height : canvas.height + Math.random() * 50,
                r: 1 + Math.random() * 1.5,
                o: w ? 0.08 + Math.random() * 0.15 : 0.12 + Math.random() * 0.35,
                c: c,
                vy: -(0.15 + Math.random() * 0.5),
                sp: Math.random() * Math.PI * 2,
                ss: 0.008 + Math.random() * 0.015,
                sa: 0.2 + Math.random() * 0.35
            };
        }

        for (var i = 0; i < AMBIENT_COUNT; i++) ambient.push(makeAmbient(true));

        // ---- Embers (fire sparks rising from bottom) ----
        var EMBER_MAX = 150;
        // Spawn interval in ms — one ember every 30-80ms (randomized per spawn)
        var emberSpawnInterval = 50;
        var emberAccum = 0; // time accumulator for spawning
        var emberColors = [
            { r: 240, g: 147, b: 251 },
            { r: 245, g: 87, b: 108 },
            { r: 200, g: 120, b: 255 },
            { r: 255, g: 180, b: 220 },
            { r: 180, g: 140, b: 255 }
        ];
        var embers = [];

        function makeEmber() {
            var c = emberColors[Math.floor(Math.random() * emberColors.length)];
            return {
                x: Math.random() * canvas.width,
                y: canvas.height + 5 + Math.random() * 25,
                startY: canvas.height,
                r: 0.8 + Math.random() * 1.8,
                maxO: 0.3 + Math.random() * 0.5,
                o: 0,
                c: c,
                vy: -(0.3 + Math.random() * 0.8),
                vx: (Math.random() - 0.5) * 0.3,
                w1p: Math.random() * Math.PI * 2,
                w1s: 0.02 + Math.random() * 0.03,
                w1a: 0.5 + Math.random() * 1.0,
                w2p: Math.random() * Math.PI * 2,
                w2s: 0.05 + Math.random() * 0.06,
                w2a: 0.2 + Math.random() * 0.5,
                tt: Math.random() * 100,
                ti: 60 + Math.random() * 80,
                ts: 0.3 + Math.random() * 0.6
            };
        }

        // ---- Main loop ----
        var lastTime = performance.now();

        function animate(now) {
            var dt = now - lastTime;
            lastTime = now;
            // Clamp dt to avoid huge jumps after tab switch
            if (dt > 100) dt = 16;

            ctx.clearRect(0, 0, canvas.width, canvas.height);
            var h = canvas.height;

            // -- Ambient --
            for (var i = 0; i < ambient.length; i++) {
                var a = ambient[i];
                a.y += a.vy;
                a.sp += a.ss;
                a.x += Math.sin(a.sp) * a.sa;
                if (a.y < -10) { ambient[i] = makeAmbient(false); continue; }
                ctx.beginPath();
                ctx.arc(a.x, a.y, a.r, 0, Math.PI * 2);
                ctx.fillStyle = 'rgba(' + a.c.r + ',' + a.c.g + ',' + a.c.b + ',' + a.o + ')';
                ctx.fill();
            }

            // -- Ember spawning (time-based, randomized interval) --
            emberAccum += dt;
            while (emberAccum >= emberSpawnInterval && embers.length < EMBER_MAX) {
                embers.push(makeEmber());
                emberAccum -= emberSpawnInterval;
                // Randomize next interval: 30-80ms
                emberSpawnInterval = 30 + Math.random() * 50;
            }
            // If at max, just reset accumulator
            if (embers.length >= EMBER_MAX) emberAccum = 0;

            // -- Ember update & draw --
            for (var e = embers.length - 1; e >= 0; e--) {
                var em = embers[e];

                em.y += em.vy;
                var travel = em.startY - em.y;

                // Wobbly path
                em.w1p += em.w1s;
                em.w2p += em.w2s;
                var wobble = Math.sin(em.w1p) * em.w1a + Math.sin(em.w2p) * em.w2a;

                // Turbulence burst
                em.tt++;
                if (em.tt > em.ti) {
                    em.tt = 0;
                    em.ti = 60 + Math.random() * 80;
                    em.vx += (Math.random() - 0.5) * em.ts;
                }
                em.vx *= 0.995;
                em.x += wobble + em.vx;

                // Life: fade over 90% of screen height
                var life = 1.0 - Math.min(1, travel / (h * 0.9));
                em.o = em.maxO * life;
                var dr = em.r * (0.3 + 0.7 * life);

                // Dead?
                if (life <= 0.01 || em.y < -20) {
                    embers.splice(e, 1);
                    continue;
                }

                // Draw ember
                ctx.beginPath();
                ctx.arc(em.x, em.y, dr, 0, Math.PI * 2);
                ctx.fillStyle = 'rgba(' + em.c.r + ',' + em.c.g + ',' + em.c.b + ',' + em.o + ')';
                ctx.fill();

                // Glow halo on bright ones
                if (em.o > 0.25 && dr > 1) {
                    ctx.beginPath();
                    ctx.arc(em.x, em.y, dr * 2.5, 0, Math.PI * 2);
                    ctx.fillStyle = 'rgba(' + em.c.r + ',' + em.c.g + ',' + em.c.b + ',' + (em.o * 0.12) + ')';
                    ctx.fill();
                }
            }

            rafId = requestAnimationFrame(animate);
        }

        resize();
        rafId = requestAnimationFrame(animate);

        var resizeTimer = null;
        window.addEventListener('resize', function() {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(resize, 200);
        });

        document.addEventListener('visibilitychange', function() {
            if (document.hidden) {
                if (rafId) cancelAnimationFrame(rafId);
                rafId = null;
            } else {
                lastTime = performance.now();
                if (!rafId) rafId = requestAnimationFrame(animate);
            }
        });
    }

    // ==========================================
    // Beam Sway (independent organic movement)
    // ==========================================
    function initBeams() {
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

        var beams = document.querySelectorAll('.beam');
        if (!beams.length) return;

        var configs = [
            { center: -12, range: 14 },
            { center: 2,   range: 12 },
            { center: 8,   range: 16 },
            { center: -4,  range: 13 },
            { center: 1,   range: 10 }
        ];

        var beamStates = [];
        for (var i = 0; i < beams.length; i++) {
            var cfg = configs[i] || { center: 0, range: 10 };
            beamStates.push({
                el: beams[i],
                center: cfg.center,
                range: cfg.range,
                speed1: 0.15 + Math.random() * 0.25,
                phase1: Math.random() * Math.PI * 2,
                amp1: 0.6 + Math.random() * 0.4,
                speed2: 0.4 + Math.random() * 0.5,
                phase2: Math.random() * Math.PI * 2,
                amp2: 0.1 + Math.random() * 0.2,
                speed3: 0.04 + Math.random() * 0.06,
                phase3: Math.random() * Math.PI * 2,
                amp3: 0.15 + Math.random() * 0.15
            });
        }

        var beamRafId = null;
        var lastTime = performance.now();

        function animateBeams(now) {
            var dt = (now - lastTime) / 1000;
            lastTime = now;

            for (var i = 0; i < beamStates.length; i++) {
                var b = beamStates[i];

                b.phase1 += b.speed1 * dt;
                b.phase2 += b.speed2 * dt;
                b.phase3 += b.speed3 * dt;

                var wave = Math.sin(b.phase1) * b.amp1
                         + Math.sin(b.phase2) * b.amp2
                         + Math.sin(b.phase3) * b.amp3;

                var totalAmp = b.amp1 + b.amp2 + b.amp3;
                var normalized = wave / totalAmp;

                var angle = b.center + normalized * b.range;
                b.el.style.transform = 'rotate(' + angle.toFixed(2) + 'deg)';
            }

            beamRafId = requestAnimationFrame(animateBeams);
        }

        beamRafId = requestAnimationFrame(animateBeams);

        document.addEventListener('visibilitychange', function() {
            if (document.hidden) {
                if (beamRafId) { cancelAnimationFrame(beamRafId); beamRafId = null; }
            } else {
                lastTime = performance.now();
                if (!beamRafId) beamRafId = requestAnimationFrame(animateBeams);
            }
        });
    }

    initBeams();
    initParticles();

    // ==========================================
    // Lightning System (overlapping, organic)
    // ==========================================
    function initLightning() {
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

        var canvas = document.getElementById('lightningCanvas');
        var flashEl = document.getElementById('lightningFlash');
        if (!canvas) return;

        var ctx = canvas.getContext('2d');
        var activeVolleys = [];
        var rafId = null;

        // Reference width for consistent bolt proportions across screen sizes
        var REF_WIDTH = 1200;

        function resize() {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
        }
        resize();
        window.addEventListener('resize', function() { resize(); });

        // --- Bolt generation ---
        function generateBolt(startX, startY, endX, endY, displacement) {
            if (displacement < 4) {
                return [{ x: startX, y: startY }, { x: endX, y: endY }];
            }
            var midX = (startX + endX) / 2 + (Math.random() - 0.5) * displacement;
            var midY = (startY + endY) / 2 + (Math.random() - 0.5) * displacement * 0.3;
            var left = generateBolt(startX, startY, midX, midY, displacement / 2);
            var right = generateBolt(midX, midY, endX, endY, displacement / 2);
            return left.concat(right.slice(1));
        }

        function generateStrike() {
            var w = canvas.width;
            var h = canvas.height;
            // Use reference width for displacement so bolts look natural on mobile
            var refW = Math.max(w, REF_WIDTH);
            var startX = w * (0.08 + Math.random() * 0.84);
            var endX = startX + (Math.random() - 0.5) * w * 0.4;
            var endY = h * (0.45 + Math.random() * 0.4);
            var mainBolt = generateBolt(startX, -10, endX, endY, refW * 0.15);

            var branches = [];
            var branchCount = 2 + Math.floor(Math.random() * 4);
            for (var b = 0; b < branchCount; b++) {
                var idx = Math.floor(Math.random() * mainBolt.length * 0.7) + Math.floor(mainBolt.length * 0.1);
                if (idx >= mainBolt.length) idx = mainBolt.length - 1;
                var origin = mainBolt[idx];
                var brEndX = origin.x + (Math.random() - 0.5) * refW * 0.2;
                var brEndY = origin.y + h * (0.05 + Math.random() * 0.15);
                branches.push(generateBolt(origin.x, origin.y, brEndX, brEndY, refW * 0.06));
            }

            return { main: mainBolt, branches: branches };
        }

        // --- Drawing ---
        function drawBoltPath(points, width, alpha, glowSize, glowColor) {
            if (points.length < 2 || alpha <= 0) return;
            ctx.save();
            ctx.strokeStyle = 'rgba(255, 255, 255, ' + alpha + ')';
            ctx.lineWidth = width;
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';
            if (glowSize > 0) {
                ctx.shadowColor = glowColor || 'rgba(180, 160, 255, 0.8)';
                ctx.shadowBlur = glowSize;
            }
            ctx.beginPath();
            ctx.moveTo(points[0].x, points[0].y);
            for (var i = 1; i < points.length; i++) {
                ctx.lineTo(points[i].x, points[i].y);
            }
            ctx.stroke();
            ctx.restore();
        }

        function drawStrike(strike, mainAlpha, branchAlpha, glow, mainW, brW) {
            drawBoltPath(strike.main, mainW + 4, mainAlpha * 0.15, glow * 1.5, 'rgba(140, 120, 255, 0.5)');
            drawBoltPath(strike.main, mainW, mainAlpha, glow, 'rgba(200, 180, 255, 0.9)');
            drawBoltPath(strike.main, mainW * 0.4, Math.min(1, mainAlpha * 1.2), glow * 0.5, 'rgba(255, 255, 255, 1)');
            for (var b = 0; b < strike.branches.length; b++) {
                drawBoltPath(strike.branches[b], brW, branchAlpha, glow * 0.6, 'rgba(180, 160, 255, 0.7)');
            }
        }

        // --- Volley keyframes ---
        var KEYFRAMES = [
            { t: 0,   mainAlpha: 0.9, branchAlpha: 0.5, glow: 35, mainW: 2.5, brW: 1.2, flash: true },
            { t: 50,  mainAlpha: 0.25, branchAlpha: 0.12, glow: 18, mainW: 1.8, brW: 0.7, flash: false },
            { t: 90,  mainAlpha: 1,   branchAlpha: 0.6, glow: 45, mainW: 3,   brW: 1.5, flash: true },
            { t: 150, mainAlpha: 0.55, branchAlpha: 0.25, glow: 22, mainW: 2, brW: 0.9, flash: false },
            { t: 210, mainAlpha: 0.18, branchAlpha: 0.06, glow: 10, mainW: 1.2, brW: 0.4, flash: false },
            { t: 300, mainAlpha: 0,   branchAlpha: 0,    glow: 0,  mainW: 0,   brW: 0,   flash: false }
        ];

        function lerpVal(a, b, t) { return a + (b - a) * t; }

        function sampleKeyframes(elapsed) {
            if (elapsed <= 0) return KEYFRAMES[0];
            if (elapsed >= KEYFRAMES[KEYFRAMES.length - 1].t) return KEYFRAMES[KEYFRAMES.length - 1];

            for (var i = 0; i < KEYFRAMES.length - 1; i++) {
                var k0 = KEYFRAMES[i];
                var k1 = KEYFRAMES[i + 1];
                if (elapsed >= k0.t && elapsed <= k1.t) {
                    var t = (elapsed - k0.t) / (k1.t - k0.t);
                    return {
                        mainAlpha: lerpVal(k0.mainAlpha, k1.mainAlpha, t),
                        branchAlpha: lerpVal(k0.branchAlpha, k1.branchAlpha, t),
                        glow: lerpVal(k0.glow, k1.glow, t),
                        mainW: lerpVal(k0.mainW, k1.mainW, t),
                        brW: lerpVal(k0.brW, k1.brW, t),
                        flash: k0.flash && t < 0.5
                    };
                }
            }
            return KEYFRAMES[KEYFRAMES.length - 1];
        }

        // --- Create a volley ---
        function createVolley() {
            var boltCount = 1 + Math.floor(Math.random() * 3);
            var strikes = [];
            for (var i = 0; i < boltCount; i++) {
                strikes.push(generateStrike());
            }

            var volley = {
                strikes: strikes,
                startTime: performance.now(),
                duration: 300,
                done: false
            };

            if (Math.random() < 0.4) {
                var afterDelay = 350 + Math.random() * 250;
                setTimeout(function() {
                    var jitteredStrikes = strikes.map(function(st) {
                        return {
                            main: st.main.map(function(pt) {
                                return { x: pt.x + (Math.random() - 0.5) * 10, y: pt.y };
                            }),
                            branches: st.branches
                        };
                    });
                    activeVolleys.push({
                        strikes: jitteredStrikes,
                        startTime: performance.now(),
                        duration: 120,
                        done: false
                    });
                }, afterDelay);
            }

            return volley;
        }

        // --- Render loop ---
        function renderFrame() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            var now = performance.now();
            var anyFlash = false;
            var hasActive = false;

            for (var v = activeVolleys.length - 1; v >= 0; v--) {
                var vol = activeVolleys[v];
                var elapsed = now - vol.startTime;

                if (elapsed > vol.duration + 50) {
                    activeVolleys.splice(v, 1);
                    continue;
                }

                hasActive = true;

                var mappedElapsed = (elapsed / vol.duration) * 300;
                var s = sampleKeyframes(mappedElapsed);

                if (s.mainAlpha > 0.01) {
                    for (var i = 0; i < vol.strikes.length; i++) {
                        drawStrike(vol.strikes[i], s.mainAlpha, s.branchAlpha, s.glow, s.mainW, s.brW);
                    }
                }

                if (s.flash) anyFlash = true;
            }

            if (anyFlash) {
                flashEl.classList.add('active');
            } else {
                flashEl.classList.remove('active');
            }

            if (hasActive || activeVolleys.length > 0) {
                rafId = requestAnimationFrame(renderFrame);
            } else {
                rafId = null;
            }
        }

        function ensureRendering() {
            if (!rafId) {
                rafId = requestAnimationFrame(renderFrame);
            }
        }

        // --- Organic scheduling ---
        function scheduleStorm() {
            var isBurst = Math.random() < 0.4;

            if (isBurst) {
                var burstCount = 2 + Math.floor(Math.random() * 3);
                var burstDelay = 0;
                for (var i = 0; i < burstCount; i++) {
                    (function(d) {
                        setTimeout(function() {
                            activeVolleys.push(createVolley());
                            ensureRendering();
                        }, d);
                    })(burstDelay);
                    burstDelay += 80 + Math.random() * 500;
                }
                setTimeout(scheduleStorm, burstDelay + 1500 + Math.random() * 3000);
            } else {
                activeVolleys.push(createVolley());
                ensureRendering();
                setTimeout(scheduleStorm, 1500 + Math.random() * 3500);
            }
        }

        var stormPaused = false;
        document.addEventListener('visibilitychange', function() {
            if (document.hidden) {
                stormPaused = true;
                if (rafId) { cancelAnimationFrame(rafId); rafId = null; }
            } else {
                if (stormPaused) {
                    stormPaused = false;
                    ensureRendering();
                }
            }
        });

        setTimeout(scheduleStorm, 1200);
    }

    initLightning();
})();
