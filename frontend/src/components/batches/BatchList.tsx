import { Group, Stack, Text, UnstyledButton } from '@mantine/core';
import type { Batch } from '../../api/types';
import { formatCents, sumCents } from '../../lib/money';
import { BatchStatusBadge } from './BatchStatusBadge';

interface BatchListProps {
  /** 筛选后的批次 */
  batches: readonly Batch[];
  /** 筛选前的批次总数（区分“还没有批次”与“无符合筛选的批次”） */
  totalCount: number;
  selectedId: number | null;
  /** 当前选中的批次被筛选排除（详情仍显示） */
  isSelectedHidden: boolean;
  onSelect: (id: number) => void;
}

function BatchListSummary({ batches, isSelectedHidden }: Pick<BatchListProps, 'batches' | 'isSelectedHidden'>) {
  return (
    <Stack gap={2} px={12} py={6} className="batch-list-summary">
      <Text size="xs" c="dimmed" className="num" data-testid="batch-list-summary">
        {batches.length} 个批次 · 合计 {formatCents(sumCents(batches.map((batch) => batch.total_cents)))}
      </Text>
      {isSelectedHidden && <Text size="xs" c="orange.8">当前批次不在筛选结果中</Text>}
    </Stack>
  );
}

export function BatchList({ batches, totalCount, selectedId, isSelectedHidden, onSelect }: BatchListProps) {
  if (totalCount === 0) {
    return <Text size="sm" c="dimmed" p="sm">还没有批次。点上方“新建批次”，再从批次里“添加记录”。</Text>;
  }
  return (
    <Stack gap={0}>
      <BatchListSummary batches={batches} isSelectedHidden={isSelectedHidden} />
      {batches.length === 0 && <Text size="sm" c="dimmed" p="sm">没有符合筛选条件的批次。</Text>}
      <Stack gap={0} role="list">
        {batches.map((batch) => (
          <UnstyledButton
            key={batch.id}
            role="listitem"
            className="batch-item"
            data-active={batch.id === selectedId || undefined}
            aria-current={batch.id === selectedId || undefined}
            onClick={() => onSelect(batch.id)}
          >
            <Group justify="space-between" wrap="nowrap" gap="xs">
              <Text size="sm" fw={600} truncate>{batch.name}</Text>
              <BatchStatusBadge status={batch.status} />
            </Group>
            <Group justify="space-between" gap="xs">
              <Text size="xs" c="dimmed">{batch.item_count} 条{batch.project_name ? ` · ${batch.project_name}` : ''}</Text>
              <Text size="sm" className="num">{formatCents(batch.total_cents)}</Text>
            </Group>
          </UnstyledButton>
        ))}
      </Stack>
    </Stack>
  );
}
