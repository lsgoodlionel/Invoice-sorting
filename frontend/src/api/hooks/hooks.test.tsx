import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, test } from 'vitest';
import { mockFetch } from '../../test/fetchMock';
import { makeDetail } from '../../test/fixtures';
import { createTestClient, TestProviders } from '../../test/render';
import { useAttachmentCandidates, useDeleteAttachment, useSetChecklistState, useUnassignedAttachments, useUpdateAttachment } from './attachments';
import {
  useBatch, useBatchItems, useBatchList, useCreateBatch, useDeleteBatch, useExportBatch,
  useMarkBatchReceived, useMarkBatchSent, useUpdateBatch,
} from './batches';
import { useDashboard } from './dashboard';
import {
  useCreateExpense, useDeleteExpense, useExpense, useExpenseList, useExpenseSearch,
  useSetExpenseStatus, useUpdateExpense, useUploadExpenseAttachments, useUploadToExpense,
} from './expenses';
import { useConfirmImport } from './imports';
import { queryKeys } from './keys';
import {
  useArchiveCategory, useCategories, useChecklistRules, useDeactivateProject, useProjects,
  useRemoveRule, useSaveCategory, useSaveProject, useSaveRule, useSettings, useUpdateSettings,
} from './settings';
import { useStats } from './stats';

const detail = makeDetail({ id: 1 });

function setup() {
  const client = createTestClient();
  const wrapper = ({ children }: { children: ReactNode }) => <TestProviders client={client}>{children}</TestProviders>;
  return { client, wrapper };
}

describe('query hooks', () => {
  test('load data from endpoints', async () => {
    mockFetch({
      'GET /api/expenses': { items: [detail], total: 1, total_cents: 96000, status_counts: {} },
      'GET /api/expenses/1': detail,
      'GET /api/attachments/unassigned': [],
      'GET /api/attachments/2/candidates': [{ expense_id: 7 }],
      'GET /api/batches': [],
      'GET /api/batches/2': { id: 2 },
      'GET /api/dashboard': { missing: [] },
      'GET /api/settings': { overdue_days: 30 },
      'GET /api/categories': [],
      'GET /api/projects': [],
      'GET /api/checklist-rules': [],
      'GET /api/stats': { rows: [] },
    });
    const { wrapper } = setup();
    const { result } = renderHook(
      () => ({
        list: useExpenseList({}),
        search: useExpenseSearch('京'),
        one: useExpense(1),
        none: useExpense(null),
        unassigned: useUnassignedAttachments(),
        candidates: useAttachmentCandidates(2, true),
        lazyCandidates: useAttachmentCandidates(3, false),
        batches: useBatchList(),
        batch: useBatch(2),
        dashboard: useDashboard(),
        settings: useSettings(),
        categories: useCategories(),
        projects: useProjects(),
        rules: useChecklistRules(),
        stats: useStats({ start: '2026-01-01', end: '2026-12-31', date_basis: 'spent', group_by: 'category' }),
      }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.stats.isSuccess).toBe(true));
    await waitFor(() => expect(result.current.search.data).toHaveLength(1));
    expect(result.current.list.data?.total).toBe(1);
    expect(result.current.one.data?.id).toBe(1);
    expect(result.current.none.fetchStatus).toBe('idle');
    expect(result.current.batch.data).toEqual({ id: 2 });
    await waitFor(() => expect(result.current.candidates.data).toEqual([{ expense_id: 7 }]));
    expect(result.current.lazyCandidates.fetchStatus).toBe('idle');
    expect(result.current.settings.data?.overdue_days).toBe(30);
  });
});

