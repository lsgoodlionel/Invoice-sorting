import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import type { RecordedCall } from '../../../test/fetchMock';
import { mockFetch } from '../../../test/fetchMock';
import { makeAttachment, makeExpense, makeInvoice } from '../../../test/fixtures';
import { renderWithProviders } from '../../../test/render';
import { UnassignedSection } from './UnassignedSection';

const invoice = makeAttachment({
  id: 11,
  expense_id: null,
  original_name: '发票A.pdf',
  invoice: makeInvoice({ issued_on: '2026-09-10', seller_name: '北京某书店', total_cents: 12800, region_name: '北京', is_nonlocal: true }),
});
const order = makeAttachment({ id: 12, expense_id: null, kind: 'order', kind_label: '订单明细', original_name: '订单截图.png', mime: 'image/png' });

function setup(extra: Record<string, unknown> = {}) {
  return mockFetch({
    'GET /api/attachments/unassigned': [invoice, order],
    'GET /api/expenses': { items: [makeExpense({ id: 42, merchant: '腾讯云' })], total: 1, total_cents: 96000, status_counts: {} },
    ...extra,
  });
}

const callTo = (calls: RecordedCall[], url: string) => calls.find((c) => c.url === url);

async function renderSection(hasOtherPrimary = false) {
  renderWithProviders(<UnassignedSection hasOtherPrimary={hasOtherPrimary} />);
  await screen.findByText('发票A.pdf');
}

describe('UnassignedSection', () => {
  test('explains unassigned files and shows invoice info with region badge', async () => {
    setup();
    await renderSection();
    expect(screen.getByText(/待归属 = 已导入但还没挂到任何支出记录的文件/)).toBeInTheDocument();
    const row = screen.getByTestId('unassigned-row-11');
    expect(within(row).getByText(/2026-09-10 · 北京某书店 · ¥128.00/)).toBeInTheDocument();
    expect(within(row).getByText('外地·北京')).toBeInTheDocument();
    expect(within(screen.getByTestId('unassigned-row-12')).getByText('—')).toBeInTheDocument();
    expect(screen.queryByText(/已选/)).not.toBeInTheDocument();
  });

  test('bulk actions that need invoices are disabled for non-invoice selection', async () => {
    const user = userEvent.setup();
    setup();
    await renderSection();
    await user.click(screen.getByRole('checkbox', { name: '选择 订单截图.png' }));
    expect(screen.getByText('已选 1 个')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '生成记录' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '重新识别' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '归属到记录…' })).toBeEnabled();
  });

  test('create-expenses sends invoice ids and reports counts with skip reasons', async () => {
    const user = userEvent.setup();
    const { calls } = setup({
      'POST /api/attachments/create-expenses': { created: [], attached: [], skipped: [{ id: 11, original_name: '发票A.pdf', reason: '缺少金额' }] },
    });
    await renderSection();
    await user.click(screen.getByRole('checkbox', { name: '全选' }));
    expect(screen.getByText('已选 2 个')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '生成记录' }));
    await waitFor(() => expect(callTo(calls, '/api/attachments/create-expenses')?.body).toEqual({ ids: [11] }));
    expect(await screen.findByText('新建 0 条、挂到已有 0 条、跳过 1 条')).toBeInTheDocument();
    expect(screen.getByTestId('create-skipped')).toHaveTextContent('发票A.pdf');
    expect(screen.getByTestId('create-skipped')).toHaveTextContent('缺少金额');
  });

  test('quick entry generates records for all invoices', async () => {
    const user = userEvent.setup();
    const { calls } = setup({ 'POST /api/attachments/create-expenses': { created: [99], attached: [], skipped: [] } });
    await renderSection();
    await user.click(screen.getByRole('button', { name: '全部发票生成记录（1）' }));
    await waitFor(() => expect(callTo(calls, '/api/attachments/create-expenses')?.body).toEqual({ ids: [11] }));
    expect(await screen.findByText('新建 1 条、挂到已有 0 条、跳过 0 条')).toBeInTheDocument();
  });

  test('reparse sends selected invoice ids and notifies', async () => {
    const user = userEvent.setup();
    const { calls } = setup({ 'POST /api/attachments/reparse': [invoice] });
    await renderSection();
    await user.click(screen.getByRole('checkbox', { name: '全选' }));
    await user.click(screen.getByRole('button', { name: '重新识别' }));
    await waitFor(() => expect(callTo(calls, '/api/attachments/reparse')?.body).toEqual({ ids: [11] }));
    expect(await screen.findByText('已重新识别 1 个')).toBeInTheDocument();
  });

  test('bulk delete asks for confirmation before posting', async () => {
    const user = userEvent.setup();
    const { calls } = setup({ 'POST /api/attachments/bulk-delete': { deleted: 2 } });
    await renderSection();
    await user.click(screen.getByRole('checkbox', { name: '全选' }));
    await user.click(screen.getByRole('button', { name: '删除' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/文件将移入回收站/)).toBeInTheDocument();
    expect(callTo(calls, '/api/attachments/bulk-delete')).toBeUndefined();
    await user.click(within(dialog).getByRole('button', { name: '删除 2 个' }));
    await waitFor(() => expect(callTo(calls, '/api/attachments/bulk-delete')?.body).toEqual({ ids: [11, 12] }));
    expect(await screen.findByText('已删除 2 个附件')).toBeInTheDocument();
  });

  test('bulk assign posts expense id and optional kind', async () => {
    const user = userEvent.setup();
    const { calls } = setup({ 'POST /api/attachments/bulk-assign': [] });
    await renderSection();
    await user.click(screen.getByRole('checkbox', { name: '全选' }));
    await user.click(screen.getByRole('button', { name: '归属到记录…' }));
    const dialog = await screen.findByRole('dialog');
    const submit = within(dialog).getByRole('button', { name: '归属' });
    expect(submit).toBeDisabled();
    await user.click(dialog.querySelector('input[aria-label="目标记录"]') as HTMLInputElement);
    await user.click(await screen.findByRole('option', { name: /腾讯云/ }));
    await user.click(dialog.querySelector('input[aria-label="统一设置类型"]') as HTMLInputElement);
    await user.click(await screen.findByRole('option', { name: '订单明细' }));
    await user.click(submit);
    await waitFor(() => expect(callTo(calls, '/api/attachments/bulk-assign')?.body).toEqual({ ids: [11, 12], expense_id: 42, kind: 'order' }));
  });

  test('single row kind change patches the attachment', async () => {
    const user = userEvent.setup();
    const { calls } = setup({ 'PATCH /api/attachments/12': { ...order, kind: 'payment' } });
    await renderSection();
    const row = screen.getByTestId('unassigned-row-12');
    await user.click(row.querySelector('input[aria-label="附件类型"]') as HTMLInputElement);
    await user.click(await screen.findByRole('option', { name: '支付记录' }));
    await waitFor(() => expect(callTo(calls, '/api/attachments/12')?.body).toEqual({ kind: 'payment' }));
  });

  test('primary button uses light variant when another primary exists', async () => {
    const user = userEvent.setup();
    setup();
    await renderSection(true);
    await user.click(screen.getByRole('checkbox', { name: '全选' }));
    expect(screen.getByRole('button', { name: '生成记录' })).toHaveAttribute('data-variant', 'light');
  });
});
