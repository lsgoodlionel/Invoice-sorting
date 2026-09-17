import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test, vi } from 'vitest';
import { mockFetch } from '../../test/fetchMock';
import { makeBatch, makeExpense } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { BatchDetailPanel } from './BatchDetailPanel';

function renderPanel(batch = makeBatch()) {
  mockFetch({ 'GET /api/projects': [] });
  const onAddExpenses = vi.fn();
  renderWithProviders(<BatchDetailPanel batch={batch} onOpenExpense={vi.fn()} onDeleted={vi.fn()} onAddExpenses={onAddExpenses} />);
  return { onAddExpenses };
}

describe('BatchDetailPanel', () => {
  test('empty draft batch shows empty state and disables export', async () => {
    const user = userEvent.setup();
    const { onAddExpenses } = renderPanel();
    const empty = screen.getByTestId('batch-items-empty');
    expect(within(empty).getByText('批次里还没有记录')).toBeInTheDocument();
    expect(within(empty).getByText('也可以在清单页勾选记录后点『加入批次』')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '生成资料包' })).toBeDisabled();
    expect(screen.getByText('先添加记录再打包')).toBeInTheDocument();
    const addButtons = screen.getAllByRole('button', { name: '添加记录' });
    expect(addButtons).toHaveLength(1);
    await user.click(addButtons[0]);
    expect(onAddExpenses).toHaveBeenCalledTimes(1);
  });

  test('draft batch with records shows add button beside the records heading', async () => {
    const user = userEvent.setup();
    const { onAddExpenses } = renderPanel(makeBatch({ item_count: 1, total_cents: 96000, expenses: [makeExpense()] }));
    expect(screen.queryByTestId('batch-items-empty')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '生成资料包' })).toBeEnabled();
    expect(screen.queryByText('先添加记录再打包')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '添加记录' }));
    expect(onAddExpenses).toHaveBeenCalledTimes(1);
  });

  test('sent batch has no add button', () => {
    renderPanel(makeBatch({ status: 'sent', item_count: 1, expenses: [makeExpense({ status: 'sent' })] }));
    expect(screen.queryByRole('button', { name: '添加记录' })).not.toBeInTheDocument();
  });

  test('shows batch creator', () => {
    renderPanel(makeBatch({ created_by: { id: 2, display_name: '张三' } }));
    expect(screen.getByText(/创建人：张三/)).toBeInTheDocument();
  });
});
