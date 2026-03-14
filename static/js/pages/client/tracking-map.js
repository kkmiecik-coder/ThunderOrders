/**
 * Tracking Map — Interactive shipment map with stepper
 * Reads config from .od-tracking[data-*] attributes
 * Dependencies: Leaflet.js, polish-cities.js (both loaded conditionally)
 */
(function() {
    'use strict';

    // ===== CONSTANTS =====
    var KOREA = [37.5665, 126.978];
    var LUBLIN = [51.2465, 22.5684]; // Urząd celny
    var GOM = [49.85, 22.15];        // Racławówka
    var POLAND_CENTER = [51.9194, 19.1451];

    // Key route points (arcs will be generated between them)
    var ROUTE_STOPS = [KOREA, LUBLIN, GOM]; // Seoul → Lublin → GOM

    /**
     * Generate a smooth arc between two points using great-circle-like curve.
     * Adds intermediate points with a northward bulge for visual appeal.
     * @param {Array} from [lat, lng]
     * @param {Array} to [lat, lng]
     * @param {number} segments Number of intermediate points
     * @param {number} bulge Fraction of distance to offset perpendicular (positive = north)
     * @returns {Array} Array of [lat, lng] points including from and to
     */
    function generateArc(from, to, segments, bulge) {
        segments = segments || 40;
        bulge = bulge !== undefined ? bulge : 0.15;
        var points = [];
        var dLat = to[0] - from[0];
        var dLng = to[1] - from[1];
        // Perpendicular direction (rotated 90° counterclockwise = northward for east-west routes)
        var perpLat = -dLng;
        var perpLng = dLat;
        // Normalize perpendicular
        var perpLen = Math.sqrt(perpLat * perpLat + perpLng * perpLng);
        if (perpLen > 0) {
            perpLat /= perpLen;
            perpLng /= perpLen;
        }
        // Scale by route distance and bulge factor
        var dist = Math.sqrt(dLat * dLat + dLng * dLng);
        perpLat *= dist * bulge;
        perpLng *= dist * bulge;

        for (var i = 0; i <= segments; i++) {
            var t = i / segments;
            // Sine bulge peaks at midpoint
            var offset = Math.sin(t * Math.PI);
            points.push([
                from[0] + dLat * t + perpLat * offset,
                from[1] + dLng * t + perpLng * offset
            ]);
        }
        return points;
    }

    // Pre-generate the full arc route: Korea → Lublin → GOM
    // (client segment added dynamically)
    var ARC_KOREA_LUBLIN = generateArc(KOREA, LUBLIN, 50, 0.12);
    var ARC_LUBLIN_GOM = generateArc(LUBLIN, GOM, 15, 0.05);
    var ROUTE_KOREA_GOM = ARC_KOREA_LUBLIN.concat(ARC_LUBLIN_GOM.slice(1));
    // Index where Lublin sits in the combined route
    var LUBLIN_IDX = ARC_KOREA_LUBLIN.length - 1;

    // Status → step index mapping
    var STATUS_TO_STEP = {
        'dostarczone_proxy': 1,
        'w_drodze_polska': 2,
        'urzad_celny': 3,
        'dostarczone_gom': 4,
        'spakowane': 5,
        'wyslane': 6,
        'dostarczone': 7
    };

    // Tile URLs
    var TILES = {
        dark: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
        light: 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png'
    };
    var TILE_ATTRIB = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>';

    // Route colors per theme
    var ROUTE_COLORS = {
        dark: {
            completed: 'rgba(167,139,250,0.4)',
            active: '#f093fb',
            activeGlow: 'rgba(240,147,251,0.25)',
            future: 'rgba(240,147,251,0.15)'
        },
        light: {
            completed: 'rgba(90,24,154,0.3)',
            active: '#9D4EDD',
            activeGlow: 'rgba(90,24,154,0.15)',
            future: 'rgba(90,24,154,0.12)'
        }
    };

    // ===== HAVERSINE =====
    function haversine(lat1, lon1, lat2, lon2) {
        var R = 6371;
        var dLat = (lat2 - lat1) * Math.PI / 180;
        var dLon = (lon2 - lon1) * Math.PI / 180;
        var a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
                Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
                Math.sin(dLon / 2) * Math.sin(dLon / 2);
        return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    function routeDistance(points) {
        var total = 0;
        for (var i = 1; i < points.length; i++) {
            total += haversine(points[i - 1][0], points[i - 1][1], points[i][0], points[i][1]);
        }
        return total;
    }

    function formatKm(km) {
        return Math.round(km).toLocaleString('pl-PL');
    }

    // ===== HELPERS =====
    function getTheme() {
        return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
    }

    function makeIcon(className, size) {
        return L.divIcon({
            className: className,
            iconSize: [size || 14, size || 14],
            iconAnchor: [(size || 14) / 2, (size || 14) / 2]
        });
    }

    // ===== MAIN INIT =====
    function initTrackingMap() {
        var section = document.querySelector('.od-tracking');
        if (!section) return;

        var status = section.dataset.status;
        var proxyStatus = section.dataset.proxyStatus || '';
        var statusTimestamps = {};
        try {
            statusTimestamps = JSON.parse(section.dataset.statusTimestamps || '{}');
        } catch (e) { /* ignore */ }
        var shippingCity = section.dataset.shippingCity || '';
        var statusName = section.dataset.orderStatusName || '';

        // Determine current step index
        var currentStepIdx = STATUS_TO_STEP[status];
        if (currentStepIdx === undefined) {
            // oczekujace with proxy — step 0 (zamowiono) or step 1 (dostarczone_do_proxy)
            if (status === 'oczekujace' && proxyStatus) {
                currentStepIdx = proxyStatus === 'dostarczone_do_proxy' ? 1 : 0;
            } else {
                return;
            }
        }

        // Client coords
        var clientCoords = (typeof window.lookupCityCoords === 'function')
            ? window.lookupCityCoords(shippingCity)
            : POLAND_CENTER;

        // Build arc GOM → Client
        var ARC_GOM_CLIENT = generateArc(GOM, clientCoords, 15, -0.03);

        // Full route: Korea → Lublin → GOM → Client (all arcs)
        var fullRoute = ROUTE_KOREA_GOM.concat(ARC_GOM_CLIENT.slice(1));

        // Midpoint on the arc for "w drodze" visual centering
        var midRouteKoreaLublin = ARC_KOREA_LUBLIN[Math.floor(ARC_KOREA_LUBLIN.length / 2)];

        // Step → map coords (for flyTo)
        var stepCoords = [
            KOREA,                  // 0: Zamówiono
            KOREA,                  // 1: Dost. do Proxy
            midRouteKoreaLublin,    // 2: W drodze (center of Korea→Lublin arc)
            LUBLIN,                 // 3: Urząd Celny
            GOM,                    // 4: Dost. do GOM
            GOM,                    // 5: Spakowane
            ARC_GOM_CLIENT[Math.floor(ARC_GOM_CLIENT.length / 2)], // 6: Wysłane (mid GOM→client)
            clientCoords            // 7: Dostarczone
        ];

        var stepZooms = [6, 6, 3, 8, 10, 10, 8, 10];

        // Current position marker coords
        var currentMarkerCoords = stepCoords[currentStepIdx];

        // ===== INIT MAP =====
        var mapEl = document.getElementById('tracking-map');
        if (!mapEl) return;

        var map = L.map(mapEl, {
            zoomControl: true,
            scrollWheelZoom: true,
            maxBounds: [[15, 5], [65, 145]],
            minZoom: 3,
            maxZoom: 14
        });

        var theme = getTheme();
        var currentTileLayer = L.tileLayer(TILES[theme], {
            attribution: TILE_ATTRIB,
            maxZoom: 18
        }).addTo(map);

        // Remove loader when tiles load
        currentTileLayer.on('load', function() {
            var loader = section.querySelector('.od-tracking__loader');
            if (loader) loader.style.display = 'none';
        });

        // ===== DRAW ROUTE =====
        var routeLayers = [];

        function getActiveSegmentPoints() {
            if (currentStepIdx <= 1) {
                // At Korea — nothing completed yet, all future
                return { completed: [], active: [], future: fullRoute };
            }

            if (currentStepIdx === 2) {
                // W drodze do Polski — Korea→Lublin is active, Lublin→GOM→Client is future
                return {
                    completed: [],
                    active: ARC_KOREA_LUBLIN.slice(),
                    future: ARC_LUBLIN_GOM.concat(ARC_GOM_CLIENT.slice(1))
                };
            }

            if (currentStepIdx === 3) {
                // Urząd Celny (Lublin) — Korea→Lublin completed, at Lublin
                return {
                    completed: ARC_KOREA_LUBLIN.slice(),
                    active: [],
                    future: ARC_LUBLIN_GOM.concat(ARC_GOM_CLIENT.slice(1))
                };
            }

            if (currentStepIdx === 4) {
                // Dostarczone do GOM — Korea→Lublin→GOM completed
                return {
                    completed: ROUTE_KOREA_GOM.slice(),
                    active: [],
                    future: ARC_GOM_CLIENT.slice()
                };
            }

            if (currentStepIdx === 5) {
                // Spakowane — at GOM, same as above
                return {
                    completed: ROUTE_KOREA_GOM.slice(),
                    active: [],
                    future: ARC_GOM_CLIENT.slice()
                };
            }

            if (currentStepIdx === 6) {
                // Wysłane — Korea→GOM completed, GOM→Client active
                return {
                    completed: ROUTE_KOREA_GOM.slice(),
                    active: ARC_GOM_CLIENT.slice(),
                    future: []
                };
            }

            // Dostarczone — everything completed
            return { completed: fullRoute, active: [], future: [] };
        }

        function drawRoute() {
            routeLayers.forEach(function(l) { map.removeLayer(l); });
            routeLayers = [];

            var colors = ROUTE_COLORS[getTheme()];
            var segments = getActiveSegmentPoints();

            // Completed segment
            if (segments.completed.length > 1) {
                routeLayers.push(
                    L.polyline(segments.completed, {
                        color: colors.completed, weight: 3, smoothFactor: 2
                    }).addTo(map)
                );
            }

            // Active segment (glow underneath + solid on top)
            if (segments.active.length > 1) {
                routeLayers.push(
                    L.polyline(segments.active, {
                        color: colors.activeGlow, weight: 10, smoothFactor: 2, opacity: 0.5
                    }).addTo(map)
                );
                routeLayers.push(
                    L.polyline(segments.active, {
                        color: colors.active, weight: 3, smoothFactor: 2
                    }).addTo(map)
                );
            }

            // Future segment
            if (segments.future.length > 1) {
                routeLayers.push(
                    L.polyline(segments.future, {
                        color: colors.future, weight: 2, dashArray: '8,8', smoothFactor: 2
                    }).addTo(map)
                );
            }
        }

        // ===== ANIMATED TRAVELING DOT =====
        var travelingDot = null;
        var animFrameId = null;

        function interpolateRoute(points, t) {
            // t is 0..1 along the full polyline
            if (points.length < 2) return points[0] || KOREA;
            // Calculate total length and find segment
            var dists = [];
            var total = 0;
            for (var i = 1; i < points.length; i++) {
                var d = haversine(points[i-1][0], points[i-1][1], points[i][0], points[i][1]);
                dists.push(d);
                total += d;
            }
            var target = t * total;
            var acc = 0;
            for (var j = 0; j < dists.length; j++) {
                if (acc + dists[j] >= target) {
                    var segT = (target - acc) / dists[j];
                    return [
                        points[j][0] + (points[j+1][0] - points[j][0]) * segT,
                        points[j][1] + (points[j+1][1] - points[j][1]) * segT
                    ];
                }
                acc += dists[j];
            }
            return points[points.length - 1];
        }

        function startTravelingDot(activePoints) {
            if (animFrameId) cancelAnimationFrame(animFrameId);
            if (travelingDot) { map.removeLayer(travelingDot); travelingDot = null; }
            if (activePoints.length < 2) return;

            var dotEl = null;
            travelingDot = L.marker(activePoints[0], {
                icon: L.divIcon({
                    className: 'tm-marker-traveler',
                    iconSize: [10, 10],
                    iconAnchor: [5, 5]
                })
            }).addTo(map);

            var travelDuration = 6000; // ms A→B
            var pauseDuration = 800;   // ms pause at end before restart
            var cycleDuration = travelDuration + pauseDuration;
            var startTime = null;

            function animate(timestamp) {
                if (!startTime) startTime = timestamp;
                var elapsed = (timestamp - startTime) % cycleDuration;
                var t = Math.min(elapsed / travelDuration, 1);

                // Ease in-out
                t = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;

                var pos = interpolateRoute(activePoints, t);
                if (travelingDot) {
                    travelingDot.setLatLng(pos);

                    // Scale down at end, scale up at start
                    if (!dotEl) {
                        dotEl = travelingDot.getElement();
                    }
                    if (dotEl) {
                        if (elapsed > travelDuration) {
                            // Pause phase — shrink to 0
                            var fadeT = (elapsed - travelDuration) / pauseDuration;
                            dotEl.style.transform += ' scale(' + (1 - fadeT) + ')';
                            dotEl.style.opacity = 1 - fadeT;
                        } else if (elapsed < 300) {
                            // Fade in at start
                            var fadeIn = elapsed / 300;
                            dotEl.style.opacity = fadeIn;
                        } else {
                            dotEl.style.opacity = 1;
                        }
                    }
                }
                animFrameId = requestAnimationFrame(animate);
            }
            animFrameId = requestAnimationFrame(animate);
        }

        drawRoute();

        // Start traveling dot on active segment
        var activeSegment = getActiveSegmentPoints();
        if (activeSegment.active.length > 1) {
            startTravelingDot(activeSegment.active);
        }

        // ===== MARKERS =====
        L.marker(KOREA, { icon: makeIcon('tm-marker-korea') }).addTo(map)
            .bindPopup('<div class="tm-popup__title">Seoul, Korea</div><div class="tm-popup__detail">Proxy zakupowe</div>', { className: 'tm-popup' });

        // Lublin (Urząd Celny)
        L.marker(LUBLIN, { icon: makeIcon('tm-marker-customs') }).addTo(map)
            .bindPopup('<div class="tm-popup__title">Urząd Celny — Lublin</div><div class="tm-popup__detail">Odprawa celna</div>', { className: 'tm-popup' });

        L.marker(GOM, { icon: makeIcon('tm-marker-gom') }).addTo(map)
            .bindPopup('<div class="tm-popup__title">GOM — Racławówka</div><div class="tm-popup__detail">Magazyn ThunderOrders<br>Podkarpackie, Polska</div>', { className: 'tm-popup' });

        var clientLabel = shippingCity || 'Polska';
        L.marker(clientCoords, { icon: makeIcon('tm-marker-client') }).addTo(map)
            .bindPopup('<div class="tm-popup__title">Adres dostawy</div><div class="tm-popup__detail">' + clientLabel + '</div>', { className: 'tm-popup' });

        // Current position (pulsing) — only for "w drodze" and "wyslane" (moving states)
        if (currentStepIdx === 2 || currentStepIdx === 6) {
            L.marker(currentMarkerCoords, { icon: makeIcon('tm-marker-current', 16) }).addTo(map)
                .bindPopup('<div class="tm-popup__title">' + statusName + '</div><div class="tm-popup__detail">Aktualna pozycja przesyłki</div>', { className: 'tm-popup' });
        }

        // Fit bounds
        map.fitBounds(L.latLngBounds([KOREA, clientCoords]).pad(0.12));

        // ===== DISTANCE =====
        var segments = getActiveSegmentPoints();
        var completedDist = routeDistance(segments.completed);
        if (segments.active.length > 1) {
            completedDist += routeDistance(segments.active) * 0.5;
        }
        var totalDist = routeDistance(fullRoute);

        var kmEl = document.getElementById('tracking-km');
        if (kmEl) {
            kmEl.innerHTML = formatKm(completedDist) + ' km <small>/ ' + formatKm(totalDist) + ' km</small>';
        }

        // ===== STEPPER INTERACTION =====
        var steps = section.querySelectorAll('.od-step');
        steps.forEach(function(stepEl, i) {
            stepEl.addEventListener('click', function() {
                if (stepCoords[i]) {
                    map.flyTo(stepCoords[i], stepZooms[i], { duration: 1.2 });
                }
            });
        });

        // ===== MOBILE AUTO-SCROLL =====
        if (window.innerWidth < 1024) {
            var activeStep = section.querySelector('.od-step--now');
            if (activeStep) {
                var stepper = section.querySelector('.od-tracking__stepper');
                setTimeout(function() {
                    var scrollLeft = activeStep.offsetLeft - (stepper.offsetWidth / 2) + (activeStep.offsetWidth / 2);
                    stepper.scrollTo({ left: scrollLeft, behavior: 'smooth' });
                }, 100);
            }
        }

        // ===== THEME SWITCHING =====
        var observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(m) {
                if (m.attributeName === 'data-theme') {
                    var newTheme = getTheme();
                    map.removeLayer(currentTileLayer);
                    currentTileLayer = L.tileLayer(TILES[newTheme], {
                        attribution: TILE_ATTRIB, maxZoom: 18
                    }).addTo(map);
                    drawRoute();
                    // Restart traveling dot
                    var seg = getActiveSegmentPoints();
                    if (seg.active.length > 1) startTravelingDot(seg.active);
                }
            });
        });
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    }

    // ===== BOOT =====
    if (typeof L !== 'undefined') {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initTrackingMap);
        } else {
            initTrackingMap();
        }
    } else {
        // Leaflet not loaded — hide section gracefully
        var section = document.querySelector('.od-tracking');
        if (section) section.style.display = 'none';
    }
})();
