import { ActionIcon, Button, Checkbox, Group, Image, Select, Table, Text, Tooltip, UnstyledButton } from '@mantine/core';
import { modals } from '@mantine/modals';
import { IconTrash } from '@tabler/icons-react';
import { attachmentsApi, useDeleteAttachment, useUpdateAttachment } from '../../../api/hooks/attachments';
import type { Attachment, AttachmentKind } from '../../../api/types';
import { ATTACHMENT_KIND_OPTIONS } from '../../../lib/status';
import { CandidateSuggestion } from './CandidateSuggestion';
import { RecognitionSummary } from './RecognitionSummary';

interface UnassignedRowProps {
  attachment: Attachment;
  isSelected: boolean;
  onToggle: (id: number) => void;
  onAssign: (id: number) => void;
  onPreview: (attachment: Attachment) => void;
}

const THUMB_SIZE = 40;

export function UnassignedRow({ attachment, isSelected, onToggle, onAssign, onPreview }: UnassignedRowProps) {
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
  const changeKind = (value: string | null) => {
    if (value && value !== attachment.kind) update.mutate({ id: attachment.id, patch: { kind: value as AttachmentKind } });
  };
  return (
    <Table.Tr data-selected={isSelected} data-testid={`unassigned-row-${attachment.id}`}>
      <Table.Td w={36}>
        <Checkbox size="xs" aria-label={`选择 ${attachment.original_name}`} checked={isSelected} onChange={() => onToggle(attachment.id)} />
      </Table.Td>
      <Table.Td w={56}>
        <UnstyledButton aria-label={`预览 ${attachment.original_name}`} onClick={() => onPreview(attachment)}>
          <Image src={attachmentsApi.thumbnailUrl(attachment.id)} w={THUMB_SIZE} h={THUMB_SIZE} fit="cover" radius="xs" alt="" />
        </UnstyledButton>
      </Table.Td>
      <Table.Td><Text size="sm" truncate maw={220} title={attachment.original_name}>{attachment.original_name}</Text></Table.Td>
      <Table.Td>
        <Select size="xs" w={130} aria-label="附件类型" data={ATTACHMENT_KIND_OPTIONS} value={attachment.kind} allowDeselect={false} onChange={changeKind} />
      </Table.Td>
      <Table.Td><RecognitionSummary attachment={attachment} /></Table.Td>
      <CandidateSuggestion attachmentId={attachment.id} />
      <Table.Td>
        <Group gap={4} wrap="nowrap" justify="flex-end">
          <Button size="compact-sm" variant="subtle" onClick={() => onAssign(attachment.id)}>归属到…</Button>
          <Tooltip label="删除">
            <ActionIcon variant="subtle" color="red" aria-label="删除附件" onClick={confirmDelete}><IconTrash size={16} /></ActionIcon>
          </Tooltip>
        </Group>
      </Table.Td>
    </Table.Tr>
  );
}
