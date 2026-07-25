export function renderHeader(container, { onRefresh, onLogout }) {
  container.innerHTML = `
    <header>
      <div class="logo">🎲 RACHEL Proxy</div>
      <div class="header-meta">
        <span class="version-tag">Dashboard</span>
        <span id="header-status-dot" class="status-dot idle"></span>
        <span id="header-status-text" class="text-muted text-sm">Connecting…</span>
      </div>
      <div class="header-actions">
        <button id="btn-refresh-status" class="btn btn-ghost btn-sm">↻ Refresh</button>
        <button id="btn-logout" class="btn btn-ghost btn-sm">✕ Disconnect</button>
      </div>
    </header>
  `;

  document.getElementById('btn-refresh-status').onclick = onRefresh;
  document.getElementById('btn-logout').onclick = onLogout;
}

export function updateHeaderStatus(statusDotClass, text) {
  const dot = document.getElementById('header-status-dot');
  const txt = document.getElementById('header-status-text');
  if (dot) dot.className = `status-dot ${statusDotClass}`;
  if (txt) txt.textContent = text;
}
