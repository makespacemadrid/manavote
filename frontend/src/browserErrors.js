// Report diagnostics without serializing console objects, DOM, or form contents.
export function initializeBrowserErrors(browser = window, doc = document) {
  const endpoint = doc.querySelector('meta[name="browser-error-endpoint"]')?.content;
  const csrf = doc.querySelector('meta[name="csrf-token"]')?.content;
  const build = doc.querySelector('meta[name="frontend-build"]')?.content;
  if (!endpoint || !csrf || typeof browser.fetch !== 'function') return;
  let count = 0;
  const seen = new Set();
  const clean = (value, limit) => String(value ?? '')
    .replaceAll(csrf, '[REDACTED]')
    .replace(/https?:\/\/[^\s<>"')]+/g, (url) => {
      try { const parsed = new URL(url); return parsed.origin + parsed.pathname; } catch { return '[URL]'; }
    })
    .replace(/\bBearer\s+[^\s,;}"']+/gi, 'Bearer [REDACTED]')
    .replace(/\b(password|secret|api[_-]?key|token|authorization|cookie)\s*[:=]\s*(?:"[^"]*"|'[^']*'|[^\s,;}]+)/gi, '$1=[REDACTED]')
    .slice(0, limit);
  const describe = (value) => {
    if (value instanceof Error) return `${value.name}: ${value.message}`;
    if (['string', 'number', 'boolean'].includes(typeof value)) return String(value);
    return '[object omitted]';
  };
  const send = (kind, message, stack = '') => {
    try {
      const payload = {
        kind, message: clean(message, 6000), stack: clean(stack, 8000),
        page: browser.location.pathname.slice(0, 300),
        ...(build && /^[a-f0-9]{16}$/.test(build) ? { build } : {}),
      };
      const key = JSON.stringify(payload);
      if (count >= 10 || seen.has(key)) return;
      seen.add(key);
      count += 1;
      // Handle upload failures silently: reporting must never report itself.
      browser.fetch(endpoint, {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: key,
      }).catch(() => {});
    } catch { /* Keep diagnostics from affecting the application. */ }
  };
  const original = browser.console.error;
  browser.console.error = function (...args) {
    original.apply(this, args);
    try {
      send('console.error', args.map(describe).join(' '), args.find((arg) => arg instanceof Error)?.stack);
    } catch { /* Preserve console behavior even for unusual objects. */ }
  };
  browser.addEventListener('error', (event) => {
    try {
      if (!event.message) return; // Resource failures do not carry useful JS diagnostics.
      send('error', event.message, event.error?.stack || `${event.filename || ''}:${event.lineno || 0}:${event.colno || 0}`);
    } catch { /* Ignore objects with throwing diagnostic getters. */ }
  });
  browser.addEventListener('unhandledrejection', (event) => {
    try {
      send('unhandledrejection', describe(event.reason), event.reason instanceof Error ? event.reason.stack : '');
    } catch { /* Ignore objects with throwing diagnostic getters. */ }
  });
}
