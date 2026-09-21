import { Divider, Stack, Text } from '@mantine/core';
import { useLicenseStatus } from '../../../api/hooks/license';
import { useQuotaStatus } from '../../../api/hooks/quota';
import { importBlockReason } from '../../../lib/ledgerTransfer';
import { LedgerExportPanel } from './LedgerExportPanel';
import { LedgerImportPanel } from './LedgerImportPanel';

/**
 * 设置 → 账本搬迁（仅管理员）：整本导出下载，或上传搬迁包合并/覆盖导入。
 * 授权失效或账套停用（只读）时只能导出。
 */
export function LedgerTransferSection() {
  const { data: license } = useLicenseStatus();
  const { data: quota } = useQuotaStatus();
  const blockReason = importBlockReason(license, quota);

  return (
    <Stack gap="md">
      <Text size="sm" c="dimmed">
        本地部署与云端之间可以双向搬迁。导入默认“合并”：已存在的记录与附件自动跳过，不改动本地内容与设置。
      </Text>
      <LedgerExportPanel />
      <Divider variant="dashed" />
      <LedgerImportPanel blockReason={blockReason} />
    </Stack>
  );
}
