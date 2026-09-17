import { ActionIcon, Anchor, Button, Group, Radio, Stack, Table, Text, Tooltip } from '@mantine/core';
import { modals } from '@mantine/modals';
import { IconDownload, IconTrash } from '@tabler/icons-react';
import dayjs from 'dayjs';
import { useState } from 'react';
import { useDeleteExport, useExportBatch } from '../../api/hooks/batches';
import type { BatchDetail, ExportLayout, ExportRecord } from '../../api/types';
import { formatCents } from '../../lib/money';

const LAYOUT_LABELS: Record<ExportLayout, string> = { by_expense: '按支出分组', by_kind: '按材料类型分组' };

const LAYOUT_HINTS: Record<ExportLayout, string> = {
  by_expense: '支撑材料按记录分文件夹，一笔支出的材料放在一个文件夹，便于逐笔核对、打印装订',
  by_kind: '支撑材料按类型分文件夹（订单明细、支付记录…），同类材料放在一起，便于按类型上传报销系统',
};

function ExportHistoryRow({ record }: { record: ExportRecord }) {
  const remove = useDeleteExport();
  const confirmDelete = () =>
    modals.openConfirmModal({
      title: '删除资料包',
      children: <Text size="sm">文件将被永久删除：{record.file_name}。记录与凭证不受影响，可随时重新生成。</Text>,
      labels: { confirm: '删除', cancel: '取消' },
      confirmProps: { color: 'red' },
      onConfirm: () => remove.mutate(record.id),
    });
  return (
    <Table.Tr>
      <Table.Td className="num">{dayjs(record.created_at).format('MM-DD HH:mm')}</Table.Td>
      <Table.Td><Anchor href={record.url || `/api/exports/${record.id}/file`} size="sm" download={record.file_name}>{record.file_name}</Anchor></Table.Td>
      <Table.Td><Text size="xs">{LAYOUT_LABELS[record.layout]}</Text></Table.Td>
      <Table.Td ta="right" className="num">{record.item_count} · {formatCents(record.total_cents)}</Table.Td>
      <Table.Td><Text size="xs" truncate maw={96}>{record.created_by?.display_name ?? '—'}</Text></Table.Td>
      <Table.Td w={40}>
        <Tooltip label="删除资料包">
          <ActionIcon variant="subtle" color="red" aria-label={`删除资料包 ${record.file_name}`} loading={remove.isPending} onClick={confirmDelete}>
            <IconTrash size={16} />
          </ActionIcon>
        </Tooltip>
      </Table.Td>
    </Table.Tr>
  );
}

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
      <Text size="xs" c="dimmed">
        {LAYOUT_HINTS[layout]}。两种方式的汇总表、打印版 PDF 与发票原件（文件名含序号、分类、金额、商家）相同。
      </Text>
      {batch.exports.length > 0 && (
        <Table className="ledger-table">
          <Table.Thead>
            <Table.Tr><Table.Th>时间</Table.Th><Table.Th>文件</Table.Th><Table.Th>结构</Table.Th><Table.Th ta="right">条数 · 金额</Table.Th><Table.Th>生成人</Table.Th><Table.Th /></Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {batch.exports.map((record) => <ExportHistoryRow key={record.id} record={record} />)}
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  );
}
