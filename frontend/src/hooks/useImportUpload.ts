import { notifications } from '@mantine/notifications';
import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useReducer, useRef, useState, type Dispatch } from 'react';
import { errorMessage } from '../api/client';
import { importsApi } from '../api/hooks/imports';
import { invalidateWorkflow } from '../api/hooks/invalidate';
import type { ImportFileResult, ImportSession, ImportStartResult } from '../api/types';
import type { UploadOptions } from '../api/upload';
import {
  EMPTY_UPLOAD_QUEUE, findDuplicateFiles, isQueueSettled, selectOverallProgress, selectStartable, selectUploadStats,
  uploadQueueReducer, type UploadItem, type UploadQueueAction, type UploadQueueState,
} from '../lib/uploadQueue';
import { createSessionKeeper, isSessionExpired, type SessionKeeper } from './importSessionKeeper';

export const UPLOAD_CONCURRENCY = 3;

export interface UploadNotice {
  message: string;
  color?: string;
}

export interface ImportUploadDeps {
  startSession: () => Promise<ImportStartResult>;
  uploadFile: (sessionId: string, file: File, options: UploadOptions) => Promise<ImportFileResult>;
  finishSession: (sessionId: string) => Promise<ImportSession>;
  notify: (notice: UploadNotice) => void;
}

const DEFAULT_DEPS: ImportUploadDeps = {
  startSession: importsApi.start,
  uploadFile: importsApi.uploadFile,
  finishSession: importsApi.finish,
  notify: ({ message, color = 'ink' }) => notifications.show({ color, message }),
};

/** 已全部结束时队列的指纹；未结束为 null。用于判断是否需要（再次）分组。 */
const settledKeyOf = (queue: UploadQueueState) =>
  isQueueSettled(queue) ? queue.items.map((item) => `${item.id}:${item.phase}`).join(',') : null;

const isAbort = (signal: AbortSignal) => signal.aborted;

async function uploadItem(item: UploadItem, signal: AbortSignal, keeper: SessionKeeper, deps: ImportUploadDeps, dispatch: Dispatch<UploadQueueAction>) {
  const options: UploadOptions = {
    signal,
    onProgress: (loaded, total) => {
      dispatch({ type: 'progress', id: item.id, loaded, total });
      if (total > 0 && loaded >= total) dispatch({ type: 'uploaded', id: item.id });
    },
  };
  const sessionId = await keeper.ensure();
  try {
    return await deps.uploadFile(sessionId, item.file, options);
  } catch (error) {
    if (!isSessionExpired(error) || isAbort(signal)) throw error;
    return deps.uploadFile(await keeper.renew(sessionId), item.file, options);
  }
}

interface FinishOutcome {
  session: ImportSession | null;
  version: number;
  /** 该结果对应的已结束队列指纹 */
  key: string | null;
}

interface FinishFailure {
  key: string;
  message: string;
}

function useUploadRunner(deps: ImportUploadDeps, dispatch: Dispatch<UploadQueueAction>) {
  const depsRef = useRef(deps);
  depsRef.current = deps;
  const controllers = useRef(new Map<string, AbortController>());
  const keeperRef = useRef<SessionKeeper | null>(null);
  keeperRef.current ??= createSessionKeeper(
    () => depsRef.current.startSession(),
    () => depsRef.current.notify({ color: 'yellow', message: '导入会话已过期，已自动重新开始' }),
  );
  const keeper = keeperRef.current;

  const run = useCallback(async (item: UploadItem) => {
    const controller = new AbortController();
    controllers.current.set(item.id, controller);
    dispatch({ type: 'start', id: item.id });
    try {
      const result = await uploadItem(item, controller.signal, keeper, depsRef.current, dispatch);
      dispatch({ type: 'result', id: item.id, result });
    } catch (error) {
      if (!isAbort(controller.signal)) dispatch({ type: 'fail', id: item.id, message: errorMessage(error) });
    } finally {
      controllers.current.delete(item.id);
    }
  }, [dispatch, keeper]);

  const isRunning = useCallback((id: string) => controllers.current.has(id), []);
  const abort = useCallback((id: string) => controllers.current.get(id)?.abort(), []);
  const abortAll = useCallback(() => controllers.current.forEach((controller) => controller.abort()), []);
  useEffect(() => abortAll, [abortAll]);
  return { run, isRunning, abort, abortAll, keeper, depsRef };
}

