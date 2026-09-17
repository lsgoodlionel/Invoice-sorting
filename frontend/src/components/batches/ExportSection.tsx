import { Anchor, Button, Group, Radio, Stack, Table, Text } from '@mantine/core';
import { IconDownload } from '@tabler/icons-react';
import dayjs from 'dayjs';
import { useState } from 'react';
import { useExportBatch } from '../../api/hooks/batches';
import type { BatchDetail, ExportLayout } from '../../api/types';
import { formatCents } from '../../lib/money';

const LAYOUT_LABELS: Record<ExportLayout, string> = { by_expense: '按支出分组', by_kind: '按材料类型分组' };

export function ExportSection({ batch }: { batch: BatchDetail }) {
  const [layout, setLayout] = useState<ExportLayout>('by_expense');
  const exportBatch = useExportBatch(batch.id);
  const isEmpty = batch.item_count === 0 || batch.expenses.length === 0;
  return (
    <Stack gap="sm">
      <Group gap="lg" align="center">
        <Radio.Group value={layout} onChange={(value) => setLayout(value === 'by_kind' ? 'by_kind' : 'by_expense')} aria-label="打包结构">
          <Group gap="md">
            <Radio value="by_expense" label={LAYOUT_LABELS.by_expense} />
            <Radio value="by_kind" label={LAYOUT_LABELS.by_kind} />
          </Group>
        </Radio.Group>
        <Button variant={isEmpty ? 'default' : 'filled'} leftSection={<IconDownload size={16} />} disabled={isEmpty}
          loading={exportBatch.isPending} onClick={() => exportBatch.mutate(layout)}>
          生成资料包
        </Button>
        {isEmpty && <Text size="sm" c="dimmed">先添加记录再打包</Text>}
      </Group>
      {batch.exports.length > 0 && (
        <Table className="ledger-table">
          <Table.Thead>
            <Table.Tr><Table.Th>时间</Table.Th><Table.Th>文件</Table.Th><Table.Th>结构</Table.Th><Table.Th ta="right">条数 · 金额</Table.Th></Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {batch.exports.map((record) => (
              <Table.Tr key={record.id}>
                <Table.Td className="num">{dayjs(record.created_at).format('MM-DD HH:mm')}</Table.Td>
                <Table.Td><Anchor href={record.url || `/api/exports/${record.id}/file`} size="sm" download={record.file_name}>{record.file_name}</Anchor></Table.Td>
                <Table.Td><Text size="xs">{LAYOUT_LABELS[record.layout]}</Text></Table.Td>
                <Table.Td ta="right" className="num">{record.item_count} · {formatCents(record.total_cents)}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  );
}
