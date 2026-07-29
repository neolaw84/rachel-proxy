import { apiFetch } from '../services/api.js';
import { showToast } from '../services/toast.js';
import { showConfirm } from '../services/modal.js';

export function renderProxyKeysPanel(container, { isCloud = false } = {}) {
  container.innerHTML = `
    <div class="panel" id="panel-proxy-keys">
      <div class="panel-header">
        <div class="panel-title">🔑 Client Proxy API Keys</div>
        <button id="btn-create-proxy-key" class="btn btn-primary btn-sm">+ Create Proxy Key</button>
      </div>
      <div class="panel-body">
        <p class="text-muted text-sm" style="margin-bottom:12px;">
          Manage client keys issued to third-party clients (JanitorAI, SillyTavern, etc.) to access the proxy completions endpoint.
        </p>

        <div id="panel-key-display-box" class="hidden" style="background:rgba(34,211,110,0.1);border:1px solid rgba(34,211,110,0.4);border-radius:var(--radius-sm);padding:14px;margin-bottom:16px;display:flex;flex-direction:column;gap:10px;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <span style="color:var(--green);font-weight:600;font-size:0.875rem;">🎉 New Client Proxy Key Created!</span>
            <button class="btn btn-ghost btn-sm" id="btn-close-key-box" style="padding:2px 8px;">✕ Close</button>
          </div>
          <p class="text-muted text-sm" style="margin:0;">
            Save your secret key now! For security reasons, it will <strong>never be shown again</strong>.
          </p>
          <div class="cred-row" style="margin:0;background:rgba(12,16,36,0.9);">
            <span id="panel-new-key-raw" class="cred-value" style="color:var(--green);font-family:var(--font-mono, monospace);word-break:break-all;"></span>
            <button class="btn btn-copy" id="btn-copy-panel-key">📋 Copy Secret Key</button>
          </div>
        </div>

        <div id="proxy-keys-list">
          <span class="spinner"></span> Loading proxy keys...
        </div>
      </div>
    </div>
  `;

  const listEl = document.getElementById('proxy-keys-list');
  const createBtn = document.getElementById('btn-create-proxy-key');
  const keyBox = document.getElementById('panel-key-display-box');
  const keyRaw = document.getElementById('panel-new-key-raw');
  const copyBtn = document.getElementById('btn-copy-panel-key');
  const closeBtn = document.getElementById('btn-close-key-box');

  function copyText(text, btn) {
    if (!text) return;
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

  if (copyBtn) {
    copyBtn.onclick = function () {
      copyText(keyRaw.textContent.trim(), this);
    };
  }

  if (closeBtn) {
    closeBtn.onclick = () => {
      keyBox.classList.add('hidden');
    };
  }

  function loadKeys() {
    listEl.innerHTML = '<span class="spinner"></span> Loading proxy keys...';
    apiFetch('/v1/proxy-keys')
      .then((res) => res.json())
      .then((data) => {
        const keys = data.keys || [];
        if (!keys.length) {
          listEl.innerHTML = '<p class="text-muted text-sm">No custom proxy keys found.</p>';
          return;
        }

        const rowsHtml = keys
          .map((k) => `
            <tr>
              <td class="key-prefix" style="font-family:monospace;font-weight:600;">${k.prefix || 'sk-'}...</td>
              <td>${k.name || 'Client Key'}</td>
              <td>${k.created_at ? new Date(k.created_at).toLocaleDateString() : '—'}</td>
              <td style="text-align:right;">
                <button class="btn btn-danger btn-sm btn-revoke-key" data-id="${k.id}" ${k.id?.includes('_default') ? 'disabled title="Bootstrap key cannot be revoked"' : ''}>Revoke</button>
              </td>
            </tr>
          `)
          .join('');

        listEl.innerHTML = `
          <table class="keys-table">
            <thead>
              <tr>
                <th>Key Prefix</th>
                <th>Name / Label</th>
                <th>Created</th>
                <th style="text-align:right;">Action</th>
              </tr>
            </thead>
            <tbody>
              ${rowsHtml}
            </tbody>
          </table>
        `;

        listEl.querySelectorAll('.btn-revoke-key').forEach((btn) => {
          btn.onclick = () => {
            const keyId = btn.getAttribute('data-id');
            if (keyId.includes('_default')) {
              showToast('Bootstrap key cannot be revoked.', 'err');
              return;
            }
            showConfirm('Revoke API Key', `Are you sure you want to revoke key ID "${keyId}"?`, () => {
              apiFetch(`/v1/proxy-keys/${keyId}`, { method: 'DELETE' })
                .then((res) => {
                  if (res.ok) {
                    showToast('Key revoked.', 'ok');
                    loadKeys();
                  } else {
                    showToast('Failed to revoke key.', 'err');
                  }
                })
                .catch(() => showToast('Failed to revoke key.', 'err'));
            });
          };
        });
      })
      .catch((e) => {
        if (e.message !== 'Unauthorized') {
          listEl.innerHTML = '<p class="text-muted text-sm">Proxy keys API not available or empty.</p>';
        }
      });
  }

  createBtn.onclick = () => {
    const keyName = prompt('Enter a name for the new proxy key:', 'JanitorAI Client Key');
    if (keyName === null) return;
    apiFetch('/v1/proxy-keys', {
      method: 'POST',
      body: JSON.stringify({ name: keyName.trim() || 'JanitorAI Client Key' }),
    })
      .then((res) => res.json())
      .then((data) => {
        showToast('New proxy key generated!', 'ok');
        if (data.proxy_key) {
          keyRaw.textContent = data.proxy_key;
          keyBox.classList.remove('hidden');
          copyText(data.proxy_key, copyBtn);
        }
        loadKeys();
      })
      .catch(() => showToast('Failed to create key.', 'err'));
  };

  loadKeys();

  return { loadKeys };
}

