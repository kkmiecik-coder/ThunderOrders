/**
 * contest-form.js — Admin contest form
 * - Prize panel: "Dodaj produkt" modal + "Dodaj zestaw" modal
 * - In-memory prizes[] array → prizes_json hidden field
 * - Image dropzone (drag-drop + click to select, preview)
 * - Criteria checkbox toggles (a11y preserved)
 * Vanilla JS, no inline scripts.
 */
(function () {
  'use strict';

  /* ====================================================================== */
  /* Helpers                                                                  */
  /* ====================================================================== */

  var debounceTimers = {};

  function debounce(key, fn, delay) {
    clearTimeout(debounceTimers[key]);
    debounceTimers[key] = setTimeout(fn, delay);
  }

  function escHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  /* ====================================================================== */
  /* Modal open / close                                                       */
  /* ====================================================================== */

  function openModal(el) {
    if (!el) return;
    el.classList.remove('closing');
    el.classList.add('active');
  }

  function closeModal(el) {
    if (!el) return;
    el.classList.add('closing');
    el.addEventListener('animationend', function handler() {
      el.classList.remove('active', 'closing');
      el.removeEventListener('animationend', handler);
    }, { once: true });
    // Fallback in case animation doesn't fire
    setTimeout(function () {
      el.classList.remove('active', 'closing');
    }, 400);
  }

  // Close modals on overlay click
  document.addEventListener('click', function (e) {
    if (e.target && e.target.classList && e.target.classList.contains('modal-overlay')) {
      closeModal(e.target);
    }
  });

  /* ====================================================================== */
  /* Prize state management                                                   */
  /* ====================================================================== */

  var prizesJsonEl = document.getElementById('prizesJson');
  var prizes = [];

  // Initialise from server-rendered JSON (edit mode)
  if (prizesJsonEl && prizesJsonEl.value) {
    try {
      prizes = JSON.parse(prizesJsonEl.value) || [];
    } catch (e) {
      prizes = [];
    }
  }

  function syncJson() {
    if (!prizesJsonEl) return;
    prizesJsonEl.value = JSON.stringify(prizes);
  }

  function clampQty(v) {
    var n = parseInt(v, 10);
    return (!n || n < 1) ? 1 : n;
  }

  /* ====================================================================== */
  /* Render prize list                                                        */
  /* ====================================================================== */

  var prizeList = document.getElementById('prizeList');

  function thumbHtml(imgUrl, size) {
    size = size || 38;
    if (imgUrl) {
      return '<img class="ca-prize-thumb" src="' + escHtml(imgUrl) + '" alt="" ' +
             'width="' + size + '" height="' + size + '">';
    }
    return '<div class="ca-prize-thumb-placeholder">📦</div>';
  }

  function stepperHtml(qty, dataAttr) {
    return '<div class="ca-prize-stepper">' +
      '<button type="button" class="ca-stepper-btn ca-stepper-minus" ' + dataAttr + '>−</button>' +
      '<input type="number" class="ca-stepper-inp" value="' + qty + '" min="1" ' + dataAttr + '>' +
      '<button type="button" class="ca-stepper-plus ca-stepper-btn" ' + dataAttr + '>+</button>' +
      '</div>';
  }

  function renderPrizes() {
    if (!prizeList) return;
    if (prizes.length === 0) {
      prizeList.innerHTML = '<div class="ca-prize-empty">Brak nagród — dodaj produkt lub zestaw powyżej.</div>';
      return;
    }
    var html = '';
    prizes.forEach(function (entry, idx) {
      if (entry.name) {
        // Set entry
        var innerHtml = '';
        (entry.items || []).forEach(function (it) {
          innerHtml += '<div class="ca-prize-set-item">' + thumbHtml(it._img, 26) +
            '<span class="ca-prize-set-qty">' + escHtml(it.quantity) + '×</span>' +
            '<span class="ca-prize-set-name">' + escHtml(it._name || '') + '</span>' +
            '</div>';
        });
        html += '<div class="ca-prize-item ca-prize-item--set" data-idx="' + idx + '">' +
          '<div class="ca-prize-set-header">' +
            '<span class="ca-prize-set-badge">Zestaw</span>' +
            '<span class="ca-prize-name">' + escHtml(entry.name) + '</span>' +
          '</div>' +
          '<div class="ca-prize-set-inner">' + innerHtml + '</div>' +
          '<div class="ca-prize-item-footer">' +
            '<span class="ca-prize-qty-label">Liczba zestawów:</span>' +
            stepperHtml(entry.quantity, 'data-entry-idx="' + idx + '"') +
            '<button type="button" class="ca-prize-remove" data-remove-idx="' + idx + '" aria-label="Usuń">×</button>' +
          '</div>' +
          '</div>';
      } else {
        // Single product entry
        var it0 = (entry.items && entry.items[0]) || {};
        html += '<div class="ca-prize-item" data-idx="' + idx + '">' +
          thumbHtml(it0._img) +
          '<span class="ca-prize-name">' + escHtml(it0._name || '—') + '</span>' +
          stepperHtml(entry.quantity, 'data-entry-idx="' + idx + '"') +
          '<button type="button" class="ca-prize-remove" data-remove-idx="' + idx + '" aria-label="Usuń">×</button>' +
          '</div>';
      }
    });
    prizeList.innerHTML = html;
    bindPrizeListEvents();
  }

  function bindPrizeListEvents() {
    if (!prizeList) return;

    // Stepper minus buttons
    prizeList.querySelectorAll('.ca-stepper-minus').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var idx = parseInt(btn.getAttribute('data-entry-idx'), 10);
        if (isNaN(idx)) return;
        prizes[idx].quantity = Math.max(1, (prizes[idx].quantity || 1) - 1);
        syncJson();
        renderPrizes();
      });
    });

    // Stepper plus buttons
    prizeList.querySelectorAll('.ca-stepper-plus').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var idx = parseInt(btn.getAttribute('data-entry-idx'), 10);
        if (isNaN(idx)) return;
        prizes[idx].quantity = (prizes[idx].quantity || 1) + 1;
        syncJson();
        renderPrizes();
      });
    });

    // Stepper inputs
    prizeList.querySelectorAll('.ca-stepper-inp').forEach(function (inp) {
      inp.addEventListener('change', function () {
        var idx = parseInt(inp.getAttribute('data-entry-idx'), 10);
        if (isNaN(idx)) return;
        prizes[idx].quantity = clampQty(inp.value);
        syncJson();
        renderPrizes();
      });
    });

    // Remove buttons
    prizeList.querySelectorAll('.ca-prize-remove').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var idx = parseInt(btn.getAttribute('data-remove-idx'), 10);
        if (isNaN(idx)) return;
        prizes.splice(idx, 1);
        syncJson();
        renderPrizes();
      });
    });
  }

  // Initial render
  renderPrizes();

  /* ====================================================================== */
  /* Product search helper (shared by both modals)                           */
  /* ====================================================================== */

  function searchProducts(q, resultsEl, onSelect) {
    if (q.length < 2) {
      resultsEl.innerHTML = '<div class="ca-picker-hint">Wpisz co najmniej 2 znaki, by wyszukać produkt.</div>';
      return;
    }
    resultsEl.innerHTML = '<div class="ca-picker-loading">Wyszukiwanie…</div>';
    fetch('/api/products/search?q=' + encodeURIComponent(q), {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.success || !data.products || !data.products.length) {
          resultsEl.innerHTML = '<div class="ca-picker-hint">Brak wyników.</div>';
          return;
        }
        var html = '';
        data.products.forEach(function (p) {
          var imgHtml = p.image_url
            ? '<img class="ca-picker-thumb" src="' + escHtml(p.image_url) + '" alt="">'
            : '<div class="ca-picker-thumb-placeholder">📦</div>';
          var sub = [];
          if (p.sku) sub.push('SKU ' + escHtml(p.sku));
          if (p.price !== undefined && p.price !== null) sub.push(escHtml(String(p.price)) + ' zł');
          html += '<div class="ca-picker-result" data-pid="' + escHtml(p.id) + '" ' +
            'data-name="' + escHtml(p.name) + '" ' +
            'data-img="' + escHtml(p.image_url || '') + '">' +
            imgHtml +
            '<div class="ca-picker-meta">' +
              '<div>' + escHtml(p.name) + '</div>' +
              '<div class="ca-picker-meta-sub">' + sub.join(' • ') + '</div>' +
            '</div>' +
            '</div>';
        });
        resultsEl.innerHTML = html;
        resultsEl.querySelectorAll('.ca-picker-result').forEach(function (row) {
          row.addEventListener('click', function () {
            onSelect({
              id: parseInt(row.getAttribute('data-pid'), 10),
              name: row.getAttribute('data-name'),
              image_url: row.getAttribute('data-img') || null,
            });
          });
        });
      })
      .catch(function () {
        resultsEl.innerHTML = '<div class="ca-picker-hint">Błąd połączenia.</div>';
      });
  }

  /* ====================================================================== */
  /* "Dodaj produkt" modal                                                   */
  /* ====================================================================== */

  var productModal = document.getElementById('prizeProductModal');
  var productSearch = document.getElementById('productModalSearch');
  var productResults = document.getElementById('productModalResults');
  var btnAddProduct = document.getElementById('btnAddProduct');
  var btnCloseProductModal = document.getElementById('btnCloseProductModal');

  if (btnAddProduct && productModal) {
    btnAddProduct.addEventListener('click', function () {
      if (productSearch) { productSearch.value = ''; }
      if (productResults) { productResults.innerHTML = '<div class="ca-picker-hint">Wpisz co najmniej 2 znaki, by wyszukać produkt.</div>'; }
      openModal(productModal);
      setTimeout(function () { if (productSearch) productSearch.focus(); }, 100);
    });
  }

  if (btnCloseProductModal && productModal) {
    btnCloseProductModal.addEventListener('click', function () { closeModal(productModal); });
  }

  if (productSearch && productResults) {
    productSearch.addEventListener('input', function () {
      var q = productSearch.value.trim();
      debounce('productSearch', function () {
        searchProducts(q, productResults, function (p) {
          prizes.push({
            name: null,
            quantity: 1,
            items: [{ product_id: p.id, quantity: 1, _name: p.name, _img: p.image_url || null }],
          });
          syncJson();
          renderPrizes();
          closeModal(productModal);
        });
      }, 280);
    });
  }

  /* ====================================================================== */
  /* "Dodaj zestaw" modal                                                    */
  /* ====================================================================== */

  var setModal = document.getElementById('prizeSetModal');
  var setModalName = document.getElementById('setModalName');
  var setModalSearch = document.getElementById('setModalSearch');
  var setModalResults = document.getElementById('setModalResults');
  var setModalItems = document.getElementById('setModalItems');
  var btnAddSet = document.getElementById('btnAddSet');
  var btnCloseSetModal = document.getElementById('btnCloseSetModal');
  var btnCancelSet = document.getElementById('btnCancelSet');
  var btnConfirmSet = document.getElementById('btnConfirmSet');

  // Temporary working list for the set modal
  var setWorkItems = [];

  function updateConfirmSetBtn() {
    if (!btnConfirmSet) return;
    var hasName = setModalName && setModalName.value.trim().length > 0;
    var hasItems = setWorkItems.length > 0;
    btnConfirmSet.disabled = !(hasName && hasItems);
  }

  function renderSetModalItems() {
    if (!setModalItems) return;
    if (setWorkItems.length === 0) {
      setModalItems.innerHTML = '';
      return;
    }
    var html = '';
    setWorkItems.forEach(function (it, idx) {
      html += '<div class="ca-prize-item" data-set-item-idx="' + idx + '">' +
        thumbHtml(it._img) +
        '<span class="ca-prize-name">' + escHtml(it._name) + '</span>' +
        '<div class="ca-prize-stepper">' +
          '<button type="button" class="ca-stepper-btn ca-stepper-minus" data-set-idx="' + idx + '">−</button>' +
          '<input type="number" class="ca-stepper-inp" value="' + it.quantity + '" min="1" data-set-idx="' + idx + '">' +
          '<button type="button" class="ca-stepper-btn ca-stepper-plus" data-set-idx="' + idx + '">+</button>' +
        '</div>' +
        '<button type="button" class="ca-prize-remove" data-set-remove="' + idx + '" aria-label="Usuń">×</button>' +
        '</div>';
    });
    setModalItems.innerHTML = html;

    setModalItems.querySelectorAll('.ca-stepper-minus').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var idx = parseInt(btn.getAttribute('data-set-idx'), 10);
        setWorkItems[idx].quantity = Math.max(1, (setWorkItems[idx].quantity || 1) - 1);
        renderSetModalItems();
      });
    });
    setModalItems.querySelectorAll('.ca-stepper-plus').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var idx = parseInt(btn.getAttribute('data-set-idx'), 10);
        setWorkItems[idx].quantity = (setWorkItems[idx].quantity || 1) + 1;
        renderSetModalItems();
      });
    });
    setModalItems.querySelectorAll('.ca-stepper-inp').forEach(function (inp) {
      inp.addEventListener('change', function () {
        var idx = parseInt(inp.getAttribute('data-set-idx'), 10);
        setWorkItems[idx].quantity = clampQty(inp.value);
        renderSetModalItems();
      });
    });
    setModalItems.querySelectorAll('.ca-prize-remove').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var idx = parseInt(btn.getAttribute('data-set-remove'), 10);
        setWorkItems.splice(idx, 1);
        renderSetModalItems();
        updateConfirmSetBtn();
      });
    });
  }

  function resetSetModal() {
    setWorkItems = [];
    if (setModalName) setModalName.value = '';
    if (setModalSearch) setModalSearch.value = '';
    if (setModalResults) setModalResults.innerHTML = '<div class="ca-picker-hint">Wpisz co najmniej 2 znaki.</div>';
    renderSetModalItems();
    updateConfirmSetBtn();
  }

  if (btnAddSet && setModal) {
    btnAddSet.addEventListener('click', function () {
      resetSetModal();
      openModal(setModal);
      setTimeout(function () { if (setModalName) setModalName.focus(); }, 100);
    });
  }

  if (btnCloseSetModal && setModal) {
    btnCloseSetModal.addEventListener('click', function () { closeModal(setModal); });
  }
  if (btnCancelSet && setModal) {
    btnCancelSet.addEventListener('click', function () { closeModal(setModal); });
  }

  if (setModalName) {
    setModalName.addEventListener('input', updateConfirmSetBtn);
  }

  if (setModalSearch && setModalResults) {
    setModalSearch.addEventListener('input', function () {
      var q = setModalSearch.value.trim();
      debounce('setSearch', function () {
        searchProducts(q, setModalResults, function (p) {
          // Allow same product multiple times (different quantities)
          setWorkItems.push({ product_id: p.id, quantity: 1, _name: p.name, _img: p.image_url || null });
          renderSetModalItems();
          updateConfirmSetBtn();
          if (setModalSearch) setModalSearch.value = '';
          if (setModalResults) setModalResults.innerHTML = '<div class="ca-picker-hint">Wpisz co najmniej 2 znaki.</div>';
        });
      }, 280);
    });
  }

  if (btnConfirmSet && setModal) {
    btnConfirmSet.addEventListener('click', function () {
      var name = setModalName ? setModalName.value.trim() : '';
      if (!name || setWorkItems.length === 0) return;
      prizes.push({
        name: name,
        quantity: 1,
        items: setWorkItems.map(function (it) {
          return { product_id: it.product_id, quantity: it.quantity, _name: it._name, _img: it._img };
        }),
      });
      syncJson();
      renderPrizes();
      closeModal(setModal);
    });
  }

  /* ====================================================================== */
  /* Image dropzone                                                           */
  /* ====================================================================== */

  var imageDrop = document.getElementById('imageDrop');
  var imageFile = document.getElementById('imageFile');
  var imagePreview = document.getElementById('imagePreview');
  var imageDropPrompt = document.getElementById('imageDropPrompt');
  var imageDropError = document.getElementById('imageDropError');

  var ALLOWED_EXTS = ['png', 'jpg', 'jpeg', 'gif', 'webp'];

  function isAllowedFile(filename) {
    var ext = filename.split('.').pop().toLowerCase();
    return ALLOWED_EXTS.indexOf(ext) !== -1;
  }

  function showPreview(file) {
    if (!isAllowedFile(file.name)) {
      if (imageDropError) imageDropError.textContent = 'Niedozwolony format. Dozwolone: PNG, JPG, GIF, WEBP.';
      return;
    }
    if (imageDropError) imageDropError.textContent = '';
    var reader = new FileReader();
    reader.onload = function (e) {
      if (imagePreview) {
        imagePreview.src = e.target.result;
        imagePreview.style.display = '';
      }
      if (imageDropPrompt) imageDropPrompt.classList.add('ca-image-drop-prompt--hidden');
    };
    reader.readAsDataURL(file);
  }

  if (imageDrop && imageFile) {
    imageDrop.addEventListener('click', function (e) {
      if (e.target !== imageFile) { imageFile.click(); }
    });
    imageFile.addEventListener('change', function () {
      if (imageFile.files && imageFile.files[0]) { showPreview(imageFile.files[0]); }
    });
    imageDrop.addEventListener('dragover', function (e) {
      e.preventDefault();
      imageDrop.classList.add('ca-image-drop--dragover');
    });
    imageDrop.addEventListener('dragleave', function () {
      imageDrop.classList.remove('ca-image-drop--dragover');
    });
    imageDrop.addEventListener('drop', function (e) {
      e.preventDefault();
      imageDrop.classList.remove('ca-image-drop--dragover');
      var files = e.dataTransfer && e.dataTransfer.files;
      if (files && files[0]) {
        try {
          var dt = new DataTransfer();
          dt.items.add(files[0]);
          imageFile.files = dt.files;
        } catch (err) {
          // Fallback — preview only
        }
        showPreview(files[0]);
      }
    });
  }

  /* ====================================================================== */
  /* Criteria toggles (a11y preserved)                                       */
  /* ====================================================================== */

  var critRows = document.querySelectorAll('[data-crit-row]');
  var NUM_CRITS = critRows.length;

  function syncCrit(idx) {
    var inp = document.getElementById('critInp' + idx);
    if (!inp) return;
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
    var row = box.closest('[data-crit-row]');
    if (row) row.setAttribute('aria-checked', active ? 'true' : 'false');
  }

  function toggleCrit(idx) {
    var inp = document.getElementById('critInp' + idx);
    if (!inp) return;
    var isActive = !inp.classList.contains('ca-cinp--disabled');
    setCritState(idx, !isActive);
    if (!isActive) {
      setTimeout(function () { inp.focus(); }, 10);
    }
  }

  for (var i = 0; i < critRows.length; i++) {
    (function (idx, row) {
      row.addEventListener('click', function (e) {
        var inp = document.getElementById('critInp' + idx);
        if (!inp) return;
        if (e.target === inp) return;
        toggleCrit(idx);
      });
      row.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          toggleCrit(idx);
        }
      });
    }(i, critRows[i]));
  }

  for (var j = 0; j < NUM_CRITS; j++) {
    syncCrit(j);
  }

  /* ====================================================================== */
  /* Delete draft form — confirm before submit                               */
  /* ====================================================================== */

  var deleteContestForm = document.getElementById('deleteContestForm');
  if (deleteContestForm) {
    deleteContestForm.addEventListener('submit', function (e) {
      if (!confirm('Na pewno usunąć ten konkurs? Tej operacji nie można cofnąć.')) {
        e.preventDefault();
      }
    });
  }

}());
