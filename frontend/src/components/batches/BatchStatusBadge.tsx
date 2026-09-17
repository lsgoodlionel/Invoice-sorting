import { Badge } from '@mantine/core';
import type { BatchStatus } from '../../api/types';
import { BATCH_STATUS_META } from '../../lib/status';

export function BatchStatusBadge({ status }: { status: BatchStatus }) {
  const meta = BATCH_STATUS_META[status];
  return (
    <Badge size="sm" color={meta.color} variant={status === 'received' ? 'filled' : 'light'}>
      {meta.label}
    </Badge>
  );
}
