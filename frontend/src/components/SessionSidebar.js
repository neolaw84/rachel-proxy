import { apiFetch } from '../services/api.js';
import { showToast } from '../services/toast.js';

export function renderSessionSidebar(container, { onSelectSession }) {
  container.innerHTML = `
    <aside id="sidebar">
      <div class="sidebar-header">
        Sessions
        <div class="flex-row" style="gap: 4px;">
          <button id="btn-import-session" class="btn btn-ghost btn-sm" title="Import Session">📥</button>
          <button id="btn-refresh-sessions" class="btn btn-ghost btn-sm">↻</button>
        </div>
      </div>
      <input type="file" id="import-file-input" accept=".json" class="hidden" />
      <div id="session-list">
        <div class="session-empty">Loading sessions…</div>
      </div>
    </aside>
  `;

  const listEl = document.getElementById('session-list');
  const refreshBtn = document.getElementById('btn-refresh-sessions');
  const importBtn = document.getElementById('btn-import-session');
  const fileInput = document.getElementById('import-file-input');

  function loadSessions() {
    listEl.innerHTML = '<div class="session-empty"><span class="spinner"></span></div>';
    apiFetch('/v1/sessions')
      .then((res) => res.json())
      .then((data) => {
        const sessions = data.sessions || [];
        if (!sessions.length) {
          listEl.innerHTML = '<div class="session-empty">No active sessions.</div>';
          return;
        }
        listEl.innerHTML = sessions
          .map((id) => {
            const safeId = id.replace(/'/g, "\\'");
            return `
              <div class="session-item" id="si-${id}" data-id="${safeId}">
                <span class="status-dot idle"></span>
                <span class="session-name">${id}</span>
              </div>
            `;
          })
          .join('');

        listEl.querySelectorAll('.session-item').forEach((item) => {
          item.onclick = () => {
            const id = item.getAttribute('data-id');
            listEl.querySelectorAll('.session-item').forEach((el) => el.classList.remove('active'));
            item.classList.add('active');
            onSelectSession(id);
          };
        });
      })
      .catch((e) => {
        if (e.message !== 'Unauthorized') {
          listEl.innerHTML = '<div class="session-empty">Failed to load sessions.</div>';
        }
      });
  }

  refreshBtn.onclick = loadSessions;
  importBtn.onclick = () => fileInput.click();

  fileInput.onchange = (event) => {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const data = JSON.parse(e.target.result);
        const defaultSessionId = file.name.replace(/\.json$/i, '');
        const sessionId = prompt('Enter a Session ID to import as:', defaultSessionId);
        if (!sessionId) return;
        const cleanId = sessionId.trim();
        if (!cleanId) {
          showToast('Invalid Session ID.', 'err');
          return;
        }

        apiFetch(`/v1/sessions/${encodeURIComponent(cleanId)}/import`, {
          method: 'POST',
          body: JSON.stringify(data),
        })
          .then((res) => {
            if (!res.ok) throw new Error('Import failed.');
            return res.json();
          })
          .then(() => {
            showToast(`Session "${cleanId}" imported successfully.`, 'ok');
            loadSessions();
            setTimeout(() => onSelectSession(cleanId), 150);
          })
          .catch((err) => {
            showToast(`Import failed: ${err.message}`, 'err');
          });
      } catch (err) {
        showToast(`Invalid JSON file: ${err.message}`, 'err');
      }
    };
    reader.readAsText(file);
    event.target.value = '';
  };

  loadSessions();

  return { loadSessions };
}
