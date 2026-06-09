/**
 * contest-form.js — Admin contest form
 * - Debounced product search (picker)
 * - Criteria checkbox toggles
 * Vanilla JS, no inline scripts.
 */
(function () {
  'use strict';

  /* ---------------------------------------------------------------------- */
  /* Product picker                                                           */
  /* ---------------------------------------------------------------------- */

  var prizeSearch = document.getElementById('prizeSearch');
  var prizeResults = document.getElementById('prizeResults');
  var prizeProductId = document.getElementById('prizeProductId');

  if (!prizeSearch || !prizeResults || !prizeProductId) return;

  var debounceTimer = null;

  function debounce(fn, delay) {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(fn, delay);
  }

  function renderPickerResults(products) {
    prizeResults.innerHTML = '';
    if (!products || products.length === 0) {
      var hint = document.createElement('div');
      hint.className = 'ca-picker-hint';
      hint.textContent = 'Brak wyników.';
      prizeResults.appendChild(hint);
      return;
    }
    products.forEach(function (p) {
      var row = document.createElement('div');
      row.className = 'ca-picker-result';
      row.setAttribute('data-id', p.id);
      row.setAttribute('data-name', p.name);

      var thumb;
      if (p.image_url) {
        thumb = document.createElement('img');
        thumb.className = 'ca-picker-thumb';
        thumb.src = p.image_url;
        thumb.alt = '';
      } else {
        thumb = document.createElement('div');
        thumb.className = 'ca-picker-thumb-placeholder';
        thumb.textContent = '📦';
      }

      var meta = document.createElement('div');
      var nameEl = document.createElement('div');
      nameEl.className = 'ca-picker-meta';
      nameEl.textContent = p.name;

      var sub = document.createElement('div');
      sub.className = 'ca-picker-meta-sub';
      var parts = [];
      if (p.sku) parts.push('SKU ' + p.sku);
      if (p.price !== undefined && p.price !== null) parts.push(p.price + ' zł');
      sub.textContent = parts.join(' • ');

      meta.appendChild(nameEl);
      meta.appendChild(sub);
      row.appendChild(thumb);
      row.appendChild(meta);

      row.addEventListener('click', function () {
        selectProduct(p.id, p.name);
      });

      prizeResults.appendChild(row);
    });
  }

  function selectProduct(id, name) {
    prizeProductId.value = id;
    prizeSearch.value = name;
    prizeResults.innerHTML = '';
    var sel = document.createElement('div');
    sel.className = 'ca-picker-result ca-picker-result--selected';
    var icon = document.createElement('div');
    icon.className = 'ca-picker-thumb-placeholder';
    icon.textContent = '📦';
    var meta = document.createElement('div');
    var nameEl = document.createElement('div');
    nameEl.className = 'ca-picker-meta';
    nameEl.textContent = name;
    var sub = document.createElement('div');
    sub.className = 'ca-picker-meta-sub';
    sub.textContent = 'Wybrano';
    meta.appendChild(nameEl);
    meta.appendChild(sub);
    sel.appendChild(icon);
    sel.appendChild(meta);
    prizeResults.appendChild(sel);
  }

  function searchProducts(q) {
    if (q.length < 2) {
      prizeResults.innerHTML = '<div class="ca-picker-hint">Wpisz co najmniej 2 znaki, by wyszukać produkt.</div>';
      return;
    }
    prizeResults.innerHTML = '<div class="ca-picker-loading">Wyszukiwanie…</div>';
    fetch('/api/products/search?q=' + encodeURIComponent(q), {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.success) {
          renderPickerResults(data.products);
        } else {
          prizeResults.innerHTML = '<div class="ca-picker-hint">Błąd wyszukiwania.</div>';
        }
      })
      .catch(function () {
        prizeResults.innerHTML = '<div class="ca-picker-hint">Błąd połączenia.</div>';
      });
  }

  prizeSearch.addEventListener('input', function () {
    var q = prizeSearch.value.trim();
    debounce(function () { searchProducts(q); }, 280);
  });

  /* ---------------------------------------------------------------------- */
  /* Criteria toggles                                                         */
  /* ---------------------------------------------------------------------- */

  // Derived from DOM so it always matches the number of [data-crit-row] elements in form.html.
  var critRows = document.querySelectorAll('[data-crit-row]');
  var NUM_CRITS = critRows.length;

  function syncCrit(idx) {
    var box = document.getElementById('critBox' + idx);
    var text = document.getElementById('critText' + idx);
    var inp = document.getElementById('critInp' + idx);
    if (!box || !text || !inp) return;
    var active = inp.value !== '' && inp.value !== null;
    setCritState(idx, active);
  }

  function setCritState(idx, active) {
    var box = document.getElementById('critBox' + idx);
    var text = document.getElementById('critText' + idx);
    var inp = document.getElementById('critInp' + idx);
    if (!box || !text || !inp) return;
    if (active) {
      box.classList.add('ca-cbox--on');
      box.textContent = '✓';
      text.classList.remove('ca-ctext--off');
      inp.classList.remove('ca-cinp--disabled');
      inp.disabled = false;
    } else {
      box.classList.remove('ca-cbox--on');
      box.textContent = '';
      text.classList.add('ca-ctext--off');
      inp.classList.add('ca-cinp--disabled');
      inp.disabled = true;
      inp.value = '';
    }
    // Keep aria-checked in sync on the row element
    var row = box.closest('[data-crit-row]');
    if (row) row.setAttribute('aria-checked', active ? 'true' : 'false');
  }

  function toggleCrit(idx) {
    var inp = document.getElementById('critInp' + idx);
    if (!inp) return;
    var isActive = !inp.classList.contains('ca-cinp--disabled');
    setCritState(idx, !isActive);
    if (!isActive) {
      // Became active — focus input
      setTimeout(function () { inp.focus(); }, 10);
    }
  }

  // Attach click and keyboard handlers to each criteria row
  for (var i = 0; i < critRows.length; i++) {
    (function (idx, row) {
      row.addEventListener('click', function (e) {
        var inp = document.getElementById('critInp' + idx);
        if (!inp) return;
        // If user clicked the input itself, don't toggle
        if (e.target === inp) return;
        toggleCrit(idx);
      });

      // Keyboard accessibility: Enter/Space toggle the criterion
      row.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault(); // prevent page scroll on Space
          toggleCrit(idx);
        }
      });
    }(i, critRows[i]));
  }

  // Sync initial state on load
  for (var j = 0; j < NUM_CRITS; j++) {
    syncCrit(j);
  }

}());
