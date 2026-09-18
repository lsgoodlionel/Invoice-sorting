import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test, vi } from 'vitest';
import type { ExpenseSummary } from '../../api/types';
import { presetRange } from '../../lib/period';
import { mockFetch, type RecordedCall } from '../../test/fetchMock';
import { makeBatch, makeExpense, makeProject } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { AddExpensesModal } from './AddExpensesModal';

const items: ExpenseSummary[] = [
  makeExpense({ id: 1, merchant: '京东某店', summary: '鼠标', amount_cents: 96000, project_id: 7, missing_count: 1, category_id: 2 }),
  makeExpense({ id: 2, merchant: '腾讯云', summary: '服务器', amount_cents: 29800, project_id: 7, category_id: 3, status: 'complete' }),
  makeExpense({ id: 3, merchant: '作废店', project_id: 7, status: 'void' }),
  makeExpense({ id: 4, merchant: '顺丰', summary: '快递', amount_cents: 1200, project_id: 8, status: 'spent' }),
];

const categories = [
  { id: 2, name: '易耗品', color: '#1F5F4A', keywords: [], route_hint: '', sort: 1, archived: false },
  { id: 3, name: '软件服务', color: '#333333', keywords: [], route_hint: '', sort: 2, archived: false },
];

/** 模拟后端按查询参数过滤未分批记录。 */
function serveExpenses(data: readonly ExpenseSummary[]) {
  return (call: RecordedCall) => {
    const params = new URL(call.url, 'http://test').searchParams;
    const number = (key: string) => (params.has(key) ? Number(params.get(key)) : null);
    const statuses = params.get('status')?.split(',') ?? [];
    const filtered = data.filter(
      (expense) =>
        (number('project_id') === null || expense.project_id === number('project_id')) &&
        (number('category_id') === null || expense.category_id === number('category_id')) &&
        (statuses.length === 0 || statuses.includes(expense.status)) &&
        (params.get('missing') !== 'true' || expense.missing_count > 0),
    );
    return { data: { items: filtered, total: filtered.length, total_cents: 0, status_counts: {} } };
  };
}

interface SetupOptions {
  data?: ExpenseSummary[];
  projectId?: number | null;
  itemsRoute?: (call: RecordedCall) => { status?: number; data?: unknown; error?: string };
}

function setup({ data = items, projectId = 7, itemsRoute }: SetupOptions = {}) {
  const mock = mockFetch({
    'GET /api/expenses': serveExpenses(data),
    'GET /api/categories': categories,
    'GET /api/projects': [makeProject({ id: 7, code: '', name: '项目七' }), makeProject({ id: 8, code: '', name: '项目八' })],
    'POST /api/batches/5/items': itemsRoute ?? (() => ({ data: makeBatch({ item_count: 1 }) })),
  });
  const onClose = vi.fn();
  renderWithProviders(<AddExpensesModal batch={makeBatch({ project_id: projectId, project_name: '项目七' })} opened onClose={onClose} />);
  return { ...mock, onClose };
}

const rowNames = () => screen.queryAllByTestId(/^candidate-/).map((row) => row.dataset.testid);
const lastExpenseUrl = (calls: RecordedCall[]) =>
  new URL([...calls].reverse().find((call) => call.url.startsWith('/api/expenses'))?.url ?? '', 'http://test').searchParams;

async function pickOption(label: string, option: string) {
  const user = userEvent.setup();
  await user.click(screen.getByRole('combobox', { name: label }));
  await user.click(await screen.findByRole('option', { name: option }));
}

