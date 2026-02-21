/**
 * Client Order Detail
 */
document.addEventListener('DOMContentLoaded', function () {

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
});
