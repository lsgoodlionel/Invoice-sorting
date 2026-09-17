import { Button, Group, Stack, Text } from '@mantine/core';
import { useSetExpenseStatus } from '../../api/hooks/expenses';
import type { ExpenseDetail, ExpenseStatus } from '../../api/types';
import { STATUS_META } from '../../lib/status';
import { StatusBadge } from '../StatusBadge';
import { StatusStepper } from '../StatusStepper';

export function StatusSection({ expense }: { expense: ExpenseDetail }) {
  const setStatus = useSetExpenseStatus(expense.id);
  const handleStep = (status: ExpenseStatus) => {
    if (status !== expense.status) setStatus.mutate({ status });
  };
  return (
    <Stack gap={6}>
      <StatusStepper status={expense.status} onStepClick={handleStep} />
      <Group gap="xs">
        {(expense.status === 'void' || expense.status_manual) && <StatusBadge status={expense.status} manual={expense.status_manual} size="xs" />}
        {expense.status === 'void' && expense.void_reason && <Text size="xs" c="dimmed">原因：{expense.void_reason}</Text>}
        {expense.status_manual && (
          <Button size="compact-xs" variant="subtle" loading={setStatus.isPending} onClick={() => setStatus.mutate({ status: null })}>
            恢复自动
          </Button>
        )}
        {!expense.status_manual && expense.status !== 'void' && (
          <Text size="xs" c="dimmed">当前「{STATUS_META[expense.status].label}」由系统自动推进，点击步骤可手动设置</Text>
        )}
      </Group>
    </Stack>
  );
}
