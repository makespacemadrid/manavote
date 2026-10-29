import { describe, it, expect, vi } from 'vitest';
import { initializeBrowserErrors } from './browserErrors.js';

function setup(enabled = true) {
  const browser = new EventTarget();
  browser.location = { pathname: '/proposals', search: '?private=secret' };
  browser.console = { error: vi.fn() };
  const original = browser.console.error;
  browser.fetch = vi.fn().mockResolvedValue({ ok: true });
  const doc = { querySelector: (selector) => enabled ? { content: selector.includes('endpoint') ? '/diagnostics/browser-errors' : 'csrf-private' } : null };
  initializeBrowserErrors(browser, doc);
  return { browser, original };
}

function emit(browser, type, properties) {
  browser.dispatchEvent(Object.assign(new Event(type), properties));
}

describe('browser diagnostics', () => {
  it('preserves console.error and uploads strings/errors without serializing objects', () => {
    const { browser, original } = setup();
    const object = { password: 'object-secret' }; object.circular = object;
    browser.console.error('failed', new Error('fixture'), object);
    expect(original).toHaveBeenCalledTimes(1);
    const [url, request] = browser.fetch.mock.calls[0];
    expect(url).toBe('/diagnostics/browser-errors');
    expect(request.headers['X-CSRFToken']).toBe('csrf-private');
    const payload = JSON.parse(request.body);
    expect(payload.kind).toBe('console.error');
    expect(payload.message).toContain('Error: fixture');
    expect(payload.stack).toContain('fixture');
    expect(request.body).not.toContain('object-secret');
    expect(payload.page).toBe('/proposals');
  });
  it('captures uncaught errors and promise rejections without suppressing browser behavior', () => {
    const { browser } = setup();
    emit(browser, 'error', { message: 'uncaught', filename: '/app.js', lineno: 2, colno: 3 });
    emit(browser, 'unhandledrejection', { reason: new Error('rejected') });
    expect(JSON.parse(browser.fetch.mock.calls[0][1].body).stack).toBe('/app.js:2:3');
    expect(JSON.parse(browser.fetch.mock.calls[1][1].body).kind).toBe('unhandledrejection');
  });
  it('redacts tokens and URL queries, deduplicates, bounds uploads, and handles failures silently', async () => {
    const { browser } = setup();
    browser.fetch.mockRejectedValue(new Error('offline'));
    browser.console.error('csrf-private password=hidden authorization: Bearer hidden-bearer https://user:pass@example.org/app.js?private=hidden#fragment');
    const payload = JSON.parse(browser.fetch.mock.calls[0][1].body);
    expect(payload.message).not.toContain('hidden');
    expect(payload.message).not.toContain('csrf-private');
    expect(payload.message).not.toContain('user:pass');
    for (let i = 0; i < 30; i++) browser.console.error(`message ${i}`);
    expect(browser.fetch).toHaveBeenCalledTimes(10);
    await Promise.resolve();
    const another = setup().browser;
    another.console.error('same'); another.console.error('same');
    expect(another.fetch).toHaveBeenCalledTimes(1);
  });
  it('does not capture on unsigned pages', () => {
    const { browser, original } = setup(false);
    browser.console.error('public');
    expect(browser.console.error).toBe(original);
    expect(browser.fetch).not.toHaveBeenCalled();
  });
});
