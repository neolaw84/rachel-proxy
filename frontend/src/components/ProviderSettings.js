import { apiFetch } from '../services/api.js';
import { showToast } from '../services/toast.js';

const PROVIDER_NAMES = {
  'openrouter_byok': 'OpenRouter (BYOK Key)',
  'openrouter_pkce': 'OpenRouter (PKCE OAuth)',
  'openai_byok': 'OpenAI (BYOK Key)',
  'gemini_byok': 'Google Gemini (BYOK Key)',
  'deepseek_byok': 'DeepSeek (BYOK Key)',
  'localhost_byok': 'Localhost / Ollama (OpenAI-Compatible)',
};

export function renderProviderSettings(container, { onProviderUpdated }) {
  container.innerHTML = `
    <div class="panel" id="panel-providers">
      <div class="panel-header">
        <div class="panel-title">2️⃣ Step 2: Select AI Provider & Credentials</div>
        <span id="provider-loading" class="spinner hidden"></span>
      </div>

      <div class="panel-body" style="display:flex;flex-direction:column;gap:14px;">
        <div>
          <label>Select Active Provider</label>
          <div id="provider-options" style="display:flex;flex-wrap:wrap;gap:12px;margin-top:6px;"></div>
        </div>

        <div id="localhost-toggle-container" class="hidden" style="background:rgba(12,16,36,0.5);padding:10px 12px;border-radius:var(--radius-sm);border:1px solid var(--border);">
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer;margin:0;text-transform:none;font-weight:500;">
            <input type="checkbox" id="chk-localhost-key-not-needed" checked />
            <span>Key Not Needed (Ollama / LocalAI / LM Studio default)</span>
          </label>
          <p class="text-muted text-xs" style="margin:4px 0 0 24px;font-size:0.75rem;">
            When checked, requests bypass the proxy API key check using 'not-needed'. Uncheck if your local server strictly requires an API key.
          </p>
        </div>

        <div id="localhost-url-container" class="hidden" style="display:flex;flex-direction:column;gap:6px;background:rgba(12,16,36,0.5);padding:10px 12px;border-radius:var(--radius-sm);border:1px solid var(--border);">
          <label for="localhost-url-input" style="font-weight:500;text-transform:none;">Localhost Base URL (OpenAI-Compatible Endpoint)</label>
          <div class="flex-row">
            <input id="localhost-url-input" type="text" placeholder="http://localhost:11434/v1/chat/completions (Ollama default)" autocomplete="off" style="flex:1;" />
            <button id="btn-save-localhost-url" class="btn btn-primary btn-sm">Save URL</button>
            <button id="btn-reset-localhost-url" class="btn btn-ghost btn-sm" title="Reset to default URL">Reset</button>
          </div>
          <div style="display:flex;gap:6px;align-items:center;margin-top:2px;flex-wrap:wrap;">
            <span class="text-muted text-xs" style="font-size:0.75rem;">Presets:</span>
            <button id="btn-preset-ollama" class="btn btn-ghost btn-xs" style="padding:1px 6px;font-size:0.75rem;">Ollama (11434)</button>
            <button id="btn-preset-lmstudio" class="btn btn-ghost btn-xs" style="padding:1px 6px;font-size:0.75rem;">LM Studio (1234)</button>
            <button id="btn-preset-vllm" class="btn btn-ghost btn-xs" style="padding:1px 6px;font-size:0.75rem;">vLLM (8000)</button>
          </div>
        </div>

        <div id="provider-key-container" style="display:flex;flex-direction:column;gap:8px;">
          <label for="provider-key-input" id="provider-key-label">API Key for Selected Provider</label>
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
  let _localhostKeyNotNeeded = true;
  let _localhostBaseUrl = null;

  function updateProviderUI(providerKey, localhostKeyNotNeeded, localhostBaseUrl) {
    const keyBox = document.getElementById('provider-key-container');
    const pkceBox = document.getElementById('pkce-container');
    const localhostToggleBox = document.getElementById('localhost-toggle-container');
    const localhostUrlBox = document.getElementById('localhost-url-container');
    const keyInput = document.getElementById('provider-key-input');
    const keyLabel = document.getElementById('provider-key-label');
    const urlInput = document.getElementById('localhost-url-input');

    if (providerKey === 'openrouter_pkce') {
      keyBox.classList.add('hidden');
      pkceBox.classList.remove('hidden');
      localhostToggleBox.classList.add('hidden');
      localhostUrlBox.classList.add('hidden');
    } else if (providerKey === 'localhost_byok') {
      pkceBox.classList.add('hidden');
      localhostToggleBox.classList.remove('hidden');
      localhostUrlBox.classList.remove('hidden');
      if (urlInput) {
        urlInput.value = localhostBaseUrl || '';
      }
      if (localhostKeyNotNeeded) {
        keyBox.classList.add('hidden');
      } else {
        keyBox.classList.remove('hidden');
        keyLabel.textContent = 'API Key for Localhost (Required)';
        keyInput.placeholder = 'Enter required local server API key...';
      }
    } else {
      keyBox.classList.remove('hidden');
      pkceBox.classList.add('hidden');
      localhostToggleBox.classList.add('hidden');
      localhostUrlBox.classList.add('hidden');
      keyLabel.textContent = 'API Key for Selected Provider';
      keyInput.placeholder = 'Paste provider API key...';
    }
  }

  function loadProviders() {
    const optionsContainer = document.getElementById('provider-options');
    const localhostCheckbox = document.getElementById('chk-localhost-key-not-needed');
    const localhostUrlInput = document.getElementById('localhost-url-input');

    apiFetch('/v1/providers')
      .then((res) => res.json())
      .then((d) => {
        _selectedProvider = d.active_provider;
        _localhostKeyNotNeeded = d.localhost_key_not_needed ?? true;
        _localhostBaseUrl = d.localhost_base_url ?? null;
        if (localhostCheckbox) {
          localhostCheckbox.checked = _localhostKeyNotNeeded;
        }
        if (localhostUrlInput) {
          localhostUrlInput.value = _localhostBaseUrl || '';
        }

        const html = Object.keys(PROVIDER_NAMES)
          .map((pk) => {
            const info = d.providers[pk] || {};
            const checked = pk === d.active_provider ? 'checked' : '';
            let statusTag = '';
            if (pk === 'localhost_byok' && _localhostKeyNotNeeded) {
              statusTag = ' <span style="color:var(--green);font-size:0.75rem;">(Ready / No Key)</span>';
            } else if (info.configured) {
              statusTag = ' <span style="color:var(--green);font-size:0.75rem;">(Key Set)</span>';
            } else {
              statusTag = ' <span style="color:var(--muted);font-size:0.75rem;">(Not Set)</span>';
            }
            return `
              <label style="text-transform:none;font-weight:normal;cursor:pointer;display:flex;align-items:center;gap:6px;background:rgba(12,16,36,0.6);padding:8px 12px;border-radius:var(--radius-sm);border:1px solid var(--border);">
                <input type="radio" name="active_provider_radio" value="${pk}" ${checked} data-pk="${pk}" />
                <span>${PROVIDER_NAMES[pk]}${statusTag}</span>
              </label>
            `;
          })
          .join('');
        optionsContainer.innerHTML = html;
        updateProviderUI(_selectedProvider, _localhostKeyNotNeeded, _localhostBaseUrl);

        optionsContainer.querySelectorAll('input[name="active_provider_radio"]').forEach((radio) => {
          radio.onchange = () => {
            const pk = radio.getAttribute('data-pk');
            _selectedProvider = pk;
            updateProviderUI(pk, _localhostKeyNotNeeded, _localhostBaseUrl);
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

  const localhostCheckbox = document.getElementById('chk-localhost-key-not-needed');
  if (localhostCheckbox) {
    localhostCheckbox.onchange = () => {
      const enabled = localhostCheckbox.checked;
      _localhostKeyNotNeeded = enabled;
      updateProviderUI(_selectedProvider, _localhostKeyNotNeeded, _localhostBaseUrl);
      apiFetch('/v1/providers/localhost-key-not-needed', {
        method: 'POST',
        body: JSON.stringify({ enabled }),
      })
        .then((res) => res.json())
        .then(() => {
          showToast(enabled ? 'Localhost key marked as not needed' : 'Localhost key marked as required', 'ok');
          loadProviders();
          if (onProviderUpdated) onProviderUpdated();
        })
        .catch((e) => {
          if (e.message !== 'Unauthorized') showToast('Failed to update localhost key setting', 'err');
        });
    };
  }

  // Localhost Custom Base URL buttons
  const saveUrlBtn = document.getElementById('btn-save-localhost-url');
  if (saveUrlBtn) {
    saveUrlBtn.onclick = () => {
      const input = document.getElementById('localhost-url-input');
      const val = input ? input.value.trim() : '';
      apiFetch('/v1/providers/localhost-base-url', {
        method: 'POST',
        body: JSON.stringify({ base_url: val || null }),
      })
        .then((res) => res.json())
        .then((d) => {
          showToast(d.localhost_base_url ? `Localhost URL set to: ${d.localhost_base_url}` : 'Localhost URL reset to default', 'ok');
          loadProviders();
          if (onProviderUpdated) onProviderUpdated();
        })
        .catch((e) => {
          if (e.message !== 'Unauthorized') showToast('Failed to save localhost URL (must start with http:// or https://)', 'err');
        });
    };
  }

  const resetUrlBtn = document.getElementById('btn-reset-localhost-url');
  if (resetUrlBtn) {
    resetUrlBtn.onclick = () => {
      const input = document.getElementById('localhost-url-input');
      if (input) input.value = '';
      apiFetch('/v1/providers/localhost-base-url', {
        method: 'POST',
        body: JSON.stringify({ base_url: null }),
      })
        .then((res) => res.json())
        .then(() => {
          showToast('Localhost URL reset to default (Ollama)', 'ok');
          loadProviders();
          if (onProviderUpdated) onProviderUpdated();
        })
        .catch((e) => {
          if (e.message !== 'Unauthorized') showToast('Failed to reset localhost URL', 'err');
        });
    };
  }

  const btnOllama = document.getElementById('btn-preset-ollama');
  if (btnOllama) {
    btnOllama.onclick = () => {
      const input = document.getElementById('localhost-url-input');
      if (input) input.value = 'http://localhost:11434/v1/chat/completions';
    };
  }

  const btnLmStudio = document.getElementById('btn-preset-lmstudio');
  if (btnLmStudio) {
    btnLmStudio.onclick = () => {
      const input = document.getElementById('localhost-url-input');
      if (input) input.value = 'http://localhost:1234/v1/chat/completions';
    };
  }

  const btnVllm = document.getElementById('btn-preset-vllm');
  if (btnVllm) {
    btnVllm.onclick = () => {
      const input = document.getElementById('localhost-url-input');
      if (input) input.value = 'http://localhost:8000/v1/chat/completions';
    };
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
