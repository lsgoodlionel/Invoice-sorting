import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import type { ImportConfirmInput, ImportSession } from '../api/types';
import { mockFetch, type RecordedCall } from '../test/fetchMock';
import { makeAttachment, makeCandidate, makeEvidence, makeGroup, makeInvoice, makeSession } from '../test/fixtures';
import { renderWithProviders } from '../test/render';
import { CollectPage } from './CollectPage';

const invoice = makeAttachment({ id: 10, expense_id: null, original_name: '升降桌发票.pdf', invoice: makeInvoice({ invoice_no: '2631', order_no: '3434253000808809' }) });
const order = makeAttachment({ id: 11, expense_id: null, kind: 'order', kind_label: '订单明细', original_name: '升降桌-交易订单.png', mime: 'image/png', evidence: makeEvidence({ currency: 'CNY', amount_cents: 45900, is_foreign: false }) });
const foreignOrder = makeAttachment({ id: 20, expense_id: null, kind: 'order', original_name: 'Claude订单.png', evidence: makeEvidence() });
const otherInvoice = makeAttachment({ id: 30, expense_id: null, original_name: '另一张发票.pdf', invoice: makeInvoice({ invoice_no: '9999' }) });

const session: ImportSession = makeSession({
  groups: [
    makeGroup({
      group_id: 'g1',
      attachments: [invoice, order],
      link_reasons: ['订单号一致'],
      summary: { spent_on: '2026-03-12', amount_cents: 45900, currency: 'CNY', original_amount_cents: null, merchant: '江苏京东海元贸易', summary: '升降桌', category_id: 1, is_online: true, invoice_exempt: false },
      candidates: [makeCandidate({ expense_id: 42, merchant: '京东', amount_cents: 45900, score: 60, reasons: ['金额相同'] })],
    }),
    makeGroup({
      group_id: 'g2',
      attachments: [foreignOrder],
      summary: { spent_on: '2026-06-28', amount_cents: 14426, currency: 'USD', original_amount_cents: 2000, merchant: 'Apple', summary: 'Claude Pro', category_id: 2, is_online: true, invoice_exempt: true },
      match: makeCandidate({ expense_id: 12, merchant: 'Claude Pro 5月', amount_cents: 14426, score: 90, reasons: ['文件名一致'] }),
      suggested_action: 'attach',
    }),
    makeGroup({ group_id: 'g3', attachments: [otherInvoice], suggested_action: 'skip', warnings: ['可能重复：同订单发票已在 #7'] }),
  ],
  duplicates: [{ original_name: 'dup.pdf', existing_expense_id: 7, reason: '发票号码重复' }],
  errors: [{ original_name: 'bad.ofd', error: '无法解析' }],
});

function setupRoutes() {
  return mockFetch({
    'GET /api/settings': { buyer_name: '', buyer_tax_id: '', overdue_days: 30, local_region: '上海', detail_platforms: [], data_dir: '/d', inbox_dir: '/d/收件箱' },
    'GET /api/categories': [
      { id: 1, name: '办公用品', color: '#333', keywords: [], route_hint: '', sort: 1, archived: false },
      { id: 2, name: '软件服务', color: '#555', keywords: [], route_hint: '', sort: 2, archived: false },
    ],
    'GET /api/projects': [],
    'GET /api/expenses': { items: [], total: 0, total_cents: 0, status_counts: {} },
    'GET /api/attachments/unassigned': [],
    'POST /api/imports': session,
    'POST /api/imports/sess-1/confirm': { created: [100], attached: [12], skipped: 1 },
  });
}

async function uploadSession(user: ReturnType<typeof userEvent.setup>) {
  renderWithProviders(<CollectPage />, { route: '/collect' });
  expect(await screen.findByText(/\/d\/收件箱/)).toBeInTheDocument();
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  await user.upload(input, [new File(['%PDF'], 'a.pdf', { type: 'application/pdf' })]);
  return screen.findByTestId('import-group-g1');
}

const confirmBody = (calls: RecordedCall[]) => calls.find((c) => c.url === '/api/imports/sess-1/confirm')?.body as ImportConfirmInput | undefined;

const inputIn = (container: HTMLElement, label: string) => container.querySelector(`input[aria-label="${label}"]`) as HTMLInputElement;

async function pickOption(user: ReturnType<typeof userEvent.setup>, input: HTMLInputElement, name: string | RegExp) {
  await user.click(input);
  await user.click(await screen.findByRole('option', { name }));
}