function useAutoFinish(queue: UploadQueueState, runner: ReturnType<typeof useUploadRunner>) {
  const client = useQueryClient();
  const settledKey = settledKeyOf(queue);
  const settledKeyRef = useRef(settledKey);
  settledKeyRef.current = settledKey;
  const [outcome, setOutcome] = useState<FinishOutcome>({ session: null, version: 0, key: null });
  const [failure, setFailure] = useState<FinishFailure | null>(null);
  const hasSessionRef = useRef(false);
  const { keeper, depsRef } = runner;

  const finish = useCallback(async (key: string) => {
    setFailure(null);
    const sessionId = keeper.currentId();
    if (!sessionId) {
      setOutcome((prev) => ({ ...prev, key }));
      return;
    }
    try {
      const session = await depsRef.current.finishSession(sessionId);
      if (settledKeyRef.current !== key) return;
      if (hasSessionRef.current) depsRef.current.notify({ message: '新文件已加入，分组已刷新' });
      hasSessionRef.current = true;
      setOutcome((prev) => ({ session, version: prev.version + 1, key }));
      void invalidateWorkflow(client);
    } catch (error) {
      if (settledKeyRef.current === key) setFailure({ key, message: errorMessage(error) });
    }
  }, [client, depsRef, keeper]);

  const lastStartedKey = useRef<string | null>(null);
  useEffect(() => {
    if (settledKey === null || settledKey === lastStartedKey.current) return;
    lastStartedKey.current = settledKey;
    void finish(settledKey);
  }, [settledKey, finish]);

  const clear = useCallback(() => {
    hasSessionRef.current = false;
    lastStartedKey.current = null;
    setFailure(null);
    setOutcome((prev) => ({ session: null, version: prev.version + 1, key: null }));
  }, []);

  const finishError = failure !== null && failure.key === settledKey ? failure.message : null;
  return {
    session: outcome.session,
    version: outcome.version,
    isFinishing: settledKey !== null && outcome.key !== settledKey && finishError === null,
    finishError,
    refinish: () => {
      if (settledKey !== null) void finish(settledKey);
    },
    clear,
  };
}

/** 收集页分文件导入：队列、并发上传、取消/重试、会话过期重开、全部结束后自动分组。 */
export function useImportUpload(overrides: Partial<ImportUploadDeps> = {}) {
  const deps = { ...DEFAULT_DEPS, ...overrides };
  const [queue, dispatch] = useReducer(uploadQueueReducer, EMPTY_UPLOAD_QUEUE);
  const queueRef = useRef(queue);
  queueRef.current = queue;
  const nextId = useRef(0);
  const runner = useUploadRunner(deps, dispatch);
  const finish = useAutoFinish(queue, runner);
  const { run, isRunning } = runner;

  useEffect(() => {
    selectStartable(queue, UPLOAD_CONCURRENCY)
      .filter((item) => !isRunning(item.id))
      .forEach((item) => void run(item));
  }, [queue, run, isRunning]);

  const addFiles = useCallback((files: readonly File[]) => {
    if (files.length === 0) return;
    const ignored = findDuplicateFiles(queueRef.current.items, files);
    if (ignored.length > 0) {
      const names = ignored.map((file) => file.name).join('、');
      runner.depsRef.current.notify({ color: 'yellow', message: `已忽略 ${ignored.length} 个重复拖入的文件：${names}` });
    }
    const entries = files.map((file) => ({ id: `upload-${(nextId.current += 1)}`, file }));
    dispatch({ type: 'add', entries });
  }, [runner.depsRef]);

  const reset = () => {
    runner.abortAll();
    runner.keeper.clear();
    dispatch({ type: 'reset' });
    finish.clear();
  };

  return {
    items: queue.items,
    stats: selectUploadStats(queue),
    overallProgress: selectOverallProgress(queue),
    isSettled: isQueueSettled(queue),
    session: finish.session,
    sessionVersion: finish.version,
    isFinishing: finish.isFinishing,
    finishError: finish.finishError,
    addFiles,
    retry: (id: string) => dispatch({ type: 'retry', id }),
    cancel: (id: string) => {
      runner.abort(id);
      dispatch({ type: 'cancel', id });
    },
    refinish: finish.refinish,
    reset,
  };
}
