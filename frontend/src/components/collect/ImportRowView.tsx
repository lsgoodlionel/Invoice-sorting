import { Image, Select, Stack, Table, Text, TextInput, Tooltip } from '@mantine/core';
import { DateInput } from '@mantine/dates';
import { IconAlertTriangle } from '@tabler/icons-react';
import { attachmentsApi } from '../../api/hooks/attachments';
import type { ImportAction, ImportRow } from '../../api/types';
import { draftProblems, type ImportDraft } from '../../lib/importRows';
import { formatCents } from '../../lib/money';
import { CategorySelect } from '../CategorySelect';
import { MoneyInput } from '../MoneyInput';

interface ImportRowViewProps {
  row: ImportRow;
  draft: ImportDraft;
  onChange: (patch: Partial<ImportDraft>) => void;
}

const THUMB_SIZE = 44;

function actionOptions(row: ImportRow) {
  const base = [
    { value: 'create', label: '新建' },
    { value: 'skip', label: '跳过' },
  ];
  if (!row.match) return base;
  const { expense_id, merchant, amount_cents } = row.match;
  return [{ value: 'attach', label: `挂到已支出 #${expense_id} ${merchant} ${formatCents(amount_cents)}` }, ...base];
}

export function ImportRowView({ row, draft, onChange }: ImportRowViewProps) {
  const hasWarnings = row.warnings.length > 0;
  const problems = draftProblems(draft);
  const isSkipped = draft.action === 'skip';
  return (
    <Table.Tr className={hasWarnings ? 'row-warning' : undefined} data-testid={`import-row-${row.row_id}`} style={{ opacity: isSkipped ? 0.5 : 1 }}>
      <Table.Td>
        <a href={row.attachment.url} target="_blank" rel="noreferrer" aria-label={`打开 ${row.attachment.original_name}`}>
          <Image src={attachmentsApi.thumbnailUrl(row.attachment.id)} w={THUMB_SIZE} h={THUMB_SIZE} fit="cover" radius="xs" alt="" />
        </a>
      </Table.Td>
      <Table.Td>
        <DateInput size="xs" w={118} aria-label="开票日期" valueFormat="YYYY-MM-DD" value={draft.spentOn} onChange={(spentOn) => onChange({ spentOn })} disabled={isSkipped} />
      </Table.Td>
      <Table.Td>
        <Stack gap={2}>
          <TextInput size="xs" aria-label="销售方" value={draft.merchant} onChange={(e) => onChange({ merchant: e.currentTarget.value })} disabled={isSkipped} />
          <Text size="xs" c="dimmed" truncate maw={220} title={row.attachment.original_name}>{draft.summary || row.attachment.original_name}</Text>
        </Stack>
      </Table.Td>
      <Table.Td>
        <MoneyInput size="xs" w={120} aria-label="金额" cents={draft.amountCents} onCentsChange={(amountCents) => onChange({ amountCents })} disabled={isSkipped} />
      </Table.Td>
      <Table.Td>
        <CategorySelect size="xs" w={120} aria-label="分类" value={draft.categoryId} onChange={(categoryId) => onChange({ categoryId })} disabled={isSkipped} />
      </Table.Td>
      <Table.Td>
        <Select
          size="xs"
          w={row.match ? 240 : 100}
          aria-label="匹配"
          data={actionOptions(row)}
          value={draft.action}
          allowDeselect={false}
          onChange={(value) => value && onChange({ action: value as ImportAction })}
        />
      </Table.Td>
      <Table.Td>
        {(hasWarnings || problems.length > 0) && (
          <Tooltip label={[...row.warnings, ...problems].join('；')} multiline w={240}>
            <Text size="xs" c={problems.length ? 'red' : 'orange.8'} style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
              <IconAlertTriangle size={14} />
              {[...row.warnings, ...problems][0]}
            </Text>
          </Tooltip>
        )}
      </Table.Td>
    </Table.Tr>
  );
}
