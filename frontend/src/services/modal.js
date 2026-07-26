export function showConfirm(title, msg, onOk) {
  const ov = document.getElementById('confirm-overlay');
  const titleEl = document.getElementById('confirm-title');
  const msgEl = document.getElementById('confirm-msg');
  const okBtn = document.getElementById('confirm-ok');
  const cancelBtn = document.getElementById('confirm-cancel');

  if (!ov || !titleEl || !msgEl || !okBtn || !cancelBtn) return;

  titleEl.textContent = title;
  msgEl.textContent = msg;
  ov.classList.remove('hidden');

  function cleanup() {
    ov.classList.add('hidden');
    okBtn.onclick = null;
    cancelBtn.onclick = null;
  }

  okBtn.onclick = () => {
    cleanup();
    onOk();
  };

  cancelBtn.onclick = cleanup;
}
