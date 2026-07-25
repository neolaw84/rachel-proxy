export function showToast(msg, type = 'ok', duration = 3000) {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  const container = document.getElementById('toast-container');
  if (container) {
    container.appendChild(el);
    setTimeout(() => {
      el.remove();
    }, duration);
  }
}
