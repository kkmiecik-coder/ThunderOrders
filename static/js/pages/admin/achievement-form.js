/**
 * Admin: Achievement form — auto-slug z nazwy
 * Tylko dla NOWEJ odznaki (gdy slug pole jest puste przy załadowaniu).
 * Po pierwszym ręcznym edycie sluga przez admina wyłącza się auto-update.
 */
(function() {
    'use strict';

    var PL_MAP = {
        'ą':'a','ć':'c','ę':'e','ł':'l','ń':'n','ó':'o','ś':'s','ź':'z','ż':'z',
        'Ą':'a','Ć':'c','Ę':'e','Ł':'l','Ń':'n','Ó':'o','Ś':'s','Ź':'z','Ż':'z'
    };

    function slugify(name) {
        var s = String(name || '');
        // Zamiana polskich znaków
        s = s.split('').map(function(c) { return PL_MAP[c] || c; }).join('');
        s = s.toLowerCase();
        // Wszystko nie-alphanum → '-'
        s = s.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
        s = s.slice(0, 80);
        return s || 'badge';
    }

    function init() {
        var nameInput = document.getElementById('name');
        var slugInput = document.getElementById('slug');
        if (!nameInput || !slugInput) return;

        // Slug edytowalny? (readonly = edycja odznaki z posiadaczami)
        if (slugInput.readOnly) return;

        // Czy admin już wpisał coś w slug? (init: pre-filled = nie auto-update)
        var slugTouched = slugInput.value.length > 0;

        // Listenery
        slugInput.addEventListener('input', function() {
            // Po manualnej edycji wyłącz auto-update
            slugTouched = slugInput.value.length > 0;
        });

        nameInput.addEventListener('input', function() {
            if (!slugTouched) {
                slugInput.value = slugify(nameInput.value);
            }
        });

        // Trigger przy załadowaniu jeśli name jest pre-filled a slug jest pusty
        if (!slugTouched && nameInput.value) {
            slugInput.value = slugify(nameInput.value);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
