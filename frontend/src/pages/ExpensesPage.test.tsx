import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import type { ExpenseListResult } from '../api/types';
import { mockFetch } from '../test/fetchMock';
import { makeAttachment, makeDetail, makeExpense } from '../test/fixtures';
import { renderWithProviders } from '../test/render';
import { ExpensesPage } from './ExpensesPage';

const list: ExpenseListResult = {
  items: [
    makeExpense({ id: 1, merchant: '京东某店', amount_cents: 96000, missing_count: 2, region_name: '北京', is_nonlocal: true }),
    makeExpense({ id: 2, merchant: '腾讯云', amount_cents: 29800, status: 'complete', batch_name: '9月第1批' }),
    makeExpense({ id: 3, merchant: 'Apple', amount_cents: 14426, invoice_exempt: true, currency: 'USD', original_amount_cents: 2000 }),
  ],
  total: 2,
  total_cents: 125800,
  status_counts: {
    invoiced: { count: 1, amount_cents: 96000 },
    complete: { count: 1, amount_cents: 29800 },
  },
};

function setupRoutes(items: ExpenseListResult = list, extra: Record<string, unknown> = {}) {
  return mockFetch({
    ...extra,
    'GET /api/expenses': items,
    'GET /api/categories': [],
    'GET /api/projects': [],
    'GET /api/batches': [],
  });
}

describe('ExpensesPage', () => {
  test('renders rows and status group counts', async () => {
    setupRoutes();
    renderWithProviders(<ExpensesPage />, { route: '/expenses?period=all' });
    expect(await screen.findByText('京东某店')).toBeInTheDocument();
    expect(screen.getByText('腾讯云')).toBeInTheDocument();
    expect(screen.getAllByText('¥960.00').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('缺 2 项')).toBeInTheDocument();
    expect(screen.getAllByText('外地')).toHaveLength(1);
    expect(screen.getByText('9月第1批')).toBeInTheDocument();
    expect(screen.getByTestId('status-count-invoiced')).toHaveTextContent('1');
    expect(screen.getByTestId('status-count-complete')).toHaveTextContent('1');
    expect(screen.getByTestId('status-count-spent')).toHaveTextContent('0');
    expect(within(screen.getByTestId('status-group-invoiced')).getByText('¥960.00')).toBeInTheDocument();
    expect(screen.getByText(/共 2 条/)).toHaveTextContent('¥1,258.00');
  });

  test('clicking a status group adds it to the request filter', async () => {
    const user = userEvent.setup();
    const { calls } = setupRoutes();
    renderWithProviders(<ExpensesPage />, { route: '/expenses?period=all' });
    await screen.findByText('京东某店');
    await user.click(screen.getByTestId('status-group-sent'));
    await waitFor(() => expect(calls.some((c) => c.url.includes('status=sent'))).toBe(true));
    expect(screen.getByTestId('status-group-sent')).toHaveAttribute('aria-pressed', 'true');
  });

  test('selection shows total and add-to-batch bar', async () => {
    const user = userEvent.setup();
    setupRoutes();
    renderWithProviders(<ExpensesPage />, { route: '/expenses?period=all' });
    await user.click(await screen.findByLabelText('选择 京东某店'));
    await user.click(screen.getByLabelText('选择 腾讯云'));
    expect(screen.getByText(/已选/)).toHaveTextContent('已选 2 条 · 合计 ¥1,258.00');
    expect(screen.getByRole('button', { name: /加入批次/ })).toBeEnabled();
  });

  test('shows guidance when empty', async () => {
    setupRoutes({ items: [], total: 0, total_cents: 0, status_counts: {} });
    renderWithProviders(<ExpensesPage />, { route: '/expenses' });
    expect(await screen.findByText('这里还没有记录')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '去收集页' })).toHaveAttribute('href', '/collect');
  });

  test('shows invoice exempt badge and original currency under amount', async () => {
    setupRoutes();
    renderWithProviders(<ExpensesPage />, { route: '/expenses?period=all' });
    const row = await screen.findByTestId('expense-row-3');
    expect(within(row).getByText('免发票')).toBeInTheDocument();
    expect(within(row).getByText('¥144.26')).toBeInTheDocument();
    expect(within(row).getByText('US$20.00')).toBeInTheDocument();
    expect(within(screen.getByTestId('expense-row-1')).queryByText('免发票')).not.toBeInTheDocument();
  });

  test('dragging files onto a row highlights it and uploads without kind', async () => {
    const detail = makeDetail({
      id: 1,
      attachments: [
        makeAttachment({ id: 10, kind_label: '发票' }),
        makeAttachment({ id: 21, kind: 'order', kind_label: '订单明细' }),
        makeAttachment({ id: 22, kind: 'payment', kind_label: '支付记录' }),
      ],
    });
    const { calls } = setupRoutes(list, { 'POST /api/expenses/1/attachments': detail });
    renderWithProviders(<ExpensesPage />, { route: '/expenses?period=all' });
    const row = await screen.findByTestId('expense-row-1');
    const files = [new File(['a'], '订单.png', { type: 'image/png' }), new File(['b'], '支付.png', { type: 'image/png' })];
    const dataTransfer = { types: ['Files'], files, dropEffect: 'none' };

    fireEvent.dragEnter(row, { dataTransfer });
    expect(row).toHaveAttribute('data-drop-over', 'true');
    expect(within(row).getByText('松开上传到此记录')).toBeInTheDocument();
    fireEvent.dragLeave(row, { dataTransfer });
    expect(row).not.toHaveAttribute('data-drop-over');

    fireEvent.dragEnter(row, { dataTransfer });
    fireEvent.dragOver(row, { dataTransfer });
    fireEvent.drop(row, { dataTransfer });
    expect(row).not.toHaveAttribute('data-drop-over');
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url === '/api/expenses/1/attachments')).toBe(true));
    const body = calls.find((c) => c.url === '/api/expenses/1/attachments')?.body as FormData;
    expect(body.getAll('files')).toHaveLength(2);
    expect(body.has('kind')).toBe(false);
    await waitFor(() => expect(document.body).toHaveTextContent('已上传 2 个文件到 #1，识别为：订单明细、支付记录'));
    expect(calls.filter((c) => c.method === 'GET' && c.url.startsWith('/api/expenses')).length).toBeGreaterThanOrEqual(2);
  });

  test('non-file drags are ignored', async () => {
    setupRoutes();
    renderWithProviders(<ExpensesPage />, { route: '/expenses?period=all' });
    const row = await screen.findByTestId('expense-row-2');
    fireEvent.dragEnter(row, { dataTransfer: { types: ['text/plain'], files: [] } });
    expect(row).not.toHaveAttribute('data-drop-over');
  });
});
