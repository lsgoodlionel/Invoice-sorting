import { describe, expect, test } from 'vitest';
import { mockFetch } from '../../test/fetchMock';
import { attachmentsApi } from './attachments';
import { batchesApi } from './batches';
import { dashboardApi } from './dashboard';
import { expensesApi } from './expenses';
import { importsApi } from './imports';
import { settingsApi } from './settings';
import { statsApi } from './stats';

const any = () => ({ data: {} });

function allRoutes() {
  const keys = [
    'GET /api/expenses', 'POST /api/expenses', 'GET /api/expenses/1', 'PATCH /api/expenses/1', 'DELETE /api/expenses/1',
    'POST /api/expenses/1/status', 'POST /api/expenses/1/attachments',
    'GET /api/attachments/unassigned', 'PATCH /api/attachments/2', 'DELETE /api/attachments/2', 'PATCH /api/checklist-items/3',
    'POST /api/attachments/bulk-delete', 'POST /api/attachments/bulk-assign', 'POST /api/attachments/create-expenses', 'POST /api/attachments/reparse', 'GET /api/attachments/2/candidates',
    'POST /api/imports/start', 'POST /api/imports/s%201/finish', 'POST /api/imports/s%201/confirm',
    'GET /api/batches', 'POST /api/batches', 'GET /api/batches/4', 'PATCH /api/batches/4', 'DELETE /api/batches/4',
    'POST /api/batches/4/items', 'POST /api/batches/4/export', 'POST /api/batches/4/sent', 'POST /api/batches/4/received', 'POST /api/batches/4/reopen', 'DELETE /api/exports/8',
    'GET /api/stats', 'GET /api/dashboard',
    'GET /api/settings', 'PUT /api/settings', 'POST /api/backup',
    'GET /api/categories', 'POST /api/categories', 'PATCH /api/categories/5', 'DELETE /api/categories/5',
    'GET /api/projects', 'POST /api/projects', 'PATCH /api/projects/6', 'DELETE /api/projects/6',
    'GET /api/checklist-rules', 'POST /api/checklist-rules', 'PATCH /api/checklist-rules/7', 'DELETE /api/checklist-rules/7',
  ];
  return Object.fromEntries(keys.map((key) => [key, any]));
}

