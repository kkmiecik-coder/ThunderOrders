/**
 * Auth Pages - Particle System (ambient dots + embers)
 * Extracted from countdown.js - particles only, no lightning/beams
 */
(function() {
    'use strict';

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

    // ---- Embers (fire sparks rising from bottom) ----
    var EMBER_MAX = 150;
    var emberSpawnInterval = 50;
    var emberAccum = 0;
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
        if (dt > 100) dt = 16;

        ctx.clearRect(0, 0, canvas.width, canvas.height);
        var h = canvas.height;

        // -- Ambient --
        for (var i = ambient.length - 1; i >= 0; i--) {
            var a = ambient[i];
            a.y += a.vy;
            a.sp += a.ss;
            a.x += Math.sin(a.sp) * a.sa;
            if (Math.abs(a.vy) < 0.08 || a.y < -10) {
                ambient.splice(i, 1);
                continue;
            }
            ctx.beginPath();
            ctx.arc(a.x, a.y, a.r, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(' + a.c.r + ',' + a.c.g + ',' + a.c.b + ',' + a.o + ')';
            ctx.fill();
        }

        while (ambient.length < AMBIENT_COUNT) {
            ambient.push(makeAmbient(false));
        }

        // -- Ember spawning --
        emberAccum += dt;
        while (emberAccum >= emberSpawnInterval && embers.length < EMBER_MAX) {
            embers.push(makeEmber());
            emberAccum -= emberSpawnInterval;
            emberSpawnInterval = 30 + Math.random() * 50;
        }
        if (embers.length >= EMBER_MAX) emberAccum = 0;

        // -- Ember update & draw --
        for (var e = embers.length - 1; e >= 0; e--) {
            var em = embers[e];
            em.y += em.vy;
            var travel = em.startY - em.y;

            em.w1p += em.w1s;
            em.w2p += em.w2s;
            var wobble = Math.sin(em.w1p) * em.w1a + Math.sin(em.w2p) * em.w2a;

            em.tt++;
            if (em.tt > em.ti) {
                em.tt = 0;
                em.ti = 60 + Math.random() * 80;
                em.vx += (Math.random() - 0.5) * em.ts;
            }
            em.vx *= 0.995;
            em.x += wobble + em.vx;

            var life = 1.0 - Math.min(1, travel / (h * 0.9));
            em.o = em.maxO * life;
            var dr = em.r * (0.3 + 0.7 * life);

            if (life <= 0.01 || em.y < -20) {
                embers.splice(e, 1);
                continue;
            }

            ctx.beginPath();
            ctx.arc(em.x, em.y, dr, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(' + em.c.r + ',' + em.c.g + ',' + em.c.b + ',' + em.o + ')';
            ctx.fill();

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

    for (var i = 0; i < AMBIENT_COUNT; i++) ambient.push(makeAmbient(true));

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
})();
