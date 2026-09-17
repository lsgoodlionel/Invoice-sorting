import { describe, expect, test } from 'vitest';
import type { ImportSession } from '../api/types';
import { makeAttachment, makeCandidate, makeEvidence, makeGroup, makeInvoice, makeSession } from '../test/fixtures';
import {
  buildConfirmInput,
  effectiveKind,
  groupAttachments,
  groupProblems,
  groupTitle,
  importGroupsReducer,
  initImportGroups,
  invoiceCount,
  operationOptions,
  operationValue,
  parseOperationValue,
  tallyGroups,
  type ImportGroupsState,
} from './importGroups';

const invoiceA = makeAttachment({ id: 1, expense_id: null, invoice: makeInvoice({ invoice_no: 'A' }) });
const orderA = makeAttachment({ id: 2, expense_id: null, kind: 'order', kind_label: '订单明细', evidence: makeEvidence({ doc_type: 'order', currency: 'CNY', amount_cents: 45900, cny_cents: 45900, merchant: '京东', item_name: '升降桌', is_foreign: false }) });
const invoiceB = makeAttachment({ id: 3, expense_id: null, invoice: makeInvoice({ invoice_no: 'B' }) });
const foreignOrder = makeAttachment({ id: 4, expense_id: null, kind: 'order', evidence: makeEvidence() });
const bankTx = makeAttachment({ id: 5, expense_id: null, kind: 'payment', evidence: makeEvidence({ doc_type: 'payment', currency: 'CNY', amount_cents: 14426, cny_cents: 14426, merchant: 'PP*APPLE.COM', item_name: '' }) });

const match = makeCandidate({ expense_id: 12, merchant: 'Claude Pro 5月', amount_cents: 14426, score: 90, reasons: ['文件名一致'] });

const session: ImportSession = makeSession({
  groups: [
    makeGroup({ group_id: 'g1', attachments: [invoiceA, orderA], link_reasons: ['订单号一致'] }),
    makeGroup({
      group_id: 'g2',
      attachments: [foreignOrder, bankTx],
      summary: { spent_on: '2026-06-28', amount_cents: 14426, currency: 'USD', original_amount_cents: 2000, merchant: 'Apple', summary: 'Claude Pro', category_id: 2, is_online: true, invoice_exempt: true },
      match,
      candidates: [makeCandidate({ expense_id: 13, merchant: 'ChatGPT', score: 60 })],
      suggested_action: 'attach',
    }),
    makeGroup({ group_id: 'g3', attachments: [invoiceB], suggested_action: 'skip', warnings: ['可能重复'] }),
  ],
});

const apply = (state: ImportGroupsState, ...actions: Parameters<typeof importGroupsReducer>[1][]) =>
  actions.reduce(importGroupsReducer, state);

const group = (state: ImportGroupsState, id: string) => {
  const found = state.groups.find((item) => item.groupId === id);
  if (!found) throw new Error(`no group ${id}`);
  return found;
};

describe('initImportGroups', () => {
  test('creates one draft per group with summary fields and suggested operation', () => {
    const state = initImportGroups(session);
    expect(state.groups.map((g) => g.groupId)).toEqual(['g1', 'g2', 'g3']);
    expect(group(state, 'g1')).toMatchObject({
      attachmentIds: [1, 2], operation: { type: 'create' }, spentOn: '2026-09-15', amountCents: 96000,
      currency: 'CNY', originalAmountCents: null, merchant: '京东某店', categoryId: 1, projectId: null, linkReasons: ['订单号一致'],
    });
    expect(group(state, 'g2')).toMatchObject({ operation: { type: 'candidate', expenseId: 12 }, currency: 'USD', originalAmountCents: 2000, invoiceExempt: true, isOnline: true });
    expect(group(state, 'g3').operation).toEqual({ type: 'skip' });
    expect(state.kinds).toEqual({});
    expect(groupAttachments(state, group(state, 'g2')).map((a) => a.id)).toEqual([4, 5]);
  });

  test('attach suggestion without match falls back to first candidate, then search', () => {
    const withCandidate = initImportGroups(makeSession({ groups: [makeGroup({ suggested_action: 'attach', candidates: [makeCandidate({ expense_id: 8 })] })] }));
    expect(withCandidate.groups[0].operation).toEqual({ type: 'candidate', expenseId: 8 });
    const bare = initImportGroups(makeSession({ groups: [makeGroup({ suggested_action: 'attach' })] }));
    expect(bare.groups[0].operation).toEqual({ type: 'search', expenseId: null });
  });

  test('reset replaces state with a new session', () => {
    const state = apply(initImportGroups(session), { type: 'reset', session: makeSession() });
    expect(state.groups.map((g) => g.groupId)).toEqual(['g1']);
  });
});

