/**
 * Client Order Detail
 */
document.addEventListener('DOMContentLoaded', function () {
    var timeline = document.getElementById('timeline');

    /* ---- HTMX comment form ---- */
    var form = document.querySelector('.od-chat__form');
    if (form) {
        form.addEventListener('htmx:afterRequest', function (e) {
            if (e.detail.successful) {
                var ta = form.querySelector('textarea');
                if (ta) ta.value = '';
                if (window.Toast && typeof window.Toast.show === 'function') {
                    window.Toast.show('Wiadomość wysłana', 'success');
                }
            } else {
                if (window.Toast && typeof window.Toast.show === 'function') {
                    window.Toast.show('Błąd wysyłania', 'error');
                }
            }
        });
    }

    /* ---- Auto-scroll on new message ---- */
    if (timeline) {
        new MutationObserver(function (muts) {
            for (var i = 0; i < muts.length; i++) {
                if (muts[i].addedNodes.length) {
                    timeline.scrollTo({ top: 0, behavior: 'smooth' });
                    break;
                }
            }
        }).observe(timeline, { childList: true });
    }

    /* ---- Keyboard: Alt+Left = back ---- */
    document.addEventListener('keydown', function (e) {
        if (e.altKey && e.key === 'ArrowLeft') {
            var back = document.querySelector('.od-back');
            if (back) window.location.href = back.href;
        }
    });

    /* ---- Collapsible sections (event delegation) ---- */
    document.addEventListener('click', function (e) {
        var trigger = e.target.closest('[data-action="toggle-section"]');
        if (!trigger) return;
        var section = trigger.closest('.od-collapse');
        if (section) section.classList.toggle('open');
    });

    /* ---- Auto-resize textarea ---- */
    var ta = document.querySelector('.od-chat__input');
    if (ta) {
        ta.addEventListener('input', function () {
            this.style.height = 'auto';
            this.style.height = Math.min(this.scrollHeight, 120) + 'px';
        });
    }
});
