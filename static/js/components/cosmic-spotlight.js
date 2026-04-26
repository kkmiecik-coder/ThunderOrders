/**
 * Cosmic Spotlight — wstrzykuje warstwy DOM (mgławice, gwiazdy, promienie supernovej)
 * dla badge-spotlight z data-rarity="cosmic". Wywoływane w momencie aktywacji spotlight'u.
 */
(function() {
    'use strict';

    function buildCosmicLayers() {
        var layers = document.createElement('div');
        layers.className = 'cosmic-layers';
        layers.innerHTML = ''
            + '<div class="cosmic-backdrop"></div>'
            + '<div class="nebula-cloud purple"></div>'
            + '<div class="nebula-cloud blue"></div>'
            + '<div class="nebula-cloud pink"></div>'
            + '<div class="star-field"></div>'
            + '<div class="stars-glow">'
            +     '<div class="glow-star" style="left: 12%; top: 18%; animation-delay: 0s;"></div>'
            +     '<div class="glow-star" style="left: 28%; top: 60%; animation-delay: 0.5s;"></div>'
            +     '<div class="glow-star" style="left: 75%; top: 22%; animation-delay: 1s;"></div>'
            +     '<div class="glow-star" style="left: 88%; top: 65%; animation-delay: 1.5s;"></div>'
            +     '<div class="glow-star" style="left: 15%; top: 82%; animation-delay: 2s;"></div>'
            +     '<div class="glow-star" style="left: 65%; top: 88%; animation-delay: 2.5s;"></div>'
            + '</div>'
            + '<div class="shooting-bg" style="top: 10%; animation-delay: 0s;"></div>'
            + '<div class="shooting-bg" style="top: 55%; animation-delay: 1.3s;"></div>'
            + '<div class="shooting-bg" style="top: 80%; animation-delay: 2.6s;"></div>'
            + '<div class="supernova-core"></div>'
            + '<div class="ray" style="--rot: 0deg; animation-delay: 0.2s;"></div>'
            + '<div class="ray" style="--rot: 45deg; animation-delay: 0.25s;"></div>'
            + '<div class="ray" style="--rot: 90deg; animation-delay: 0.3s;"></div>'
            + '<div class="ray" style="--rot: 135deg; animation-delay: 0.35s;"></div>'
            + '<div class="ray" style="--rot: 180deg; animation-delay: 0.4s;"></div>'
            + '<div class="ray" style="--rot: 225deg; animation-delay: 0.45s;"></div>'
            + '<div class="ray" style="--rot: 270deg; animation-delay: 0.5s;"></div>'
            + '<div class="ray" style="--rot: 315deg; animation-delay: 0.55s;"></div>';
        return layers;
    }

    function injectCosmicLayers(spotlight) {
        if (!spotlight) return;
        if (spotlight.dataset.cosmicInjected === '1') return;
        if (spotlight.dataset.rarity !== 'cosmic') return;

        var layers = buildCosmicLayers();
        spotlight.insertBefore(layers, spotlight.firstChild);
        spotlight.dataset.cosmicInjected = '1';
    }

    function removeCosmicLayers(spotlight) {
        if (!spotlight) return;
        var existing = spotlight.querySelector('.cosmic-layers');
        if (existing) {
            existing.remove();
            spotlight.dataset.cosmicInjected = '';
        }
    }

    // API global do wywołania z kodu spotlight'u galerii
    window.CosmicSpotlight = {
        inject: injectCosmicLayers,
        remove: removeCosmicLayers
    };
})();
