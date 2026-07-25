import { apiFetch } from '../services/api.js';
import { showToast } from '../services/toast.js';
import { showConfirm } from '../services/modal.js';

export function renderProxyKeysPanel(container) {
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
        <div id="proxy-keys-list">
          <span class="spinner"></span> Loading proxy keys...
        </div>
      </div>
    </div>
  `;

  const listEl = document.getElementById('proxy-keys-list');
  const createBtn = document.getElementById('btn-create-proxy-key');

  function loadKeys() {
    listEl.innerHTML = '<span class="spinner"></span> Loading proxy keys...';
    apiFetch('/v1/keys')
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
              <td class="key-prefix">${k.key_prefix || k.id}</td>
              <td>${k.label || 'Default Client Key'}</td>
              <td>${k.created_at ? new Date(k.created_at).toLocaleDateString() : '—'}</td>
              <td style="text-align:right;">
                <button class="btn btn-danger btn-sm btn-revoke-key" data-id="${k.id}">Revoke</button>
              </td>
            </tr>
          `)
          .join('');

        listEl.innerHTML = `
          <table class="keys-table">
            <thead>
              <tr>
                <th>Key Prefix</th>
                <th>Label</th>
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
            showConfirm('Revoke API Key', `Are you sure you want to revoke key ID "${keyId}"?`, () => {
              apiFetch(`/v1/keys/${keyId}`, { method: 'DELETE' })
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
    const label = prompt('Enter a label for the new proxy key:', 'Client Key');
    if (label === null) return;
    apiFetch('/v1/keys', {
      method: 'POST',
      body: JSON.stringify({ label: label.trim() || 'Client Key' }),
    })
      .then((res) => res.json())
      .then((data) => {
        showToast('New proxy key generated!', 'ok');
        if (data.raw_key) {
          alert(`Save your key now! It will not be shown again:\n\n${data.raw_key}`);
        }
        loadKeys();
      })
      .catch(() => showToast('Failed to create key.', 'err'));
  };

  loadKeys();

  return { loadKeys };
}
