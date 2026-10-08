// One keyboard/focus controller for server-rendered password, danger and feedback dialogs.
export function createDialog(modal, { onClose = () => {} } = {}) {
  const panel = modal.querySelector('.danger-modal-panel');
  let opener = null;
  const focusable = () => Array.from(modal.querySelectorAll(
    'button:not([disabled]), a[href], input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )).filter((element) => element.getClientRects().length && !element.hidden);
  const close = () => {
    modal.hidden = true;
    onClose();
    if (opener?.isConnected) opener.focus();
    opener = null;
  };
  const open = (trigger = document.activeElement, initial = panel) => {
    opener = trigger;
    modal.hidden = false;
    initial.focus();
  };
  modal.addEventListener('click', (event) => {
    if (event.target === modal) close();
  });
  modal.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
    } else if (event.key === 'Tab') {
      const elements = focusable();
      const first = elements[0];
      const last = elements.at(-1);
      if (!first) { event.preventDefault(); panel.focus(); return; }
      if (event.shiftKey && (document.activeElement === first || !elements.includes(document.activeElement))) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !elements.includes(document.activeElement))) {
        event.preventDefault(); first.focus();
      }
    }
  });
  document.addEventListener('focusin', (event) => {
    if (!modal.hidden && !modal.contains(event.target)) (focusable()[0] ?? panel).focus();
  });
  return { open, close };
}

export function initializeDialogs() {
  const passwordModal = document.getElementById('changePasswordModal');
  if (passwordModal) {
    const dialog = createDialog(passwordModal, { onClose: () => {
      passwordModal.querySelectorAll('input[type="password"]').forEach((input) => { input.value = ''; });
    } });
    document.querySelectorAll('[data-password-open]').forEach((button) => {
      button.addEventListener('click', () => {
        document.getElementById('changePasswordMemberId').value = button.dataset.memberId;
        document.getElementById('changePasswordUser').textContent = `${passwordModal.dataset.changingLabel} ${button.dataset.username}`;
        dialog.open(button, document.getElementById('newPassword'));
      });
    });
    passwordModal.querySelector('[data-password-cancel]').addEventListener('click', dialog.close);
  }
  const dangerModal = document.getElementById('dangerActionModal');
  if (dangerModal) {
    let pendingForm = null;
    const dialog = createDialog(dangerModal, { onClose: () => { pendingForm = null; } });
    window.hideDangerAction = dialog.close;
    window.confirmDangerAction = (form, prompt) => {
      pendingForm = form;
      document.getElementById('dangerActionMessage').textContent = prompt;
      dialog.open();
      return false;
    };
    window.submitDangerAction = () => {
      const form = pendingForm;
      dialog.close();
      form?.submit();
    };
    dangerModal.querySelector('[data-danger-cancel]').addEventListener('click', dialog.close);
    dangerModal.querySelector('[data-danger-confirm]').addEventListener('click', window.submitDangerAction);
  }
  const feedbackModal = document.getElementById('feedbackModal');
  if (feedbackModal) {
    const dialog = createDialog(feedbackModal);
    document.addEventListener('click', (event) => {
      const button = event.target.closest('[data-feedback-open]');
      if (button) dialog.open(button, document.getElementById('feedback-message'));
    });
    feedbackModal.querySelector('[data-feedback-cancel]').addEventListener('click', dialog.close);
  }
}
