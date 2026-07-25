import { getApiKey, setApiKey } from '../services/api.js';

export function renderLocalAuthModal(container, onConnected) {
  container.innerHTML = `
    <div id="auth-overlay">
      <div class="auth-box">
        <h1>🎲 RACHEL Proxy</h1>
        <p>Enter your <strong>Proxy API Key</strong> to unlock the administration dashboard.</p>
        <div>
          <label for="auth-key-input">Proxy API Key</label>
          <input id="auth-key-input" type="password" placeholder="Paste key here…" autocomplete="off" />
        </div>
        <div id="auth-error" class="auth-error"></div>
        <button id="auth-submit" class="btn btn-primary" style="align-self:flex-end;">Connect &rarr;</button>
      </div>
    </div>
  `;

  const overlay = document.getElementById('auth-overlay');
  const errorEl = document.getElementById('auth-error');
  const inputEl = document.getElementById('auth-key-input');
  const submitBtn = document.getElementById('auth-submit');

  function showAuth(msg) {
    setApiKey('');
    overlay.classList.remove('hidden');
    errorEl.textContent = msg || '';
    inputEl.value = '';
  }

  function hideAuth() {
    overlay.classList.add('hidden');
  }

  function tryConnect(key) {
    errorEl.textContent = 'Verifying…';
    fetch('/v1/status', { headers: { 'Authorization': `Bearer ${key}` } })
      .then((res) => {
        if (res.ok) {
          setApiKey(key);
          hideAuth();
          onConnected();
        } else {
          errorEl.textContent = 'Invalid API key. Please check and try again.';
        }
      })
      .catch(() => {
        errorEl.textContent = 'Connection failed. Is the proxy running?';
      });
  }

  submitBtn.onclick = () => {
    const key = inputEl.value.trim();
    if (!key) {
      errorEl.textContent = 'Please enter a key.';
      return;
    }
    tryConnect(key);
  };

  inputEl.onkeydown = (e) => {
    if (e.key === 'Enter') submitBtn.click();
  };

  // Auto-connect if key exists in storage
  const existingKey = getApiKey();
  if (existingKey) {
    tryConnect(existingKey);
  }

  return { showAuth, hideAuth };
}
