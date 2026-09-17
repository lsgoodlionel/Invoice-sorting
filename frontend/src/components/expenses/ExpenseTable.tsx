import { Checkbox, Table } from '@mantine/core';
import type { ExpenseSummary } from '../../api/types';
import { ExpenseRow } from './ExpenseRow';

interface ExpenseTableProps {
  items: readonly ExpenseSummary[];
  selectedIds: readonly number[];
  onToggle: (id: number) => void;
  onToggleAll: (checked: boolean) => void;
  onOpen: (id: number) => void;
  /** 文件拖到某行上时回调 */
  onDropFiles: (id: number, files: File[]) => void;
}

export function ExpenseTable({ items, selectedIds, onToggle, onToggleAll, onOpen, onDropFiles }: ExpenseTableProps) {
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
            <Table.Th title="可把文件直接拖到行上补传">商家 · 摘要</Table.Th>
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
              onDropFiles={onDropFiles}
            />
          ))}
        </Table.Tbody>
      </Table>
    </div>
  );
}
