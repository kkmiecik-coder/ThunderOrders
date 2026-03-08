/**
 * Auth Tabs - Login / Register / Verify morphing form
 * Handles tab switching, AJAX register, inline verify with code inputs
 */
(function() {
    'use strict';

    document.addEventListener('DOMContentLoaded', function() {
        var container = document.getElementById('auth-container');
        var form = document.getElementById('auth-form');
        var submitBtn = document.getElementById('auth-submit-btn');
        var emailInput = document.getElementById('auth-email');
        var passwordInput = document.getElementById('auth-password');
        var confirmInput = document.getElementById('password-confirm-input');

        if (!container || !form) return;

        var verifyToken = null;

        // ========== Required fields ==========
        function updateRequiredFields() {
            var isRegister = container.classList.contains('mode-register');
            var isVerify = container.classList.contains('mode-verify');
            if (confirmInput) confirmInput.required = isRegister && !isVerify;
            if (passwordInput) passwordInput.required = !isVerify;
            if (emailInput) emailInput.required = !isVerify;
        }
        updateRequiredFields();

        // ========== Remove Turnstile iframe from tab order ==========
        var turnstileEl = container.querySelector('.cf-turnstile');
        if (turnstileEl) {
            var fixTurnstile = function() {
                var iframe = turnstileEl.querySelector('iframe');
                if (iframe) { iframe.setAttribute('tabindex', '-1'); return true; }
                return false;
            };
            if (!fixTurnstile()) {
                new MutationObserver(function(mutations, obs) {
                    if (fixTurnstile()) obs.disconnect();
                }).observe(turnstileEl, { childList: true, subtree: true });
            }
        }

        // ========== Tab switching (login <-> register) ==========
        document.addEventListener('click', function(e) {
            var link = e.target.closest('.auth-switch-tab');
            if (!link) return;
            e.preventDefault();

            // Block switching when in verify mode
            if (container.classList.contains('mode-verify')) return;

            var target = link.dataset.tab;
            var isRegister = target === 'register';

            container.classList.toggle('mode-register', isRegister);
            form.action = isRegister ? '/auth/register' : '/auth/login';

            if (submitBtn) {
                submitBtn.classList.toggle('auth-submit-login', !isRegister);
                submitBtn.classList.toggle('auth-submit-register', isRegister);
            }

            updateRequiredFields();
            history.replaceState(null, '', isRegister ? '/auth/register' : '/auth/login');
            document.title = (isRegister ? 'Rejestracja' : 'Logowanie') + ' - ThunderOrders';
        });

        // ========== Form submit ==========
        form.addEventListener('submit', function(e) {
            var isRegister = container.classList.contains('mode-register');
            var isVerify = container.classList.contains('mode-verify');

            // Login mode: let the browser submit normally
            if (!isRegister && !isVerify) return;

            e.preventDefault();

            if (isVerify) {
                submitVerifyCode();
            } else {
                submitRegister();
            }
        });

        // ========== AJAX Register ==========
        function submitRegister() {
            submitBtn.classList.add('loading');
            clearFieldErrors();

            var formData = new FormData(form);

            fetch('/auth/register', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json'
                }
            })
            .then(function(resp) {
                if (resp.status === 429) {
                    throw { rateLimit: true };
                }
                return resp.json();
            })
            .then(function(data) {
                submitBtn.classList.remove('loading');

                if (data.success) {
                    verifyToken = data.token;
                    switchToVerify(data.email, data.seconds_remaining);
                } else if (data.errors) {
                    showFieldErrors(data.errors);
                } else if (data.error) {
                    notify(data.error, 'error');
                }
            })
            .catch(function(err) {
                submitBtn.classList.remove('loading');
                if (err && err.rateLimit) {
                    switchToError('Zbyt wiele prób rejestracji. Spróbuj ponownie później.');
                } else {
                    notify('Wystąpił błąd. Spróbuj ponownie.', 'error');
                }
            });
        }

        // ========== Switch to error mode ==========
        function switchToError(message) {
            var msgEl = document.getElementById('auth-error-message');
            if (msgEl) msgEl.textContent = message;

            container.classList.remove('mode-register', 'mode-verify');
            container.classList.add('mode-error');
            updateRequiredFields();
        }

        // Error back button - return to register
        var errorBackBtn = document.getElementById('error-back-btn');
        if (errorBackBtn) {
            errorBackBtn.addEventListener('click', function() {
                container.classList.remove('mode-error');
                container.classList.add('mode-register');
                if (submitBtn) {
                    submitBtn.classList.remove('auth-submit-login');
                    submitBtn.classList.add('auth-submit-register');
                }
                updateRequiredFields();
            });
        }

        // ========== Switch to verify mode ==========
        function switchToVerify(email, secondsRemaining) {
            // Set email in subtitle
            var verifyEmailEl = document.getElementById('verify-email');
            if (verifyEmailEl) verifyEmailEl.textContent = email;

            // Switch CSS mode
            container.classList.remove('mode-register');
            container.classList.add('mode-verify');

            // Update button style (default purple)
            if (submitBtn) {
                submitBtn.classList.remove('auth-submit-register', 'auth-submit-login');
            }

            updateRequiredFields();
            initCodeInputs();

            if (secondsRemaining > 0) {
                startCountdown(secondsRemaining);
            }
            setupResendButton();

            document.title = 'Weryfikacja - ThunderOrders';

            // Focus first code input after CSS transition
            setTimeout(function() {
                var first = container.querySelector('.code-input');
                if (first) first.focus();
            }, 450);
        }

        // ========== Code inputs ==========
        function initCodeInputs() {
            var inputs = container.querySelectorAll('.code-input');
            if (!inputs.length) return;

            inputs.forEach(function(input, index) {
                input.addEventListener('input', function(e) {
                    var val = e.target.value;
                    if (!/^\d*$/.test(val)) { e.target.value = ''; return; }
                    if (val.length > 1) { e.target.value = val[0]; val = val[0]; }

                    if (val.length === 1 && index < inputs.length - 1) {
                        inputs[index + 1].focus();
                    }

                    // Auto-submit when all 6 filled
                    if (index === inputs.length - 1 && val.length === 1) {
                        var allFilled = Array.from(inputs).every(function(inp) { return inp.value.length === 1; });
                        if (allFilled) setTimeout(submitVerifyCode, 150);
                    }

                    hideCodeError();
                });

                input.addEventListener('keydown', function(e) {
                    if (e.key === 'Backspace' && input.value === '' && index > 0) {
                        inputs[index - 1].focus();
                        inputs[index - 1].value = '';
                    }
                    if (e.key === 'ArrowLeft' && index > 0) { e.preventDefault(); inputs[index - 1].focus(); }
                    if (e.key === 'ArrowRight' && index < inputs.length - 1) { e.preventDefault(); inputs[index + 1].focus(); }
                });

                input.addEventListener('paste', function(e) {
                    e.preventDefault();
                    var digits = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6);
                    if (!digits.length) return;
                    digits.split('').forEach(function(d, i) { if (inputs[i]) inputs[i].value = d; });
                    var last = Math.min(digits.length, inputs.length) - 1;
                    inputs[Math.min(last + 1, inputs.length - 1)].focus();
                    if (digits.length === 6) setTimeout(submitVerifyCode, 150);
                });

                input.addEventListener('focus', function() { this.select(); });
            });
        }

        // ========== AJAX Verify Code ==========
        function submitVerifyCode() {
            if (!verifyToken) return;

            var inputs = container.querySelectorAll('.code-input');
            var code = Array.from(inputs).map(function(inp) { return inp.value; }).join('');
            if (code.length !== 6) return;

            submitBtn.classList.add('loading');

            var formData = new FormData();
            inputs.forEach(function(inp) { formData.append(inp.name, inp.value); });

            // CSRF token
            var csrfInput = form.querySelector('input[name="csrf_token"]');
            if (csrfInput) formData.append('csrf_token', csrfInput.value);

            fetch('/auth/verify-email-code/' + verifyToken, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json'
                }
            })
            .then(function(resp) { return resp.json(); })
            .then(function(data) {
                submitBtn.classList.remove('loading');

                if (data.success) {
                    window.location.href = data.redirect;
                } else {
                    showCodeError(data.error || 'Nieprawidłowy kod');
                    inputs.forEach(function(inp) { inp.classList.add('error'); inp.value = ''; });
                    setTimeout(function() {
                        inputs.forEach(function(inp) { inp.classList.remove('error'); });
                    }, 500);
                    inputs[0].focus();
                }
            })
            .catch(function() {
                submitBtn.classList.remove('loading');
                notify('Wystąpił błąd. Spróbuj ponownie.', 'error');
            });
        }

        // ========== Resend code ==========
        function setupResendButton() {
            var btn = document.getElementById('resend-btn');
            if (!btn) return;

            btn.addEventListener('click', function() {
                if (this.disabled || !verifyToken) return;

                this.disabled = true;
                var origText = this.textContent;
                this.textContent = 'Wysyłanie...';

                var csrfToken = '';
                var meta = document.querySelector('meta[name="csrf-token"]');
                if (meta) csrfToken = meta.getAttribute('content');
                if (!csrfToken) {
                    var inp = form.querySelector('input[name="csrf_token"]');
                    if (inp) csrfToken = inp.value;
                }

                fetch('/auth/resend-code/' + verifyToken, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    }
                })
                .then(function(resp) { return resp.json(); })
                .then(function(data) {
                    if (data.success) {
                        notify(data.message, 'success');
                        startCountdown(data.seconds_remaining);
                    } else {
                        notify(data.error, 'error');
                        if (data.seconds_remaining) {
                            startCountdown(data.seconds_remaining);
                        } else {
                            btn.disabled = false;
                            btn.textContent = origText;
                        }
                    }
                })
                .catch(function() {
                    notify('Wystąpił błąd.', 'error');
                    btn.disabled = false;
                    btn.textContent = origText;
                });
            });
        }

        // ========== Countdown ==========
        function startCountdown(seconds) {
            var btn = document.getElementById('resend-btn');
            var text = document.getElementById('resend-text');
            if (!btn || !text) return;

            btn.disabled = true;
            btn.classList.add('disabled');
            var remaining = seconds;

            function tick() {
                if (remaining > 0) {
                    text.innerHTML = 'Wyślij kod ponownie za <span class="countdown">' + remaining + '</span>s';
                    remaining--;
                    setTimeout(tick, 1000);
                } else {
                    text.textContent = 'Nie otrzymałeś kodu?';
                    btn.disabled = false;
                    btn.classList.remove('disabled');
                    btn.textContent = 'Wyślij ponownie';
                }
            }
            tick();
        }

        // ========== Helpers ==========
        function showCodeError(msg) {
            var el = container.querySelector('.code-error');
            if (el) { el.textContent = msg; el.style.display = 'block'; }
        }

        function hideCodeError() {
            var el = container.querySelector('.code-error');
            if (el) el.style.display = 'none';
        }

        function showFieldErrors(errors) {
            clearFieldErrors();
            for (var field in errors) {
                var input = form.querySelector('[name="' + field + '"]');
                if (!input) continue;
                var group = input.closest('.auth-input-group');
                if (!group) continue;
                var div = document.createElement('div');
                div.className = 'form-error';
                div.textContent = errors[field];
                group.appendChild(div);
            }
        }

        function clearFieldErrors() {
            form.querySelectorAll('.form-error').forEach(function(el) { el.remove(); });
        }

        function notify(message, type) {
            if (typeof showToast === 'function') { showToast(message, type); return; }
            if (typeof showNotification === 'function') { showNotification(message, type); return; }
        }
    });
})();
