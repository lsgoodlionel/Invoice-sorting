import { Alert, Button, Stack, Text } from '@mantine/core';
import { IconLock } from '@tabler/icons-react';
import { useState } from 'react';
import { useAuthStatus } from '../../../api/hooks/auth';
import { useBeforeUnloadGuard } from '../../../hooks/useBeforeUnloadGuard';
import { ImportConfirmForm } from './ImportConfirmForm';
import { ImportPreviewView } from './ImportPreviewView';
import { ImportProgress } from './ImportProgress';
import { ImportResultView } from './ImportResultView';
import { PackageDropzone } from './PackageDropzone';
import { useLedgerImport, type LedgerImport } from './useLedgerImport';

const INTRO = '把其他账户、账套或服务器导出的搬迁包导入到当前账本。先上传并生成预览，确认后才会真正写入。';
const REJECT_MESSAGE = '只能导入 .zip 搬迁包';
const DEFAULT_TARGET_NAME = '本账本';

function ImportStage({ state, targetName }: { state: LedgerImport; targetName: string }) {
  switch (state.phase) {
    case 'hashing':
    case 'uploading':
      return <ImportProgress phase={state.phase} file={state.file} percent={state.percent} onCancel={state.cancel} />;
    case 'analyzing':
      return <ImportProgress phase={state.phase} file={state.file} percent={null} onCancel={state.cancel} />;
    case 'importing':
      return <ImportProgress phase="importing" file={state.file} percent={state.job?.progress ?? null} message={state.job?.message} />;
    case 'preview':
      return state.preview ? (
        <Stack gap="md">
          <ImportPreviewView preview={state.preview} file={state.file} />
          <ImportConfirmForm
            targetName={state.preview.target_name || targetName}
            isSubmitting={state.isConfirming}
            error={state.confirmError}
            onConfirm={state.confirm}
            onCancel={state.cancel}
          />
        </Stack>
      ) : null;
    case 'done':
      return state.job ? <ImportResultView job={state.job} onFinish={state.finish} /> : null;
    case 'failed':
      return (
        <Stack gap="xs">
          <Alert color="red" variant="light" title="导入没有完成">{state.error}</Alert>
          <Button variant="outline" onClick={state.cancel} style={{ alignSelf: 'flex-start' }}>重新选择文件</Button>
        </Stack>
      );
    default:
      return null;
  }
}

/** 导入账本：选择 → 分片上传 → 预览 → 选择模式确认 → 进度 → 结果。只读时禁用。 */
export function LedgerImportPanel({ blockReason }: { blockReason: string | null }) {
  const state = useLedgerImport();
  const [rejectMessage, setRejectMessage] = useState('');
  const { data: auth } = useAuthStatus();
  useBeforeUnloadGuard(state.isBusy);
  const pickError = rejectMessage || state.error;

  const pick = (file: File) => {
    setRejectMessage('');
    state.begin(file);
  };

  return (
    <Stack gap="xs">
      <Text fw={600}>导入</Text>
      <Text size="sm" c="dimmed">{INTRO}</Text>
      {blockReason && (
        <Alert color="yellow" variant="light" icon={<IconLock size={16} />} title="暂不能导入">
          {`${blockReason}（导出仍可使用）`}
        </Alert>
      )}
      {state.phase === 'idle' ? (
        <>
          <PackageDropzone onFile={pick} onReject={() => setRejectMessage(REJECT_MESSAGE)} disabled={Boolean(blockReason)} />
          {pickError && <Text size="sm" c="red">{pickError}</Text>}
        </>
      ) : (
        <ImportStage state={state} targetName={auth?.tenant?.name || DEFAULT_TARGET_NAME} />
      )}
    </Stack>
  );
}