describe('CollectPage grouped confirm', () => {
  test('renders groups with files, link reasons, warnings, currency and tally', async () => {
    const user = userEvent.setup();
    setupRoutes();
    const g1 = await uploadSession(user);
    expect(screen.getByText(/本次导入：3 组 · 4 个文件/)).toBeInTheDocument();
    expect(screen.getByText('dup.pdf')).toBeInTheDocument();
    expect(screen.getByText('bad.ofd')).toBeInTheDocument();
    expect(within(g1).getByTestId('group-file-10')).toBeInTheDocument();
    expect(within(g1).getByTestId('link-reasons')).toHaveTextContent('订单号一致');
    expect(within(g1).queryByLabelText('原币金额')).not.toBeInTheDocument();

    const g2 = screen.getByTestId('import-group-g2');
    expect(within(g2).getByDisplayValue('挂到 #12 Claude Pro 5月 ¥144.26 · 90 分 · 文件名一致')).toBeInTheDocument();
    expect(within(g2).getByLabelText('原币金额')).toHaveValue('20.00');
    expect(within(g2).getByRole('switch', { name: '免发票（境外）' })).toBeChecked();
    expect(within(screen.getByTestId('import-group-g3')).getByText(/可能重复/)).toBeInTheDocument();
    expect(screen.getByTestId('import-tally')).toHaveTextContent('共 3 组 · 新建 1 · 挂到已有 1 · 留待归属 1');

    await user.hover(screen.getByLabelText('分组与匹配说明'));
    expect(await screen.findByText(/系统会把同一笔支出的发票、订单、支付记录归为一组/)).toBeInTheDocument();
  });

  test('changing operation to a candidate and editing kinds builds the confirm payload', async () => {
    const user = userEvent.setup();
    const { calls } = setupRoutes();
    const g1 = await uploadSession(user);

    await pickOption(user, inputIn(g1, '类型 升降桌-交易订单.png'), '支付记录');
    await pickOption(user, inputIn(g1, '操作'), /挂到 #42 京东/);
    expect(within(g1).getByLabelText('商家')).toBeDisabled();
    expect(screen.getByTestId('import-tally')).toHaveTextContent('新建 0 · 挂到已有 2 · 留待归属 1');

    const g2 = screen.getByTestId('import-group-g2');
    await pickOption(user, inputIn(g2, '操作'), '新建记录');

    await user.click(screen.getByRole('button', { name: '全部确认' }));
    await waitFor(() => expect(confirmBody(calls)).toBeDefined());
    expect(confirmBody(calls)).toEqual({
      groups: [
        { group_id: 'g1', attachment_ids: [10, 11], kinds: { 11: 'payment' }, action: 'attach', expense_id: 42 },
        {
          group_id: 'g2', attachment_ids: [20], action: 'create', spent_on: '2026-06-28', amount_cents: 14426, currency: 'USD',
          original_amount_cents: 2000, merchant: 'Apple', summary: 'Claude Pro', category_id: 2, project_id: null, is_online: true, invoice_exempt: true,
        },
        { group_id: 'g3', attachment_ids: [30], action: 'skip' },
      ],
    });
    expect(await screen.findByText(/新建 1 条，挂到已有 1 条，1 个文件留在待归属/)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByTestId('import-group-g1')).not.toBeInTheDocument());
  });

  test('moving a second invoice into a group marks it red and disables confirm; splitting restores', async () => {
    const user = userEvent.setup();
    const { calls } = setupRoutes();
    await uploadSession(user);

    await user.click(screen.getByRole('button', { name: '文件操作 另一张发票.pdf' }));
    await user.click(await screen.findByRole('menuitem', { name: '移到其他组…' }));
    const dialog = await screen.findByRole('dialog');
    await pickOption(user, inputIn(dialog, '目标组'), '组 1 · 江苏京东海元贸易');
    await user.click(within(dialog).getByRole('button', { name: '移动' }));

    const g1 = screen.getByTestId('import-group-g1');
    await waitFor(() => expect(screen.queryByTestId('import-group-g3')).not.toBeInTheDocument());
    expect(g1).toHaveAttribute('data-invalid', 'true');
    expect(within(g1).getByText(/一组最多一张发票/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '全部确认' })).toBeDisabled();

    await user.click(within(g1).getByRole('button', { name: '文件操作 另一张发票.pdf' }));
    await user.click(await screen.findByRole('menuitem', { name: '拆为单独一组' }));
    const split = await screen.findByTestId('import-group-split-1');
    expect(within(split).getByTestId('group-file-30')).toBeInTheDocument();
    expect(g1).not.toHaveAttribute('data-invalid');
    expect(screen.getByRole('button', { name: '全部确认' })).toBeEnabled();

    await user.click(screen.getByRole('button', { name: '全部确认' }));
    await waitFor(() => expect(confirmBody(calls)?.groups.map((g) => [g.group_id, g.attachment_ids])).toEqual([
      ['g1', [10, 11]], ['split-1', [30]], ['g2', [20]],
    ]));
  });

  test('create group without amount is blocked with a hint', async () => {
    const user = userEvent.setup();
    setupRoutes();
    const g1 = await uploadSession(user);
    await user.clear(within(g1).getByLabelText('人民币金额'));
    expect(within(g1).getByText('请填写人民币金额')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '全部确认' })).toBeDisabled();
    expect(screen.getByText('1 组需要处理后才能确认')).toBeInTheDocument();
  });
});
