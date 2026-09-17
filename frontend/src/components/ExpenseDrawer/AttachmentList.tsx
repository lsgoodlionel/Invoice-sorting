import { ActionIcon, Collapse, Group, Select, Stack, Text, Tooltip } from '@mantine/core';
import { modals } from '@mantine/modals';
import { IconArrowBackUp, IconEye, IconTrash } from '@tabler/icons-react';
import { useState } from 'react';
import { useDeleteAttachment, useUpdateAttachment } from '../../api/hooks/attachments';
import type { Attachment, AttachmentKind } from '../../api/types';
import { ATTACHMENT_KIND_OPTIONS } from '../../lib/status';
import { AttachmentPreview } from '../AttachmentPreview';

const KB = 1024;

function formatSize(bytes: number): string {
  return bytes >= KB * KB ? `${(bytes / KB / KB).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / KB))} KB`;
}

function AttachmentRow({ attachment }: { attachment: Attachment }) {
  const [isPreviewOpen, setPreviewOpen] = useState(false);
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
    <Stack gap={4} className="attachment-row">
      <Group gap="xs" wrap="nowrap">
        <Text size="sm" truncate style={{ flex: 1 }} title={attachment.original_name}>{attachment.original_name}</Text>
        <Text size="xs" c="dimmed" className="num">{formatSize(attachment.size)}</Text>
        <Select
          size="xs"
          w={130}
          aria-label="附件类型"
          data={ATTACHMENT_KIND_OPTIONS}
          value={attachment.kind}
          allowDeselect={false}
          onChange={(kind) => kind && update.mutate({ id: attachment.id, patch: { kind: kind as AttachmentKind } })}
        />
        <Tooltip label="预览">
          <ActionIcon variant="subtle" aria-label="预览" onClick={() => setPreviewOpen((v) => !v)}><IconEye size={16} /></ActionIcon>
        </Tooltip>
        <Tooltip label="移回待归属">
          <ActionIcon variant="subtle" aria-label="移回待归属" onClick={() => update.mutate({ id: attachment.id, patch: { expense_id: null } })}>
            <IconArrowBackUp size={16} />
          </ActionIcon>
        </Tooltip>
        <Tooltip label="删除">
          <ActionIcon variant="subtle" color="red" aria-label="删除附件" onClick={confirmDelete}><IconTrash size={16} /></ActionIcon>
        </Tooltip>
      </Group>
      <Collapse expanded={isPreviewOpen}>{isPreviewOpen && <AttachmentPreview attachment={attachment} />}</Collapse>
    </Stack>
  );
}

export function AttachmentList({ attachments }: { attachments: readonly Attachment[] }) {
  if (attachments.length === 0) return <Text size="sm" c="dimmed">暂无附件，可在上方凭证清单中拖入。</Text>;
  return (
    <Stack gap="xs">
      {attachments.map((attachment) => (
        <AttachmentRow key={attachment.id} attachment={attachment} />
      ))}
    </Stack>
  );
}
