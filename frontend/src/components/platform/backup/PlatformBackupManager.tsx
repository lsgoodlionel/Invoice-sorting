import { Alert, Button, Group, List, Stack, Text } from '@mantine/core';
import { IconDatabaseExport, IconShieldLock } from '@tabler/icons-react';
import { errorMessage } from '../../../api/client';
import { platformBackupUrl, useCreatePlatformBackup, usePlatformBackups } from '../../../api/hooks/platformBackups';
import { BackupFileTable } from '../../BackupFileTable';

function PlatformBackupNotes() {
  return (
    <Stack gap="xs">
      <Text size="sm" c="dimmed">
        平台数据库含全部账号、账套、套餐、授权与邮件设置，与各账套的「备份与搬迁」无关（账套里的记录和附件不在其中）。
        服务器保留最近的备份，可随时下载。
      </Text>
      <Alert color="red" variant="light" icon={<IconShieldLock size={16} />} title="请妥善保管下载的文件">
        <List size="sm" spacing={2}>
          <List.Item>下载的文件含全部账号的密码哈希，请妥善保管，不要外传。</List.Item>
          <List.Item>恢复时需同时具备服务器上的 secret.key，否则邮件密码需要重新填写。</List.Item>
        </List>
      </Alert>
    </Stack>
  );
}

/** 平台 → 平台备份：备份平台数据库、列出服务器保留的备份并下载。仅平台管理员可见。 */
export function PlatformBackupManager() {
  const { data } = usePlatformBackups();
  const backups = data?.items ?? [];
  const create = useCreatePlatformBackup();
  const notice = create.data?.notice ?? data?.notice;

  return (
    <Stack gap="md">
      <PlatformBackupNotes />
      <Group>
        <Button
          variant="filled"
          leftSection={<IconDatabaseExport size={16} stroke={1.6} />}
          loading={create.isPending}
          onClick={() => create.mutate()}
        >
          备份平台数据库
        </Button>
      </Group>
      {notice && <Alert color="ink" variant="light">{notice}</Alert>}
      {create.error && <Alert color="red" variant="light">{errorMessage(create.error)}</Alert>}
      <BackupFileTable
        files={backups}
        label="平台数据库备份"
        emptyText="还没有平台数据库备份。"
        downloadUrl={platformBackupUrl}
      />
    </Stack>
  );
}
