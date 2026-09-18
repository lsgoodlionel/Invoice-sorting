import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test, vi } from 'vitest';
import { makeExpense } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { BatchExpensesTable } from './BatchExpensesTable';

const expenses = [
  makeExpense({ id: 1, merchant: '京东某店', category_id: 2, category_name: '易耗品', status: 'complete' }),
  makeExpense({ id: 2, merchant: '腾讯云', category_id: 3, category_name: '软件服务', status: 'invoiced' }),
  makeExpense({ id: 3, merchant: '顺丰', category_id: 2, category_name: '易耗品', status: 'invoiced' }),
];

function setup() {
  renderWithProviders(<BatchExpensesTable expenses={expenses} canRemove={false} onRemove={vi.fn()} onOpen={vi.fn()} />);
}

const merchants = () => screen.getAllByTestId(/^batch-expense-/).map((row) => row.dataset.testid);

describe('BatchExpensesTable filters', () => {
  test('shows all rows with the count by default', () => {
    setup();
    expect(merchants()).toEqual(['batch-expense-1', 'batch-expense-2', 'batch-expense-3']);
    expect(screen.getByTestId('batch-filter-count')).toHaveTextContent('显示 3 / 共 3 条');
  });

  test('filters by category and status locally and updates the count', async () => {
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole('combobox', { name: '按分类筛选' }));
    await user.click(await screen.findByRole('option', { name: '易耗品' }));
    expect(merchants()).toEqual(['batch-expense-1', 'batch-expense-3']);
    await user.click(screen.getByRole('checkbox', { name: '已开票' }));
    expect(merchants()).toEqual(['batch-expense-3']);
    expect(screen.getByTestId('batch-filter-count')).toHaveTextContent('显示 1 / 共 3 条');
  });

  test('shows a hint when nothing matches', async () => {
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole('combobox', { name: '按分类筛选' }));
    await user.click(await screen.findByRole('option', { name: '软件服务' }));
    await user.click(screen.getByRole('checkbox', { name: '凭证齐全' }));
    expect(screen.queryAllByTestId(/^batch-expense-/)).toHaveLength(0);
    expect(screen.getByText('没有符合筛选条件的记录')).toBeInTheDocument();
  });
});
