import { Alert, Button, Divider, Group, Stack, Text } from '@mantine/core';
import { modals } from '@mantine/modals';
import { IconAlertTriangle } from '@tabler/icons-react';
import { useState, type ReactNode } from 'react';
import { useBatchItems, useDeleteBatch, useReopenBatch } from '../../api/hooks/batches';
import type { BatchDetail } from '../../api/types';
import { formatCents } from '../../lib/money';
import { BatchInfoForm } from './BatchInfoForm';
import { BatchItemsSection } from './BatchItemsSection';
import { BatchStatusBadge } from './BatchStatusBadge';
import { ExportSection } from './ExportSection';
import { ReceivedModal } from './ReceivedModal';
import { SentModal } from './SentModal';

interface BatchDetailPanelProps {
  batch: BatchDetail;
  onOpenExpense: (id: number) => void;
  onDeleted: () => void;
  onAddExpenses: () => void;
}

function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Stack gap="xs">
      <Divider label={<span className="section-label">{label}</span>} labelPosition="left" />
      {children}
    </Stack>
  );
}

export function BatchDetailPanel({ batch, onOpenExpense, onDeleted, onAddExpenses }: BatchDetailPanelProps) {
  const [modal, setModal] = useState<'sent' | 'received' | null>(null);
  const items = useBatchItems();
  const remove = useDeleteBatch();
  const reopen = useReopenBatch(batch.id);
  const isDraft = batch.status === 'draft';
  const isFullyReceived = batch.status === 'received';

  const confirmReopen = () =>
    modals.openConfirmModal({
      title: '重新打开批次',
      children: <Text size="sm">将清空外发与到账登记，记录状态按凭证清单重新计算，之后可调整记录或重新外发。</Text>,
      labels: { confirm: '重新打开', cancel: '取消' },
      onConfirm: () => reopen.mutate(undefined),
    });

  const confirmDelete = () =>
    modals.openConfirmModal({
      title: '删除批次',
      children: <Text size="sm">批次中的记录会回到“未分批”。</Text>,
      labels: { confirm: '删除', cancel: '取消' },
      confirmProps: { color: 'red' },
      onConfirm: () => remove.mutate(batch.id, { onSuccess: onDeleted }),
    });

  return (
    <Stack gap="lg">
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Stack gap={2}>
          <Group gap="xs"><Text fw={700} size="xl">{batch.name}</Text><BatchStatusBadge status={batch.status} /></Group>
          <Text size="sm" c="dimmed" className="num">
            共 {batch.item_count} 条 · {formatCents(batch.total_cents)}
            {batch.sent_on && ` · 外发 ${batch.sent_on}${batch.receiver ? ` 至 ${batch.receiver}` : ''}`}
            {batch.received_on && ` · 到账 ${batch.received_on} ${formatCents(batch.received_cents)}`}
            {batch.created_by && ` · 创建人：${batch.created_by.display_name}`}
          </Text>
        </Stack>
        <Group gap="xs" wrap="nowrap">
          {isDraft && (
            <Button variant="outline" onClick={() => setModal('sent')} disabled={batch.item_count === 0}>标记已外发</Button>
          )}
          {!isDraft && (
            <Button variant="outline" onClick={() => setModal('received')} disabled={isFullyReceived}>登记到账</Button>
          )}
          {!isDraft && <Button variant="subtle" onClick={confirmReopen}>重新打开</Button>}
          {isDraft && <Button variant="subtle" color="red" onClick={confirmDelete}>删除</Button>}
        </Group>
      </Group>
      {batch.missing_item_count > 0 && (
        <Alert color="orange" icon={<IconAlertTriangle size={16} />} variant="light">
          {batch.missing_item_count} 条记录仍有必需凭证缺项，外发前请补齐或在详情中标记“不需要”。
        </Alert>
      )}
      <BatchInfoForm batch={batch} />
      <Section label="打包">
        <ExportSection batch={batch} />
      </Section>
      <BatchItemsSection
        expenses={batch.expenses}
        count={batch.item_count}
        isDraft={isDraft}
        onAdd={onAddExpenses}
        onOpen={onOpenExpense}
        onRemove={(id) => items.mutate({ id: batch.id, change: { remove: [id] } })}
      />
      <SentModal batch={batch} opened={modal === 'sent'} onClose={() => setModal(null)} />
      <ReceivedModal batch={batch} opened={modal === 'received'} onClose={() => setModal(null)} />
    </Stack>
  );
}
