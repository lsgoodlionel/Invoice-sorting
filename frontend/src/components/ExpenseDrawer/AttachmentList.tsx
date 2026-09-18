import { ActionIcon, Collapse, Group, Select, Stack, Text, Tooltip } from '@mantine/core';
import dayjs from 'dayjs';
import { modals } from '@mantine/modals';
import { IconArrowBackUp, IconEye, IconTrash } from '@tabler/icons-react';
import { useState } from 'react';
import { useDeleteAttachment, useUpdateAttachment } from '../../api/hooks/attachments';
import type { Attachment, AttachmentKind } from '../../api/types';
import { evidenceParts, isEvidenceRecognized } from '../../lib/evidence';
import { uploaderName } from '../../lib/operator';
import { hasTransportDetails, transportParts } from '../../lib/travelDetails';
import { ATTACHMENT_KIND_OPTIONS } from '../../lib/status';
import { AttachmentPreview } from '../AttachmentPreview';
import { useCurrentUser } from '../auth/CurrentUserContext';
import { RegionBadge } from '../RegionBadge';

const KB = 1024;

function formatSize(bytes: number): string {
  return bytes >= KB * KB ? `${(bytes / KB / KB).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / KB))} KB`;
}

function InvoiceLine({ attachment }: { attachment: Attachment }) {
  const invoice = attachment.invoice;
  if (!invoice || (!invoice.region_name && !invoice.order_no)) return null;
  return (
    <Group gap="xs" wrap="nowrap">
      <RegionBadge regionName={invoice.region_name} isNonlocal={invoice.is_nonlocal} showUnknown={false} />
      {invoice.order_no && <Text size="xs" c="dimmed" className="num">订单号 {invoice.order_no}</Text>}
    </Group>
  );
}

/** 交通票发票的行程：火车 G7123 · 上海虹桥 → 苏州园区 · 08-15 · 张三 */
function TravelLine({ attachment }: { attachment: Attachment }) {
  const details = attachment.invoice?.details;
  if (!hasTransportDetails(details)) return null;
  return <Text size="xs" c="dimmed" className="num" data-testid={`travel-${attachment.id}`}>{transportParts(details).join(' · ')}</Text>;
}

/** 非发票凭证识别摘要：类型 · 日期 · 金额币种 · 订单号 */
function EvidenceLine({ attachment }: { attachment: Attachment }) {
  if (attachment.invoice || !isEvidenceRecognized(attachment.evidence)) return null;
  const { evidence } = attachment;
  const parts = evidenceParts({ ...evidence, merchant: '', item_name: '' });
  return <Text size="xs" c="dimmed" className="num" data-testid={`evidence-${attachment.id}`}>{parts.join(' · ')}</Text>;
}

/** “上传：张三 · MM-DD HH:mm”；关闭认证时无上传人，只显示时间。 */
function UploaderLine({ attachment }: { attachment: Attachment }) {
  const { authEnabled } = useCurrentUser();
  const time = dayjs(attachment.created_at).format('MM-DD HH:mm');
  const label = authEnabled ? `上传：${uploaderName(attachment.uploaded_by)} · ${time}` : `上传 · ${time}`;
  return (
    <Text size="xs" c="dimmed" data-testid={`attachment-uploader-${attachment.id}`}>
      <span className="num">{label}</span>
    </Text>
  );
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
      <UploaderLine attachment={attachment} />
      <InvoiceLine attachment={attachment} />
      <TravelLine attachment={attachment} />
      <EvidenceLine attachment={attachment} />
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
