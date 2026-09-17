import { Button, Group, Stack, Text, Textarea } from '@mantine/core';
import { modals } from '@mantine/modals';
import { useState } from 'react';
import { useDeleteExpense, useSetExpenseStatus } from '../../api/hooks/expenses';
import type { ExpenseDetail } from '../../api/types';

interface DangerZoneProps {
  expense: ExpenseDetail;
  onDeleted: () => void;
}

export function DangerZone({ expense, onDeleted }: DangerZoneProps) {
  const [reason, setReason] = useState('');
  const setStatus = useSetExpenseStatus(expense.id);
  const remove = useDeleteExpense();
  const isVoid = expense.status === 'void';

  const confirmDelete = () =>
    modals.openConfirmModal({
      title: '删除这条支出？',
      children: <Text size="sm">记录将被删除，附件文件移入回收站。</Text>,
      labels: { confirm: '删除', cancel: '取消' },
      confirmProps: { color: 'red' },
      onConfirm: () => remove.mutate(expense.id, { onSuccess: onDeleted }),
    });

  return (
    <Stack gap="xs" className="danger-zone">
      {!isVoid && (
        <Group align="flex-end" wrap="nowrap">
          <Textarea
            label="作废原因"
            placeholder="如：个人承担、重复、退货"
            autosize
            minRows={1}
            style={{ flex: 1 }}
            value={reason}
            onChange={(e) => setReason(e.currentTarget.value)}
          />
          <Button
            color="red"
            variant="outline"
            disabled={!reason.trim()}
            loading={setStatus.isPending}
            onClick={() => setStatus.mutate({ status: 'void', note: reason.trim() }, { onSuccess: () => setReason('') })}
          >
            作废
          </Button>
        </Group>
      )}
      {isVoid && (
        <Button variant="outline" w="fit-content" onClick={() => setStatus.mutate({ status: null })}>
          取消作废（恢复自动状态）
        </Button>
      )}
      <Button color="red" variant="subtle" w="fit-content" onClick={confirmDelete} loading={remove.isPending}>
        删除记录
      </Button>
    </Stack>
  );
}
