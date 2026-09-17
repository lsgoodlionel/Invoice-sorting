import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import type { ExportRecord } from '../../api/types';
import { mockFetch } from '../../test/fetchMock';
import { makeBatch, makeExpense } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { ExportSection } from './ExportSection';

const record: ExportRecord = {
  id: 8,
  layout: 'by_kind',
  file_name: '报销资料_9月第1批_20260917_140000.zip',
  url: '/api/exports/8/file',
  sha256: 'abc',
  item_count: 1,
  total_cents: 96000,
  created_at: '2026-09-17T14:00:00+08:00',
  created_by: null,
};

describe('ExportSection', () => {
  test('explains the selected layout', async () => {
    const user = userEvent.setup();
    mockFetch({});
    renderWithProviders(<ExportSection batch={makeBatch({ item_count: 1, expenses: [makeExpense()] })} />);
    expect(screen.getByText(/一笔支出的材料放在一个文件夹/)).toBeInTheDocument();
    await user.click(screen.getByRole('radio', { name: '按材料类型分组' }));
    expect(screen.getByText(/同类材料放在一起/)).toBeInTheDocument();
  });

  test('deletes an exported package after confirmation', async () => {
    const user = userEvent.setup();
    const { calls } = mockFetch({ 'DELETE /api/exports/8': null });
    const batch = makeBatch({ item_count: 1, expenses: [makeExpense()], exports: [record] });
    renderWithProviders(<ExportSection batch={batch} />);

    await user.click(screen.getByRole('button', { name: `删除资料包 ${record.file_name}` }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/文件将被永久删除/)).toBeInTheDocument();
    expect(calls.find((call) => call.method === 'DELETE')).toBeUndefined();
    await user.click(within(dialog).getByRole('button', { name: '删除' }));

    await waitFor(() => expect(calls.find((call) => call.method === 'DELETE')?.url).toBe('/api/exports/8'));
  });

  test('shows who generated each package', () => {
    mockFetch({});
    const batch = makeBatch({ item_count: 1, expenses: [makeExpense()], exports: [{ ...record, created_by: { id: 2, display_name: '张三' } }] });
    renderWithProviders(<ExportSection batch={batch} />);
    expect(screen.getByRole('columnheader', { name: '生成人' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '张三' })).toBeInTheDocument();
  });
});
