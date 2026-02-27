/**
 * Upload Page - Mobilna strona uploadu zdjecia (QR code flow)
 * Obsluguje wybor pliku, podglad, wysylanie na serwer
 */

(function () {
    'use strict';

    // ---- Pobranie elementow DOM ----
    var uploadInput = document.getElementById('upload-input');
    var uploadPreview = document.getElementById('upload-preview');
    var previewImage = document.getElementById('preview-img');
    var removePreview = document.getElementById('preview-remove');
    var uploadBtn = document.getElementById('upload-submit');
    var uploadProgress = document.getElementById('upload-progress');
    var progressBar = document.getElementById('progress-bar');
    var progressText = document.getElementById('progress-text');
    var sessionToken = document.getElementById('session-token');
    var uploadZone = document.getElementById('upload-zone');

    // Sprawdzenie czy wszystkie elementy istnieja
    if (!uploadInput || !uploadBtn || !sessionToken) return;

    // ---- Obsluga zmiany pliku w input ----
    uploadInput.addEventListener('change', function () {
        var file = uploadInput.files[0];
        if (!file) return;

        // Walidacja typu pliku
        if (!file.type.startsWith('image/')) {
            showError('Wybierz plik graficzny (JPG, PNG, WebP)');
            uploadInput.value = '';
            return;
        }

        // Walidacja rozmiaru (max 10MB)
        if (file.size > 10 * 1024 * 1024) {
            showError('Plik jest za duzy. Maksymalny rozmiar to 10MB.');
            uploadInput.value = '';
            return;
        }

        // Odczyt pliku i wyswietlenie podgladu
        var reader = new FileReader();
        reader.onload = function (e) {
            if (previewImage) previewImage.src = e.target.result;
            if (uploadPreview) uploadPreview.classList.add('visible');
            if (uploadZone) uploadZone.style.display = 'none';
            uploadBtn.disabled = false;
        };
        reader.readAsDataURL(file);
    });

    // ---- Usuniecie podgladu ----
    if (removePreview) {
        removePreview.addEventListener('click', function () {
            uploadInput.value = '';
            if (previewImage) previewImage.src = '';
            if (uploadPreview) uploadPreview.classList.remove('visible');
            if (uploadZone) uploadZone.style.display = '';
            uploadBtn.disabled = true;
        });
    }

    // ---- Wysylanie zdjecia na serwer ----
    uploadBtn.addEventListener('click', function (e) {
        e.preventDefault();

        var file = uploadInput.files[0];
        if (!file) {
            showError('Najpierw wybierz zdjecie');
            return;
        }

        // Zablokowanie przycisku podczas wysylania
        uploadBtn.disabled = true;
        uploadBtn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg> Wysylanie...';

        // Pokazanie paska postepu
        if (uploadProgress) uploadProgress.classList.add('visible');
        if (progressBar) progressBar.style.width = '0%';

        // Przygotowanie danych formularza
        var formData = new FormData();
        formData.append('image', file);

        var token = sessionToken.value;
        var url = '/collection/upload/' + token;

        // Wysylanie z uzyciem XMLHttpRequest dla sledzenia postepu
        var xhr = new XMLHttpRequest();

        // Sledzenie postepu wysylania
        xhr.upload.addEventListener('progress', function (evt) {
            if (evt.lengthComputable && progressBar) {
                var percent = Math.round((evt.loaded / evt.total) * 100);
                progressBar.style.width = percent + '%';
                if (progressText) progressText.textContent = 'Wysylanie... ' + percent + '%';
            }
        });

        // Obsluga zakonczenia wysylania
        xhr.addEventListener('load', function () {
            if (xhr.status >= 200 && xhr.status < 300) {
                var data;
                try {
                    data = JSON.parse(xhr.responseText);
                } catch (parseErr) {
                    showError('Nieprawidlowa odpowiedz serwera');
                    resetUploadBtn();
                    return;
                }

                if (data.success) {
                    // Sukces - zamiana zawartosci karty na komunikat sukcesu
                    showSuccessState();
                } else {
                    showError(data.message || 'Wystapil blad podczas wysylania');
                    resetUploadBtn();
                }
            } else {
                // Blad HTTP - proba odczytania komunikatu z odpowiedzi
                var errorMsg = 'Wystapil blad podczas wysylania';
                try {
                    var errData = JSON.parse(xhr.responseText);
                    if (errData.message) errorMsg = errData.message;
                } catch (parseErr) {
                    // Pozostaw domyslny komunikat
                }
                showError(errorMsg);
                resetUploadBtn();
            }
        });

        // Obsluga bledu sieci
        xhr.addEventListener('error', function () {
            showError('Blad polaczenia. Sprawdz internet i sprobuj ponownie.');
            resetUploadBtn();
        });

        // Obsluga timeoutu
        xhr.addEventListener('timeout', function () {
            showError('Przekroczono czas oczekiwania. Sprobuj ponownie.');
            resetUploadBtn();
        });

        xhr.open('POST', url);
        xhr.timeout = 60000; // 60 sekund timeout
        xhr.send(formData);
    });

    // ---- Wyswietlenie stanu sukcesu ----
    function showSuccessState() {
        var card = document.querySelector('.upload-card');
        if (!card) return;

        // Zamiana calej zawartosci karty na komunikat sukcesu
        card.innerHTML =
            '<div class="upload-icon upload-icon--success">' +
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
                    '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>' +
                    '<polyline points="22 4 12 14.01 9 11.01"></polyline>' +
                '</svg>' +
            '</div>' +
            '<h1 class="upload-title">Zdjecie przeslane!</h1>' +
            '<p class="upload-subtitle">Mozesz zamknac te strone.</p>' +
            '<div class="upload-branding">' +
                '<a href="/">ThunderOrders</a>' +
            '</div>';
    }

    // ---- Resetowanie przycisku wysylania ----
    function resetUploadBtn() {
        uploadBtn.disabled = false;
        uploadBtn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg> Wyslij zdjecie';
        if (uploadProgress) uploadProgress.classList.remove('visible');
        if (progressBar) progressBar.style.width = '0%';
    }

    // ---- Wyswietlenie komunikatu bledu ----
    function showError(message) {
        if (typeof window.showToast === 'function') {
            window.showToast(message, 'error');
        } else {
            alert(message);
        }
    }

})();
