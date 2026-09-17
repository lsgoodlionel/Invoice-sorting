import { Button, Group, Stack, Text, Title } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconPlus } from '@tabler/icons-react';
import { useState } from 'react';
import { useConfirmImport, useImportFiles } from '../api/hooks/imports';
import { useSettings } from '../api/hooks/settings';
import type { ImportSession } from '../api/types';
import { ImportConfirmTable } from '../components/collect/ImportConfirmTable';
import { ImportDropzone } from '../components/collect/ImportDropzone';
import { ImportIssues } from '../components/collect/ImportIssues';
import { UnassignedList } from '../components/collect/UnassignedList';
import { useQuickAdd } from '../components/QuickAddContext';
import { draftsFromSession, toConfirmRow, updateDraft, type ImportDraft } from '../lib/importRows';

function sessionSummary(session: ImportSession): string {
  const parts = [`${session.rows.length} 张发票`, `${session.attachments.length} 个附件`];
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
  const [drafts, setDrafts] = useState<ImportDraft[]>([]);

  const handleFiles = (files: File[]) => {
    if (files.length === 0) return;
    importFiles.mutate(files, {
      onSuccess: (result) => {
        setSession(result);
        setDrafts(draftsFromSession(result));
      },
    });
  };

  const handleConfirm = () => {
    if (!session) return;
    confirm.mutate(
      { sessionId: session.session_id, rows: drafts.map(toConfirmRow) },
      {
        onSuccess: (result) => {
          notifications.show({
            color: 'ink',
            title: '导入完成',
            message: `新建 ${result.created.length} 条，挂到已有 ${result.attached.length} 条，跳过 ${result.skipped} 条`,
          });
          setSession(null);
          setDrafts([]);
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
          {session.rows.length > 0 ? (
            <ImportConfirmTable
              rows={session.rows}
              drafts={drafts}
              onChange={(rowId, patch) => setDrafts((current) => updateDraft(current, rowId, patch))}
              onConfirm={handleConfirm}
              isSubmitting={confirm.isPending}
            />
          ) : (
            <Text size="sm" c="dimmed">本次没有识别到发票，非发票文件已放入下方“待归属附件”。</Text>
          )}
        </Stack>
      )}
      <UnassignedList />
    </Stack>
  );
}
