import { Checkbox, Table } from '@mantine/core';
import type { Attachment } from '../../../api/types';
import { UnassignedRow } from './UnassignedRow';

interface UnassignedTableProps {
  items: readonly Attachment[];
  selectedIds: readonly number[];
  onToggle: (id: number) => void;
  onToggleAll: (checked: boolean) => void;
  onAssign: (id: number) => void;
  onPreview: (attachment: Attachment) => void;
}

const TABLE_MIN_WIDTH = 1180;

export function UnassignedTable({ items, selectedIds, onToggle, onToggleAll, onAssign, onPreview }: UnassignedTableProps) {
  const selectedCount = selectedIds.length;
  const isAllSelected = items.length > 0 && selectedCount === items.length;
  return (
    <div className="table-scroll">
      <Table className="ledger-table" miw={TABLE_MIN_WIDTH}>
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
            <Table.Th>预览</Table.Th>
            <Table.Th>文件名</Table.Th>
            <Table.Th>类型</Table.Th>
            <Table.Th>识别信息</Table.Th>
            <Table.Th>建议</Table.Th>
            <Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {items.map((attachment) => (
            <UnassignedRow
              key={attachment.id}
              attachment={attachment}
              isSelected={selectedIds.includes(attachment.id)}
              onToggle={onToggle}
              onAssign={onAssign}
              onPreview={onPreview}
            />
          ))}
        </Table.Tbody>
      </Table>
    </div>
  );
}
