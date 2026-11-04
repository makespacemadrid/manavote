import { describe, it, expect } from 'vitest';
import { DRAFT_TTL, draftStorageKey, validDraft, consumeDraftReceipts } from './drafts.js';

describe('stored drafts', () => {
  const now = 2000000000000;
  const draft = { version: 1, updatedAt: now, fields: { title: [{ value: 'My proposal' }] }, rows: {} };
  it('isolates accounts, forms and edited record identifiers', () => {
    expect(draftStorageKey('1', 'proposal:edit:2')).not.toBe(draftStorageKey('2', 'proposal:edit:2'));
    expect(draftStorageKey('1', 'proposal:edit:2')).not.toBe(draftStorageKey('1', 'proposal:edit:3'));
    expect(draftStorageKey('1:a', 'b')).not.toBe(draftStorageKey('1', 'a:b'));
  });
  it('expires after seven days and rejects invalid/future data', () => {
    expect(validDraft(draft, now)).toBe(true);
    expect(validDraft(draft, now + DRAFT_TTL)).toBe(false);
    expect(validDraft({ ...draft, updatedAt: now + 120000 }, now)).toBe(false);
    for (const fields of [[], { title: ['malformed'] }, { title: [{ value: 'x', checked: 'true' }] }]) {
      expect(validDraft({ ...draft, fields }, now)).toBe(false);
    }
    expect(validDraft({ ...draft, rows: { '#component-rows': 31 } }, now)).toBe(false);
  });
  it('clears only the confirmed submission and preserves newer edits and other accounts', () => {
    const values = new Map();
    const storage = { getItem: key => values.get(key), removeItem: key => values.delete(key) };
    const key = draftStorageKey('1', 'proposal:new');
    const other = draftStorageKey('2', 'proposal:new');
    const receipts = [{ key: 'proposal:new', nonce: 'confirmed' }];
    values.set(key, JSON.stringify({ ...draft, submittedNonce: 'different' }));
    consumeDraftReceipts(storage, '1', receipts);
    expect(values.has(key)).toBe(true);
    values.set(key, JSON.stringify(draft));
    consumeDraftReceipts(storage, '1', receipts);
    expect(values.has(key)).toBe(true);
    values.set(key, JSON.stringify({ ...draft, submittedNonce: 'confirmed' }));
    values.set(other, values.get(key));
    consumeDraftReceipts(storage, '1', receipts);
    expect(values.has(key)).toBe(false);
    expect(values.has(other)).toBe(true);
  });
});
