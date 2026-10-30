/** Progressive enhancements; forms and permissions remain server-owned. */
export function projectedOrderCents(total, unitPrice, current, quantity) {
  return total + unitPrice * (quantity - current);
}

function initializeRows(doc) {
  const definitions = [
    ['component-rows', 'component-row-template', 'add-component', '.remove-component', 30, 1],
    ['cost-rows', 'cost-row-template', 'add-cost', '.remove-cost', 20, 0],
    ['edit-cost-rows', 'edit-cost-template', 'add-edit-cost', '.remove-edit-cost', 20, 0],
  ];
  for (const [id, templateId, addId, removeSelector, limit, minimum] of definitions) {
    const rows = doc.getElementById(id);
    if (!rows) continue;
    const add = doc.getElementById(addId);
    const template = doc.getElementById(templateId);
    const sync = () => {
      add.disabled = rows.children.length >= limit;
      rows.querySelectorAll(removeSelector).forEach(button => { button.disabled = rows.children.length <= minimum; });
    };
    add.addEventListener('click', () => {
      if (add.disabled) return;
      rows.append(template.content.cloneNode(true));
      sync();
      rows.lastElementChild.querySelector('input')?.focus();
    });
    rows.addEventListener('click', event => {
      const remove = event.target.closest(removeSelector);
      if (!remove || remove.disabled) return;
      remove.closest('.component-input-row, .edit-cost-row').remove();
      sync(); add.focus();
    });
    sync();
  }
}

export function initializeUX(doc = document, browser = window) {
  initializeRows(doc);
  const spanish = doc.documentElement.lang === 'es';
  const scrollLabel = spanish ? 'Desliza para ver más columnas' : 'Scroll to see more columns';
  for (const table of doc.querySelectorAll('main table')) {
    let region = table.parentElement;
    if (!region.classList.contains('table-scroll')) {
      const wrapper = doc.createElement('div');
      table.before(wrapper); wrapper.append(table); region = wrapper;
      region.className = 'table-scroll';
    }
    const hint = doc.createElement('p'); hint.className = 'scroll-hint'; hint.textContent = scrollLabel;
    region.before(hint);
    const sync = () => {
      const overflow = table.scrollWidth > region.clientWidth + 1;
      hint.hidden = !overflow;
      if (overflow) {
        region.tabIndex = 0; region.setAttribute('role', 'region'); region.setAttribute('aria-label', scrollLabel);
      } else {
        region.removeAttribute('tabindex'); region.removeAttribute('role'); region.removeAttribute('aria-label');
      }
    };
    sync(); if (browser.ResizeObserver) new browser.ResizeObserver(sync).observe(region);
  }
  doc.querySelector('[data-error-summary]')?.focus();
  for (const form of doc.querySelectorAll('form.quantity-form[data-order-total]')) {
    const input = form.querySelector('[name=quantity]');
    const result = doc.createElement('output'); result.className = 'quantity-preview'; result.setAttribute('aria-live', 'polite');
    input.id && result.setAttribute('for', input.id);
    form.append(result);
    const sync = () => {
      if (!input.validity.valid || input.value === '') { result.textContent = ''; return; }
      const total = projectedOrderCents(Number(form.dataset.orderTotal), Number(form.dataset.unitPrice), Number(form.dataset.currentQuantity), Number(input.value));
      const over = Boolean(form.dataset.cap) && total > Number(form.dataset.cap);
      result.dataset.over = String(over);
      result.textContent = `${form.dataset.previewLabel}: ${new Intl.NumberFormat(doc.documentElement.lang, { style: 'currency', currency: 'EUR' }).format(total / 100)}${over ? ` · ${form.dataset.overLabel}` : ''}`;
    };
    input.addEventListener('input', sync); sync();
  }
  for (const button of doc.querySelectorAll('[data-copy-command]')) {
    const label = button.textContent;
    button.addEventListener('click', async () => {
      try { await browser.navigator.clipboard.writeText(button.dataset.copyCommand); button.textContent = button.dataset.copied; }
      catch { button.textContent = `${button.dataset.copyFailed}: ${button.dataset.copyCommand}`; }
      button.setAttribute('aria-live', 'polite');
      browser.setTimeout(() => { button.textContent = label; }, 5000);
    });
  }
  for (const form of doc.querySelectorAll('[data-error-download]')) {
    const button = form.querySelector('button');
    const status = doc.querySelector('[data-error-download-status]');
    form.addEventListener('submit', async event => {
      event.preventDefault(); if (button.disabled) return;
      button.disabled = true; form.setAttribute('aria-busy', 'true'); status.textContent = form.dataset.busyLabel;
      try {
        const response = await browser.fetch(form.action, { method: 'POST', body: new FormData(form), credentials: 'same-origin' });
        if (!response.ok || response.redirected || !response.headers.get('Content-Type')?.includes('application/json')) throw new Error('Download unavailable');
        const blob = await response.blob();
        const link = doc.createElement('a'); link.href = browser.URL.createObjectURL(blob); link.download = 'manavote-errors.json';
        doc.body.append(link); link.click(); link.remove();
        status.textContent = form.dataset.successLabel;
        // Re-render the server's authoritative pending/archive lists after generation.
        browser.setTimeout(() => { browser.location.href = form.dataset.refreshUrl; }, 750);
      } catch {
        status.textContent = form.dataset.errorLabel; button.disabled = false;
      } finally { form.removeAttribute('aria-busy'); }
    });
  }
}
