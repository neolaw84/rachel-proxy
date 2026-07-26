export function renderHeader(container, { onRefresh, onLogout, onSelectTab, onCopyConfig }) {
  container.innerHTML = `
    <header>
      <div class="logo">🎲 RACHEL</div>
      <div class="nav-tabs" id="nav-tabs">
        <button class="nav-tab active" data-tab="setup">🚀 Setup & AI Provider</button>
        <button class="nav-tab" data-tab="sessions">💬 Session Inspector</button>
        <button class="nav-tab" data-tab="keys">🔑 Proxy Keys</button>
        <button class="nav-tab" data-tab="status">📡 System Status</button>
      </div>
      <div class="header-meta">
        <span id="header-status-dot" class="status-dot idle"></span>
        <span id="header-status-text" class="text-muted text-sm">Connecting…</span>
      </div>
      <div class="header-actions">
        <button id="btn-copy-config" class="btn btn-copy btn-sm">📋 Copy Credentials</button>
        <button id="btn-refresh-status" class="btn btn-ghost btn-sm">↻ Refresh</button>
        <button id="btn-logout" class="btn btn-ghost btn-sm">✕ Disconnect</button>
      </div>
    </header>
  `;

  document.getElementById('btn-refresh-status').onclick = onRefresh;
  document.getElementById('btn-logout').onclick = onLogout;
  if (onCopyConfig) {
    document.getElementById('btn-copy-config').onclick = onCopyConfig;
  }

  const tabsContainer = document.getElementById('nav-tabs');
  tabsContainer.querySelectorAll('.nav-tab').forEach((tabBtn) => {
    tabBtn.onclick = () => {
      tabsContainer.querySelectorAll('.nav-tab').forEach((b) => b.classList.remove('active'));
      tabBtn.classList.add('active');
      const tabName = tabBtn.getAttribute('data-tab');
      if (onSelectTab) onSelectTab(tabName);
    };
  });
}

export function updateHeaderStatus(statusDotClass, text) {
  const dot = document.getElementById('header-status-dot');
  const txt = document.getElementById('header-status-text');
  if (dot) dot.className = `status-dot ${statusDotClass}`;
  if (txt) txt.textContent = text;
}