describe('AddExpensesModal', () => {
  test('requests unbatched expenses of the batch project and hides void', async () => {
    const { calls } = setup();
    await screen.findByText('京东某店');
    const params = lastExpenseUrl(calls);
    expect(params.get('unbatched')).toBe('true');
    expect(params.get('page_size')).toBe('500');
    expect(params.get('project_id')).toBe('7');
    expect(params.has('start')).toBe(false);
    expect(rowNames()).toEqual(['candidate-1', 'candidate-2']);
    expect(within(screen.getByTestId('candidate-1')).getByText('缺 1 项')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '全部日期' })).toHaveAttribute('aria-pressed', 'true');
  });

  test('show all projects drops the project param and search filters locally', async () => {
    const user = userEvent.setup();
    const { calls } = setup();
    await screen.findByText('京东某店');
    await user.click(screen.getByRole('switch', { name: '显示全部项目' }));
    await waitFor(() => expect(rowNames()).toEqual(['candidate-1', 'candidate-2', 'candidate-4']));
    expect(lastExpenseUrl(calls).has('project_id')).toBe(false);
    await user.type(screen.getByRole('textbox', { name: '搜索记录' }), '快递');
    expect(rowNames()).toEqual(['candidate-4']);
  });

  test('an explicitly chosen project wins over the batch project', async () => {
    const { calls } = setup();
    await screen.findByText('京东某店');
    await pickOption('经费项目筛选', '项目八');
    await waitFor(() => expect(rowNames()).toEqual(['candidate-4']));
    expect(lastExpenseUrl(calls).get('project_id')).toBe('8');
    expect(screen.getByRole('switch', { name: '显示全部项目' })).toBeDisabled();
  });

  test('period preset and date basis become start/end/date_basis', async () => {
    const user = userEvent.setup();
    const { calls } = setup();
    await screen.findByText('京东某店');
    await user.click(screen.getByRole('button', { name: '本月' }));
    const month = presetRange('this_month') ?? { start: '', end: '' };
    await waitFor(() => expect(lastExpenseUrl(calls).get('start')).toBe(month.start));
    expect(lastExpenseUrl(calls).get('end')).toBe(month.end);
    expect(lastExpenseUrl(calls).get('date_basis')).toBe('spent');
    await user.click(screen.getByRole('combobox', { name: '日期口径' }));
    await user.click(await screen.findByRole('option', { name: '开票日期' }));
    await waitFor(() => expect(lastExpenseUrl(calls).get('date_basis')).toBe('invoiced'));
  });

  test('category, status and missing-evidence filters are sent to the server', async () => {
    const user = userEvent.setup();
    const { calls } = setup({ projectId: null });
    await screen.findByText('京东某店');
    await pickOption('分类筛选', '易耗品');
    await waitFor(() => expect(lastExpenseUrl(calls).get('category_id')).toBe('2'));
    await user.click(screen.getByRole('checkbox', { name: '已开票' }));
    await user.click(screen.getByRole('checkbox', { name: '已支出' }));
    await waitFor(() => expect(lastExpenseUrl(calls).get('status')).toBe('invoiced,spent'));
    await user.click(screen.getByRole('radio', { name: '只看缺凭证' }));
    await waitFor(() => expect(lastExpenseUrl(calls).get('missing')).toBe('true'));
    expect(rowNames()).toEqual(['candidate-1']);
  });

  test('only-complete evidence filters locally without the missing param', async () => {
    const user = userEvent.setup();
    const { calls } = setup({ projectId: null });
    await screen.findByText('京东某店');
    await user.click(screen.getByRole('radio', { name: '只看凭证齐全' }));
    expect(rowNames()).toEqual(['candidate-2', 'candidate-4']);
    expect(lastExpenseUrl(calls).has('missing')).toBe(false);
  });

  test('shows result totals and selects the whole filtered result', async () => {
    const user = userEvent.setup();
    setup({ projectId: null });
    await screen.findByText('京东某店');
    expect(screen.getByTestId('result-summary')).toHaveTextContent('符合条件 3 条 · 合计 ¥1,270.00');
    await user.click(screen.getByRole('checkbox', { name: '全选当前筛选结果' }));
    expect(screen.getByTestId('selection-summary')).toHaveTextContent('已选 3 条 · 合计 ¥1,270.00');
    await user.click(screen.getByRole('checkbox', { name: '全选当前筛选结果' }));
    expect(screen.getByTestId('selection-summary')).toHaveTextContent('已选 0 条');
  });

  test('changing filters keeps selections still in the result and drops the rest', async () => {
    const user = userEvent.setup();
    const { calls } = setup({ projectId: null });
    await user.click(await screen.findByLabelText('选择 京东某店'));
    await user.click(screen.getByLabelText('选择 腾讯云'));
    await user.click(screen.getByRole('radio', { name: '只看凭证齐全' }));
    expect(screen.getByTestId('selection-summary')).toHaveTextContent('已选 1 条 · 合计 ¥298.00');
    expect(screen.getByText('筛选变化，已取消 1 条不在结果中的勾选')).toBeInTheDocument();
    await user.click(screen.getByRole('radio', { name: '全部' }));
    expect(screen.getByLabelText('选择 京东某店')).not.toBeChecked();
    expect(screen.getByLabelText('选择 腾讯云')).toBeChecked();
    await user.click(screen.getByRole('button', { name: '加入批次' }));
    await waitFor(() => expect(calls.find((call) => call.method === 'POST')?.body).toEqual({ add: [2], force: false }));
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
    setup({ data: [makeExpense({ id: 3, status: 'void' })], projectId: null });
    expect(await screen.findByText('没有未分批的记录，先去收集页导入发票')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '去收集页' })).toHaveAttribute('href', '/collect');
    expect(screen.getByRole('button', { name: '加入批次' })).toBeDisabled();
  });

  test('hints to show all projects when the batch project has nothing', async () => {
    setup({ data: [makeExpense({ id: 4, project_id: 8 })] });
    expect(await screen.findByText('「项目七」下没有未分批记录，可打开“显示全部项目”。')).toBeInTheDocument();
  });
});
