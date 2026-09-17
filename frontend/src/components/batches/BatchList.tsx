import { Group, Stack, Text, UnstyledButton } from '@mantine/core';
import type { Batch } from '../../api/types';
import { formatCents } from '../../lib/money';
import { BatchStatusBadge } from './BatchStatusBadge';

interface BatchListProps {
  batches: readonly Batch[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}

export function BatchList({ batches, selectedId, onSelect }: BatchListProps) {
  if (batches.length === 0) {
    return <Text size="sm" c="dimmed" p="sm">还没有批次。点上方“新建批次”，再从批次里“添加记录”。</Text>;
  }
  return (
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
  );
}
