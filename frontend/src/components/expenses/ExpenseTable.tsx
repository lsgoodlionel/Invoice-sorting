import { Badge, Checkbox, Group, Table, Text } from '@mantine/core';
import type { ExpenseSummary } from '../../api/types';
import { formatCents } from '../../lib/money';
import { CategoryDot } from '../CategoryDot';
import { StatusBadge } from '../StatusBadge';

interface ExpenseTableProps {
  items: readonly ExpenseSummary[];
  selectedIds: readonly number[];
  onToggle: (id: number) => void;
  onToggleAll: (checked: boolean) => void;
  onOpen: (id: number) => void;
}

function ExpenseRow({
  expense,
  isSelected,
  onToggle,
  onOpen,
}: {
  expense: ExpenseSummary;
  isSelected: boolean;
  onToggle: (id: number) => void;
  onOpen: (id: number) => void;
}) {
  return (
    <Table.Tr
      className="clickable"
      tabIndex={0}
      data-selected={isSelected}
      onClick={() => onOpen(expense.id)}
      onKeyDown={(event) => {
        if (event.key === 'Enter') onOpen(expense.id);
      }}
    >
      <Table.Td onClick={(event) => event.stopPropagation()} w={36}>
        <Checkbox size="xs" aria-label={`选择 ${expense.merchant}`} checked={isSelected} onChange={() => onToggle(expense.id)} />
      </Table.Td>
      <Table.Td className="num" w={96}>{expense.spent_on}</Table.Td>
      <Table.Td style={{ maxWidth: 320 }}>
        <Group gap={6} wrap="nowrap">
          <Text size="sm" fw={500} truncate>{expense.merchant}</Text>
          {expense.is_nonlocal && (
            <Badge size="xs" radius="xs" color="orange" variant="light" title={`开票地区：${expense.region_name}`} style={{ flexShrink: 0 }}>外地</Badge>
          )}
        </Group>
        {expense.summary && <Text size="xs" c="dimmed" truncate>{expense.summary}</Text>}
      </Table.Td>
      <Table.Td><CategoryDot color={expense.category_color} name={expense.category_name} /></Table.Td>
      <Table.Td ta="right" className="num" fw={500}>{formatCents(expense.amount_cents)}</Table.Td>
      <Table.Td><StatusBadge status={expense.status} manual={expense.status_manual} /></Table.Td>
      <Table.Td>
        {expense.missing_count > 0 && (
          <Badge size="sm" color="orange" variant="outline">缺 {expense.missing_count} 项</Badge>
        )}
      </Table.Td>
      <Table.Td><Text size="xs" c="dimmed" truncate maw={160}>{expense.batch_name ?? ''}</Text></Table.Td>
    </Table.Tr>
  );
}

export function ExpenseTable({ items, selectedIds, onToggle, onToggleAll, onOpen }: ExpenseTableProps) {
  const selectedCount = items.filter((item) => selectedIds.includes(item.id)).length;
  const isAllSelected = items.length > 0 && selectedCount === items.length;
  return (
    <div className="table-scroll">
      <Table className="ledger-table" miw={860}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>
              <Checkbox
                size="xs"
                aria-label="全选"
                checked={isAllSelected}
                indeterminate={selectedCount > 0 && !isAllSelected}
                onChange={(event) => onToggleAll(event.currentTarget.checked)}
              />
            </Table.Th>
            <Table.Th>日期</Table.Th>
            <Table.Th>商家 · 摘要</Table.Th>
            <Table.Th>分类</Table.Th>
            <Table.Th ta="right">金额</Table.Th>
            <Table.Th>状态</Table.Th>
            <Table.Th>凭证</Table.Th>
            <Table.Th>批次</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {items.map((expense) => (
            <ExpenseRow
              key={expense.id}
              expense={expense}
              isSelected={selectedIds.includes(expense.id)}
              onToggle={onToggle}
              onOpen={onOpen}
            />
          ))}
        </Table.Tbody>
      </Table>
    </div>
  );
}
