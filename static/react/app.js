// Development fallback. `npm run build` replaces this file with the React bundle.
for (const nav of document.querySelectorAll('[data-mobile-nav]')) {
  const toggle = nav.querySelector('[data-nav-toggle]');
  toggle?.addEventListener('click', () => {
    const isOpen = nav.classList.toggle('mobile-open');
    toggle.setAttribute('aria-expanded', String(isOpen));
  });
}
