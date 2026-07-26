import { apiFetch } from '../services/api.js';
import { updateHeaderStatus } from './Header.js';

const PROVIDER_NAMES = {
  'openrouter_byok': 'OpenRouter (BYOK Key)',
  'openrouter_pkce': 'OpenRouter (PKCE OAuth)',
  'openai_byok': 'OpenAI (BYOK Key)',
  'gemini_byok': 'Google Gemini (BYOK Key)',
  'deepseek_byok': 'DeepSeek (BYOK Key)',
};

export function renderProxyStatus(container, { onStatusLoaded }) {
  container.innerHTML = `
    <div class="panel" id="panel-status">
      <div class="panel-header">
        <div class="panel-title">📡 Proxy Status</div>
        <span id="status-loading" class="spinner"></span>
      </div>
      <div class="panel-body">
        <div class="status-grid" id="status-grid"></div>
      </div>
    </div>
  `;

  const spinner = document.getElementById('status-loading');
  const grid = document.getElementById('status-grid');

  function loadStatus() {
    spinner.classList.remove('hidden');
    apiFetch('/v1/status')
      .then((res) => res.json())
      .then((d) => {
        const cards = [
          { label: 'Active Provider', value: PROVIDER_NAMES[d.active_provider] || d.active_provider },
          { label: 'Provider Key', value: d.provider_key_set ? '✓ Set' : '✗ Missing', cls: d.provider_key_set ? 'ok' : 'err' },
          { label: 'Sandbox Engine', value: d.sandbox_engine || '—' },
          { label: 'Sandbox Timeout', value: d.sandbox_timeout + 's' },
          { label: 'Max Iterations', value: d.max_iterations },
          { label: 'Active Sessions', value: d.active_sessions_count },
        ];
        grid.innerHTML = cards
          .map(
            (c) => `
          <div class="stat-card">
            <div class="stat-label">${c.label}</div>
            <div class="stat-value ${c.cls || ''}">${c.value}</div>
          </div>
        `
          )
          .join('');

        if (d.provider_key_set) {
          updateHeaderStatus('ok', 'Proxy OK');
        } else {
          updateHeaderStatus('warn', 'API key missing');
        }

        if (onStatusLoaded) onStatusLoaded(d);
      })
      .catch((e) => {
        if (e.message !== 'Unauthorized') {
          updateHeaderStatus('err', 'Error');
        }
      })
      .finally(() => {
        spinner.classList.add('hidden');
      });
  }

  loadStatus();

  return { loadStatus };
}
