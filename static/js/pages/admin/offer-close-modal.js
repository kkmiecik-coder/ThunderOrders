/**
 * Modal „Zamknij całkowicie" strony sprzedażowej (#closeModal).
 * Współdzielony przez listę ofert (admin/offers/list.html) i dashboard LIVE
 * (admin/offers/live_dashboard.html) — oba szablony includują _close_modal.html.
 * Obsługuje tryb pojedynczy (openCloseModal) i zbiorczy (openBulkCloseModal).
 */
(function () {
    let closePageId = null;
    let bulkCloseIds = null; // gdy ustawione → modal działa w trybie zbiorczym

    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta && meta.content) return meta.content;
        const el = document.querySelector('input[name="csrf_token"]');
        return el ? el.value : '';
    }

    function notify(message, type) {
        if (typeof window.showToast === 'function') {
            window.showToast(message, type);
        } else {
            alert(message);
        }
    }

    // Poprawna forma rzeczownika 'strona' w bierniku dla liczby n (dla komunikatów).
    function pluralStrony(n) {
        if (n === 1) return 'stronę';
        if (n % 10 >= 2 && n % 10 <= 4 && !(n % 100 >= 12 && n % 100 <= 14)) return 'strony';
        return 'stron';
    }

    function resetDeadlineFields() {
        document.getElementById('paymentDeadlineDate').value = '';
        document.getElementById('paymentDeadlineTime').value = '23:59';
        document.getElementById('deadlineError').style.display = 'none';
    }

    function showDeadlineError(message) {
        const deadlineError = document.getElementById('deadlineError');
        deadlineError.textContent = message;
        deadlineError.style.display = 'block';
        // Na mobile pola terminu bywają poniżej widocznego obszaru modala — przewiń do błędu.
        // Celowo bez behavior:'smooth' — focus() potrafi przerwać płynne przewijanie.
        document.getElementById('paymentDeadlineDate').focus({ preventScroll: true });
        deadlineError.scrollIntoView({ block: 'center' });
    }

    // Zwraca 'YYYY-MM-DDTHH:MM' albo null (po pokazaniu błędu walidacji).
    function readValidDeadline() {
        const deadlineDate = document.getElementById('paymentDeadlineDate').value;
        const deadlineTime = document.getElementById('paymentDeadlineTime').value;

        if (!deadlineDate || !deadlineTime) {
            showDeadlineError('Termin płatności jest wymagany.');
            return null;
        }
        const deadlineDatetime = new Date(`${deadlineDate}T${deadlineTime}`);
        if (deadlineDatetime <= new Date()) {
            showDeadlineError('Termin płatności musi być w przyszłości.');
            return null;
        }
        document.getElementById('deadlineError').style.display = 'none';
        return `${deadlineDate}T${deadlineTime}`;
    }

    function readSendEmails() {
        // Checkbox maili jest ukrywany dla stron typu preorder.
        const checkbox = document.getElementById('sendEmailsCheckbox');
        return checkbox && checkbox.closest('#closeInfoExclusive').style.display !== 'none'
            ? checkbox.checked
            : false;
    }

    function setLoading(loading) {
        const btn = document.getElementById('closeCompleteBtn');
        btn.querySelector('.btn-text').style.display = loading ? 'none' : 'inline';
        btn.querySelector('.btn-loading').style.display = loading ? 'inline-flex' : 'none';
        btn.disabled = loading;
    }

    function postCloseComplete(pageId, sendEmails, paymentDeadline) {
        return fetch(`/admin/offers/${pageId}/close-complete`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                send_emails: sendEmails,
                payment_deadline: paymentDeadline
            })
        }).then(r => r.json());
    }

    window.openCloseModal = function (pageId, pageName, pageType) {
        closePageId = pageId;
        bulkCloseIds = null; // tryb pojedynczy — wyzeruj ewentualny stan zbiorczy
        document.getElementById('closePageName').textContent = pageName;

        // Toggle exclusive vs preorder info
        const isPreorder = pageType === 'preorder';
        document.getElementById('closeInfoExclusive').style.display = isPreorder ? 'none' : '';
        document.getElementById('closeInfoPreorder').style.display = isPreorder ? '' : 'none';
        document.getElementById('closeWarningText').textContent = isPreorder
            ? 'Po zamknięciu nie będzie możliwości wznowienia sprzedaży.'
            : 'Po zamknięciu nie będzie możliwości wznowienia sprzedaży ani zmiany alokacji produktów.';

        resetDeadlineFields();
        document.getElementById('closeModal').classList.add('active');
    };

    // Tryb zbiorczy całkowitego zamknięcia — reużywa #closeModal (bulk toolbar listy).
    window.openBulkCloseModal = function (ids) {
        bulkCloseIds = ids;
        closePageId = null;
        document.getElementById('closePageName').textContent = `zaznaczone strony (${ids.length})`;
        // Mieszane typy dozwolone — pokaż info exclusive (z opcją maili), ukryj wariant preorder.
        document.getElementById('closeInfoExclusive').style.display = '';
        document.getElementById('closeInfoPreorder').style.display = 'none';
        document.getElementById('closeWarningText').textContent =
            'Po zamknięciu nie będzie możliwości wznowienia sprzedaży ani zmiany alokacji produktów.';
        resetDeadlineFields();
        document.getElementById('closeModal').classList.add('active');
    };

    window.closeCloseModal = function () {
        const modal = document.getElementById('closeModal');
        modal.classList.add('closing');
        setTimeout(() => {
            modal.classList.remove('active', 'closing');
            closePageId = null;
            bulkCloseIds = null;
            setLoading(false);
        }, 350);
    };

    window.executeCloseComplete = async function () {
        if (bulkCloseIds && bulkCloseIds.length) {
            return executeBulkCloseComplete();
        }
        if (!closePageId) return;

        const paymentDeadline = readValidDeadline();
        if (!paymentDeadline) return;
        const sendEmails = readSendEmails();

        setLoading(true);
        try {
            const data = await postCloseComplete(closePageId, sendEmails, paymentDeadline);
            if (data.success) {
                // Redirect to summary page
                if (data.redirect) {
                    window.location.href = data.redirect;
                } else {
                    window.location.reload();
                }
            } else {
                notify(data.error || 'Wystąpił błąd podczas zamykania strony', 'error');
                setLoading(false);
            }
        } catch (error) {
            console.error('Error closing page:', error);
            notify('Błąd połączenia z serwerem', 'error');
            setLoading(false);
        }
    };

    async function executeBulkCloseComplete() {
        const paymentDeadline = readValidDeadline();
        if (!paymentDeadline) return;

        const sendEmailsCheckbox = document.getElementById('sendEmailsCheckbox');
        const sendEmails = sendEmailsCheckbox ? sendEmailsCheckbox.checked : false;

        setLoading(true);

        const ids = bulkCloseIds.slice();
        let ok = 0, fail = 0;
        for (const id of ids) {
            try {
                const data = await postCloseComplete(id, sendEmails, paymentDeadline);
                if (data.success) { ok++; } else { fail++; console.error('close-complete failed for', id, data.error); }
            } catch (e) {
                fail++;
                console.error('bulk close-complete error', id, e);
            }
        }

        notify(fail === 0
            ? `Zamknięto całkowicie ${ok} ${pluralStrony(ok)}.`
            : `Zamknięto ${ok} ${pluralStrony(ok)}, błędów: ${fail}.`);
        setTimeout(() => { window.location.href = '/admin/offers'; }, 700);
    }

    document.addEventListener('DOMContentLoaded', function () {
        const modal = document.getElementById('closeModal');
        if (!modal) return;
        // Zamknięcie kliknięciem w tło
        modal.addEventListener('click', function (e) {
            if (e.target === this) window.closeCloseModal();
        });
        // Zamknięcie klawiszem Escape
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && modal.classList.contains('active')) {
                window.closeCloseModal();
            }
        });
    });
})();
