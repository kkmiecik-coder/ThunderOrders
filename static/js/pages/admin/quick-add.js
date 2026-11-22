/**
 * Szybkie dodawanie produktów on hand — ekran pod telefon.
 *
 * Zdjęcia zmniejszane w przeglądarce (canvas → JPEG, dłuższy bok max 1600 px)
 * przed wysłaniem: szybciej na słabym internecie i omija HEIC z iPhone'a.
 * Lista „dodane w tej rundzie” w sessionStorage (tylko wygoda — może zniknąć).
 * Przy błędzie zapisu NIC nie jest czyszczone, żeby dało się ponowić.
 */
(function () {
    'use strict';

    var MAX_SIDE = 1600;
    var JPEG_QUALITY = 0.85;
    var STORAGE_KEY = 'quickAddRound';

    var form = document.getElementById('qa-form');
    if (!form) return;

    var photosInput = document.getElementById('qa-photos');
    var previews = document.getElementById('qa-previews');
    var photoLabel = document.getElementById('qa-photo-label');
    var nameInput = document.getElementById('qa-name');
    var priceInput = document.getElementById('qa-price');
    var qtyInput = document.getElementById('qa-quantity');
    var descInput = document.getElementById('qa-description');
    var submitBtn = document.getElementById('qa-submit');
    var list = document.getElementById('qa-list');
    var listEmpty = document.getElementById('qa-list-empty');

    var maxPhotos = parseInt(form.dataset.maxPhotos, 10) || 10;
    var createUrl = form.dataset.createUrl;
    var baseUrl = form.dataset.baseUrl.replace(/\/$/, '');

    var photos = [];      // [{blob, url}]
    var photoSeq = 0;
    var round = [];       // produkty z tej rundy (kształt z serialize_quick_product)
    var saving = false;

    function toast(msg, type) {
        if (typeof window.showToast === 'function') window.showToast(msg, type);
    }

    function getCsrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) return meta.getAttribute('content');
        var match = document.cookie.match(/csrf_token=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    function formatPrice(str) {
        return String(str).replace('.', ',') + ' zł';
    }

    // ---------- zdjęcia ----------

    function loadImage(file) {
        if (window.createImageBitmap) {
            return createImageBitmap(file, { imageOrientation: 'from-image' })
                .catch(function () { return loadViaImg(file); });
        }
        return loadViaImg(file);
    }

    function loadViaImg(file) {
        return new Promise(function (resolve, reject) {
            var url = URL.createObjectURL(file);
            var img = new Image();
            img.onload = function () { URL.revokeObjectURL(url); resolve(img); };
            img.onerror = function () { URL.revokeObjectURL(url); reject(new Error('decode')); };
            img.src = url;
        });
    }

    function shrink(file) {
        return loadImage(file).then(function (img) {
            var w = img.width, h = img.height;
            var scale = Math.min(1, MAX_SIDE / Math.max(w, h));
            var canvas = document.createElement('canvas');
            canvas.width = Math.round(w * scale);
            canvas.height = Math.round(h * scale);
            canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
            if (img.close) img.close();
            return new Promise(function (resolve, reject) {
                canvas.toBlob(function (blob) {
                    blob ? resolve(blob) : reject(new Error('toBlob'));
                }, 'image/jpeg', JPEG_QUALITY);
            });
        });
    }

    function renderPreviews() {
        previews.textContent = '';
        photos.forEach(function (p, i) {
            var box = document.createElement('div');
            box.className = 'qa-preview';
            var img = document.createElement('img');
            img.src = p.url;
            img.alt = 'Zdjęcie ' + (i + 1);
            box.appendChild(img);
            if (i === 0) {
                var main = document.createElement('span');
                main.className = 'qa-preview-main';
                main.textContent = 'Główne';
                box.appendChild(main);
            }
            var rm = document.createElement('button');
            rm.type = 'button';
            rm.className = 'qa-preview-remove';
            rm.dataset.index = String(i);
            rm.setAttribute('aria-label', 'Usuń zdjęcie');
            var x = document.createElement('span');
            x.textContent = '×';
            rm.appendChild(x);
            box.appendChild(rm);
            previews.appendChild(box);
        });
        photoLabel.textContent = photos.length ? 'Dodaj kolejne zdjęcie' : 'Zrób / wybierz zdjęcie';
    }

    photosInput.addEventListener('change', function () {
        var files = Array.prototype.slice.call(photosInput.files || []);
        photosInput.value = '';
        if (!files.length) return;
        var free = maxPhotos - photos.length;
        if (files.length > free) {
            toast('Maksymalnie ' + maxPhotos + ' zdjęć', 'warning');
            files = files.slice(0, Math.max(0, free));
        }
        files.reduce(function (chain, file) {
            return chain.then(function () {
                return shrink(file).then(function (blob) {
                    photos.push({ blob: blob, url: URL.createObjectURL(blob) });
                    renderPreviews();
                }).catch(function () {
                    toast('Nie udało się odczytać zdjęcia', 'error');
                });
            });
        }, Promise.resolve());
    });

    previews.addEventListener('click', function (e) {
        var btn = e.target.closest('.qa-preview-remove');
        if (!btn) return;
        var i = parseInt(btn.dataset.index, 10);
        var removed = photos.splice(i, 1)[0];
        if (removed) URL.revokeObjectURL(removed.url);
        renderPreviews();
    });

    function clearForm() {
        photos.forEach(function (p) { URL.revokeObjectURL(p.url); });
        photos = [];
        renderPreviews();
        nameInput.value = '';
        priceInput.value = '';
        qtyInput.value = '1';
        descInput.value = '';
    }

    // ---------- zapis ----------

    form.addEventListener('submit', function (e) {
        e.preventDefault();
        if (saving) return;
        if (!photos.length) { toast('Dodaj co najmniej jedno zdjęcie', 'warning'); return; }
        if (!nameInput.value.trim()) { toast('Podaj nazwę', 'warning'); nameInput.focus(); return; }
        if (!priceInput.value.trim()) { toast('Podaj poprawną cenę', 'warning'); priceInput.focus(); return; }

        var fd = new FormData();
        fd.append('name', nameInput.value);
        fd.append('sale_price', priceInput.value);
        fd.append('quantity', qtyInput.value);
        fd.append('description', descInput.value);
        photos.forEach(function (p) {
            photoSeq += 1;
            fd.append('images', p.blob, 'zdjecie-' + photoSeq + '.jpg');
        });

        saving = true;
        submitBtn.disabled = true;
        submitBtn.textContent = 'Zapisuję…';

        fetch(createUrl, {
            method: 'POST',
            headers: { 'X-CSRFToken': getCsrfToken(), 'X-Requested-With': 'XMLHttpRequest' },
            body: fd,
            credentials: 'same-origin'
        }).then(function (r) {
            return r.json().catch(function () { return {}; }).then(function (data) {
                return { ok: r.ok, data: data };
            });
        }).then(function (res) {
            if (res.ok && res.data.success) {
                round.unshift(res.data.product);
                saveRound();
                renderList();
                toast('Dodano: ' + res.data.product.name, 'success');
                clearForm();
                photosInput.focus();
            } else {
                toast(res.data.error || 'Nie udało się zapisać — sprawdź internet i spróbuj ponownie', 'error');
            }
        }).catch(function () {
            toast('Nie udało się zapisać — sprawdź internet i spróbuj ponownie', 'error');
        }).then(function () {
            saving = false;
            submitBtn.disabled = false;
            submitBtn.textContent = 'Dodaj i następny';
        });
    });

    // ---------- lista rundy ----------

    function saveRound() {
        try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(round)); } catch (e) { /* bez pamięci — trudno */ }
    }

    function loadRound() {
        try {
            var raw = sessionStorage.getItem(STORAGE_KEY);
            var parsed = raw ? JSON.parse(raw) : [];
            return Array.isArray(parsed) ? parsed : [];
        } catch (e) {
            return [];
        }
    }

    function el(tag, cls, text) {
        var node = document.createElement(tag);
        if (cls) node.className = cls;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    function renderItem(p) {
        var li = el('li', 'qa-item' + (p.is_active ? '' : ' qa-item-hidden'));
        li.dataset.id = String(p.id);

        var main = el('div', 'qa-item-main');
        var thumb = el('img', 'qa-item-thumb');
        thumb.alt = '';
        if (p.thumb_url) thumb.src = p.thumb_url;
        main.appendChild(thumb);

        var info = el('div', 'qa-item-info');
        var name = el('div', 'qa-item-name', p.name);
        if (!p.is_active) name.appendChild(el('span', 'qa-item-badge', 'Ukryty'));
        info.appendChild(name);
        info.appendChild(el('div', 'qa-item-meta', formatPrice(p.sale_price) + ' · szt. ' + p.quantity));
        main.appendChild(info);
        li.appendChild(main);

        if (p.is_active) {
            var actions = el('div', 'qa-item-actions');
            var edit = el('button', 'qa-btn', 'Popraw');
            edit.type = 'button';
            edit.dataset.action = 'edit';
            var hide = el('button', 'qa-btn qa-btn-danger', 'Ukryj');
            hide.type = 'button';
            hide.dataset.action = 'hide';
            actions.appendChild(edit);
            actions.appendChild(hide);
            li.appendChild(actions);
        }
        return li;
    }

    function renderEditForm(li, p) {
        var existing = li.querySelector('.qa-edit');
        if (existing) { existing.remove(); return; }
        var box = el('div', 'qa-edit');
        var n = el('input', 'qa-input');
        n.type = 'text'; n.maxLength = 255; n.value = p.name; n.dataset.field = 'name';
        n.setAttribute('aria-label', 'Nazwa');
        var row = el('div', 'qa-row');
        var c1 = el('div', 'qa-col');
        var pr = el('input', 'qa-input');
        pr.type = 'text'; pr.inputMode = 'decimal'; pr.value = String(p.sale_price).replace('.', ',');
        pr.dataset.field = 'sale_price'; pr.setAttribute('aria-label', 'Cena');
        c1.appendChild(pr);
        var c2 = el('div', 'qa-col qa-col-small');
        var q = el('input', 'qa-input');
        q.type = 'number'; q.min = '1'; q.step = '1'; q.inputMode = 'numeric'; q.value = String(p.quantity);
        q.dataset.field = 'quantity'; q.setAttribute('aria-label', 'Ilość');
        c2.appendChild(q);
        row.appendChild(c1); row.appendChild(c2);
        var save = el('button', 'qa-btn qa-btn-primary', 'Zapisz');
        save.type = 'button';
        save.dataset.action = 'save';
        box.appendChild(n); box.appendChild(row); box.appendChild(save);
        li.appendChild(box);
        n.focus();
    }

    function renderList() {
        list.textContent = '';
        round.forEach(function (p) { list.appendChild(renderItem(p)); });
        listEmpty.style.display = round.length ? 'none' : '';
    }

    function findInRound(id) {
        for (var i = 0; i < round.length; i++) if (round[i].id === id) return i;
        return -1;
    }

    function postJson(url, body) {
        return fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify(body || {}),
            credentials: 'same-origin'
        }).then(function (r) {
            return r.json().catch(function () { return {}; }).then(function (data) {
                return { ok: r.ok, data: data };
            });
        });
    }

    function replaceInRound(product) {
        var i = findInRound(product.id);
        if (i >= 0) round[i] = product;
        saveRound();
        renderList();
    }

    list.addEventListener('click', function (e) {
        var btn = e.target.closest('button[data-action]');
        if (!btn) return;
        var li = btn.closest('.qa-item');
        var id = parseInt(li.dataset.id, 10);
        var idx = findInRound(id);
        if (idx < 0) return;
        var p = round[idx];
        var action = btn.dataset.action;

        if (action === 'edit') {
            renderEditForm(li, p);
            return;
        }

        if (action === 'save') {
            var box = li.querySelector('.qa-edit');
            var body = {};
            box.querySelectorAll('input[data-field]').forEach(function (inp) {
                body[inp.dataset.field] = inp.value;
            });
            btn.disabled = true;
            postJson(baseUrl + '/' + id + '/update', body).then(function (res) {
                if (res.ok && res.data.success) {
                    replaceInRound(res.data.product);
                    toast('Zapisano zmiany', 'success');
                } else {
                    btn.disabled = false;
                    toast(res.data.error || 'Nie udało się zapisać — spróbuj ponownie', 'error');
                }
            }).catch(function () {
                btn.disabled = false;
                toast('Nie udało się zapisać — sprawdź internet i spróbuj ponownie', 'error');
            });
            return;
        }

        if (action === 'hide') {
            if (!window.confirm('Ukryć ten produkt ze sklepu?')) return;
            btn.disabled = true;
            postJson(baseUrl + '/' + id + '/hide').then(function (res) {
                if (res.ok && res.data.success) {
                    replaceInRound(res.data.product);
                    toast('Produkt ukryty', 'success');
                } else {
                    btn.disabled = false;
                    toast(res.data.error || 'Nie udało się ukryć — spróbuj ponownie', 'error');
                }
            }).catch(function () {
                btn.disabled = false;
                toast('Nie udało się ukryć — sprawdź internet i spróbuj ponownie', 'error');
            });
        }
    });

    round = loadRound();
    renderList();
})();
