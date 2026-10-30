/** Native submissions keep server redirects, CSRF and submitter name/value intact. */
export function initializeForms(doc = document, browser = window) {
  const es = doc.documentElement.lang === 'es';
  const labels = es ? {
    busy: 'Enviando…', slow: 'La respuesta está tardando. No vuelvas a enviar mientras se procesa.',
    offline: 'Sin conexión. Tus datos siguen aquí; vuelve a enviar cuando tengas conexión.',
    invalid: 'Revisa los campos indicados antes de enviar.',
    image: 'Elige una imagen JPG o PNG. Tus otros datos siguen aquí.',
  } : {
    busy: 'Submitting…', slow: 'The response is taking a while. Please avoid resubmitting while it processes.',
    offline: 'You are offline. Your entries are still here; submit again when connected.',
    invalid: 'Check the highlighted fields before submitting.',
    image: 'Choose a JPG or PNG image. Your other entries are still here.',
  };
  const states = new Map();
  for (const form of doc.querySelectorAll('form')) {
    if (form.method.toLowerCase() !== 'post' || form.matches('[data-error-download]')) continue;
    const status = doc.createElement('p');
    status.className = 'form-status'; status.setAttribute('role', 'status'); status.hidden = true;
    // Keep the live message outside aria-busy so assistive technology can announce it.
    form.after(status);
    const state = { busy: false, dirty: false, timer: null, controls: [] };
    states.set(form, state);
    const show = (text, error = false) => {
      status.textContent = text; status.hidden = false;
      status.classList.toggle('field-error', error);
    };
    const reset = () => {
      state.busy = false; browser.clearTimeout(state.timer);
      form.removeAttribute('aria-busy');
      for (const [button, value] of state.controls) {
        if (value === null) button.removeAttribute('aria-disabled'); else button.setAttribute('aria-disabled', value);
      }
      state.controls = []; status.hidden = true;
    };
    form.addEventListener('input', event => {
      state.dirty = true;
      const input = event.target;
      if (input.matches('input,select,textarea') && input.validity.valid) input.removeAttribute('aria-invalid');
    });
    form.addEventListener('change', () => { state.dirty = true; });
    form.addEventListener('click', event => {
      if (event.target.closest('[id^=add-],.remove-component,.remove-cost,.remove-edit-cost,[data-add-group-component],[data-remove-group-component]')) state.dirty = true;
    });
    form.addEventListener('invalid', event => {
      event.target.setAttribute('aria-invalid', 'true'); show(labels.invalid, true);
    }, true);
    for (const input of form.querySelectorAll('input[type=file][accept*=".png"]')) {
      input.addEventListener('change', () => {
        const invalid = [...input.files].some(file => !/\.(jpe?g|png)$/i.test(file.name));
        input.setCustomValidity(invalid ? labels.image : '');
        input.setAttribute('aria-invalid', String(invalid));
        if (invalid) { show(labels.image, true); input.reportValidity(); }
        else { status.hidden = true; input.removeAttribute('aria-invalid'); }
      });
    }
    // A cancelled danger confirmation must never lock its form.
    form.addEventListener('submit', event => {
      if (event.defaultPrevented) return;
      if (state.busy) { event.preventDefault(); return; }
      if (browser.navigator.onLine === false) { event.preventDefault(); show(labels.offline, true); return; }
      state.busy = true; form.setAttribute('aria-busy', 'true'); show(labels.busy);
      for (const button of form.querySelectorAll('button[type=submit],button:not([type]),input[type=submit]')) {
        state.controls.push([button, button.getAttribute('aria-disabled')]);
        // Do not disable: native form serialization must include the clicked vote/action.
        button.setAttribute('aria-disabled', 'true');
      }
      state.timer = browser.setTimeout(() => show(labels.slow), 15000);
    });
    browser.addEventListener('pageshow', reset);
  }
  browser.addEventListener('beforeunload', event => {
    if (![...states.values()].some(state => state.busy) && [...states].some(([form, state]) => form.hasAttribute('data-protect-changes') && state.dirty)) {
      event.preventDefault(); event.returnValue = '';
    }
  });
}
