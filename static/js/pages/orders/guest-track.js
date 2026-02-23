/**
 * ThunderOrders - Guest Track Page JS
 * Obsługa uploadu płatności i zlecenia wysyłki dla gościa
 */

document.addEventListener('DOMContentLoaded', function() {
    const container = document.querySelector('.track-container');
    if (!container) return;

    const token = container.dataset.token;
    if (!token) return;

    // === Upload Payment Modal ===
    const openBtn = document.getElementById('openUploadModal');
    const modal = document.getElementById('uploadPaymentModal');
    const closeBtn = document.getElementById('closeUploadModal');
    const uploadForm = document.getElementById('uploadPaymentForm');

    if (openBtn && modal) {
        openBtn.addEventListener('click', function() {
            modal.classList.add('active');
        });

        closeBtn.addEventListener('click', function() {
            modal.classList.remove('active');
        });

        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                modal.classList.remove('active');
            }
        });
    }

    if (uploadForm) {
        uploadForm.addEventListener('submit', function(e) {
            e.preventDefault();

            const checkedStages = uploadForm.querySelectorAll('input[name="stages"]:checked');
            const stages = Array.from(checkedStages).map(cb => cb.value);

            if (stages.length === 0) {
                alert('Wybierz przynajmniej jeden etap płatności');
                return;
            }

            const fileInput = document.getElementById('proofFile');
            if (!fileInput.files || fileInput.files.length === 0) {
                alert('Wybierz plik potwierdzenia');
                return;
            }

            const submitBtn = document.getElementById('submitUpload');
            submitBtn.disabled = true;
            submitBtn.textContent = 'Wysyłanie...';

            const formData = new FormData();
            formData.append('stages', JSON.stringify(stages));
            formData.append('proof_file', fileInput.files[0]);

            fetch('/order/track/' + token + '/upload-payment', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert(data.message || 'Potwierdzenie przesłane');
                    window.location.reload();
                } else {
                    alert(data.error || 'Wystąpił błąd');
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Wyślij potwierdzenie';
                }
            })
            .catch(function() {
                alert('Wystąpił błąd połączenia');
                submitBtn.disabled = false;
                submitBtn.textContent = 'Wyślij potwierdzenie';
            });
        });
    }

    // === Shipping Form ===
    const addressType = document.getElementById('addressType');
    const homeFields = document.getElementById('homeFields');
    const pickupFields = document.getElementById('pickupFields');
    const shippingForm = document.getElementById('shippingForm');

    if (addressType && homeFields && pickupFields) {
        addressType.addEventListener('change', function() {
            if (this.value === 'home') {
                homeFields.style.display = 'block';
                pickupFields.style.display = 'none';
            } else {
                homeFields.style.display = 'none';
                pickupFields.style.display = 'block';
            }
        });
    }

    if (shippingForm) {
        shippingForm.addEventListener('submit', function(e) {
            e.preventDefault();

            var type = addressType.value;
            var payload = { address_type: type };

            if (type === 'home') {
                payload.shipping_name = document.getElementById('shippingName').value;
                payload.shipping_address = document.getElementById('shippingAddress').value;
                payload.shipping_postal_code = document.getElementById('shippingPostal').value;
                payload.shipping_city = document.getElementById('shippingCity').value;

                if (!payload.shipping_name || !payload.shipping_address || !payload.shipping_postal_code || !payload.shipping_city) {
                    alert('Wypełnij wszystkie pola adresu');
                    return;
                }
            } else {
                payload.pickup_courier = document.getElementById('pickupCourier').value;
                payload.pickup_point_id = document.getElementById('pickupPointId').value;
                payload.pickup_address = document.getElementById('pickupAddress').value;
                payload.pickup_postal_code = document.getElementById('pickupPostal').value;
                payload.pickup_city = document.getElementById('pickupCity').value;

                if (!payload.pickup_point_id || !payload.pickup_address || !payload.pickup_postal_code || !payload.pickup_city) {
                    alert('Wypełnij wszystkie pola punktu odbioru');
                    return;
                }
            }

            var submitBtn = document.getElementById('submitShipping');
            submitBtn.disabled = true;
            submitBtn.textContent = 'Tworzenie...';

            fetch('/order/track/' + token + '/shipping-request', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(function(response) { return response.json(); })
            .then(function(data) {
                if (data.success) {
                    alert(data.message + ' (' + data.request_number + ')');
                    window.location.reload();
                } else {
                    alert(data.error || 'Wystąpił błąd');
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Zlec wysyłkę';
                }
            })
            .catch(function() {
                alert('Wystąpił błąd połączenia');
                submitBtn.disabled = false;
                submitBtn.textContent = 'Zlec wysyłkę';
            });
        });
    }
});
