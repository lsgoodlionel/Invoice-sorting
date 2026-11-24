import { Checkbox, Table, UnstyledButton } from '@mantine/core';
import { IconArrowsSort, IconChevronDown, IconChevronUp } from '@tabler/icons-react';
import type { DateBasis, ExpenseSortBy, ExpenseSummary, SortOrder } from '../../api/types';
import { DEFAULT_EXPENSE_COLUMNS, type ExpenseColumnKey } from '../../lib/expenseColumns';
import { ExpenseRow } from './ExpenseRow';

interface ExpenseTableProps {
  items: readonly ExpenseSummary[];
  selectedIds: readonly number[];
  onToggle: (id: number) => void;
  onToggleAll: (checked: boolean) => void;
  onOpen: (id: number) => void;
  /** 文件拖到某行上时回调 */
  onDropFiles: (id: number, files: File[]) => void;
  columns?: readonly ExpenseColumnKey[];
  sortBy?: ExpenseSortBy;
  sortOrder?: SortOrder;
  dateBasis?: DateBasis;
  onSort?: (sortBy: ExpenseSortBy, dateBasis?: DateBasis) => void;
}

function SortHeader({ label, active, order, onClick }: { label: string; active: boolean; order: SortOrder; onClick: () => void }) {
  const Icon = active ? (order === 'asc' ? IconChevronUp : IconChevronDown) : IconArrowsSort;
  return <UnstyledButton onClick={onClick} aria-label={`按${label}排序`}><span>{label} <Icon size={12} /></span></UnstyledButton>;
}

export function ExpenseTable({ items, selectedIds, onToggle, onToggleAll, onOpen, onDropFiles, columns = DEFAULT_EXPENSE_COLUMNS, sortBy = 'date', sortOrder = 'desc', dateBasis = 'spent', onSort = () => undefined }: ExpenseTableProps) {
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
            {columns.includes('spent_on') && <Table.Th><SortHeader label="业务发生日期" active={sortBy === 'date' && dateBasis === 'spent'} order={sortOrder} onClick={() => onSort('date', 'spent')} /></Table.Th>}
            {columns.includes('issued_on') && <Table.Th><SortHeader label="发票开票日期" active={sortBy === 'date' && dateBasis === 'invoiced'} order={sortOrder} onClick={() => onSort('date', 'invoiced')} /></Table.Th>}
            {columns.includes('created_on') && <Table.Th><SortHeader label="凭证填报日期" active={sortBy === 'date' && dateBasis === 'created'} order={sortOrder} onClick={() => onSort('date', 'created')} /></Table.Th>}
            {columns.includes('summary') && <Table.Th title="可把文件直接拖到行上补传"><SortHeader label="商家 · 摘要" active={sortBy === 'summary'} order={sortOrder} onClick={() => onSort('summary')} /></Table.Th>}
            {columns.includes('item_name') && <Table.Th>名称</Table.Th>}
            {columns.includes('category') && <Table.Th><SortHeader label="分类" active={sortBy === 'category'} order={sortOrder} onClick={() => onSort('category')} /></Table.Th>}
            {columns.includes('lab_platform') && <Table.Th>平台申请</Table.Th>}
            {columns.includes('unit_price') && <Table.Th ta="right">单价</Table.Th>}
            {columns.includes('quantity') && <Table.Th ta="right">数量</Table.Th>}
            {columns.includes('amount') && <Table.Th ta="right"><SortHeader label="总价" active={sortBy === 'amount'} order={sortOrder} onClick={() => onSort('amount')} /></Table.Th>}
            {columns.includes('invoice_no') && <Table.Th>发票号</Table.Th>}
            {columns.includes('status') && <Table.Th><SortHeader label="状态" active={sortBy === 'status'} order={sortOrder} onClick={() => onSort('status')} /></Table.Th>}
            {columns.includes('evidence') && <Table.Th>凭证</Table.Th>}
            {columns.includes('batch') && <Table.Th>批次</Table.Th>}
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
              columns={columns}
            />
          ))}
        </Table.Tbody>
      </Table>
    </div>
  );
}