describe('field and operation updates', () => {
  test('updateFields is immutable and only touches the target group', () => {
    const state = initImportGroups(session);
    const next = apply(state, { type: 'updateFields', groupId: 'g1', patch: { merchant: '江苏京东', projectId: 3 } });
    expect(group(next, 'g1')).toMatchObject({ merchant: '江苏京东', projectId: 3 });
    expect(group(state, 'g1').merchant).toBe('京东某店');
    expect(group(next, 'g2')).toBe(group(state, 'g2'));
  });

  test('switching currency to CNY clears original amount', () => {
    const next = apply(initImportGroups(session), { type: 'updateFields', groupId: 'g2', patch: { currency: 'CNY' } });
    expect(group(next, 'g2')).toMatchObject({ currency: 'CNY', originalAmountCents: null });
  });

  test('setOperation changes the chosen action', () => {
    const next = apply(initImportGroups(session), { type: 'setOperation', groupId: 'g1', operation: { type: 'search', expenseId: 99 } });
    expect(group(next, 'g1').operation).toEqual({ type: 'search', expenseId: 99 });
  });

  test('unknown group ids leave state unchanged', () => {
    const state = initImportGroups(session);
    expect(apply(state, { type: 'updateFields', groupId: 'nope', patch: { merchant: 'x' } }).groups).toEqual(state.groups);
  });
});

describe('kinds', () => {
  test('setKind records changes and removes them when reverted', () => {
    const state = initImportGroups(session);
    const changed = apply(state, { type: 'setKind', attachmentId: 2, kind: 'payment' });
    expect(changed.kinds).toEqual({ 2: 'payment' });
    expect(effectiveKind(changed, 2)).toBe('payment');
    expect(state.kinds).toEqual({});
    expect(apply(changed, { type: 'setKind', attachmentId: 2, kind: 'order' }).kinds).toEqual({});
  });

  test('changing a file to invoice counts toward the multi-invoice check', () => {
    const state = apply(initImportGroups(session), { type: 'setKind', attachmentId: 2, kind: 'invoice' });
    expect(invoiceCount(state, group(state, 'g1'))).toBe(2);
    expect(groupProblems(state, group(state, 'g1'))).toContain('一组最多一张发票，请把多余的发票移到其他组或拆为单独一组');
  });
});

describe('moving and splitting files', () => {
  test('moveAttachment moves a file and drops the emptied group', () => {
    const state = initImportGroups(session);
    const next = apply(state, { type: 'moveAttachment', attachmentId: 3, targetGroupId: 'g1' });
    expect(next.groups.map((g) => g.groupId)).toEqual(['g1', 'g2']);
    expect(group(next, 'g1').attachmentIds).toEqual([1, 2, 3]);
    expect(invoiceCount(next, group(next, 'g1'))).toBe(2);
    expect(group(state, 'g1').attachmentIds).toEqual([1, 2]);
  });

  test('moveAttachment to own group or unknown group is a no-op', () => {
    const state = initImportGroups(session);
    expect(apply(state, { type: 'moveAttachment', attachmentId: 1, targetGroupId: 'g1' })).toBe(state);
    expect(apply(state, { type: 'moveAttachment', attachmentId: 1, targetGroupId: 'zzz' })).toBe(state);
  });

  test('splitAttachment creates a new create-group after the source with fields from the file', () => {
    const next = apply(initImportGroups(session), { type: 'splitAttachment', attachmentId: 5 });
    expect(next.groups.map((g) => g.groupId)).toEqual(['g1', 'g2', 'split-1', 'g3']);
    expect(group(next, 'g2').attachmentIds).toEqual([4]);
    expect(group(next, 'split-1')).toMatchObject({
      attachmentIds: [5], operation: { type: 'create' }, spentOn: '2026-06-28', amountCents: 14426, currency: 'CNY',
      merchant: 'PP*APPLE.COM', categoryId: 2, isOnline: true, invoiceExempt: true, match: null, candidates: [], linkReasons: [],
    });
    const again = apply(next, { type: 'splitAttachment', attachmentId: 2 });
    expect(group(again, 'split-2')).toMatchObject({ attachmentIds: [2], amountCents: 45900, merchant: '京东', summary: '升降桌', invoiceExempt: false });
  });

  test('split of an invoice uses invoice fields; single-file group split is a no-op', () => {
    const state = initImportGroups(session);
    const next = apply(state, { type: 'splitAttachment', attachmentId: 1 });
    expect(group(next, 'split-1')).toMatchObject({ spentOn: '2026-09-15', amountCents: 96000, merchant: '京东某店', summary: '鼠标', currency: 'CNY' });
    expect(apply(state, { type: 'splitAttachment', attachmentId: 3 })).toBe(state);
    expect(apply(state, { type: 'splitAttachment', attachmentId: 404 })).toBe(state);
  });

  test('foreign order split keeps original currency amount', () => {
    const next = apply(initImportGroups(session), { type: 'splitAttachment', attachmentId: 4 });
    expect(group(next, 'split-1')).toMatchObject({ currency: 'USD', originalAmountCents: 2000, amountCents: null, invoiceExempt: true });
    expect(groupProblems(next, group(next, 'split-1'))).toEqual(['请填写人民币金额']);
  });
});

