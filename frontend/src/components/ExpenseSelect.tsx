import { Select, type SelectProps } from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { useState } from 'react';
import { useExpenseSearch } from '../api/hooks/expenses';
import { formatCents } from '../lib/money';

interface ExpenseSelectProps extends Omit<SelectProps, 'data' | 'value' | 'onChange' | 'searchable'> {
  value: number | null;
  onChange: (id: number | null) => void;
}

const SEARCH_DEBOUNCE_MS = 250;

/** 可搜索的支出选择器：输入商家/摘要/发票号远程搜索。 */
export function ExpenseSelect({ value, onChange, ...rest }: ExpenseSelectProps) {
  const [search, setSearch] = useState('');
  const [debounced] = useDebouncedValue(search, SEARCH_DEBOUNCE_MS);
  const { data = [] } = useExpenseSearch(debounced);
  const options = data.map((expense) => ({
    value: String(expense.id),
    label: `#${expense.id} ${expense.spent_on} ${expense.merchant} ${formatCents(expense.amount_cents)}`,
  }));
  return (
    <Select
      searchable
      clearable
      placeholder="搜索商家 / 摘要 / 发票号"
      nothingFoundMessage="没有匹配的支出"
      filter={({ options: items }) => items}
      data={options}
      value={value === null ? null : String(value)}
      onChange={(next) => onChange(next === null ? null : Number(next))}
      onSearchChange={setSearch}
      {...rest}
    />
  );
}
