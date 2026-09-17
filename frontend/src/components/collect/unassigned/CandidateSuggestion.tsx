import { Button, Group, Loader, Table, Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useState } from 'react';
import { ApiError } from '../../../api/client';
import { useAttachmentCandidates, useBulkAssignAttachments } from '../../../api/hooks/attachments';
import { candidateLabel, candidateReasons } from '../../../lib/candidates';
import { useInViewOnce } from './useInViewOnce';

const TEXT_MAX_WIDTH = 280;
const HTTP_CONFLICT = 409;
const ASSIGNED_PATTERN = /#(\d+)/;

/** 查询时附件已被归属（收件箱自动处理、其他页面操作等），显示事实而不是错误。 */
function assignedElsewhereText(error: unknown): string | null {
  if (!(error instanceof ApiError) || error.status !== HTTP_CONFLICT) return null;
  const match = ASSIGNED_PATTERN.exec(error.message);
  return match ? `已挂到记录 #${match[1]}（列表刷新中）` : '已处理（列表刷新中）';
}

/** “建议”列：行进入视口或点击后才请求候选记录，避免一次请求几十个。 */
export function CandidateSuggestion({ attachmentId }: { attachmentId: number }) {
  const { ref, isInView } = useInViewOnce<HTMLTableCellElement>();
  const [isRequested, setRequested] = useState(false);
  const isEnabled = isInView || isRequested;
  const { data, isError, error } = useAttachmentCandidates(attachmentId, isEnabled);
  const assign = useBulkAssignAttachments();
  const top = data?.[0];

  const adopt = () => {
    if (!top) return;
    assign.mutate(
      { ids: [attachmentId], expense_id: top.expense_id },
      { onSuccess: () => notifications.show({ color: 'ink', message: `已挂到 #${top.expense_id}` }) },
    );
  };

  const renderBody = () => {
    if (!isEnabled) {
      return <Button size="compact-xs" variant="subtle" onClick={() => setRequested(true)}>查看建议</Button>;
    }
    const handled = assignedElsewhereText(error);
    if (handled) return <Text size="xs" c="dimmed">{handled}</Text>;
    if (isError) return <Text size="xs" c="red">建议加载失败，稍后自动重试</Text>;
    if (!data) return <Loader size="xs" aria-label="正在加载建议" />;
    if (!top) return <Text size="xs" c="dimmed">—</Text>;
    const reasons = candidateReasons(top);
    const text = `建议挂到 ${candidateLabel(top)}${reasons ? `（${reasons}）` : ''}`;
    return (
      <Group gap={4} wrap="nowrap">
        <Text size="xs" truncate maw={TEXT_MAX_WIDTH} title={text}>{text}</Text>
        <Button size="compact-xs" variant="light" loading={assign.isPending} onClick={adopt}>采纳</Button>
      </Group>
    );
  };

  return <Table.Td ref={ref} data-testid={`suggestion-${attachmentId}`}>{renderBody()}</Table.Td>;
}
