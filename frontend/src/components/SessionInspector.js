import { apiFetch } from '../services/api.js';
import { showToast } from '../services/toast.js';
import { showConfirm } from '../services/modal.js';

function syntaxHighlight(obj) {
  const json = JSON.stringify(obj, null, 2);
  return json.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, (match) => {
    let cls = 'json-num';
    if (/^"/.test(match)) cls = /:$/.test(match) ? 'json-key' : 'json-string';
    else if (/true|false/.test(match)) cls = 'json-bool';
    else if (/null/.test(match)) cls = 'json-null';
    return `<span class="${cls}">${match}</span>`;
  });
}

export function renderSessionInspector(container, { onSessionModified }) {
  container.innerHTML = `
    <div class="panel" id="panel-session">
      <div class="panel-header">
        <div class="panel-title" id="session-panel-title">📂 Session Inspector</div>
        <div class="flex-row hidden" id="session-actions">
          <button id="btn-export-session" class="btn btn-ghost btn-sm">📥 Export</button>
          <button id="btn-reset-session" class="btn btn-warning btn-sm">↻ Reset</button>
          <button id="btn-delete-session" class="btn btn-danger btn-sm">✕ Delete</button>
        </div>
      </div>
      <div class="panel-body" id="session-body">
        <p class="text-muted text-sm">Select a session from the sidebar to inspect it.</p>
      </div>
    </div>
  `;

  let _currentSession = null;
  const titleEl = document.getElementById('session-panel-title');
  const bodyEl = document.getElementById('session-body');
  const actionsEl = document.getElementById('session-actions');
  const exportBtn = document.getElementById('btn-export-session');
  const resetBtn = document.getElementById('btn-reset-session');
  const deleteBtn = document.getElementById('btn-delete-session');

  function selectSession(id) {
    _currentSession = id;
    titleEl.textContent = `🗂 Session: ${id}`;
    bodyEl.innerHTML = '<span class="spinner"></span>';
    actionsEl.classList.add('hidden');

    apiFetch(`/v1/sessions/${encodeURIComponent(id)}`)
      .then((res) => {
        if (res.status === 404) {
          bodyEl.innerHTML = `<p class="text-muted text-sm">No state found for session <code>${id}</code>.</p>`;
          return;
        }
        return res.json().then((d) => {
          actionsEl.classList.remove('hidden');
          const turnsHtml = (d.turns || [])
            .map(
              (t, i) => `
            <div class="turn-card">
              <div class="turn-header" data-turn-idx="${i}">
                <span class="turn-idx">#${i + 1}</span>
                <span class="turn-key">${t.turn_key}</span>
                <span class="spacer"></span>
                <span class="text-muted arrow">►</span>
              </div>
              <div class="turn-body">
                <div class="turn-diff">
                  <div class="turn-diff-col">
                    <div class="turn-diff-label">Before</div>
                    <pre class="json-block" style="max-height:200px;">${syntaxHighlight(t.before)}</pre>
                  </div>
                  <div class="turn-diff-col">
                    <div class="turn-diff-label">After</div>
                    <pre class="json-block" style="max-height:200px;">${syntaxHighlight(t.after)}</pre>
                  </div>
                </div>
              </div>
            </div>
          `
            )
            .join('');

          bodyEl.innerHTML = `
            <div style="margin-bottom:14px;">
              <div class="panel-title text-sm" style="margin-bottom:8px;">Current State (latest turn)</div>
              <pre class="json-block">${syntaxHighlight(d.current_state)}</pre>
            </div>
            <div class="panel-title text-sm" style="margin-bottom:8px;">Turn History (${d.turn_count} turn${d.turn_count !== 1 ? 's' : ''})</div>
            <div class="turn-list">${turnsHtml}</div>
          `;

          bodyEl.querySelectorAll('.turn-header').forEach((hdr) => {
            hdr.onclick = () => {
              const body = hdr.nextElementSibling;
              const arrow = hdr.querySelector('.arrow');
              body.classList.toggle('open');
              arrow.innerHTML = body.classList.contains('open') ? '▼' : '►';
            };
          });
        });
      })
      .catch((e) => {
        if (e.message !== 'Unauthorized') {
          bodyEl.innerHTML = '<p class="text-muted text-sm">Failed to load session data.</p>';
        }
      });
  }

  exportBtn.onclick = () => {
    if (!_currentSession) return;
    apiFetch(`/v1/sessions/${encodeURIComponent(_currentSession)}/export`)
      .then((res) => {
        if (!res.ok) throw new Error('Failed to export session data.');
        return res.json();
      })
      .then((data) => {
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${_currentSession}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        showToast(`Session "${_currentSession}" exported successfully.`, 'ok');
      })
      .catch((e) => {
        if (e.message !== 'Unauthorized') showToast(`Export failed: ${e.message}`, 'err');
      });
  };

  resetBtn.onclick = () => {
    if (!_currentSession) return;
    showConfirm('Reset Session', `Clear all state history for "${_currentSession}"? The session ID is preserved but all turn data will be wiped.`, () => {
      apiFetch(`/v1/sessions/${encodeURIComponent(_currentSession)}/reset`, { method: 'POST' })
        .then((res) => {
          if (res.ok) {
            showToast(`Session "${_currentSession}" reset.`, 'ok');
            selectSession(_currentSession);
            if (onSessionModified) onSessionModified();
          } else {
            showToast('Reset failed.', 'err');
          }
        })
        .catch((e) => {
          if (e.message !== 'Unauthorized') showToast('Reset failed.', 'err');
        });
    });
  };

  deleteBtn.onclick = () => {
    if (!_currentSession) return;
    showConfirm('Delete Session', `Permanently delete all data for "${_currentSession}"? This cannot be undone.`, () => {
      apiFetch(`/v1/sessions/${encodeURIComponent(_currentSession)}`, { method: 'DELETE' })
        .then((res) => {
          if (res.ok) {
            showToast(`Session "${_currentSession}" deleted.`, 'ok');
            _currentSession = null;
            titleEl.textContent = '📂 Session Inspector';
            bodyEl.innerHTML = '<p class="text-muted text-sm">Select a session from the sidebar to inspect it.</p>';
            actionsEl.classList.add('hidden');
            if (onSessionModified) onSessionModified();
          } else {
            showToast('Delete failed.', 'err');
          }
        })
        .catch((e) => {
          if (e.message !== 'Unauthorized') showToast('Delete failed.', 'err');
        });
    });
  };

  return { selectSession };
}
