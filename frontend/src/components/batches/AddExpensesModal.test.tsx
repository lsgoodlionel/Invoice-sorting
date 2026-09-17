import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test, vi } from 'vitest';
import type { ExpenseSummary } from '../../api/types';
import { mockFetch, type RecordedCall } from '../../test/fetchMock';
import { makeBatch, makeExpense } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { AddExpensesModal } from './AddExpensesModal';

const items: ExpenseSummary[] = [
  makeExpense({ id: 1, merchant: '京东某店', summary: '鼠标', amount_cents: 96000, project_id: 7, missing_count: 1 }),
  makeExpense({ id: 2, merchant: '腾讯云', summary: '服务器', amount_cents: 29800, project_id: 7 }),
  makeExpense({ id: 3, merchant: '作废店', project_id: 7, status: 'void' }),
  makeExpense({ id: 4, merchant: '顺丰', summary: '快递', amount_cents: 1200, project_id: 8 }),
];

function list(data: ExpenseSummary[]) {
  return { items: data, total: data.length, total_cents: 0, status_counts: {} };
}

function setup(options: { data?: ExpenseSummary[]; itemsRoute?: (call: RecordedCall) => { status?: number; data?: unknown; error?: string } } = {}) {
  const mock = mockFetch({
    'GET /api/expenses': list(options.data ?? items),
    'POST /api/batches/5/items': options.itemsRoute ?? (() => ({ data: makeBatch({ item_count: 1 }) })),
  });
  const onClose = vi.fn();
  renderWithProviders(<AddExpensesModal batch={makeBatch({ project_id: 7 })} opened onClose={onClose} />);
  return { ...mock, onClose };
}

const rowNames = () => screen.getAllByTestId(/^candidate-/).map((row) => row.dataset.testid);

describe('AddExpensesModal', () => {
  test('requests unbatched expenses and hides void and other projects by default', async () => {
    const { calls } = setup();
    await screen.findByText('京东某店');
    const request = calls.find((call) => call.url.startsWith('/api/expenses'));
    expect(request?.url).toContain('unbatched=true');
    expect(request?.url).toContain('page_size=500');
    expect(rowNames()).toEqual(['candidate-1', 'candidate-2']);
    expect(screen.queryByText('作废店')).not.toBeInTheDocument();
    expect(within(screen.getByTestId('candidate-1')).getByText('缺 1 项')).toBeInTheDocument();
  });

  test('toggle shows all projects and search filters locally', async () => {
    const user = userEvent.setup();
    setup();
    await screen.findByText('京东某店');
    await user.click(screen.getByRole('switch', { name: '显示全部项目' }));
    expect(rowNames()).toEqual(['candidate-1', 'candidate-2', 'candidate-4']);
    await user.type(screen.getByRole('textbox', { name: '搜索记录' }), '快递');
    expect(rowNames()).toEqual(['candidate-4']);
    expect(screen.queryByText('作废店')).not.toBeInTheDocument();
  });

  test('submits selected ids and closes on success', async () => {
    const user = userEvent.setup();
    const { calls, onClose } = setup();
    await user.click(await screen.findByLabelText('选择 京东某店'));
    await user.click(screen.getByLabelText('选择 腾讯云'));
    expect(screen.getByTestId('selection-summary')).toHaveTextContent('已选 2 条 · 合计 ¥1,258.00');
    await user.click(screen.getByRole('button', { name: '加入批次' }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    const post = calls.find((call) => call.method === 'POST');
    expect(post?.body).toEqual({ add: [1, 2], force: false });
  });

  test('shows 409 error and retries with force', async () => {
    const user = userEvent.setup();
    const itemsRoute = (call: RecordedCall) =>
      (call.body as { force: boolean }).force
        ? { data: makeBatch({ item_count: 1 }) }
        : { status: 409, error: '京东某店 仍缺必需凭证：发票' };
    const { calls, onClose } = setup({ itemsRoute });
    await user.click(await screen.findByLabelText('选择 京东某店'));
    await user.click(screen.getByRole('button', { name: '加入批次' }));
    expect(await screen.findByText('京东某店 仍缺必需凭证：发票')).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: '仍然加入' }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    const posts = calls.filter((call) => call.method === 'POST').map((call) => call.body);
    expect(posts).toEqual([{ add: [1], force: false }, { add: [1], force: true }]);
  });

  test('shows empty state with link to collect page when nothing is unbatched', async () => {
    setup({ data: [makeExpense({ id: 3, status: 'void' })] });
    expect(await screen.findByText('没有未分批的记录，先去收集页导入发票')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '去收集页' })).toHaveAttribute('href', '/collect');
    expect(screen.getByRole('button', { name: '加入批次' })).toBeDisabled();
  });
});