describe('validation and tally', () => {
  test('create requires date and amount; search requires a target; skip is lenient', () => {
    const state = apply(
      initImportGroups(session),
      { type: 'updateFields', groupId: 'g1', patch: { spentOn: null, amountCents: null } },
      { type: 'setOperation', groupId: 'g2', operation: { type: 'search', expenseId: null } },
      { type: 'updateFields', groupId: 'g3', patch: { amountCents: null } },
    );
    expect(groupProblems(state, group(state, 'g1'))).toEqual(['请填写日期', '请填写人民币金额']);
    expect(groupProblems(state, group(state, 'g2'))).toEqual(['请选择要挂到的记录']);
    expect(groupProblems(state, group(state, 'g3'))).toEqual([]);
    expect(tallyGroups(state)).toEqual({ total: 3, create: 1, attach: 1, skip: 1, invalid: 2 });
  });

  test('tally counts candidate and search as attach', () => {
    expect(tallyGroups(initImportGroups(session))).toEqual({ total: 3, create: 1, attach: 1, skip: 1, invalid: 0 });
  });
});

describe('operation select helpers', () => {
  test('encode and decode operation values', () => {
    expect(operationValue({ type: 'create' })).toBe('create');
    expect(operationValue({ type: 'candidate', expenseId: 12 })).toBe('expense:12');
    expect(operationValue({ type: 'search', expenseId: 5 })).toBe('search');
    expect(parseOperationValue('skip')).toEqual({ type: 'skip' });
    expect(parseOperationValue('expense:12')).toEqual({ type: 'candidate', expenseId: 12 });
    expect(parseOperationValue('search')).toEqual({ type: 'search', expenseId: null });
    expect(parseOperationValue('expense:abc')).toBeNull();
    expect(parseOperationValue('bogus')).toBeNull();
  });

  test('options list create, match, candidates, search and skip', () => {
    const state = initImportGroups(session);
    expect(operationOptions(group(state, 'g2')).map((o) => o.value)).toEqual(['create', 'expense:12', 'expense:13', 'search', 'skip']);
    expect(operationOptions(group(state, 'g2'))[1].label).toBe('挂到 #12 Claude Pro 5月 ¥144.26 · 90 分 · 文件名一致');
    expect(operationOptions(group(state, 'g1')).map((o) => o.label)).toEqual(['新建记录', '搜索其他记录…', '留在待归属']);
  });
});

describe('buildConfirmInput', () => {
  test('uses current grouping, kinds and per-action fields', () => {
    const state = apply(
      initImportGroups(session),
      { type: 'setKind', attachmentId: 2, kind: 'payment' },
      { type: 'updateFields', groupId: 'g1', patch: { merchant: ' 江苏京东 ', summary: ' 升降桌 ', projectId: 3, isOnline: true } },
      { type: 'setOperation', groupId: 'g2', operation: { type: 'candidate', expenseId: 13 } },
      { type: 'setKind', attachmentId: 3, kind: 'other' },
    );
    expect(buildConfirmInput(state)).toEqual({
      groups: [
        {
          group_id: 'g1', attachment_ids: [1, 2], kinds: { 2: 'payment' }, action: 'create',
          spent_on: '2026-09-15', amount_cents: 96000, currency: 'CNY', original_amount_cents: null,
          merchant: '江苏京东', summary: '升降桌', category_id: 1, project_id: 3, is_online: true, invoice_exempt: false,
        },
        { group_id: 'g2', attachment_ids: [4, 5], action: 'attach', expense_id: 13 },
        { group_id: 'g3', attachment_ids: [3], action: 'skip' },
      ],
    });
  });

  test('foreign create keeps original amount; search attach uses selected id; moved files follow', () => {
    const state = apply(
      initImportGroups(session),
      { type: 'setOperation', groupId: 'g2', operation: { type: 'create' } },
      { type: 'setOperation', groupId: 'g1', operation: { type: 'search', expenseId: 77 } },
      { type: 'moveAttachment', attachmentId: 3, targetGroupId: 'g2' },
    );
    const [g1, g2] = buildConfirmInput(state).groups;
    expect(g1).toEqual({ group_id: 'g1', attachment_ids: [1, 2], action: 'attach', expense_id: 77 });
    expect(g2).toMatchObject({ group_id: 'g2', attachment_ids: [4, 5, 3], action: 'create', currency: 'USD', original_amount_cents: 2000, amount_cents: 14426, invoice_exempt: true });
  });
});

describe('groupTitle', () => {
  test('uses index, merchant or first file name', () => {
    const state = initImportGroups(session);
    expect(groupTitle(state, group(state, 'g1'), 0)).toBe('组 1 · 京东某店');
    const blank = apply(state, { type: 'updateFields', groupId: 'g1', patch: { merchant: ' ' } });
    expect(groupTitle(blank, group(blank, 'g1'), 0)).toBe('组 1 · 发票_123.pdf');
  });
});
