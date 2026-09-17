import { screen, within } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';
import { makeExpense } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { ExpenseTable } from './ExpenseTable';

describe('ExpenseTable creator', () => {
  test('shows creator under the merchant only when known', () => {
    const items = [makeExpense({ id: 1, created_by: { id: 2, display_name: '张三' } }), makeExpense({ id: 2, merchant: '收件箱商家' })];
    renderWithProviders(
      <ExpenseTable items={items} selectedIds={[]} onToggle={vi.fn()} onToggleAll={vi.fn()} onOpen={vi.fn()} onDropFiles={vi.fn()} />,
    );
    expect(within(screen.getByTestId('expense-row-1')).getByText('创建：张三')).toBeInTheDocument();
    expect(within(screen.getByTestId('expense-row-2')).queryByText(/创建：/)).not.toBeInTheDocument();
  });
});
