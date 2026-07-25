import { apiFetch } from '../services/api.js';
import { showToast } from '../services/toast.js';

const PROVIDER_NAMES = {
  'openrouter_byok': 'OpenRouter (BYOK Key)',
  'openrouter_pkce': 'OpenRouter (PKCE OAuth)',
  'openai_byok': 'OpenAI (BYOK Key)',
  'gemini_byok': 'Google Gemini (BYOK Key)',
  'deepseek_byok': 'DeepSeek (BYOK Key)',
};

export function renderProviderSettings(container, { onProviderUpdated }) {
  container.innerHTML = `
    <div class="panel" id="panel-providers">
      <div class="panel-header">
        <div class="panel-title">⚡ Active LLM Provider & Credentials</div>
        <span id="provider-loading" class="spinner hidden"></span>
      </div>
      <div class="panel-body" style="display:flex;flex-direction:column;gap:14px;">
        <div>
          <label>Select Active Provider</label>
          <div id="provider-options" style="display:flex;flex-wrap:wrap;gap:12px;margin-top:6px;"></div>
        </div>

        <div id="provider-key-container" style="display:flex;flex-direction:column;gap:8px;">
          <label for="provider-key-input">API Key for Selected Provider</label>
          <div class="flex-row">
            <input id="provider-key-input" type="password" placeholder="Paste provider API key..." autocomplete="off" style="flex:1;" />
            <button id="btn-save-provider-key" class="btn btn-primary btn-sm">Save Key</button>
          </div>
        </div>

        <div id="pkce-container" class="hidden" style="margin-top:4px;">
          <p class="text-muted text-sm" style="margin-bottom:8px;">Authorizes RACHEL via OpenRouter OAuth PKCE without copying raw keys.</p>
          <a href="/v1/auth/openrouter/authorize" class="btn btn-primary btn-sm" id="btn-connect-pkce">🔗 Connect OpenRouter (PKCE)</a>
        </div>
      </div>
    </div>
  `;

  let _selectedProvider = null;

  function updateProviderUI(providerKey) {
    const keyBox = document.getElementById('provider-key-container');
    const pkceBox = document.getElementById('pkce-container');
    if (providerKey === 'openrouter_pkce') {
      keyBox.classList.add('hidden');
      pkceBox.classList.remove('hidden');
    } else {
      keyBox.classList.remove('hidden');
      pkceBox.classList.add('hidden');
    }
  }

  function loadProviders() {
    const optionsContainer = document.getElementById('provider-options');
    apiFetch('/v1/providers')
      .then((res) => res.json())
      .then((d) => {
        _selectedProvider = d.active_provider;
        const html = Object.keys(PROVIDER_NAMES)
          .map((pk) => {
            const info = d.providers[pk] || {};
            const checked = pk === d.active_provider ? 'checked' : '';
            const statusTag = info.configured
              ? ' <span style="color:var(--green);font-size:0.75rem;">(Key Set)</span>'
              : ' <span style="color:var(--muted);font-size:0.75rem;">(Not Set)</span>';
            return `
              <label style="text-transform:none;font-weight:normal;cursor:pointer;display:flex;align-items:center;gap:6px;background:rgba(12,16,36,0.6);padding:8px 12px;border-radius:var(--radius-sm);border:1px solid var(--border);">
                <input type="radio" name="active_provider_radio" value="${pk}" ${checked} data-pk="${pk}" />
                <span>${PROVIDER_NAMES[pk]}${statusTag}</span>
              </label>
            `;
          })
          .join('');
        optionsContainer.innerHTML = html;
        updateProviderUI(_selectedProvider);

        optionsContainer.querySelectorAll('input[name="active_provider_radio"]').forEach((radio) => {
          radio.onchange = () => {
            const pk = radio.getAttribute('data-pk');
            _selectedProvider = pk;
            updateProviderUI(pk);
            apiFetch('/v1/providers/active', {
              method: 'POST',
              body: JSON.stringify({ provider: pk }),
            })
              .then((res) => res.json())
              .then(() => {
                showToast(`Active provider updated: ${PROVIDER_NAMES[pk]}`, 'ok');
                if (onProviderUpdated) onProviderUpdated();
              })
              .catch((e) => {
                if (e.message !== 'Unauthorized') showToast('Failed to set active provider', 'err');
              });
          };
        });
      })
      .catch((e) => {
        if (e.message !== 'Unauthorized') showToast('Failed to load provider config', 'err');
      });
  }

  document.getElementById('btn-save-provider-key').onclick = () => {
    const keyInput = document.getElementById('provider-key-input');
    const val = keyInput.value.trim();
    if (!val) {
      showToast('Please enter an API key.', 'warn');
      return;
    }
    if (!_selectedProvider || _selectedProvider === 'openrouter_pkce') return;

    apiFetch('/v1/providers/credentials', {
      method: 'POST',
      body: JSON.stringify({ provider: _selectedProvider, api_key: val }),
    })
      .then((res) => res.json())
      .then(() => {
        showToast(`API key saved for ${PROVIDER_NAMES[_selectedProvider]}`, 'ok');
        keyInput.value = '';
        loadProviders();
        if (onProviderUpdated) onProviderUpdated();
      })
      .catch((e) => {
        if (e.message !== 'Unauthorized') showToast('Failed to save API key.', 'err');
      });
  };

  loadProviders();

  return { loadProviders };
}
