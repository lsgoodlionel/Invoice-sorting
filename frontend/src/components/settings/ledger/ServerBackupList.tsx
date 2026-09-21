import { Stack, Text } from '@mantine/core';
import { backupPackageUrl, useBackupPackages } from '../../../api/hooks/backupPackages';
import { BackupFileTable } from '../../BackupFileTable';

/** 服务器上保留的完整备份（最近 10 份），可再次下载。 */
export function ServerBackupList() {
  const { data: packages = [] } = useBackupPackages();
  return (
    <Stack gap="xs">
      <Text fw={600}>服务器上保留的备份</Text>
      <Text size="sm" c="dimmed">
        每次「备份并下载」都会在服务器上留一份，保留最近 10 份，可随时再次下载。服务器硬盘损坏时它们会一起丢失，请以下载到本机的为准。
      </Text>
      <BackupFileTable
        files={packages}
        label="服务器上保留的备份"
        emptyText="服务器上还没有备份。"
        downloadUrl={backupPackageUrl}
      />
    </Stack>
  );
}
