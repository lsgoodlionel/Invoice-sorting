import { describe, expect, test } from 'vitest';
import { makeExpense } from '../test/fixtures';
import {
  UNCATEGORIZED,
  batchCategoryOptions,
  batchStatusOptions,
  filterBatchExpenses,
} from './batchExpenseFilters';

const expenses = [
  makeExpense({ id: 1, category_id: 2, category_name: '办公', status: 'complete' }),
  makeExpense({ id: 2, category_id: 3, category_name: '差旅', status: 'invoiced' }),
  makeExpense({ id: 3, category_id: null, category_name: null, status: 'complete' }),
  makeExpense({ id: 4, category_id: 2, category_name: '办公', status: 'sent' }),
];

const ids = (list: readonly { id: number }[]) => list.map((item) => item.id);

describe('filterBatchExpenses', () => {
  test('no filters keeps all', () => {
    expect(ids(filterBatchExpenses(expenses, { category: null, statuses: [] }))).toEqual([1, 2, 3, 4]);
  });

  test('filters by category, including uncategorized', () => {
    expect(ids(filterBatchExpenses(expenses, { category: '2', statuses: [] }))).toEqual([1, 4]);
    expect(ids(filterBatchExpenses(expenses, { category: UNCATEGORIZED, statuses: [] }))).toEqual([3]);
  });

  test('filters by any of the selected statuses and combines with category', () => {
    expect(ids(filterBatchExpenses(expenses, { category: null, statuses: ['complete', 'sent'] }))).toEqual([1, 3, 4]);
    expect(ids(filterBatchExpenses(expenses, { category: '2', statuses: ['complete'] }))).toEqual([1]);
  });
});

describe('options', () => {
  test('category options come from the batch, deduplicated, uncategorized last', () => {
    expect(batchCategoryOptions(expenses)).toEqual([
      { value: '2', label: '办公' },
      { value: '3', label: '差旅' },
      { value: UNCATEGORIZED, label: '未分类' },
    ]);
  });

  test('status options follow the workflow order and only include present statuses', () => {
    expect(batchStatusOptions(expenses)).toEqual([
      { value: 'invoiced', label: '已开票' },
      { value: 'complete', label: '凭证齐全' },
      { value: 'sent', label: '已外发' },
    ]);
  });
});
