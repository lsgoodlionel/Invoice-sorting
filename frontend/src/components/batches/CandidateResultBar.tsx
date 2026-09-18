import { Checkbox, Group, Text } from '@mantine/core';
import { formatCents } from '../../lib/money';

interface CandidateResultBarProps {
  count: number;
  totalCents: number;
  checkedCount: number;
  onToggleAll: (checked: boolean) => void;
}

/** 列表上方：全选当前筛选结果 + 符合条件条数与合计。 */
export function CandidateResultBar({ count, totalCents, checkedCount, onToggleAll }: CandidateResultBarProps) {
  const isAllChecked = count > 0 && checkedCount === count;
  return (
    <Group justify="space-between" wrap="nowrap" gap="sm">
      <Checkbox
        size="xs"
        label="全选当前筛选结果"
        checked={isAllChecked}
        indeterminate={checkedCount > 0 && !isAllChecked}
        disabled={count === 0}
        onChange={() => onToggleAll(!isAllChecked)}
      />
      <Text size="sm" c="dimmed" data-testid="result-summary">
        符合条件 <b className="num">{count}</b> 条 · 合计 <b className="num">{formatCents(totalCents)}</b>
      </Text>
    </Group>
  );
}
