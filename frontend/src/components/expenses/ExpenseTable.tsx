import { Checkbox, Table, UnstyledButton } from '@mantine/core';
import { IconArrowsSort, IconChevronDown, IconChevronUp } from '@tabler/icons-react';
import { useState, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react';
import type { DateBasis, ExpenseSortBy, ExpenseSummary, SortOrder } from '../../api/types';
import { DEFAULT_EXPENSE_COLUMNS, DEFAULT_EXPENSE_COLUMN_WIDTHS, type ExpenseColumnKey } from '../../lib/expenseColumns';
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
  widths?: Readonly<Record<ExpenseColumnKey, number>>;
  onWidthChange?: (key: ExpenseColumnKey, width: number) => void;
  sortBy?: ExpenseSortBy;
  sortOrder?: SortOrder;
  dateBasis?: DateBasis;
  onSort?: (sortBy: ExpenseSortBy, dateBasis?: DateBasis) => void;
}

function SortHeader({ label, active, order, onClick }: { label: string; active: boolean; order: SortOrder; onClick: () => void }) {
  const Icon = active ? (order === 'asc' ? IconChevronUp : IconChevronDown) : IconArrowsSort;
  return <UnstyledButton onClick={onClick} aria-label={`按${label}排序`}><span>{label} <Icon size={12} /></span></UnstyledButton>;
}

function ResizableHeader({ column, width, onWidthChange, children }: { column: ExpenseColumnKey; width: number; onWidthChange: (key: ExpenseColumnKey, width: number) => void; children: ReactNode }) {
  const [dragWidth, setDragWidth] = useState<number | null>(null);
  const shownWidth = dragWidth ?? width;
  const startResize = (event: ReactPointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.stopPropagation();
    const startX = event.clientX;
    const startWidth = shownWidth;
    const move = (moveEvent: PointerEvent) => setDragWidth(Math.min(600, Math.max(64, startWidth + moveEvent.clientX - startX)));
    const finish = (upEvent: PointerEvent) => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', finish);
      const next = Math.min(600, Math.max(64, startWidth + upEvent.clientX - startX));
      setDragWidth(null);
      onWidthChange(column, Math.round(next));
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', finish);
  };
  return (
    <Table.Th style={{ width: shownWidth, minWidth: shownWidth, maxWidth: shownWidth, position: 'relative' }}>
      {children}
      <button type="button" className="column-resize-handle" aria-label={`调整${column}列宽`} onPointerDown={startResize} />
    </Table.Th>
  );
}

function headerFor(column: ExpenseColumnKey, sortBy: ExpenseSortBy, sortOrder: SortOrder, dateBasis: DateBasis, onSort: (sortBy: ExpenseSortBy, dateBasis?: DateBasis) => void): ReactNode {
  switch (column) {
    case 'spent_on': return <SortHeader label="业务发生日期" active={sortBy === 'date' && dateBasis === 'spent'} order={sortOrder} onClick={() => onSort('date', 'spent')} />;
    case 'issued_on': return <SortHeader label="发票开票日期" active={sortBy === 'date' && dateBasis === 'invoiced'} order={sortOrder} onClick={() => onSort('date', 'invoiced')} />;
    case 'created_on': return <SortHeader label="凭证填报日期" active={sortBy === 'date' && dateBasis === 'created'} order={sortOrder} onClick={() => onSort('date', 'created')} />;
    case 'summary': return <SortHeader label="商家 · 摘要" active={sortBy === 'summary'} order={sortOrder} onClick={() => onSort('summary')} />;
    case 'category': return <SortHeader label="分类" active={sortBy === 'category'} order={sortOrder} onClick={() => onSort('category')} />;
    case 'amount': return <SortHeader label="总价" active={sortBy === 'amount'} order={sortOrder} onClick={() => onSort('amount')} />;
    case 'status': return <SortHeader label="状态" active={sortBy === 'status'} order={sortOrder} onClick={() => onSort('status')} />;
    case 'item_name': return '名称';
    case 'lab_platform': return '平台申请';
    case 'unit_price': return '单价';
    case 'quantity': return '数量';
    case 'invoice_no': return '发票号';
    case 'evidence': return '凭证';
    case 'batch': return '批次';
  }
}

export function ExpenseTable({ items, selectedIds, onToggle, onToggleAll, onOpen, onDropFiles, columns = DEFAULT_EXPENSE_COLUMNS, widths = DEFAULT_EXPENSE_COLUMN_WIDTHS, onWidthChange = () => undefined, sortBy = 'date', sortOrder = 'desc', dateBasis = 'spent', onSort = () => undefined }: ExpenseTableProps) {
  const selectedCount = items.filter((item) => selectedIds.includes(item.id)).length;
  const isAllSelected = items.length > 0 && selectedCount === items.length;
  return (
    <div className="table-scroll">
      <Table className="ledger-table resizable-ledger-table" miw={860} style={{ width: Math.max(860, 44 + columns.reduce((total, key) => total + widths[key], 0)), tableLayout: 'fixed' }}>
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
            {columns.map((column) => <ResizableHeader key={column} column={column} width={widths[column]} onWidthChange={onWidthChange}>{headerFor(column, sortBy, sortOrder, dateBasis, onSort)}</ResizableHeader>)}
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
              widths={widths}
            />
          ))}
        </Table.Tbody>
      </Table>
    </div>
  );
}
