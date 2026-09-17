import { ActionIcon, Badge, Table, Text, Tooltip } from '@mantine/core';
import { IconCircleMinus } from '@tabler/icons-react';
import type { ExpenseSummary } from '../../api/types';
import { formatCents } from '../../lib/money';
import { CategoryDot } from '../CategoryDot';
import { StatusBadge } from '../StatusBadge';

interface BatchExpensesTableProps {
  expenses: readonly ExpenseSummary[];
  canRemove: boolean;
  onRemove: (id: number) => void;
  onOpen: (id: number) => void;
}

export function BatchExpensesTable({ expenses, canRemove, onRemove, onOpen }: BatchExpensesTableProps) {
  return (
    <div className="table-scroll">
      <Table className="ledger-table" miw={680}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>日期</Table.Th>
            <Table.Th>商家 · 摘要</Table.Th>
            <Table.Th>分类</Table.Th>
            <Table.Th ta="right">金额</Table.Th>
            <Table.Th>状态</Table.Th>
            <Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {expenses.map((expense) => (
            <Table.Tr key={expense.id} className="clickable" tabIndex={0} onClick={() => onOpen(expense.id)} onKeyDown={(e) => e.key === 'Enter' && onOpen(expense.id)}>
              <Table.Td className="num">{expense.spent_on}</Table.Td>
              <Table.Td>
                <Text size="sm" truncate maw={240}>{expense.merchant}</Text>
                {expense.summary && <Text size="xs" c="dimmed" truncate maw={240}>{expense.summary}</Text>}
              </Table.Td>
              <Table.Td><CategoryDot color={expense.category_color} name={expense.category_name} /></Table.Td>
              <Table.Td ta="right" className="num">{formatCents(expense.amount_cents)}</Table.Td>
              <Table.Td>
                <StatusBadge status={expense.status} manual={expense.status_manual} />
                {expense.missing_count > 0 && <Badge ml={4} size="sm" color="orange" variant="outline">缺 {expense.missing_count} 项</Badge>}
              </Table.Td>
              <Table.Td onClick={(e) => e.stopPropagation()} w={40}>
                {canRemove && (
                  <Tooltip label="移出批次">
                    <ActionIcon variant="subtle" aria-label="移出批次" onClick={() => onRemove(expense.id)}>
                      <IconCircleMinus size={16} />
                    </ActionIcon>
                  </Tooltip>
                )}
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </div>
  );
}