describe('endpoint functions follow the contract', () => {
  test('expenses', async () => {
    const { calls } = mockFetch(allRoutes());
    await expensesApi.list({ status: ['spent', 'sent'], q: '京东', unbatched: true });
    await expensesApi.get(1);
    await expensesApi.create({ spent_on: '2026-09-01', amount_cents: 100, merchant: 'x' });
    await expensesApi.update(1, { note: 'n' });
    await expensesApi.remove(1);
    await expensesApi.setStatus(1, 'void', '重复');
    await expensesApi.setStatus(1, null);
    await expensesApi.upload(1, [new File(['a'], 'a.png')], 'order');
    await expensesApi.upload(1, [new File(['a'], 'a.png')]);
    expect(calls[0].url).toBe(`/api/expenses?status=spent%2Csent&q=${encodeURIComponent('京东')}&unbatched=true`);
    expect(calls[5].body).toEqual({ status: 'void', note: '重复' });
    expect(calls[6].body).toEqual({ status: null });
    expect((calls[7].body as FormData).get('kind')).toBe('order');
    expect((calls[8].body as FormData).has('kind')).toBe(false);
  });

  test('attachments and checklist', async () => {
    const { calls } = mockFetch(allRoutes());
    await attachmentsApi.unassigned();
    await attachmentsApi.update(2, { expense_id: null });
    await attachmentsApi.remove(2);
    await attachmentsApi.setChecklistState(3, 'not_needed', '线下购买');
    await attachmentsApi.setChecklistState(3, 'missing');
    await attachmentsApi.bulkDelete([1, 2]);
    await attachmentsApi.bulkAssign({ ids: [1], expense_id: 4, kind: 'order' });
    await attachmentsApi.createExpenses([1]);
    await attachmentsApi.reparse([2]);
    await attachmentsApi.candidates(2);
    expect(calls[1].body).toEqual({ expense_id: null });
    expect(calls[3].body).toEqual({ state: 'not_needed', reason: '线下购买' });
    expect(calls[4].body).toEqual({ state: 'missing' });
    expect(calls[5]).toMatchObject({ method: 'POST', url: '/api/attachments/bulk-delete', body: { ids: [1, 2] } });
    expect(calls[6]).toMatchObject({ method: 'POST', url: '/api/attachments/bulk-assign', body: { ids: [1], expense_id: 4, kind: 'order' } });
    expect(calls[7]).toMatchObject({ method: 'POST', url: '/api/attachments/create-expenses', body: { ids: [1] } });
    expect(calls[8]).toMatchObject({ method: 'POST', url: '/api/attachments/reparse', body: { ids: [2] } });
    expect(calls[9]).toMatchObject({ method: 'GET', url: '/api/attachments/2/candidates' });
    expect(attachmentsApi.thumbnailUrl(9)).toBe('/api/attachments/9/thumbnail');
    expect(attachmentsApi.fileUrl(9)).toBe('/api/attachments/9/file');
  });

  test('imports', async () => {
    const { calls } = mockFetch(allRoutes());
    await importsApi.start();
    await importsApi.finish('s 1');
    await importsApi.confirm('s 1', { groups: [{ group_id: 'g1', attachment_ids: [1], action: 'skip' }] });
    expect(calls[0]).toMatchObject({ method: 'POST', url: '/api/imports/start' });
    expect(calls[1]).toMatchObject({ method: 'POST', url: '/api/imports/s%201/finish' });
    expect(calls[2]).toMatchObject({
      method: 'POST',
      url: '/api/imports/s%201/confirm',
      body: { groups: [{ group_id: 'g1', attachment_ids: [1], action: 'skip' }] },
    });
  });

  test('batches', async () => {
    const { calls } = mockFetch(allRoutes());
    await batchesApi.list('draft');
    await batchesApi.get(4);
    await batchesApi.create({ name: 'b' });
    await batchesApi.update(4, { note: 'n' });
    await batchesApi.remove(4);
    await batchesApi.changeItems(4, { add: [1], force: true });
    await batchesApi.exportZip(4, 'by_kind');
    await batchesApi.markSent(4, { sent_on: '2026-09-01' });
    await batchesApi.markReceived(4, { received_on: '2026-09-02', expense_ids: [1] });
    await batchesApi.reopen(4);
    await batchesApi.removeExport(8);
    expect(calls[0].url).toBe('/api/batches?status=draft');
    expect(calls[5].body).toEqual({ add: [1], force: true });
    expect(calls[6].body).toEqual({ layout: 'by_kind' });
    expect(batchesApi.exportFileUrl(8)).toBe('/api/exports/8/file');
    expect(calls.at(-2)?.url).toBe('/api/batches/4/reopen');
    expect(calls.at(-1)).toMatchObject({ method: 'DELETE', url: '/api/exports/8' });
    expect(calls.at(-2)?.method).toBe('POST');
  });

  test('stats, dashboard, settings', async () => {
    const { calls } = mockFetch(allRoutes());
    const query = { start: '2026-01-01', end: '2026-12-31', date_basis: 'spent' as const, group_by: 'month' as const };
    await statsApi.get(query);
    await dashboardApi.get();
    await settingsApi.get();
    await settingsApi.update({ overdue_days: 20 });
    await settingsApi.backup();
    await settingsApi.categories();
    await settingsApi.createCategory({ name: 'c' });
    await settingsApi.updateCategory(5, { name: 'c2' });
    await settingsApi.archiveCategory(5);
    await settingsApi.projects();
    await settingsApi.createProject({ name: 'p' });
    await settingsApi.updateProject(6, { active: true });
    await settingsApi.deactivateProject(6);
    await settingsApi.rules();
    await settingsApi.createRule({ category_id: null, attachment_kind: 'payment', level: 'required', condition: { amount_gte: 100000 }, hint: '' });
    await settingsApi.updateRule(7, { hint: 'h' });
    await settingsApi.removeRule(7);
    expect(calls[0].url).toBe('/api/stats?start=2026-01-01&end=2026-12-31&date_basis=spent&group_by=month');
    expect(statsApi.exportUrl(query)).toBe('/api/stats/export?start=2026-01-01&end=2026-12-31&date_basis=spent&group_by=month');
    expect(calls).toHaveLength(17);
    expect(calls.every((call) => call.url.startsWith('/api/'))).toBe(true);
  });
});
