import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';
import { DEFAULT_EXPENSE_TABLE_PREFERENCES } from '../../lib/expenseColumns';
import { renderWithProviders } from '../../test/render';
import { ExpenseColumnSelector } from './ExpenseColumnSelector';

test('saves visibility and order only after confirmation', async () => {
  const user = userEvent.setup();
  const onSave = vi.fn();
  renderWithProviders(<ExpenseColumnSelector value={{ ...DEFAULT_EXPENSE_TABLE_PREFERENCES, order: [...DEFAULT_EXPENSE_TABLE_PREFERENCES.order], visible: [...DEFAULT_EXPENSE_TABLE_PREFERENCES.visible], widths: { ...DEFAULT_EXPENSE_TABLE_PREFERENCES.widths } }} onSave={onSave} />);

  await user.click(screen.getByRole('button', { name: '列设置' }));
  await user.click(screen.getByRole('checkbox', { name: '发票开票日期' }));
  await user.click(screen.getByRole('button', { name: '下移业务发生日期' }));
  expect(onSave).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: '保存设置' }));

  const saved = onSave.mock.calls[0][0];
  expect(saved.visible).not.toContain('issued_on');
  expect(saved.order.slice(0, 2)).toEqual(['issued_on', 'spent_on']);
});
