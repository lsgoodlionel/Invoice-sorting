import { Group, Text, UnstyledButton } from '@mantine/core';
import type { ExpenseStatus, StatusCounts } from '../../api/types';
import { formatCents } from '../../lib/money';
import { ALL_STATUSES, STATUS_META } from '../../lib/status';

interface StatusGroupBarProps {
  counts: StatusCounts;
  selected: readonly ExpenseStatus[];
  onToggle: (status: ExpenseStatus) => void;
}

/** 状态分组条：每个状态显示数量与金额，点击切换筛选。 */
export function StatusGroupBar({ counts, selected, onToggle }: StatusGroupBarProps) {
  return (
    <Group gap={0} wrap="nowrap" className="status-bar" role="group" aria-label="按状态筛选">
      {ALL_STATUSES.map((status) => {
        const meta = STATUS_META[status];
        const entry = counts[status] ?? { count: 0, amount_cents: 0 };
        const isActive = selected.includes(status);
        return (
          <UnstyledButton
            key={status}
            className="status-cell"
            data-active={isActive || undefined}
            aria-pressed={isActive}
            data-testid={`status-group-${status}`}
            onClick={() => onToggle(status)}
          >
            <Text size="xs" c="dimmed" className={status === 'void' ? 'status-void' : undefined}>
              <span className="status-dot" data-status={status} aria-hidden />
              {meta.shortLabel}
            </Text>
            <Group gap={6} align="baseline" wrap="nowrap">
              <Text fw={700} size="lg" className="num" data-testid={`status-count-${status}`}>
                {entry.count}
              </Text>
              <Text size="xs" c="dimmed" className="num">
                {formatCents(entry.amount_cents)}
              </Text>
            </Group>
          </UnstyledButton>
        );
      })}
    </Group>
  );
}
