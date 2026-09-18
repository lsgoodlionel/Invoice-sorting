import { Anchor, Button, Group, Progress, Stack, Text } from '@mantine/core';
import { IconCircleCheck } from '@tabler/icons-react';
import { Link } from 'react-router';
import { expenseDetailLink } from '../../../lib/expenseFilters';
import type { UploadItem } from '../../../lib/uploadQueue';

interface UploadFileStatusProps {
  item: UploadItem;
  onRetry: (id: string) => void;
}

const WARN_COLOR = 'yellow.9';
const ERROR_COLOR = 'red.7';

function RetryButton({ item, onRetry }: UploadFileStatusProps) {
  return (
    <Button size="compact-xs" variant="default" aria-label={`重试 ${item.name}`} onClick={() => onRetry(item.id)}>
      重试
    </Button>
  );
}

function ProgressStatus({ item }: { item: UploadItem }) {
  const isProcessing = item.phase === 'processing';
  return (
    <Stack gap={2}>
      <Progress
        size="sm"
        value={isProcessing ? 100 : item.progress}
        striped={isProcessing}
        animated={isProcessing}
        aria-label={`${item.name} ${isProcessing ? '识别进度' : '上传进度'}`}
      />
      <Text size="xs" c="dimmed" className="num">{isProcessing ? '识别中…' : `上传中 ${item.progress}%`}</Text>
    </Stack>
  );
}

function doneLabel(item: UploadItem): string {
  if (!item.recognizedAs) return '已导入';
  return [`识别为：${item.recognizedAs}`, item.recognizedDetail].filter(Boolean).join(' · ');
}

function DoneStatus({ item }: { item: UploadItem }) {
  return (
    <Stack gap={0}>
      <Group gap={4} wrap="nowrap">
        <IconCircleCheck size={14} stroke={1.8} color="var(--accent)" aria-hidden />
        <Text size="xs" c="ink.7">{doneLabel(item)}</Text>
      </Group>
      {item.message && <Text size="xs" c={WARN_COLOR}>{item.message}</Text>}
    </Stack>
  );
}

function DuplicateStatus({ item }: { item: UploadItem }) {
  return (
    <Group gap={6} wrap="wrap">
      <Text size="xs" fw={600} c={WARN_COLOR}>已存在</Text>
      {item.message && <Text size="xs" c="dimmed">{item.message}</Text>}
      {item.existingExpenseId !== null && (
        <Anchor component={Link} to={expenseDetailLink(item.existingExpenseId)} size="xs">
          查看 #{item.existingExpenseId}
        </Anchor>
      )}
    </Group>
  );
}

/** 单个文件的状态：进度条、识别结论、重复/失败原因与重试。 */
export function UploadFileStatus({ item, onRetry }: UploadFileStatusProps) {
  switch (item.phase) {
    case 'waiting':
      return <Text size="xs" c="dimmed">等待中</Text>;
    case 'uploading':
    case 'processing':
      return <ProgressStatus item={item} />;
    case 'done':
      return <DoneStatus item={item} />;
    case 'duplicate':
      return <DuplicateStatus item={item} />;
    case 'error':
      return (
        <Group gap={6} wrap="nowrap" justify="space-between">
          <Text size="xs" c={ERROR_COLOR}>失败：{item.message || '导入失败'}</Text>
          <RetryButton item={item} onRetry={onRetry} />
        </Group>
      );
    case 'cancelled':
      return (
        <Group gap={6} wrap="nowrap" justify="space-between">
          <Text size="xs" c="dimmed">已取消</Text>
          <RetryButton item={item} onRetry={onRetry} />
        </Group>
      );
  }
}
