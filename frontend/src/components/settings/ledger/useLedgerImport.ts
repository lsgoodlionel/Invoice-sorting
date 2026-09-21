import { useCallback, useEffect, useRef, useState } from 'react';
import { errorMessage } from '../../../api/client';
import {
  backupApi,
  useConfirmImport,
  useImportJob,
  type ImportJob,
  type ImportMode,
  type ImportPreview,
} from '../../../api/hooks/backup';
import { uploadLedgerPackage, type UploadStage } from '../../../api/ledgerUpload';
import { packageFileError } from '../../../lib/ledgerTransfer';
import { notifyError } from '../../../queryClient';

export type ImportPhase = 'idle' | UploadStage | 'preview' | 'importing' | 'done' | 'failed';

interface ImportState {
  phase: ImportPhase;
  file: File | null;
  uploadId: string | null;
  percent: number;
  preview: ImportPreview | null;
  error: string;
}

const IDLE: ImportState = { phase: 'idle', file: null, uploadId: null, percent: 0, preview: null, error: '' };

const BUSY_PHASES: readonly ImportPhase[] = ['hashing', 'uploading', 'analyzing', 'importing'];

const isAbort = (error: unknown) => error instanceof DOMException && error.name === 'AbortError';

export interface LedgerImport {
  phase: ImportPhase;
  file: File | null;
  percent: number;
  preview: ImportPreview | null;
  job: ImportJob | null;
  error: string;
  confirmError: string;
  isConfirming: boolean;
  /** 上传或导入进行中（离开页面需提示） */
  isBusy: boolean;
  begin: (file: File) => void;
  confirm: (mode: ImportMode, confirmName: string, includeSettings: boolean) => void;
  /** 取消上传或放弃导入：中止请求并让服务端清理暂存 */
  cancel: () => void;
  /** 导入结束后回到初始状态 */
  finish: () => void;
}

/** 已提交导入后，任务归服务端所有，不再由前端 DELETE。 */
function deriveJobPhase(state: ImportState, job: ImportJob | undefined, hasJobError: boolean): ImportPhase {
  if (state.phase !== 'importing') return state.phase;
  if (job?.status === 'done') return 'done';
  if (job?.status === 'failed' || hasJobError) return 'failed';
  return 'importing';
}

export function useLedgerImport(): LedgerImport {
  const [state, setState] = useState<ImportState>(IDLE);
  const controllerRef = useRef<AbortController | null>(null);
  const uploadIdRef = useRef<string | null>(null);
  const confirmMutation = useConfirmImport();
  const jobQuery = useImportJob(state.uploadId, state.phase === 'importing');

  const discard = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    const uploadId = uploadIdRef.current;
    uploadIdRef.current = null;
    if (uploadId) backupApi.cancelImport(uploadId).catch((error: unknown) => notifyError(error, '清理上传暂存失败'));
  }, []);

  useEffect(() => discard, [discard]);

  const begin = (file: File) => {
    discard();
    confirmMutation.reset();
    const problem = packageFileError(file);
    if (problem) {
      setState({ ...IDLE, error: problem });
      return;
    }
    const controller = new AbortController();
    controllerRef.current = controller;
    const update = (next: Partial<ImportState>) => {
      if (!controller.signal.aborted) setState((current) => ({ ...current, ...next }));
    };
    setState({ ...IDLE, phase: 'hashing', file });
    uploadLedgerPackage(file, {
      signal: controller.signal,
      onStage: (phase) => update({ phase, percent: 0 }),
      onPercent: (percent) => update({ percent }),
      onCreated: (uploadId) => {
        uploadIdRef.current = uploadId;
        update({ uploadId });
      },
    })
      .then((preview) => update({ phase: 'preview', preview }))
      .catch((error: unknown) => {
        if (!isAbort(error)) update({ phase: 'failed', error: errorMessage(error) });
      });
  };

  const confirm = (mode: ImportMode, confirmName: string, includeSettings: boolean) => {
    if (!state.uploadId) return;
    const input =
      mode === 'replace'
        ? { mode, confirm_name: confirmName, include_settings: true }
        : { mode, include_settings: includeSettings };
    confirmMutation.mutate(
      { uploadId: state.uploadId, input },
      {
        onSuccess: () => {
          uploadIdRef.current = null;
          setState((current) => ({ ...current, phase: 'importing' }));
        },
      },
    );
  };

  const cancel = () => {
    discard();
    confirmMutation.reset();
    setState(IDLE);
  };

  const job = jobQuery.data ?? null;
  const phase = deriveJobPhase(state, jobQuery.data, jobQuery.isError);
  const jobError = job?.error || (jobQuery.error ? errorMessage(jobQuery.error) : '导入失败，请查看服务端日志');
  return {
    phase,
    file: state.file,
    percent: state.percent,
    preview: state.preview,
    job,
    error: state.phase === 'importing' ? jobError : state.error,
    confirmError: confirmMutation.error ? errorMessage(confirmMutation.error) : '',
    isConfirming: confirmMutation.isPending,
    isBusy: BUSY_PHASES.includes(phase),
    begin,
    confirm,
    cancel,
    finish: cancel,
  };
}
