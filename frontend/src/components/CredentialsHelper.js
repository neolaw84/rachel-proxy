import { getApiKey, apiFetch } from '../services/api.js';
import { showToast } from '../services/toast.js';

export function renderCredentialsHelper(container, { isCloud = false } = {}) {
  const isCloudMode = isCloud || Boolean(import.meta.env.VITE_MULTI_TENANT);

  if (isCloudMode) {
    container.innerHTML = `
      <div class="panel" id="panel-credentials">
        <div class="panel-header">
          <div class="panel-title">1️⃣ Step 1: Connect Your Roleplay Client (JanitorAI / SillyTavern)</div>
        </div>
        <div class="panel-body" style="display:flex;flex-direction:column;gap:12px;">
          <p class="text-muted text-sm">
            Copy these credentials into your chat app's custom API settings (select <strong>OpenAI / Custom Proxy</strong> format):
          </p>
          <div class="cred-row">
            <span class="cred-label">API URL</span>
            <span id="cred-endpoint" class="cred-value">—</span>
            <button class="btn btn-copy" id="btn-copy-endpoint">📋 Copy URL</button>
          </div>

          <div id="cloud-key-section" style="display:flex;flex-direction:column;gap:10px;">
            <div class="cred-row">
              <span class="cred-label">Client Key</span>
              <div id="cloud-key-select-container" style="flex:1;">
                <span class="text-muted text-sm">Loading keys...</span>
              </div>
              <button class="btn btn-primary btn-sm" id="btn-create-cloud-key">➕ Create New Key</button>
            </div>
            <div id="new-key-display-box" class="hidden" style="background:rgba(34,211,110,0.1);border:1px solid rgba(34,211,110,0.4);border-radius:var(--radius-sm);padding:12px;display:flex;flex-direction:column;gap:8px;">
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <span style="color:var(--green);font-weight:600;font-size:0.8rem;">🎉 New Client Key Created! (Save now, won't be shown again)</span>
                <button class="btn btn-ghost btn-sm" id="btn-close-cloud-key-box" style="padding:2px 8px;">✕ Close</button>
              </div>
              <div class="cred-row" style="margin:0;background:rgba(12,16,36,0.9);">
                <span id="new-key-raw" class="cred-value" style="color:var(--green);font-family:monospace;word-break:break-all;"></span>
                <button class="btn btn-copy" id="btn-copy-new-key">📋 Copy Secret Key</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;
  } else {
    container.innerHTML = `
      <div class="panel" id="panel-credentials">
        <div class="panel-header">
          <div class="panel-title">1️⃣ Step 1: Connect Your Roleplay Client (JanitorAI / SillyTavern)</div>
        </div>
        <div class="panel-body" style="display:flex;flex-direction:column;gap:12px;">
          <p class="text-muted text-sm">
            Copy these credentials into your chat app's custom API settings (select <strong>OpenAI / Custom Proxy</strong> format):
          </p>
          <div class="cred-row">
            <span class="cred-label">API URL</span>
            <span id="cred-endpoint" class="cred-value">—</span>
            <button class="btn btn-copy" id="btn-copy-endpoint">📋 Copy URL</button>
          </div>
          <div class="cred-row">
            <span class="cred-label">Master Key</span>
            <span id="cred-key" class="cred-value masked">••••••••••••••••</span>
            <button class="btn btn-copy btn-sm" id="btn-reveal-key">Show</button>
            <button class="btn btn-copy" id="btn-copy-key">📋 Copy Key</button>
          </div>
        </div>
      </div>
    `;
  }

  function copyText(text, btn) {
    if (!text || text === '—') return;
    navigator.clipboard.writeText(text).then(() => {
      const orig = btn.textContent;
      btn.textContent = '✓ Copied!';
      btn.classList.add('copied');
      setTimeout(() => {
        btn.textContent = orig;
        btn.classList.remove('copied');
      }, 2000);
    });
  }

  const endpointEl = document.getElementById('cred-endpoint');
  const copyEndpointBtn = document.getElementById('btn-copy-endpoint');
  if (copyEndpointBtn) {
    copyEndpointBtn.onclick = function () {
      copyText(endpointEl.textContent.trim(), this);
    };
  }

  if (isCloudMode) {
    const selectContainer = document.getElementById('cloud-key-select-container');
    const createBtn = document.getElementById('btn-create-cloud-key');
    const newKeyBox = document.getElementById('new-key-display-box');
    const newKeyRaw = document.getElementById('new-key-raw');
    const copyNewKeyBtn = document.getElementById('btn-copy-new-key');

    function loadCloudKeys() {
      apiFetch('/v1/proxy-keys')
        .then((res) => res.json())
        .then((data) => {
          const keys = data.keys || [];
          if (!keys.length) {
            selectContainer.innerHTML = `<span class="text-muted text-sm">No client keys generated yet. Click "+ Create New Key".</span>`;
          } else {
            const options = keys
              .map((k) => `<option value="${k.id}">${k.name || 'Client Key'} (${k.prefix || 'sk'}...)</option>`)
              .join('');
            selectContainer.innerHTML = `<select id="cloud-key-select" class="cred-value" style="width:100%;padding:6px 10px;background:rgba(12,16,36,0.8);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text);">${options}</select>`;
          }
        })
        .catch(() => {
          selectContainer.innerHTML = `<span class="text-muted text-sm">Create a client key to connect your chat app.</span>`;
        });
    }

    createBtn.onclick = () => {
      const keyName = prompt('Enter a name for your new client API key (e.g. JanitorAI Laptop):', 'JanitorAI Client Key');
      if (keyName === null) return;
      apiFetch('/v1/proxy-keys', {
        method: 'POST',
        body: JSON.stringify({ name: keyName.trim() || 'JanitorAI Client Key' }),
      })
        .then((res) => res.json())
        .then((data) => {
          showToast('New client API key generated!', 'ok');
          if (data.proxy_key) {
            newKeyRaw.textContent = data.proxy_key;
            newKeyBox.classList.remove('hidden');
            copyText(data.proxy_key, copyNewKeyBtn);
          }
          loadCloudKeys();
        })
        .catch(() => showToast('Failed to create key.', 'err'));
    };

    const closeKeyBoxBtn = document.getElementById('btn-close-cloud-key-box');
    if (closeKeyBoxBtn) {
      closeKeyBoxBtn.onclick = () => {
        newKeyBox.classList.add('hidden');
      };
    }

    if (copyNewKeyBtn) {
      copyNewKeyBtn.onclick = function () {
        copyText(newKeyRaw.textContent.trim(), this);
      };
    }

    loadCloudKeys();
  } else {
    let _keyVisible = false;
    const keyEl = document.getElementById('cred-key');
    const revealBtn = document.getElementById('btn-reveal-key');
    const copyKeyBtn = document.getElementById('btn-copy-key');

    if (revealBtn) {
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
    }

    if (copyKeyBtn) {
      copyKeyBtn.onclick = function () {
        copyText(getApiKey(), this);
      };
    }
  }

  function updateEndpoint(url) {
    if (endpointEl) endpointEl.textContent = url || '—';
  }

  return { updateEndpoint };
}

