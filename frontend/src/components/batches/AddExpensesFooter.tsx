import { Alert, Button, Group, Stack, Text } from '@mantine/core';
import { formatCents } from '../../lib/money';
import type { BatchAddConflict } from './useAddToBatch';

interface AddExpensesFooterProps {
  count: number;
  totalCents: number;
  conflict: BatchAddConflict | null;
  isPending: boolean;
  onClose: () => void;
  onSubmit: () => void;
  onConfirm: () => void;
}

/** 已选汇总 + 409 冲突说明 + 主操作（加入批次 / 仍然加入）。 */
export function AddExpensesFooter({ count, totalCents, conflict, isPending, onClose, onSubmit, onConfirm }: AddExpensesFooterProps) {
  return (
    <Stack gap="sm">
      {conflict && <Alert color="orange" title="需要确认">{conflict.message}</Alert>}
      <Group justify="space-between" wrap="nowrap">
        <Text size="sm" data-testid="selection-summary">
          已选 <b className="num">{count}</b> 条 · 合计 <b className="num">{formatCents(totalCents)}</b>
        </Text>
        <Group gap="xs" wrap="nowrap">
          <Button variant="subtle" onClick={onClose}>取消</Button>
          {conflict ? (
            <Button variant="filled" color="orange" loading={isPending} onClick={onConfirm}>仍然加入</Button>
          ) : (
            <Button variant="filled" disabled={count === 0} loading={isPending} onClick={onSubmit}>加入批次</Button>
          )}
        </Group>
      </Group>
    </Stack>
  );
}
