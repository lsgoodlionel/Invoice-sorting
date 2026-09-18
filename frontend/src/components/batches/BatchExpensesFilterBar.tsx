import { Chip, Group, Select, Text } from '@mantine/core';
import type { ExpenseSummary } from '../../api/types';
import { batchCategoryOptions, batchStatusOptions, type BatchExpenseFilter } from '../../lib/batchExpenseFilters';
import { isStatus } from '../../lib/status';

interface BatchExpensesFilterBarProps {
  expenses: readonly ExpenseSummary[];
  filter: BatchExpenseFilter;
  shownCount: number;
  onChange: (filter: BatchExpenseFilter) => void;
}

/** 批次记录表上方的分类与状态筛选（仅影响显示，打包仍为整个批次）。 */
export function BatchExpensesFilterBar({ expenses, filter, shownCount, onChange }: BatchExpensesFilterBarProps) {
  return (
    <Group gap="sm" wrap="wrap" align="center">
      <Select
        aria-label="按分类筛选"
        size="xs"
        w={140}
        placeholder="全部分类"
        clearable
        data={batchCategoryOptions(expenses)}
        value={filter.category}
        onChange={(category) => onChange({ ...filter, category })}
      />
      <Chip.Group multiple value={[...filter.statuses]} onChange={(next) => onChange({ ...filter, statuses: next.filter(isStatus) })}>
        <Group gap={4} role="group" aria-label="按状态筛选">
          {batchStatusOptions(expenses).map((option) => (
            <Chip key={option.value} value={option.value} size="xs" variant="outline">{option.label}</Chip>
          ))}
        </Group>
      </Chip.Group>
      <Text size="xs" c="dimmed" ml="auto" className="num" data-testid="batch-filter-count">
        显示 {shownCount} / 共 {expenses.length} 条
      </Text>
    </Group>
  );
}
