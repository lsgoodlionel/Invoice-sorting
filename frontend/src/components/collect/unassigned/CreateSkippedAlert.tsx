import { Alert, List, Text } from '@mantine/core';
import type { CreateExpensesSkip } from '../../../api/types';

export function CreateSkippedAlert({ skipped, onClose }: { skipped: readonly CreateExpensesSkip[]; onClose: () => void }) {
  if (skipped.length === 0) return null;
  return (
    <Alert color="yellow" variant="light" withCloseButton onClose={onClose} title={`${skipped.length} 张发票未生成记录`} data-testid="create-skipped">
      <List size="sm" spacing={2}>
        {skipped.map((item) => (
          <List.Item key={item.id}>
            {item.original_name}<Text span size="xs" c="dimmed">　{item.reason}</Text>
          </List.Item>
        ))}
      </List>
      <Text size="xs" c="dimmed" mt={4}>可先“重新识别”，或在清单中手动记一笔后归属。</Text>
    </Alert>
  );
}
