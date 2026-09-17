import { describe, expect, test } from 'vitest';
import { makeImportRow } from '../test/fixtures';
import { draftFromRow, draftProblems, draftsFromSession, tallyDrafts, toConfirmRow, updateDraft } from './importRows';

describe('import drafts', () => {
  test('defaults to attach when matched, create otherwise', () => {
    const matched = draftFromRow(makeImportRow({ match: { expense_id: 5, merchant: 'x', amount_cents: 1, spent_on: '2026-09-01' } }));
    expect(matched).toMatchObject({ action: 'attach', matchExpenseId: 5 });
    expect(draftFromRow(makeImportRow()).action).toBe('create');
  });

  test('updateDraft is immutable', () => {
    const drafts = draftsFromSession({ session_id: 's', rows: [makeImportRow(), makeImportRow({ row_id: 'r2' })], attachments: [], duplicates: [], errors: [], notices: [] });
    const next = updateDraft(drafts, 'r2', { categoryId: 9 });
    expect(next[1].categoryId).toBe(9);
    expect(drafts[1].categoryId).toBe(1);
    expect(next[0]).toBe(drafts[0]);
  });

  test('validation problems', () => {
    const base = draftFromRow(makeImportRow());
    expect(draftProblems(base)).toEqual([]);
    expect(draftProblems({ ...base, spentOn: null, amountCents: null, merchant: ' ' })).toEqual(['缺少日期', '缺少金额', '缺少销售方']);
    expect(draftProblems({ ...base, action: 'attach', matchExpenseId: null })).toEqual(['缺少目标支出']);
    expect(draftProblems({ ...base, action: 'skip', amountCents: null })).toEqual([]);
  });

  test('toConfirmRow builds contract payload', () => {
    const base = draftFromRow(makeImportRow({ match: { expense_id: 5, merchant: 'x', amount_cents: 1, spent_on: '2026-09-01' } }));
    expect(toConfirmRow({ ...base, merchant: ' 京东 ', projectId: 3 })).toEqual({
      row_id: 'r1', action: 'attach', expense_id: 5, spent_on: '2026-09-15', amount_cents: 96000,
      merchant: '京东', summary: '鼠标', category_id: 1, project_id: 3,
    });
    const skipped = toConfirmRow({ ...base, action: 'skip', spentOn: null, amountCents: null });
    expect(skipped).toMatchObject({ action: 'skip', spent_on: '', amount_cents: 0 });
    expect(skipped).not.toHaveProperty('expense_id');
  });

  test('isOnline defaults from suggestion and is sent only for create rows', () => {
    const online = draftFromRow(makeImportRow({ suggested: { ...makeImportRow().suggested, is_online: true } }));
    expect(online.isOnline).toBe(true);
    expect(toConfirmRow(online)).toMatchObject({ action: 'create', is_online: true });
    expect(toConfirmRow({ ...online, isOnline: false })).toMatchObject({ is_online: false });
    expect(toConfirmRow({ ...online, action: 'skip' })).not.toHaveProperty('is_online');
    const matched = draftFromRow(makeImportRow({ match: { expense_id: 5, merchant: 'x', amount_cents: 1, spent_on: '2026-09-01' } }));
    expect(toConfirmRow(matched)).not.toHaveProperty('is_online');
  });

  test('tallyDrafts counts actions and invalid rows', () => {
    const base = draftFromRow(makeImportRow());
    expect(tallyDrafts([base, { ...base, action: 'skip' }, { ...base, merchant: '' }])).toEqual({ create: 2, attach: 0, skip: 1, invalid: 1 });
  });
});
