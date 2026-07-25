import { getApiKey } from '../services/api.js';

export function renderCredentialsHelper(container) {
  container.innerHTML = `
    <div class="panel" id="panel-credentials">
      <div class="panel-header">
        <div class="panel-title">🔑 Credentials Helper</div>
      </div>
      <div class="panel-body" style="display:flex;flex-direction:column;gap:10px;">
        <div class="cred-row">
          <span class="cred-label">API Endpoint</span>
          <span id="cred-endpoint" class="cred-value">—</span>
          <button class="btn btn-copy" id="btn-copy-endpoint">Copy</button>
        </div>
        <div class="cred-row">
          <span class="cred-label">API Key</span>
          <span id="cred-key" class="cred-value masked">••••••••••••••••</span>
          <button class="btn btn-copy btn-sm" id="btn-reveal-key">Show</button>
          <button class="btn btn-copy" id="btn-copy-key">Copy</button>
        </div>
        <p class="text-muted text-sm">
          Paste the <strong>API Endpoint</strong> as the <em>API URL</em> and the <strong>API Key</strong> as the <em>Bearer token</em> in your roleplay client (e.g. JanitorAI).
        </p>
      </div>
    </div>
  `;

  let _keyVisible = false;

  function copyText(text, btn) {
    navigator.clipboard.writeText(text).then(() => {
      const orig = btn.textContent;
      btn.textContent = '✓ Copied';
      btn.classList.add('copied');
      setTimeout(() => {
        btn.textContent = orig;
        btn.classList.remove('copied');
      }, 2000);
    });
  }

  const endpointEl = document.getElementById('cred-endpoint');
  const keyEl = document.getElementById('cred-key');
  const revealBtn = document.getElementById('btn-reveal-key');
  const copyEndpointBtn = document.getElementById('btn-copy-endpoint');
  const copyKeyBtn = document.getElementById('btn-copy-key');

  revealBtn.onclick = () => {
    _keyVisible = !_keyVisible;
    if (_keyVisible) {
      keyEl.textContent = getApiKey();
      keyEl.classList.remove('masked');
      revealBtn.textContent = 'Hide';
    } else {
      keyEl.innerHTML = '••••••••••••••••';
      keyEl.classList.add('masked');
      revealBtn.textContent = 'Show';
    }
  };

  copyEndpointBtn.onclick = function () {
    copyText(endpointEl.textContent.trim(), this);
  };

  copyKeyBtn.onclick = function () {
    copyText(getApiKey(), this);
  };

  function updateEndpoint(url) {
    if (endpointEl) endpointEl.textContent = url || '—';
  }

  return { updateEndpoint };
}
