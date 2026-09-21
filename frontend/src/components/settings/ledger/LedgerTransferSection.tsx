import { Divider, Stack, Text } from '@mantine/core';
import { useLicenseStatus } from '../../../api/hooks/license';
import { useQuotaStatus } from '../../../api/hooks/quota';
import { importBlockReason } from '../../../lib/ledgerTransfer';
import { LedgerExportPanel } from './LedgerExportPanel';
import { LedgerImportPanel } from './LedgerImportPanel';
import { SnapshotPanel } from './SnapshotPanel';

/**
 * 设置 → 备份与搬迁（仅管理员）：
 * 1. 完整备份（推荐）——整本导出下载到本机，含全部附件，也是搬迁包；
 * 2. 数据库快照——只含数据库、留在服务器，做有风险的操作前留底；
 * 3. 导入——从导出包合并或覆盖。授权失效或账套停用（只读）时只能导出。
 */
export function LedgerTransferSection() {
  const { data: license } = useLicenseStatus();
  const { data: quota } = useQuotaStatus();
  const blockReason = importBlockReason(license, quota);

  return (
    <Stack gap="md">
      <Text size="sm" c="dimmed">
        <b>定期把完整备份下载到本机</b>才能防住服务器硬盘损坏；同一个导出包也能导入到别的账户、账套或服务器。
      </Text>
      <Stack gap="xs">
        <Text fw={600}>完整备份（推荐）</Text>
        <LedgerExportPanel />
      </Stack>
      <Divider variant="dashed" />
      <SnapshotPanel />
      <Divider variant="dashed" />
      <LedgerImportPanel blockReason={blockReason} />
    </Stack>
  );
}
