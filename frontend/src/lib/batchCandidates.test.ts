import { describe, expect, test } from 'vitest';
import { makeExpense } from '../test/fixtures';
import { filterBatchCandidates, selectableExpenses } from './batchCandidates';

const items = [
  makeExpense({ id: 1, merchant: '京东某店', summary: '鼠标', project_id: 7 }),
  makeExpense({ id: 2, merchant: '腾讯云', summary: '服务器', project_id: 8, invoice_no: '2644000001' }),
  makeExpense({ id: 3, merchant: '作废店', project_id: 7, status: 'void' }),
  makeExpense({ id: 4, merchant: '顺丰', summary: '快递', project_id: null }),
];

describe('batch candidates', () => {
  test('excludes void expenses', () => {
    expect(selectableExpenses(items).map((e) => e.id)).toEqual([1, 2, 4]);
  });

  test('limits to batch project unless showing all projects', () => {
    const candidates = selectableExpenses(items);
    expect(filterBatchCandidates(candidates, { projectId: 7, showAllProjects: false, search: '' }).map((e) => e.id)).toEqual([1]);
    expect(filterBatchCandidates(candidates, { projectId: 7, showAllProjects: true, search: '' }).map((e) => e.id)).toEqual([1, 2, 4]);
    expect(filterBatchCandidates(candidates, { projectId: null, showAllProjects: false, search: '' }).map((e) => e.id)).toEqual([1, 2, 4]);
  });

  test('searches merchant, summary and invoice number case-insensitively', () => {
    const candidates = selectableExpenses(items);
    const run = (search: string) =>
      filterBatchCandidates(candidates, { projectId: null, showAllProjects: false, search }).map((e) => e.id);
    expect(run('快递')).toEqual([4]);
    expect(run(' 腾讯 ')).toEqual([2]);
    expect(run('26440')).toEqual([2]);
    expect(run('none')).toEqual([]);
  });
});
