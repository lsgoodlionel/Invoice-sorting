import { describe, expect, test } from 'vitest';
import { makeAttachment } from '../test/fixtures';
import { pruneSelection, selectedInvoiceIds, summarizeCreateResult, toggleAllIds, toggleId } from './unassigned';

const items = [
  makeAttachment({ id: 1, kind: 'invoice', expense_id: null }),
  makeAttachment({ id: 2, kind: 'order', expense_id: null }),
  makeAttachment({ id: 3, kind: 'invoice', expense_id: null }),
];

describe('unassigned selection', () => {
  test('toggleId adds and removes without mutating', () => {
    const start = [1];
    expect(toggleId(start, 2)).toEqual([1, 2]);
    expect(toggleId(start, 1)).toEqual([]);
    expect(start).toEqual([1]);
  });

  test('toggleAllIds selects every item or clears', () => {
    expect(toggleAllIds(items, true)).toEqual([1, 2, 3]);
    expect(toggleAllIds(items, false)).toEqual([]);
  });

  test('pruneSelection drops ids that are no longer listed', () => {
    expect(pruneSelection([1, 9, 3], items)).toEqual([1, 3]);
  });

  test('selectedInvoiceIds keeps only invoice attachments', () => {
    expect(selectedInvoiceIds([1, 2, 3], items)).toEqual([1, 3]);
    expect(selectedInvoiceIds([2], items)).toEqual([]);
  });

  test('summarizeCreateResult formats counts', () => {
    expect(summarizeCreateResult({ created: [5, 6], attached: [7], skipped: [{ id: 3, original_name: 'a.pdf', reason: '缺少金额' }] }))
      .toBe('新建 2 条、挂到已有 1 条、跳过 1 条');
  });
});
