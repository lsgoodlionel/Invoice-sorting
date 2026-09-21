import { Button, Group, Progress, Stack, Text } from '@mantine/core';
import { formatFileSize } from '../../../lib/fileMeta';
import type { ImportPhase } from './useLedgerImport';

const PHASE_LABELS: Partial<Record<ImportPhase, string>> = {
  hashing: '正在校验文件',
  uploading: '正在上传',
  analyzing: '服务端正在合并校验，生成预览…',
  importing: '正在导入',
};

interface ImportProgressProps {
  phase: ImportPhase;
  file: File | null;
  /** 0–100；null 表示进度未知 */
  percent: number | null;
  message?: string;
  onCancel?: () => void;
}

/** 上传与导入进度：文件名与大小、阶段、百分比。 */
export function ImportProgress({ phase, file, percent, message, onCancel }: ImportProgressProps) {
  const isKnown = percent !== null;
  const label = PHASE_LABELS[phase] ?? '';
  return (
    <Stack gap={6} className="upload-panel" p="sm">
      {file && (
        <Text size="sm">
          {file.name}
          <Text span size="xs" c="dimmed" className="num">{`　${formatFileSize(file.size)}`}</Text>
        </Text>
      )}
      <Progress value={isKnown ? percent : 100} animated={!isKnown} striped={!isKnown} aria-label={label} />
      <Group justify="space-between" gap="xs">
        <Text size="xs" c="dimmed">{isKnown ? `${label} ${percent}%` : label}</Text>
        {onCancel && (
          <Button size="xs" variant="subtle" color="red" onClick={onCancel}>
            取消上传
          </Button>
        )}
      </Group>
      {message && <Text size="xs">{message}</Text>}
      {phase === 'importing' && <Text size="xs" c="dimmed">导入进行中，请不要关闭或刷新页面。</Text>}
    </Stack>
  );
}
