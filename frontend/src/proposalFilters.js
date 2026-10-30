/** Submit the existing GET form so filters retain shareable, server-owned URLs. */
export function initializeProposalFilters(doc = document, browser = window) {
  const form = doc.getElementById('proposal-query');
  if (!form) return;
  const submitButton = form.querySelector('[data-query-submit]');
  if (submitButton) submitButton.hidden = true;
  let timer;
  const cancel = () => browser.clearTimeout(timer);
  const submit = () => { cancel(); form.requestSubmit(); };
  // form.elements includes the advanced controls associated through form="…".
  for (const control of form.elements) {
    if (control.tagName === 'SELECT') control.addEventListener('change', submit);
    if (control.type === 'search') {
      const schedule = event => {
        cancel();
        if (!event.isComposing) timer = browser.setTimeout(submit, 450);
      };
      control.addEventListener('input', schedule);
      control.addEventListener('compositionend', schedule);
    }
  }
  form.addEventListener('submit', cancel);
}
