/**
 * Client Order Detail - Enhanced Interactions
 */

document.addEventListener('DOMContentLoaded', function() {
    // Auto-scroll timeline to bottom (newest messages first, but scroll to see form)
    const timeline = document.getElementById('timeline');
    if (timeline && timeline.children.length > 0) {
        // Timeline is already in reverse order (newest first), no need to scroll
    }

    // Handle comment form submission
    const commentForm = document.querySelector('.comment-form');
    if (commentForm) {
        commentForm.addEventListener('htmx:afterRequest', function(event) {
            if (event.detail.successful) {
                // Clear the textarea after successful submission
                const textarea = commentForm.querySelector('textarea');
                if (textarea) {
                    textarea.value = '';
                }

                // Show success message
                showToast('Wiadomość została wysłana', 'success');
            } else {
                showToast('Wystąpił błąd podczas wysyłania wiadomości', 'error');
            }
        });
    }

    // Add smooth scroll to timeline when new message is added
    if (timeline) {
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.addedNodes.length > 0) {
                    // Scroll to top to see new message (since it's prepended)
                    timeline.scrollTo({ top: 0, behavior: 'smooth' });
                }
            });
        });

        observer.observe(timeline, { childList: true });
    }

    // Enhance back link with keyboard shortcut
    document.addEventListener('keydown', function(e) {
        // Alt + Left Arrow = Go back
        if (e.altKey && e.key === 'ArrowLeft') {
            const backLink = document.querySelector('.back-link');
            if (backLink) {
                window.location.href = backLink.href;
            }
        }
    });

    // Add loading state to tracking button
    const trackingBtn = document.querySelector('.tracking-info .btn-primary');
    if (trackingBtn) {
        trackingBtn.addEventListener('click', function() {
            this.style.opacity = '0.6';
        });
    }
});

/**
 * Show toast notification
 */
function showToast(message, type = 'info') {
    // Check if toast system exists
    if (typeof window.showToast === 'function') {
        window.showToast(message, type);
    } else {
        // Fallback to console
        console.log(`[${type.toUpperCase()}] ${message}`);
    }
}
