import { afterEach, describe, expect, test } from 'vitest';
import { DEFAULT_EXPENSE_COLUMNS, expenseTableStorageKey, readExpenseTablePreferences, saveExpenseTablePreferences } from './expenseColumns';

afterEach(() => localStorage.clear());

describe('expense table preferences', () => {
  test('defaults to all columns and keeps users separate', () => {
    expect(readExpenseTablePreferences(1).visible).toEqual(DEFAULT_EXPENSE_COLUMNS);
    const first = readExpenseTablePreferences(1);
    first.order = ['amount', ...first.order.filter((key) => key !== 'amount')];
    first.visible = ['amount', 'item_name'];
    first.widths.amount = 188;
    saveExpenseTablePreferences(1, first);

    expect(readExpenseTablePreferences(1)).toMatchObject({ order: expect.arrayContaining(['amount']), visible: ['amount', 'item_name'], widths: { amount: 188 } });
    expect(readExpenseTablePreferences(2).visible).toEqual(DEFAULT_EXPENSE_COLUMNS);
    expect(localStorage.getItem(expenseTableStorageKey(1))).not.toBeNull();
  });

  test('repairs unknown, missing and unsafe stored values', () => {
    localStorage.setItem(expenseTableStorageKey(null), JSON.stringify({ order: ['amount', 'bad'], visible: ['amount'], widths: { amount: 9999 } }));
    const result = readExpenseTablePreferences(null);
    expect(result.order[0]).toBe('amount');
    expect(result.order).toHaveLength(DEFAULT_EXPENSE_COLUMNS.length);
    expect(result.visible).toEqual(['amount']);
    expect(result.widths.amount).toBe(600);
  });
});
