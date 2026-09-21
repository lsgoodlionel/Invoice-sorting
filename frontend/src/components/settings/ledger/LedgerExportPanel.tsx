import { Alert, Anchor, Button, Checkbox, Group, Stack, Text } from '@mantine/core';
import { IconDownload } from '@tabler/icons-react';
import { useEffect, useRef, useState } from 'react';
import { errorMessage } from '../../../api/client';
import { useLedgerExport, type LedgerExportJob } from '../../../api/hooks/backup';
import { triggerDownload } from '../../../lib/download';
import { formatFileSize } from '../../../lib/fileMeta';

const INTRO = '把当前账本（记录、附件原件、分类与项目、凭证清单、批次、时间线）打成一个搬迁包，可导入到另一个账户、账套或服务器。';

const downloadLabel = (job: LedgerExportJob) =>
  `下载 ${job.file || '搬迁包'}${job.size ? `（${formatFileSize(job.size)}）` : ''}`;

/** 完成时自动下载一次（同一任务不重复触发）。 */
function useAutoDownload(job: LedgerExportJob | null): void {
  const downloadedRef = useRef<string | null>(null);
  useEffect(() => {
    if (job?.status !== 'done' || !job.download_url || downloadedRef.current === job.job) return;
    downloadedRef.current = job.job;
    triggerDownload(job.download_url, job.file);
  }, [job]);
}

/** 导出账本：登记任务 → 轮询 → 完成后自动下载并保留链接。只读状态下仍可用。 */
export function LedgerExportPanel() {
  const [shouldSkipPackages, setShouldSkipPackages] = useState(false);
  const { start, isRunning, job, error } = useLedgerExport();
  useAutoDownload(job);
  const isDone = job?.status === 'done' && Boolean(job.download_url);

  return (
    <Stack gap="xs">
      <Text size="sm" c="dimmed">{INTRO}</Text>
      <Group gap="md">
        <Button
          variant="outline"
          loading={isRunning}
          leftSection={<IconDownload size={16} stroke={1.6} />}
          onClick={() => start(!shouldSkipPackages)}
        >
          导出账本
        </Button>
        <Checkbox
          label="不含资料包"
          description="已生成的资料包可随时重新生成，不带可减小体积"
          checked={shouldSkipPackages}
          disabled={isRunning}
          onChange={(event) => setShouldSkipPackages(event.currentTarget.checked)}
        />
      </Group>
      {isRunning && <Text size="sm" c="dimmed">正在后台打包，完成后自动开始下载…</Text>}
      {isDone && job && (
        <Anchor href={job.download_url} size="sm" data-testid="ledger-export-download">
          {downloadLabel(job)}
        </Anchor>
      )}
      {job?.status === 'failed' && <Alert color="red" variant="light">{job.error || '导出失败，请查看服务端日志'}</Alert>}
      {Boolean(error) && <Alert color="red" variant="light">{errorMessage(error)}</Alert>}
    </Stack>
  );
}
