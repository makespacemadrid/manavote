import { describe, it, expect } from 'vitest';
import { projectedOrderCents } from './ux.js';

describe('order preview', () => {
  it('replaces the members existing quantity and includes shared costs in the base', () => {
    expect(projectedOrderCents(9500, 3000, 3, 4)).toBe(12500);
    expect(projectedOrderCents(9500, 3000, 3, 5)).toBe(15500);
    expect(projectedOrderCents(9500, 3000, 3, 0)).toBe(500);
  });
  it('keeps decimal prices in exact cents', () => {
    expect(projectedOrderCents(20, 10, 2, 3)).toBe(30);
  });
});
