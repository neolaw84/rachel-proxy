const LS_KEY = 'rpg_proxy_api_key';

let _apiKey = localStorage.getItem(LS_KEY) || '';
let _onUnauthorizedCallback = null;

export function getApiKey() {
  return _apiKey;
}

export function setApiKey(key) {
  _apiKey = key || '';
  if (_apiKey) {
    localStorage.setItem(LS_KEY, _apiKey);
  } else {
    localStorage.removeItem(LS_KEY);
  }
}

export function onUnauthorized(cb) {
  _onUnauthorizedCallback = cb;
}

export function apiFetch(path, opts = {}) {
  const headers = Object.assign(
    {
      'Authorization': `Bearer ${_apiKey}`,
      'Content-Type': 'application/json',
    },
    opts.headers || {}
  );

  return fetch(path, Object.assign({}, opts, { headers })).then((res) => {
    if (res.status === 401) {
      if (_onUnauthorizedCallback) {
        _onUnauthorizedCallback('Invalid API key. Please reconnect.');
      }
      throw new Error('Unauthorized');
    }
    return res;
  });
}
