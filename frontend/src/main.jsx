import { hydrateRoot } from 'react-dom/client';
import { Nav } from './Nav.jsx';
import './styles.css';
import { initializeDialogs } from './dialogs.js';

initializeDialogs();

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
  button.addEventListener('click', () => window.print());
}

function sortableValue(cell, type) {
  const value = cell?.dataset.sortValue ?? cell?.textContent.trim() ?? '';
  return type === 'number' ? Number(value.replace(/[^0-9+.-]/g, '')) : value.toLocaleLowerCase();
}

for (const table of document.querySelectorAll('[data-sortable-table]')) {
  const body = table.tBodies[0];
  if (!body) continue;

  table.querySelectorAll('thead th').forEach((header, column) => {
    const label = header.textContent.trim();
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'table-sort-button';
    button.textContent = label;
    button.setAttribute('aria-label', `Sort by ${label}`);
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
      rows.forEach((row) => body.append(row));
    });
  });
}
