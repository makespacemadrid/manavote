export function initializeAdminTabs() {
  const page = document.querySelector('.admin-page');
  if (!page) return;
  const sections = {
    members: ['add-member', 'registration-settings', 'members', 'stats', 'poll-stats'],
    budget: ['thresholds', 'budget', 'budget-history', 'proposal-history'],
    polls: ['polls'], group_purchases: ['group-purchases'], coins: ['coins'],
    errors: ['errors'], feedback: ['feedback'], settings: ['settings', 'timezone', 'backup', 'telegram'],
  };
  const active = () => {
    const url = new URL(window.location.href);
    return [url.hash.slice(1), url.searchParams.get('tab'), page.dataset.defaultTab, 'members'].find((key) => Object.hasOwn(sections, key));
  };
  const show = (key) => {
    page.querySelectorAll('.card').forEach((card) => { card.hidden = !sections[key].includes(card.id); });
    page.querySelectorAll('.admin-tab-btn').forEach((button) => {
      button.classList.toggle('active', button.dataset.section === key);
      if (button.dataset.section === key) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');
    });
  };
  const navigate = () => show(active());
  page.querySelectorAll('.admin-tab-btn').forEach((button) => button.addEventListener('click', (event) => {
    event.preventDefault();
    const url = new URL(window.location.href);
    url.searchParams.set('tab', button.dataset.section);
    url.hash = button.dataset.section;
    window.history.pushState(null, '', url);
    navigate();
  }));
  window.addEventListener('popstate', navigate);
  window.addEventListener('hashchange', navigate);
  page.querySelectorAll('form').forEach((form) => form.addEventListener('submit', (event) => {
    let field = form.querySelector('input[name="tab"]');
    if (!field) { field = document.createElement('input'); field.type = 'hidden'; field.name = 'tab'; form.append(field); }
    field.value = active();
    if (event.submitter?.hasAttribute('data-feedback-delete')) {
      event.preventDefault();
      window.confirmDangerAction(form, event.submitter.textContent.trim() + '?');
    }
  }));
  navigate();
}
