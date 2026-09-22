import { Alert, Anchor, Button, Checkbox, Group, Stack, Text } from '@mantine/core';
import { IconDownload, IconShieldLock } from '@tabler/icons-react';
import { useEffect, useRef, useState } from 'react';
import { errorMessage } from '../../../api/client';
import { useAuthStatus } from '../../../api/hooks/auth';
import { useLedgerExport, type LedgerExportJob } from '../../../api/hooks/backup';
import { triggerDownload } from '../../../lib/download';
import { formatFileSize } from '../../../lib/fileMeta';

const INTRO = '包含整个数据库、系统设置与全部附件，同一个包也能在别的账户、账套或服务器上导入。';
/** 单账套部署的备份带登录账号（账本搬迁设计 2.1）；SaaS 的账号是平台共用的，不随账套走 */
const ACCOUNTS_HINT = '备份文件包含登录账号与密码哈希，请当作敏感文件妥善保管；在新机器上“清空后整套覆盖”即可带回账号与密码。';

const downloadLabel = (job: LedgerExportJob) =>
  `下载 ${job.file || '备份包'}${job.size ? `（${formatFileSize(job.size)}）` : ''}`;

/** 完成时自动下载一次（同一任务不重复触发）。 */
function useAutoDownload(job: LedgerExportJob | null): void {
  const downloadedRef = useRef<string | null>(null);
  useEffect(() => {
    if (job?.status !== 'done' || !job.download_url || downloadedRef.current === job.job) return;
    downloadedRef.current = job.job;
    triggerDownload(job.download_url, job.file);
  }, [job]);
}

/**
 * 一键备份：生成完整包 → 轮询 → 完成后自动下载到本机，服务器同时保留一份（列表随之刷新）。
 * 只读状态下仍可用。本分区唯一的 filled 主按钮。
 */
export function BackupNowPanel() {
  const [shouldSkipPackages, setShouldSkipPackages] = useState(false);
  const { start, isRunning, job, error } = useLedgerExport();
  const { data: auth } = useAuthStatus();
  // 等认证状态返回再判断，避免 SaaS 下先闪出这句提示
  const isSingleTenant = auth !== undefined && !auth.multi_tenant;
  useAutoDownload(job);
  const isDone = job?.status === 'done' && Boolean(job.download_url);

  return (
    <Stack gap="xs">
      <Text size="sm" c="dimmed">{INTRO}</Text>
      {isSingleTenant && (
        <Group gap={6} wrap="nowrap" align="flex-start" data-testid="backup-accounts-hint">
          <IconShieldLock size={16} stroke={1.6} aria-hidden style={{ flexShrink: 0, marginTop: 2 }} />
          <Text size="sm" c="orange.8">{ACCOUNTS_HINT}</Text>
        </Group>
      )}
      <Group gap="md" align="flex-start">
        <Button
          variant="filled"
          loading={isRunning}
          leftSection={<IconDownload size={16} stroke={1.6} />}
          onClick={() => start(!shouldSkipPackages)}
        >
          备份并下载
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
      {job?.status === 'failed' && <Alert color="red" variant="light">{job.error || '备份失败，请查看服务端日志'}</Alert>}
      {Boolean(error) && <Alert color="red" variant="light">{errorMessage(error)}</Alert>}
    </Stack>
  );
}
