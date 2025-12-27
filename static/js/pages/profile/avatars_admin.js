function openNewSeriesModal() {
    document.getElementById('newSeriesModal').classList.add('active');
    document.getElementById('series-name').focus();
}

function closeNewSeriesModal() {
    const modal = document.getElementById('newSeriesModal');
    modal.classList.add('closing');
    setTimeout(() => {
        modal.classList.remove('active', 'closing');
        document.getElementById('series-name').value = '';
        document.getElementById('series-slug').value = '';
    }, 350);
}

// Auto-generate slug from name
document.getElementById('series-name').addEventListener('input', function() {
    const slug = this.value
        .toLowerCase()
        .replace(/[^a-z0-9\s-]/g, '')
        .replace(/\s+/g, '-')
        .replace(/-+/g, '-')
        .trim();
    document.getElementById('series-slug').value = slug;
});

function deleteSeries(seriesId, seriesName) {
    if (!confirm(`Czy na pewno chcesz usunąć serię "${seriesName}"?\n\nWszystkie avatary w tej serii zostaną usunięte.`)) {
        return;
    }

    // Get CSRF token from meta tag or form
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content ||
                      document.querySelector('input[name="csrf_token"]')?.value;

    fetch(`/profile/avatars/series/${seriesId}`, {
        method: 'DELETE',
        headers: {
            'X-CSRFToken': csrfToken,
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Remove card from DOM
            const card = document.querySelector(`[data-series-id="${seriesId}"]`);
            if (card) {
                card.style.opacity = '0';
                card.style.transform = 'translateY(-10px)';
                setTimeout(() => card.remove(), 300);
            }
            window.showToast('Seria została usunięta.', 'success');
        } else {
            window.showToast(data.message, 'error');
        }
    })
    .catch(error => {
        window.showToast('Wystąpił błąd podczas usuwania serii.', 'error');
    });
}

function deleteAvatar(avatarId) {
    if (!confirm('Czy na pewno chcesz usunąć ten avatar?')) {
        return;
    }

    // Get CSRF token from meta tag or form
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content ||
                      document.querySelector('input[name="csrf_token"]')?.value;

    fetch(`/profile/avatars/${avatarId}`, {
        method: 'DELETE',
        headers: {
            'X-CSRFToken': csrfToken,
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Remove avatar from DOM
            const item = document.querySelector(`[data-avatar-id="${avatarId}"]`);
            if (item) {
                item.style.opacity = '0';
                item.style.transform = 'scale(0.8)';
                setTimeout(() => item.remove(), 300);
            }
            window.showToast('Avatar został usunięty.', 'success');
        } else {
            window.showToast(data.message, 'error');
        }
    })
    .catch(error => {
        window.showToast('Wystąpił błąd podczas usuwania avatara.', 'error');
    });
}

// Close modal on Escape
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeNewSeriesModal();
    }
});

// Close modal on overlay click
document.getElementById('newSeriesModal').addEventListener('click', function(e) {
    if (e.target === this) {
        closeNewSeriesModal();
    }
});
