import { Badge, Checkbox, Table, Text } from '@mantine/core';
import type { ExpenseSummary } from '../../api/types';
import { formatCents } from '../../lib/money';
import { CategoryDot } from '../CategoryDot';
import { StatusBadge } from '../StatusBadge';

interface CandidateTableProps {
  expenses: readonly ExpenseSummary[];
  selectedIds: readonly number[];
  onToggle: (id: number) => void;
  onToggleAll: (ids: readonly number[], checked: boolean) => void;
}

/** 可加入批次的记录表：勾选、日期、商家·摘要、分类、金额、状态、缺项。 */
export function CandidateTable({ expenses, selectedIds, onToggle, onToggleAll }: CandidateTableProps) {
  const visibleIds = expenses.map((expense) => expense.id);
  const checkedCount = visibleIds.filter((id) => selectedIds.includes(id)).length;
  const isAllChecked = visibleIds.length > 0 && checkedCount === visibleIds.length;

  return (
    <Table className="ledger-table" miw={640} stickyHeader>
      <Table.Thead>
        <Table.Tr>
          <Table.Th w={36}>
            <Checkbox
              aria-label="全选当前列表"
              checked={isAllChecked}
              indeterminate={checkedCount > 0 && !isAllChecked}
              onChange={() => onToggleAll(visibleIds, !isAllChecked)}
            />
          </Table.Th>
          <Table.Th>日期</Table.Th>
          <Table.Th>商家 · 摘要</Table.Th>
          <Table.Th>分类</Table.Th>
          <Table.Th ta="right">金额</Table.Th>
          <Table.Th>状态</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {expenses.map((expense) => (
          <Table.Tr
            key={expense.id}
            data-testid={`candidate-${expense.id}`}
            className="clickable"
            data-selected={selectedIds.includes(expense.id) || undefined}
            onClick={() => onToggle(expense.id)}
          >
            <Table.Td onClick={(event) => event.stopPropagation()}>
              <Checkbox
                aria-label={`选择 ${expense.merchant}`}
                checked={selectedIds.includes(expense.id)}
                onChange={() => onToggle(expense.id)}
              />
            </Table.Td>
            <Table.Td className="num">{expense.spent_on}</Table.Td>
            <Table.Td>
              <Text size="sm" truncate maw={220}>{expense.merchant}</Text>
              {expense.summary && <Text size="xs" c="dimmed" truncate maw={220}>{expense.summary}</Text>}
            </Table.Td>
            <Table.Td><CategoryDot color={expense.category_color} name={expense.category_name} /></Table.Td>
            <Table.Td ta="right" className="num">{formatCents(expense.amount_cents)}</Table.Td>
            <Table.Td>
              <StatusBadge status={expense.status} manual={expense.status_manual} />
              {expense.missing_count > 0 && (
                <Badge ml={4} size="sm" color="orange" variant="outline">缺 {expense.missing_count} 项</Badge>
              )}
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  );
}
