import { hydrateRoot } from 'react-dom/client';
import { Nav } from './Nav.jsx';
import './styles.css';
import { initializeProposalFilters } from './proposalFilters.js';
import { initializeUX } from './ux.js';
import { initializeForms } from './forms.js';
import { initializeBudget } from './budget.js';
import { initializeDialogs } from './dialogs.js';
import { initializeBrowserErrors } from './browserErrors.js';
import { initializeAdminTabs } from './adminTabs.js';

initializeBrowserErrors();
initializeDialogs();
initializeAdminTabs();
initializeUX();
initializeForms();
initializeBudget();
initializeProposalFilters();

for (const rows of document.querySelectorAll('[data-new-component-rows]')) {
  const form = rows.closest('form');
  const add = form.querySelector('[data-add-group-component]');
  const template = form.querySelector('[data-new-component-template]');
  const updateLimit = () => {
    add.disabled = Number(rows.dataset.existingCount) + rows.children.length >= 30;
  };
  add.addEventListener('click', () => {
    if (add.disabled) return;
    rows.append(template.content.cloneNode(true));
    rows.lastElementChild.querySelector('input').focus();
    updateLimit();
  });
  rows.addEventListener('click', (event) => {
    const remove = event.target.closest('[data-remove-group-component]');
    if (!remove) return;
    remove.closest('.group-component-input-row').remove();
    updateLimit();
    add.focus();
  });
  updateLimit();
}

function readProps(root) {
  try {
    return JSON.parse(root.dataset.reactProps ?? '');
  } catch (error) {
    console.error('Unable to initialize React navigation: invalid properties.', error);
    return null;
  }
}

for (const root of document.querySelectorAll('[data-react-nav]')) {
  const props = readProps(root);
  if (props) {
    hydrateRoot(root, <Nav {...props} />, {
      onRecoverableError: (error) => console.error('React navigation hydration warning.', error),
    });
  }
}

for (const button of document.querySelectorAll('[data-print-page]')) {
  button.addEventListener('click', async () => {
    const label = button.textContent;
    button.disabled = true;
    try {
      await Promise.all([...document.querySelectorAll('.qr-label img')].map(img => img.decode()));
      window.print();
    } catch {
      button.textContent = button.dataset.printError || label;
    } finally { button.disabled = false; }
  });
}

function sortableValue(cell, type) {
  const value = cell?.dataset.sortValue ?? cell?.textContent.trim() ?? '';
  return type === 'number' ? Number(value.replace(/[^0-9+.-]/g, '')) : value.toLocaleLowerCase();
}

for (const table of document.querySelectorAll('[data-sortable-table]')) {
  const body = table.tBodies[0];
  if (!body) continue;

  table.querySelectorAll('thead th').forEach((header, column) => {
    if (column === 0 && table.hasAttribute('data-row-positions')) return;
    const label = header.textContent.trim();
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'table-sort-button';
    button.textContent = label;
    button.setAttribute('aria-label', `${document.documentElement.lang === 'es' ? 'Ordenar por' : 'Sort by'} ${label}`);
    header.textContent = '';
    header.append(button);

    button.addEventListener('click', () => {
      const direction = header.getAttribute('aria-sort') === 'ascending' ? 'descending' : 'ascending';
      table.querySelectorAll('thead th').forEach((other) => other.removeAttribute('aria-sort'));
      header.setAttribute('aria-sort', direction);
      const multiplier = direction === 'ascending' ? 1 : -1;
      const type = header.dataset.sortType ?? 'text';
      const rows = Array.from(body.rows);
      rows.sort((left, right) => {
        const leftValue = sortableValue(left.cells[column], type);
        const rightValue = sortableValue(right.cells[column], type);
        if (type === 'number') return (leftValue - rightValue) * multiplier;
        return leftValue.localeCompare(rightValue, undefined, { numeric: true }) * multiplier;
      });
      rows.forEach((row, index) => {
        if (table.hasAttribute('data-row-positions')) row.cells[0].textContent = String(index + 1);
        body.append(row);
      });
    });
  });
}