describe('mutation hooks', () => {
  test('expense mutations write detail into cache', async () => {
    const { calls } = mockFetch({
      'POST /api/expenses': detail,
      'PATCH /api/expenses/1': detail,
      'POST /api/expenses/1/status': detail,
      'POST /api/expenses/1/attachments': detail,
      'DELETE /api/expenses/1': null,
      'PATCH /api/checklist-items/5': detail,
      'PATCH /api/attachments/9': {},
      'DELETE /api/attachments/9': null,
      'POST /api/imports/s/confirm': { created: [], attached: [], skipped: 0 },
    });
    const { client, wrapper } = setup();
    const { result } = renderHook(
      () => ({
        create: useCreateExpense(), update: useUpdateExpense(1), status: useSetExpenseStatus(1),
        upload: useUploadExpenseAttachments(1), uploadTo: useUploadToExpense(), remove: useDeleteExpense(), checklist: useSetChecklistState(),
        updateAttachment: useUpdateAttachment(), deleteAttachment: useDeleteAttachment(),
        confirm: useConfirmImport(),
      }),
      { wrapper },
    );
    await act(async () => {
      await result.current.create.mutateAsync({ spent_on: '2026-09-01', amount_cents: 1, merchant: 'x' });
      await result.current.update.mutateAsync({ note: 'x' });
      await result.current.status.mutateAsync({ status: null });
      await result.current.upload.mutateAsync({ files: [new File(['a'], 'a.pdf')], kind: 'order' });
      await result.current.uploadTo.mutateAsync({ id: 1, files: [new File(['b'], 'b.png')] });
      await result.current.remove.mutateAsync(1);
      await result.current.checklist.mutateAsync({ id: 5, state: 'not_needed' });
      await result.current.updateAttachment.mutateAsync({ id: 9, patch: { kind: 'order' } });
      await result.current.deleteAttachment.mutateAsync(9);
      await result.current.confirm.mutateAsync({ sessionId: 's', input: { groups: [] } });
    });
    expect(client.getQueryData(queryKeys.expense(1))).toEqual(detail);
    expect(calls.map((c) => c.method)).toContain('DELETE');
  });

  test('batch and settings mutations', async () => {
    const { calls } = mockFetch({
      'POST /api/batches': { id: 3 }, 'PATCH /api/batches/3': {}, 'DELETE /api/batches/3': null,
      'POST /api/batches/3/items': {}, 'POST /api/batches/3/export': {}, 'POST /api/batches/3/sent': {},
      'POST /api/batches/3/received': {}, 'PUT /api/settings': {},
      'POST /api/categories': {}, 'PATCH /api/categories/1': {}, 'DELETE /api/categories/1': null,
      'POST /api/projects': {}, 'PATCH /api/projects/1': {}, 'DELETE /api/projects/1': null,
      'POST /api/checklist-rules': {}, 'PATCH /api/checklist-rules/1': {}, 'DELETE /api/checklist-rules/1': null,
    });
    const { wrapper } = setup();
    const { result } = renderHook(
      () => ({
        create: useCreateBatch(), update: useUpdateBatch(3), remove: useDeleteBatch(), items: useBatchItems(),
        exportZip: useExportBatch(3), sent: useMarkBatchSent(3), received: useMarkBatchReceived(3),
        settings: useUpdateSettings(), saveCategory: useSaveCategory(), archive: useArchiveCategory(),
        saveProject: useSaveProject(), deactivate: useDeactivateProject(), saveRule: useSaveRule(), removeRule: useRemoveRule(),
      }),
      { wrapper },
    );
    const rule = { category_id: null, attachment_kind: 'invoice' as const, level: 'required' as const, condition: {}, hint: '' };
    await act(async () => {
      const r = result.current;
      await r.create.mutateAsync({ name: 'b' });
      await r.update.mutateAsync({ name: 'c' });
      await r.items.mutateAsync({ id: 3, change: { remove: [1] } });
      await r.exportZip.mutateAsync('by_expense');
      await r.sent.mutateAsync({ sent_on: '2026-09-01' });
      await r.received.mutateAsync({ received_on: '2026-09-02' });
      await r.remove.mutateAsync(3);
      await r.settings.mutateAsync({ overdue_days: 10 });
      await r.saveCategory.mutateAsync({ id: null, input: { name: 'c' } });
      await r.saveCategory.mutateAsync({ id: 1, input: { name: 'c' } });
      await r.archive.mutateAsync(1);
      await r.saveProject.mutateAsync({ id: null, input: { name: 'p' } });
      await r.saveProject.mutateAsync({ id: 1, input: { name: 'p', active: true } });
      await r.deactivate.mutateAsync(1);
      await r.saveRule.mutateAsync({ id: null, input: rule });
      await r.saveRule.mutateAsync({ id: 1, input: rule });
      await r.removeRule.mutateAsync(1);
    });
    expect(calls).toHaveLength(17);
  });
});
