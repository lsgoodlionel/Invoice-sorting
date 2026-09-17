import { Button, Group, Kbd, Paper, Text } from '@mantine/core';
import { formatCents } from '../../lib/money';

interface SelectionBarProps {
  count: number;
  totalCents: number;
  onAddToBatch: () => void;
  onClear: () => void;
}

export function SelectionBar({ count, totalCents, onAddToBatch, onClear }: SelectionBarProps) {
  return (
    <Paper className="selection-bar" px="lg" py="sm" radius={0}>
      <Group justify="space-between" wrap="nowrap">
        <Text size="sm">
          已选 <b className="num">{count}</b> 条 · 合计 <b className="num">{formatCents(totalCents)}</b>
        </Text>
        <Group gap="xs" wrap="nowrap">
          <Button variant="subtle" onClick={onClear} disabled={count === 0}>
            清除选择
          </Button>
          <Button variant="filled" onClick={onAddToBatch} disabled={count === 0} rightSection={<Kbd size="xs">B</Kbd>}>
            加入批次
          </Button>
        </Group>
      </Group>
    </Paper>
  );
}
