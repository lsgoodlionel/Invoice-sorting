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

  test('shows the recognized travel scope', () => {
    renderWithProviders(
      <ExpenseTable
        items={[makeExpense({ travel_scope: 'nonlocal', travel_scope_label: '市外' })]}
        selectedIds={[]}
        onToggle={vi.fn()}
        onToggleAll={vi.fn()}
        onOpen={vi.fn()}
        onDropFiles={vi.fn()}
      />,
    );
    expect(screen.getByText('市外')).toBeInTheDocument();
  });

  test('shows three dates and business columns and exposes sortable headers', () => {
    const onSort = vi.fn();
    renderWithProviders(
      <ExpenseTable
        items={[makeExpense({ spent_on: '2026-09-01', issued_on: '2026-09-03', created_on: '2026-09-04', item_name: '订书机', unit_price_cents: 1200, quantity: 2, amount_cents: 2400, invoice_no: 'INV-1', requires_lab_platform: false })]}
        selectedIds={[]}
        onToggle={vi.fn()}
        onToggleAll={vi.fn()}
        onOpen={vi.fn()}
        onDropFiles={vi.fn()}
        onSort={onSort}
      />,
    );
    expect(screen.getByText('2026-09-01')).toBeInTheDocument();
    expect(screen.getByText('2026-09-03')).toBeInTheDocument();
    expect(screen.getByText('2026-09-04')).toBeInTheDocument();
    expect(screen.getByText('订书机')).toBeInTheDocument();
    expect(screen.getByText('INV-1')).toBeInTheDocument();
    screen.getByRole('button', { name: '按状态排序' }).click();
    expect(onSort).toHaveBeenCalledWith('status');
  });
});
