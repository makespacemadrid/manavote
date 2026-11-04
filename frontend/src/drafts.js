// Opt-in, account/form-scoped local drafts. Only declared fields are serialized.
export const DRAFT_TTL = 7 * 24 * 60 * 60 * 1000;
const PREFIX = 'manavote:draft:v1:';
const ROWS = [
  ['#component-rows', '#add-component', '.remove-component', 1, 30],
  ['#cost-rows', '#add-cost', '.remove-cost', 0, 20],
  ['#edit-cost-rows', '#add-edit-cost', '.remove-edit-cost', 0, 20],
  ['[data-new-component-rows]', '[data-add-group-component]', '[data-remove-group-component]', 0, 30],
];
const TYPES = new Set(['text', 'search', 'url', 'email', 'number', 'date', 'datetime-local', 'time', 'textarea', 'select-one', 'checkbox', 'radio']);

export function draftStorageKey(owner, formKey) {
  return PREFIX + encodeURIComponent(owner) + ':' + encodeURIComponent(formKey);
}

export function validDraft(value, now = Date.now()) {
  return value?.version === 1 && Number.isFinite(value.updatedAt) && value.updatedAt <= now + 60000 &&
    now - value.updatedAt < DRAFT_TTL && value.fields && typeof value.fields === 'object' && !Array.isArray(value.fields) &&
    Object.values(value.fields).every(entries => Array.isArray(entries) && entries.length <= 100 &&
      entries.every(entry => typeof entry?.value === 'string' && entry.value.length <= 200000 &&
        (entry.checked === undefined || typeof entry.checked === 'boolean'))) &&
    value.rows && typeof value.rows === 'object' && !Array.isArray(value.rows) &&
    Object.values(value.rows).every(count => Number.isInteger(count) && count >= 0 && count <= 30);
}

export function consumeDraftReceipts(storage, owner, receipts) {
  for (const receipt of receipts) {
    if (typeof receipt?.key !== 'string' || typeof receipt?.nonce !== 'string') continue;
    const key = draftStorageKey(owner, receipt.key);
    const raw = storage.getItem(key);
    let draft;
    try { draft = JSON.parse(raw || 'null'); }
    catch { storage.removeItem(key); continue; }
    if (draft?.submittedNonce === receipt.nonce) storage.removeItem(key);
  }
}

