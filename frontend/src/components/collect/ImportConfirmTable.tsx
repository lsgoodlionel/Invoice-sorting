import { Button, Group, Table, Text } from '@mantine/core';
import type { ImportRow } from '../../api/types';
import { type ImportDraft, tallyDrafts } from '../../lib/importRows';
import { REGION_HELP } from '../../lib/region';
import { HelpLabel } from '../HelpLabel';
import { ImportRowView } from './ImportRowView';

interface ImportConfirmTableProps {
  rows: readonly ImportRow[];
  drafts: readonly ImportDraft[];
  onChange: (rowId: string, patch: Partial<ImportDraft>) => void;
  onConfirm: () => void;
  isSubmitting: boolean;
}

const TABLE_MIN_WIDTH = 1280;
const MATCH_HELP =
  '匹配：如果之前手动『记一笔』记过这笔支出（状态为已支出、金额相同、日期相差 7 天内），发票会直接挂到那条记录上，而不是重复新建。可改为新建或跳过。';

function TallyText({ drafts }: { drafts: readonly ImportDraft[] }) {
  const tally = tallyDrafts(drafts);
  return (
    <Text size="sm" data-testid="import-tally">
      新建 <b className="num">{tally.create}</b> · 挂到已有记录 <b className="num">{tally.attach}</b> · 跳过 <b className="num">{tally.skip}</b>
      {tally.invalid > 0 && <Text span c="red" size="sm">　{tally.invalid} 行需要补全</Text>}
    </Text>
  );
}

export function ImportConfirmTable({ rows, drafts, onChange, onConfirm, isSubmitting }: ImportConfirmTableProps) {
  const hasInvalid = tallyDrafts(drafts).invalid > 0;
  return (
    <>
      <TallyText drafts={drafts} />
      <div className="table-scroll">
        <Table className="ledger-table" miw={TABLE_MIN_WIDTH}>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>预览</Table.Th>
              <Table.Th>开票日期</Table.Th>
              <Table.Th>销售方</Table.Th>
              <Table.Th>金额</Table.Th>
              <Table.Th>分类</Table.Th>
              <Table.Th><HelpLabel label="地区" help={REGION_HELP} /></Table.Th>
              <Table.Th>网购</Table.Th>
              <Table.Th><HelpLabel label="匹配" help={MATCH_HELP} /></Table.Th>
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
      <Group justify="flex-end">
        <Button variant="filled" size="md" onClick={onConfirm} loading={isSubmitting} disabled={hasInvalid}>
          全部确认
        </Button>
      </Group>
    </>
  );
}
