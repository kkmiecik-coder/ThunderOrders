/**
 * ThunderOrders - Toast Component
 * System powiadomień toast
 */

window.showToast = function(message, type = 'info', duration = 5000) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const icons = {
        'success': '✓',
        'error': '✕',
        'warning': '⚠',
        'info': 'ℹ',
        'danger': '✕' // Alias for error
    };

    const titles = {
        'success': 'Sukces',
        'error': 'Błąd',
        'warning': 'Ostrzeżenie',
        'info': 'Informacja',
        'danger': 'Błąd'
    };

    const toast = document.createElement('div');
    toast.className = `toast toast-${type === 'danger' ? 'error' : type}`;
    toast.innerHTML = `
        <div class="toast-icon">${icons[type] || icons.info}</div>
        <div class="toast-content">
            <div class="toast-title">${titles[type] || titles.info}</div>
            <div class="toast-message">${message}</div>
        </div>
        <button class="toast-close" onclick="this.parentElement.remove()">×</button>
    `;

    container.appendChild(toast);

    // Auto remove after duration
    setTimeout(() => {
        toast.style.animation = 'toast-slide-out 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, duration);
};

// Slide out animation
const style = document.createElement('style');
style.textContent = `
@keyframes toast-slide-out {
    from {
        transform: translateX(0);
        opacity: 1;
    }
    to {
        transform: translateX(100%);
        opacity: 0;
    }
}
`;
document.head.appendChild(style);
