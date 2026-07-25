import { getApiKey, setApiKey } from '../services/api.js';

export function renderCloudAuthModal(container, onConnected) {
  container.innerHTML = `
    <div id="auth-overlay">
      <div class="auth-box">
        <h1>🎲 RACHEL Cloud</h1>
        <p>Sign in to access your multi-tenant administration dashboard.</p>
        <div id="auth-error" class="auth-error"></div>
        <button id="auth-sso-submit" class="btn btn-primary" style="justify-content:center;">
          Sign In with SSO &rarr;
        </button>
      </div>
    </div>
  `;

  const overlay = document.getElementById('auth-overlay');
  const errorEl = document.getElementById('auth-error');
  const ssoBtn = document.getElementById('auth-sso-submit');

  function showAuth(msg) {
    overlay.classList.remove('hidden');
    errorEl.textContent = msg || '';
  }

  function hideAuth() {
    overlay.classList.add('hidden');
  }

  ssoBtn.onclick = () => {
    // Redirect to OIDC endpoint or trigger OAuth PKCE
    window.location.href = '/v1/auth/sso/login';
  };

  const existingKey = getApiKey();
  if (existingKey) {
    hideAuth();
    onConnected();
  } else {
    showAuth();
  }

  return { showAuth, hideAuth };
}
