import { ActionIcon, Button, Group, Image, Select, Stack, Table, Text, Tooltip } from '@mantine/core';
import { modals } from '@mantine/modals';
import { IconTrash } from '@tabler/icons-react';
import { useState } from 'react';
import { attachmentsApi, useDeleteAttachment, useUnassignedAttachments, useUpdateAttachment } from '../../api/hooks/attachments';
import type { Attachment, AttachmentKind } from '../../api/types';
import { ATTACHMENT_KIND_OPTIONS } from '../../lib/status';
import { ExpenseSelect } from '../ExpenseSelect';

function UnassignedRow({ attachment }: { attachment: Attachment }) {
  const [expenseId, setExpenseId] = useState<number | null>(null);
  const [kind, setKind] = useState<AttachmentKind>(attachment.kind);
  const update = useUpdateAttachment();
  const remove = useDeleteAttachment();
  const confirmDelete = () =>
    modals.openConfirmModal({
      title: '删除附件',
      children: <Text size="sm">「{attachment.original_name}」将移入回收站。</Text>,
      labels: { confirm: '删除', cancel: '取消' },
      confirmProps: { color: 'red' },
      onConfirm: () => remove.mutate(attachment.id),
    });
  return (
    <Table.Tr>
      <Table.Td w={56}>
        <a href={attachment.url} target="_blank" rel="noreferrer" aria-label={`打开 ${attachment.original_name}`}>
          <Image src={attachmentsApi.thumbnailUrl(attachment.id)} w={40} h={40} fit="cover" radius="xs" alt="" />
        </a>
      </Table.Td>
      <Table.Td><Text size="sm" truncate maw={220} title={attachment.original_name}>{attachment.original_name}</Text></Table.Td>
      <Table.Td><Select size="xs" w={130} aria-label="附件类型" data={ATTACHMENT_KIND_OPTIONS} value={kind} allowDeselect={false} onChange={(v) => v && setKind(v as AttachmentKind)} /></Table.Td>
      <Table.Td><ExpenseSelect size="xs" w={300} aria-label="目标支出" value={expenseId} onChange={setExpenseId} /></Table.Td>
      <Table.Td>
        <Group gap={4} wrap="nowrap">
          <Button size="compact-sm" variant="outline" disabled={expenseId === null} loading={update.isPending}
            onClick={() => expenseId !== null && update.mutate({ id: attachment.id, patch: { expense_id: expenseId, kind } })}>
            归属
          </Button>
          <Tooltip label="删除">
            <ActionIcon variant="subtle" color="red" aria-label="删除附件" onClick={confirmDelete}><IconTrash size={16} /></ActionIcon>
          </Tooltip>
        </Group>
      </Table.Td>
    </Table.Tr>
  );
}

export function UnassignedList() {
  const { data = [] } = useUnassignedAttachments();
  return (
    <Stack gap="xs" id="unassigned">
      <Group justify="space-between">
        <Text className="section-label">待归属附件 {data.length}</Text>
      </Group>
      {data.length === 0 ? (
        <Text size="sm" c="dimmed">没有待归属的附件。订单截图、支付记录等非发票文件导入后会出现在这里。</Text>
      ) : (
        <div className="table-scroll">
          <Table className="ledger-table" miw={760}>
            <Table.Tbody>
              {data.map((attachment) => <UnassignedRow key={attachment.id} attachment={attachment} />)}
            </Table.Tbody>
          </Table>
        </div>
      )}
    </Stack>
  );
}
