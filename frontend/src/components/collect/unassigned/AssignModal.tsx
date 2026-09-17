import { Button, Group, Modal, Select, Stack, Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useEffect, useState } from 'react';
import { useBulkAssignAttachments } from '../../../api/hooks/attachments';
import type { AttachmentKind } from '../../../api/types';
import { ATTACHMENT_KIND_OPTIONS } from '../../../lib/status';
import { ExpenseSelect } from '../../ExpenseSelect';

interface AssignModalProps {
  /** 要归属的附件 id；null 表示关闭 */
  ids: readonly number[] | null;
  onClose: () => void;
  onAssigned: () => void;
}

export function AssignModal({ ids, onClose, onAssigned }: AssignModalProps) {
  const assign = useBulkAssignAttachments();
  const [expenseId, setExpenseId] = useState<number | null>(null);
  const [kind, setKind] = useState<AttachmentKind | null>(null);
  const count = ids?.length ?? 0;

  useEffect(() => {
    if (ids === null) return;
    setExpenseId(null);
    setKind(null);
  }, [ids]);

  const submit = () => {
    if (ids === null || expenseId === null) return;
    assign.mutate(
      { ids: [...ids], expense_id: expenseId, ...(kind ? { kind } : {}) },
      {
        onSuccess: () => {
          notifications.show({ color: 'ink', message: `已将 ${count} 个附件归属到 #${expenseId}` });
          onAssigned();
          onClose();
        },
      },
    );
  };

  return (
    <Modal opened={ids !== null} onClose={onClose} title={`归属 ${count} 个附件到记录`}>
      <Stack gap="sm">
        <Text size="xs" c="dimmed">挂到记录后，文件会出现在该记录的附件与凭证清单中；如需新建记录，请先“快速记一笔”。</Text>
        <ExpenseSelect label="目标记录" aria-label="目标记录" value={expenseId} onChange={setExpenseId} />
        <Select
          label="统一设置类型（可选）"
          aria-label="统一设置类型"
          placeholder="保持各自类型"
          clearable
          data={ATTACHMENT_KIND_OPTIONS}
          value={kind}
          onChange={(value) => setKind(value as AttachmentKind | null)}
        />
        <Group justify="flex-end">
          <Button variant="subtle" onClick={onClose}>取消</Button>
          <Button variant="filled" disabled={expenseId === null} loading={assign.isPending} onClick={submit}>归属</Button>
        </Group>
      </Stack>
    </Modal>
  );
}
