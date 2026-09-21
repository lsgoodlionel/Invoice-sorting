import { Divider, Stack, Text } from '@mantine/core';
import { useLicenseStatus } from '../../../api/hooks/license';
import { useQuotaStatus } from '../../../api/hooks/quota';
import { importBlockReason } from '../../../lib/ledgerTransfer';
import { BackupNowPanel } from './BackupNowPanel';
import { LedgerImportPanel } from './LedgerImportPanel';
import { ServerBackupList } from './ServerBackupList';

/**
 * 设置 → 备份与搬迁（仅管理员）：
 * 1. 备份并下载——备份与导出是同一个完整包，下载到本机，服务器也保留最近 10 份；
 * 2. 导入——从备份包合并或覆盖，可选同时导入系统设置。授权失效或账套停用（只读）时只能备份。
 */
export function LedgerTransferSection() {
  const { data: license } = useLicenseStatus();
  const { data: quota } = useQuotaStatus();
  const blockReason = importBlockReason(license, quota);

  return (
    <Stack gap="md">
      <Text size="sm" c="dimmed">
        <b>定期把备份下载到本机</b>才能防住服务器硬盘损坏。
      </Text>
      <BackupNowPanel />
      <ServerBackupList />
      <Divider variant="dashed" />
      <LedgerImportPanel blockReason={blockReason} />
    </Stack>
  );
}
