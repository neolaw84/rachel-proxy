import { onUnauthorized } from './services/api.js';
import { renderLocalAuthModal } from './auth/LocalAuthModal.js';
import { renderCloudAuthModal } from './auth/CloudAuthModal.js';

import { renderHeader } from './components/Header.js';
import { renderSessionSidebar } from './components/SessionSidebar.js';
import { renderProviderSettings } from './components/ProviderSettings.js';
import { renderProxyKeysPanel } from './components/ProxyKeysPanel.js';
import { renderCredentialsHelper } from './components/CredentialsHelper.js';
import { renderProxyStatus } from './components/ProxyStatus.js';
import { renderSessionInspector } from './components/SessionInspector.js';

document.addEventListener('DOMContentLoaded', () => {
  const authContainer = document.getElementById('auth-container');
  const headerContainer = document.getElementById('header-container');
  const sidebarContainer = document.getElementById('sidebar-container');
  const providerContainer = document.getElementById('provider-settings-container');
  const proxyKeysContainer = document.getElementById('proxy-keys-container');
  const credentialsContainer = document.getElementById('credentials-helper-container');
  const statusContainer = document.getElementById('proxy-status-container');
  const sessionInspectorContainer = document.getElementById('session-inspector-container');

  const views = {
    setup: document.getElementById('view-setup'),
    sessions: document.getElementById('view-sessions'),
    keys: document.getElementById('view-keys'),
    status: document.getElementById('view-status'),
  };

  let sessionSidebar = null;
  let providerSettings = null;
  let proxyKeysPanel = null;
  let credentialsHelper = null;
  let proxyStatus = null;
  let sessionInspector = null;

  function switchTab(tabName) {
    Object.keys(views).forEach((name) => {
      if (views[name]) {
        if (name === tabName) {
          views[name].classList.add('active');
        } else {
          views[name].classList.remove('active');
        }
      }
    });

    if (tabName === 'sessions' && sessionSidebar) {
      sessionSidebar.loadSessions();
    } else if (tabName === 'keys' && proxyKeysPanel) {
      proxyKeysPanel.loadKeys();
    } else if (tabName === 'status' && proxyStatus) {
      proxyStatus.loadStatus();
    }
  }

  function onConnected() {
    if (proxyStatus) proxyStatus.loadStatus();
    if (providerSettings) providerSettings.loadProviders();
    if (sessionSidebar) sessionSidebar.loadSessions();
    if (proxyKeysPanel) proxyKeysPanel.loadKeys();
  }

  // Tree-shaken build target conditional
  const isCloud = Boolean(import.meta.env.VITE_MULTI_TENANT);
  const authController = isCloud
    ? renderCloudAuthModal(authContainer, onConnected)
    : renderLocalAuthModal(authContainer, onConnected);

  onUnauthorized((msg) => {
    authController.showAuth(msg);
  });

  renderHeader(headerContainer, {
    onRefresh: () => {
      if (proxyStatus) proxyStatus.loadStatus();
      if (providerSettings) providerSettings.loadProviders();
      if (proxyKeysPanel) proxyKeysPanel.loadKeys();
    },
    onLogout: () => {
      authController.showAuth();
    },
    onSelectTab: (tabName) => {
      switchTab(tabName);
    },
    onCopyConfig: () => {
      switchTab('setup');
      const tabs = document.querySelectorAll('.nav-tab');
      tabs.forEach((t) => t.classList.toggle('active', t.getAttribute('data-tab') === 'setup'));
      const card = document.getElementById('panel-credentials');
      if (card) {
        card.scrollIntoView({ behavior: 'smooth' });
      }
    },
  });

  sessionInspector = renderSessionInspector(sessionInspectorContainer, {
    onSessionModified: () => {
      if (sessionSidebar) sessionSidebar.loadSessions();
    },
  });

  sessionSidebar = renderSessionSidebar(sidebarContainer, {
    onSelectSession: (sessionId) => {
      sessionInspector.selectSession(sessionId);
    },
  });

  providerSettings = renderProviderSettings(providerContainer, {
    onProviderUpdated: () => {
      if (proxyStatus) proxyStatus.loadStatus();
    },
  });

  proxyKeysPanel = renderProxyKeysPanel(proxyKeysContainer, { isCloud });

  credentialsHelper = renderCredentialsHelper(credentialsContainer, { isCloud });

  proxyStatus = renderProxyStatus(statusContainer, {
    onStatusLoaded: (data) => {
      if (credentialsHelper) {
        credentialsHelper.updateEndpoint(data.api_endpoint);
      }
    },
  });
});

