import { Button, Group, Table, Text } from '@mantine/core';
import type { ImportRow } from '../../api/types';
import { type ImportDraft, tallyDrafts } from '../../lib/importRows';
import { ImportRowView } from './ImportRowView';

interface ImportConfirmTableProps {
  rows: readonly ImportRow[];
  drafts: readonly ImportDraft[];
  onChange: (rowId: string, patch: Partial<ImportDraft>) => void;
  onConfirm: () => void;
  isSubmitting: boolean;
}

export function ImportConfirmTable({ rows, drafts, onChange, onConfirm, isSubmitting }: ImportConfirmTableProps) {
  const tally = tallyDrafts(drafts);
  return (
    <>
      <div className="table-scroll">
        <Table className="ledger-table" miw={900}>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>预览</Table.Th>
              <Table.Th>开票日期</Table.Th>
              <Table.Th>销售方</Table.Th>
              <Table.Th>金额</Table.Th>
              <Table.Th>分类</Table.Th>
              <Table.Th>匹配</Table.Th>
              <Table.Th>提示</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((row) => {
              const draft = drafts.find((item) => item.rowId === row.row_id);
              return draft ? (
                <ImportRowView key={row.row_id} row={row} draft={draft} onChange={(patch) => onChange(row.row_id, patch)} />
              ) : null;
            })}
          </Table.Tbody>
        </Table>
      </div>
      <Group justify="space-between">
        <Text size="sm" c="dimmed">
          新建 {tally.create} · 挂到已有 {tally.attach} · 跳过 {tally.skip}
          {tally.invalid > 0 && <Text span c="red" size="sm">　{tally.invalid} 行需要补全</Text>}
        </Text>
        <Button variant="filled" size="md" onClick={onConfirm} loading={isSubmitting} disabled={tally.invalid > 0}>
          全部确认
        </Button>
      </Group>
    </>
  );
}
