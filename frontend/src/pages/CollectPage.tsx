import { Button, Group, Stack, Text, Title } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconPlus } from '@tabler/icons-react';
import { useState } from 'react';
import { useConfirmImport, useImportFiles } from '../api/hooks/imports';
import { useSettings } from '../api/hooks/settings';
import type { ImportConfirmInput, ImportSession } from '../api/types';
import { ImportGroupsPanel } from '../components/collect/groups/ImportGroupsPanel';
import { ImportDropzone } from '../components/collect/ImportDropzone';
import { ImportIssues } from '../components/collect/ImportIssues';
import { UnassignedSection } from '../components/collect/unassigned/UnassignedSection';
import { useQuickAdd } from '../components/QuickAddContext';

function sessionSummary(session: ImportSession): string {
  const fileCount = session.groups.reduce((total, group) => total + group.attachments.length, 0);
  const parts = [`${session.groups.length} 组`, `${fileCount} 个文件`];
  if (session.duplicates.length) parts.push(`${session.duplicates.length} 个重复已跳过`);
  if (session.errors.length) parts.push(`${session.errors.length} 个失败`);
  return parts.join(' · ');
}

export function CollectPage() {
  const { data: settings } = useSettings();
  const { openQuickAdd } = useQuickAdd();
  const importFiles = useImportFiles();
  const confirm = useConfirmImport();
  const [session, setSession] = useState<ImportSession | null>(null);
  const hasConfirmTable = session !== null && session.groups.length > 0;

  const handleFiles = (files: File[]) => {
    if (files.length === 0) return;
    importFiles.mutate(files, { onSuccess: setSession });
  };

  const handleConfirm = (input: ImportConfirmInput) => {
    if (!session) return;
    confirm.mutate(
      { sessionId: session.session_id, input },
      {
        onSuccess: (result) => {
          notifications.show({
            color: 'ink',
            title: '导入完成',
            message: `新建 ${result.created.length} 条，挂到已有 ${result.attached.length} 条，${result.skipped} 个文件留在待归属`,
          });
          setSession(null);
        },
      },
    );
  };

  return (
    <Stack gap="lg" className="page">
      <Group justify="space-between" align="flex-end">
        <Title order={1} className="page-title">收集</Title>
        <Button variant="outline" leftSection={<IconPlus size={14} />} onClick={openQuickAdd}>快速记一笔</Button>
      </Group>
      <ImportDropzone onFiles={handleFiles} isLoading={importFiles.isPending} inboxDir={settings?.inbox_dir} />
      {session && (
        <Stack gap="sm">
          <Text className="section-label">本次导入：{sessionSummary(session)}</Text>
          <ImportIssues duplicates={session.duplicates} errors={session.errors} notices={session.notices} />
          {hasConfirmTable ? (
            <ImportGroupsPanel key={session.session_id} session={session} onConfirm={handleConfirm} isSubmitting={confirm.isPending} />
          ) : (
            <Text size="sm" c="dimmed">本次没有需要确认的文件。</Text>
          )}
        </Stack>
      )}
      <UnassignedSection hasOtherPrimary={hasConfirmTable} />
    </Stack>
  );
}
