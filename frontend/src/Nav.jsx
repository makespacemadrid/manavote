import { useEffect, useRef, useState } from 'react';

export function Nav({ username, links, currentPath }) {
  const [isOpen, setIsOpen] = useState(false);
  const navRef = useRef(null);

  useEffect(() => {
    // Besides making initialization observable in browser diagnostics, this
    // distinguishes the hydrated component from the no-JavaScript fallback.
    navRef.current?.setAttribute('data-react-hydrated', 'true');

    const closeOnEscape = (event) => {
      if (event.key === 'Escape') setIsOpen(false);
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, []);

  return (
    <nav
      ref={navRef}
      className={`nav${isOpen ? ' mobile-open' : ''}`}
      data-mobile-nav
      aria-label={username.navigationLabel}
    >
      <div className="nav-header">
        <span>{username.label}: <strong>{username.value}</strong></span>
        <button
          className="nav-toggle"
          type="button"
          aria-label={username.toggleLabel}
          aria-expanded={isOpen}
          aria-controls="primary-navigation"
          data-nav-toggle
          onClick={() => setIsOpen((open) => !open)}
        >
          ☰
        </button>
      </div>
      <div className="nav-links" id="primary-navigation" data-nav-links>
        {links.map((link) => (
          <a
            href={link.href}
            key={link.href}
            aria-current={link.href === currentPath ? 'page' : undefined}
            onClick={() => setIsOpen(false)}
          >
            {link.label}
          </a>
        ))}
      </div>
    </nav>
  );
}