export function initializeDrafts(doc = document, browser = window) {
  const owner = doc.querySelector('meta[name=draft-owner]')?.content;
  if (!owner) return;
  const es = doc.documentElement.lang === 'es';
  const text = es ? {
    hint: 'El texto se guarda en este navegador durante 7 días. Las imágenes deben seleccionarse de nuevo.',
    found: 'Hay un borrador guardado. Restáuralo o descártalo para empezar a guardar cambios aquí.',
    saved: 'Borrador guardado en este navegador. Las imágenes no se guardan.',
    restored: 'Borrador restaurado. Revisa los datos y selecciona de nuevo las imágenes antes de enviar.',
    discard: 'Descartar borrador', restore: 'Restaurar borrador',
    discarded: 'Borrador eliminado. Los datos actuales siguen en el formulario.',
    unavailable: 'No se pudo guardar el borrador en este navegador. Mantén esta página abierta para conservar los datos.',
    changed: 'El formulario ha cambiado. No se pudo restaurar el borrador completo; el borrador guardado se conserva.',
    otherTab: 'Otra pestaña actualizó el borrador. Restáuralo o descártalo antes de guardar más cambios.',
  } : {
    hint: 'Text is saved on this browser for 7 days. Images must be selected again.',
    found: 'A saved draft is available. Restore or discard it to start saving changes here.',
    saved: 'Draft saved on this browser. Images are not saved.',
    restored: 'Draft restored. Review the entries and select any images again before submitting.',
    discard: 'Discard draft', restore: 'Restore draft',
    discarded: 'Draft deleted. Your current entries remain in the form.',
    unavailable: 'Draft saving is unavailable on this browser. Keep this page open to retain your entries.',
    changed: 'The form has changed. The full draft could not be restored; the saved draft is still available.',
    otherTab: 'Another tab updated this draft. Restore or discard it before saving more changes.',
  };
  let storage;
  try { storage = browser.localStorage; } catch { /* Forms still work without storage. */ }
  const read = key => {
    if (!storage) throw new Error('Storage unavailable');
    const raw = storage.getItem(key);
    if (!raw) return null;
    let value;
    try { value = JSON.parse(raw); } catch { storage.removeItem(key); return null; }
    if (raw.length > 250000 || !validDraft(value)) { storage.removeItem(key); return null; }
    return value;
  };
  // A receipt names the exact successful submission. Newer edits have a different nonce.
  try {
    const receipts = JSON.parse(doc.querySelector('meta[name=draft-receipts]')?.content || '[]');
    consumeDraftReceipts(storage, owner, receipts);
    for (let index = storage.length - 1; index >= 0; index--) {
      const key = storage.key(index);
      if (key?.startsWith(PREFIX + encodeURIComponent(owner) + ':')) read(key);
    }
  } catch { /* A denied/quota-limited store is reported beside each draft form. */ }

  for (const form of doc.querySelectorAll('form[data-draft-key][data-draft-fields]')) {
    const key = draftStorageKey(owner, form.dataset.draftKey);
    const allowed = form.dataset.draftFields.split(/\s+/);
    const controls = () => [...form.elements].filter(input => input.name && !input.disabled && TYPES.has(input.type) &&
      allowed.some(name => name === input.name || (name.endsWith('*') && input.name.startsWith(name.slice(0, -1)) && /^\d+$/.test(input.name.slice(name.length - 1)))));
    const serialize = () => {
      const fields = Object.create(null), rows = Object.create(null);
      for (const input of controls()) {
        (fields[input.name] ??= []).push({ value: input.value,
          ...(['checkbox', 'radio'].includes(input.type) ? { checked: input.checked } : {}) });
      }
      for (const [selector] of ROWS) {
        const container = form.querySelector(selector);
        if (container) rows[selector] = container.children.length;
      }
      return { version: 1, updatedAt: Date.now(), fields, rows };
    };
    const panel = doc.createElement('div'); panel.className = 'draft-controls';
    const status = doc.createElement('p'); status.className = 'help-text'; status.setAttribute('role', 'status'); status.textContent = text.hint;
    const buttons = doc.createElement('div'); buttons.className = 'button-row';
    const restore = doc.createElement('button'), discard = doc.createElement('button');
    for (const button of [restore, discard]) { button.type = 'button'; button.className = 'btn btn-secondary'; }
    restore.textContent = text.restore; restore.dataset.draftRestore = '';
    discard.textContent = text.discard; discard.dataset.draftDiscard = '';
    buttons.append(restore, discard); panel.append(status, buttons); form.prepend(panel);
    let pending = false, dirty = false, restoring = false;
    const unavailable = () => { status.textContent = text.unavailable; };
    const refresh = () => {
      try {
        pending = Boolean(read(key)); restore.hidden = !pending; discard.hidden = !pending;
        status.textContent = pending ? text.found : text.hint;
      } catch { restore.hidden = true; discard.hidden = true; unavailable(); }
    };
    const save = (nonce = null) => {
      if (pending || restoring || !dirty) return;
      try {
        const value = serialize();
        if (nonce) value.submittedNonce = nonce;
        const raw = JSON.stringify(value);
        if (raw.length > 250000 || !validDraft(value)) throw new Error('Draft too large');
        if (!storage) throw new Error('Storage unavailable');
        storage.setItem(key, raw);
        discard.hidden = false;
        if (status.textContent !== text.saved) status.textContent = text.saved;
      } catch { unavailable(); }
    };
    refresh();
    const changed = () => { if (!restoring) { dirty = true; save(); } };
    form.addEventListener('input', event => { if (controls().includes(event.target)) changed(); });
    form.addEventListener('change', event => { if (controls().includes(event.target)) changed(); });
    form.addEventListener('click', event => {
      if (event.target.closest('[id^=add-],.remove-component,.remove-cost,.remove-edit-cost,[data-add-group-component],[data-remove-group-component]')) changed();
    });
    restore.addEventListener('click', () => {
      try {
        const draft = read(key); if (!draft) { refresh(); return; }
        restoring = true;
        for (const [selector, , , min, max] of ROWS) {
          const container = form.querySelector(selector);
          const count = draft.rows[selector];
          if (container && count !== undefined && (count < min || count > max - Number(container.dataset.existingCount || 0))) throw new Error('Rows changed');
        }
        for (const [selector, add, remove, min, max] of ROWS) {
          const container = form.querySelector(selector);
          if (!container || draft.rows[selector] === undefined) continue;
          const count = draft.rows[selector];
          const limit = max - Number(container.dataset.existingCount || 0);
          if (count < min || count > limit) throw new Error('Rows changed');
          while (container.children.length !== count) {
            const before = container.children.length;
            const button = before < count ? form.querySelector(add) : container.lastElementChild.querySelector(remove);
            if (!button || button.disabled) throw new Error('Rows changed');
            button.click();
            if (container.children.length === before) throw new Error('Rows changed');
          }
        }
        const indexes = Object.create(null);
        const present = new Set(controls().map(input => input.name));
        const changedFields = Object.keys(draft.fields).some(name => !present.has(name));
        for (const input of controls()) {
          const index = indexes[input.name] || 0; indexes[input.name] = index + 1;
          const entry = draft.fields[input.name]?.[index]; if (!entry) continue;
          if (['checkbox', 'radio'].includes(input.type)) input.checked = Boolean(entry.checked);
          else input.value = entry.value;
          input.dispatchEvent(new Event('input', { bubbles: true }));
          input.dispatchEvent(new Event('change', { bubbles: true }));
        }
        if (changedFields) { restoring = false; status.textContent = text.changed; return; }
        pending = false; restoring = false; dirty = true; save(); restore.hidden = true;
        status.textContent = text.restored; controls()[0]?.focus();
      } catch { restoring = false; status.textContent = text.changed; }
    });
    discard.addEventListener('click', () => {
      try {
        storage.removeItem(key); pending = false; dirty = false;
        restore.hidden = true; discard.hidden = true; status.textContent = text.discarded;
      } catch { unavailable(); }
    });
    // Run after the form's validation/confirmation/offline guard has accepted submission.
    doc.addEventListener('submit', event => {
      if (event.target !== form || event.defaultPrevented) return;
      const nonce = browser.crypto?.randomUUID?.() || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
      let input = form.querySelector('input[name=_draft_nonce]');
      if (!input) { input = doc.createElement('input'); input.type = 'hidden'; input.name = '_draft_nonce'; form.append(input); }
      input.value = nonce;
      if (!pending) { dirty = true; save(nonce); }
    });
    browser.addEventListener('pagehide', () => { if (dirty && !form.hasAttribute('aria-busy')) save(); });
    browser.addEventListener('pageshow', event => { if (event.persisted) { dirty = false; refresh(); } });
    browser.addEventListener('storage', event => {
      if (event.key === key || event.key === null) { dirty = false; refresh(); if (pending) status.textContent = text.otherTab; }
    });
  }
}
