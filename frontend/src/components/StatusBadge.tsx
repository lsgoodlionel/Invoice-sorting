import { Badge, Group, Tooltip } from '@mantine/core';
import type { ExpenseStatus } from '../api/types';
import { STATUS_META } from '../lib/status';

interface StatusBadgeProps {
  status: ExpenseStatus;
  manual?: boolean;
  size?: 'xs' | 'sm' | 'md';
}

export function StatusBadge({ status, manual = false, size = 'sm' }: StatusBadgeProps) {
  const meta = STATUS_META[status];
  return (
    <Group gap={4} wrap="nowrap" display="inline-flex">
      <Badge
        size={size}
        color={meta.color}
        variant={meta.variant}
        leftSection={status === 'void' ? undefined : <span aria-hidden>●</span>}
        className={status === 'void' ? 'status-void' : undefined}
        data-status={status}
      >
        {meta.label}
      </Badge>
      {manual && (
        <Tooltip label="状态为手动设置，不会自动变化">
          <Badge size="xs" variant="outline" color="paper.6">
            手动
          </Badge>
        </Tooltip>
      )}
    </Group>
  );
}
