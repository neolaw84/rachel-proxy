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

  let sessionSidebar = null;
  let providerSettings = null;
  let proxyKeysPanel = null;
  let credentialsHelper = null;
  let proxyStatus = null;
  let sessionInspector = null;

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

  proxyKeysPanel = renderProxyKeysPanel(proxyKeysContainer);

  credentialsHelper = renderCredentialsHelper(credentialsContainer);

  proxyStatus = renderProxyStatus(statusContainer, {
    onStatusLoaded: (data) => {
      if (credentialsHelper) {
        credentialsHelper.updateEndpoint(data.api_endpoint);
      }
    },
  });
});
