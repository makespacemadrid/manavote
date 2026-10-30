import { describe, it, expect } from 'vitest';
import { initializeBudget } from './budget.js';

describe('Budget progressive enhancement', () => {
  it('keeps activity filters working when the chart library is unavailable', () => {
    const buttons = ['all', 'proposal', 'approved', 'budget_in', 'budget_out'].map(filter => ({
      dataset: { filter }, classList: { toggle() {} }, attributes: {},
      setAttribute(key, value) { this.attributes[key] = value; },
      addEventListener(event, callback) { this.click = callback; },
    }));
    const rows = ['proposal', 'approved'].map(category => ({ dataset: { category }, style: {} }));
    const doc = { getElementById: () => ({}), querySelectorAll: selector => selector === '.calendar-row' ? rows : buttons };
    initializeBudget(doc, {});
    buttons[1].click();
    expect(rows[0].style.display).toBe('none');
    expect(rows[1].style.display).toBe('');
    expect(buttons[1].attributes['aria-pressed']).toBe('false');
    buttons[0].click();
    expect(rows[0].style.display).toBe('');
    expect(buttons[0].attributes['aria-pressed']).toBe('true');
  });
});
