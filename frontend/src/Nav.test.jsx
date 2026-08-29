import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { Nav } from './Nav.jsx';

const props = {
  username: {
    label: 'Logged in as',
    value: 'Ada',
    toggleLabel: 'Toggle navigation',
    navigationLabel: 'Primary navigation',
  },
  currentPath: '/proposals',
  links: [
    { href: '/proposals', label: 'Proposals' },
    { action: 'feedback', label: 'Feedback' },
  ],
};

describe('Nav', () => {
  it('renders accessible navigation and identifies the current page', () => {
    const html = renderToStaticMarkup(<Nav {...props} />);

    expect(html).toContain('Ada');
    expect(html).toContain('aria-label="Primary navigation"');
    expect(html).toContain('aria-controls="primary-navigation"');
    expect(html).toContain('aria-current="page"');
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain('class="nav-feedback"');
    expect(html).toContain('aria-haspopup="dialog"');
  });
});
