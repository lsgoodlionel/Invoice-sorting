import { Button, Group, Stack, Text, Title } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconPlus } from '@tabler/icons-react';
import { useConfirmImport } from '../api/hooks/imports';
import { useSettings } from '../api/hooks/settings';
import type { ImportConfirmInput, ImportSession } from '../api/types';
import { ImportGroupsPanel } from '../components/collect/groups/ImportGroupsPanel';
import { ImportDropzone } from '../components/collect/ImportDropzone';
import { UnassignedSection } from '../components/collect/unassigned/UnassignedSection';
import { UploadPanel } from '../components/collect/upload/UploadPanel';
import { useQuickAdd } from '../components/QuickAddContext';
import { useImportUpload } from '../hooks/useImportUpload';

function sessionSummary(session: ImportSession): string {
  const fileCount = session.groups.reduce((total, group) => total + group.attachments.length, 0);
  return `${session.groups.length} 组 · ${fileCount} 个文件`;
}

function ReviewSection({ session, version, onConfirm, isSubmitting }: {
  session: ImportSession;
  version: number;
  onConfirm: (input: ImportConfirmInput) => void;
  isSubmitting: boolean;
}) {
  return (
    <Stack gap="sm">
      <Text className="section-label">本次导入：{sessionSummary(session)}</Text>
      {session.groups.length > 0 ? (
        <ImportGroupsPanel key={`${session.session_id}-${version}`} session={session} onConfirm={onConfirm} isSubmitting={isSubmitting} />
      ) : (
        <Text size="sm" c="dimmed">本次没有需要确认的文件。</Text>
      )}
    </Stack>
  );
}

export function CollectPage() {
  const { data: settings } = useSettings();
  const { openQuickAdd } = useQuickAdd();
  const upload = useImportUpload();
  const confirm = useConfirmImport();
  const { session } = upload;
  const hasItems = upload.items.length > 0;
  const isReviewReady = session !== null && upload.isSettled && !upload.isFinishing && upload.finishError === null;
  const hasConfirmTable = isReviewReady && session.groups.length > 0;

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
          upload.reset();
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
      <Stack gap="sm">
        <ImportDropzone onFiles={upload.addFiles} inboxDir={settings?.inbox_dir} />
        {hasItems && (
          <UploadPanel
            items={upload.items}
            stats={upload.stats}
            overallProgress={upload.overallProgress}
            isSettled={upload.isSettled}
            isFinishing={upload.isFinishing}
            finishError={upload.finishError}
            onRetry={upload.retry}
            onCancel={upload.cancel}
            onClear={upload.reset}
            onRefinish={upload.refinish}
          />
        )}
      </Stack>
      {hasItems && !upload.isSettled && (
        <Text size="sm" c="dimmed">等待全部文件处理完成后再确认分组…</Text>
      )}
      {isReviewReady && (
        <ReviewSection session={session} version={upload.sessionVersion} onConfirm={handleConfirm} isSubmitting={confirm.isPending} />
      )}
      <UnassignedSection hasOtherPrimary={hasConfirmTable} />
    </Stack>
  );
}
