import { Button, Group, Loader, Table, Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useState } from 'react';
import { useAttachmentCandidates, useBulkAssignAttachments } from '../../../api/hooks/attachments';
import { candidateLabel, candidateReasons } from '../../../lib/candidates';
import { useInViewOnce } from './useInViewOnce';

const TEXT_MAX_WIDTH = 280;

/** “建议”列：行进入视口或点击后才请求候选记录，避免一次请求几十个。 */
export function CandidateSuggestion({ attachmentId }: { attachmentId: number }) {
  const { ref, isInView } = useInViewOnce<HTMLTableCellElement>();
  const [isRequested, setRequested] = useState(false);
  const isEnabled = isInView || isRequested;
  const { data, isError } = useAttachmentCandidates(attachmentId, isEnabled);
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
    if (isError) return <Text size="xs" c="red">建议加载失败</Text>;
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
