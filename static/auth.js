const loginForm = document.querySelector('#login-form');
const registerForm = document.querySelector('#register-form');
const authStatus = document.querySelector('#auth-status');
const tabButtons = document.querySelectorAll('.auth-tab');

function setStatus(message, state = 'info') {
    if (!authStatus) return;
    authStatus.textContent = message;
    authStatus.dataset.state = state;
}

function switchPane(target) {
    document.querySelectorAll('.auth-pane').forEach((pane) => {
        pane.hidden = pane.id !== `${target}-pane`;
    });

    tabButtons.forEach((btn) => {
        btn.setAttribute('aria-selected', btn.dataset.target === target ? 'true' : 'false');
    });
}

tabButtons.forEach((button) => {
    button.addEventListener('click', () => switchPane(button.dataset.target));
});

async function submitJson(url, payload) {
    const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        const message = data.detail || data.message || 'Request failed.';
        throw new Error(message);
    }
    return data;
}

if (loginForm) {
    loginForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        const formData = new FormData(loginForm);
        const payload = Object.fromEntries(formData.entries());
        payload.client = 'web';
        setStatus('Signing in…', 'info');
        try {
            await submitJson('/api/v1/auth/login', payload);
            setStatus('Login successful! Redirecting…', 'success');
            window.location.href = '/';
        } catch (error) {
            setStatus(error.message, 'error');
        }
    });
}

if (registerForm) {
    registerForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        const formData = new FormData(registerForm);
        const payload = Object.fromEntries(formData.entries());
        setStatus('Creating account…', 'info');
        try {
            await submitJson('/api/v1/auth/register', payload);
            setStatus('Account created. Logging you in…', 'success');
            await submitJson('/api/v1/auth/login', {
                username: payload.username,
                password: payload.password,
                client: 'web',
            });
            window.location.href = '/';
        } catch (error) {
            setStatus(error.message, 'error');
        }
    });
}
