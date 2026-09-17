import { Button, Group, Progress, Stack, Text } from '@mantine/core';
import { formatUploadSummary, type UploadStats } from '../../../lib/uploadQueue';

interface UploadSummaryProps {
  stats: UploadStats;
  overallProgress: number;
  isSettled: boolean;
  isFinishing: boolean;
  finishError: string | null;
  onClear: () => void;
  onRefinish: () => void;
}

export function UploadSummary({ stats, overallProgress, isSettled, isFinishing, finishError, onClear, onRefinish }: UploadSummaryProps) {
  return (
    <Stack gap={6} className="upload-summary">
      <Group justify="space-between" wrap="nowrap" gap="sm">
        <Text size="sm" fw={600} className="num" aria-live="polite">{formatUploadSummary(stats, isSettled)}</Text>
        {isSettled && <Button size="compact-sm" variant="subtle" color="paper.7" onClick={onClear}>清空列表</Button>}
      </Group>
      <Progress size="xs" value={overallProgress} color={isSettled ? 'ink' : 'ink.5'} aria-label="整体导入进度" />
      {isFinishing && <Text size="xs" c="dimmed">正在分组匹配…</Text>}
      {finishError && (
        <Group gap="xs">
          <Text size="xs" c="red.7">{finishError}</Text>
          <Button size="compact-xs" variant="default" onClick={onRefinish}>重新分组</Button>
        </Group>
      )}
    </Stack>
  );
}
