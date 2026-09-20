import { Alert, Button, Group, Stack, Text } from '@mantine/core';
import { IconDownload } from '@tabler/icons-react';
import { errorMessage } from '../../api/client';
import { formatBytes } from '../../lib/platform';
import { useTenantExport } from './useTenantExport';

const INTRO = '导出该账套的数据库快照、文件库与资料包，用于搬迁、备份或交付客户自持。';

/** 导出账套：登记任务 → 轮询状态 → 完成后下载。 */
export function TenantExportSection({ slug }: { slug: string }) {
  const { start, isRunning, job, error } = useTenantExport(slug);
  const isDone = job?.status === 'done';
  const isFailed = job?.status === 'failed';

  return (
    <Stack gap="xs">
      <Text size="xs" c="dimmed">{INTRO}</Text>
      <Group gap="xs">
        <Button
          size="xs"
          variant="outline"
          loading={isRunning}
          leftSection={<IconDownload size={14} stroke={1.6} />}
          onClick={start}
        >
          {isRunning ? '正在打包…' : '导出账套'}
        </Button>
        {isDone && (
          <Button size="xs" variant="subtle" component="a" href={job.download_url} data-testid="export-download">
            下载 {job.file}（{formatBytes(job.size)}）
          </Button>
        )}
      </Group>
      {isFailed && <Alert color="red" variant="light">{job.error || '导出失败，请查看服务端日志'}</Alert>}
      {Boolean(error) && <Alert color="red" variant="light">{errorMessage(error)}</Alert>}
    </Stack>
  );
}
