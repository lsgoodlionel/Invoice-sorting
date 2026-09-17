import { QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, test, vi } from 'vitest';
import { ApiError } from '../api/client';
import type { ImportFileResult, ImportSession } from '../api/types';
import type { UploadOptions } from '../api/upload';
import { makeAttachment, makeSession } from '../test/fixtures';
import { createTestClient } from '../test/render';
import { useImportUpload, type ImportUploadDeps } from './useImportUpload';

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason: unknown) => void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

interface UploadCall extends Deferred<ImportFileResult> {
  sessionId: string;
  file: File;
  options: UploadOptions;
}

const fileResult = (name: string, overrides: Partial<ImportFileResult> = {}): ImportFileResult => ({
  original_name: name, status: 'imported', attachment: makeAttachment({ id: 1, expense_id: null }),
  recognized_as: '发票', message: '', existing_expense_id: null, ...overrides,
});

function setup(options: { sessionIds?: string[]; finish?: ImportUploadDeps['finishSession'] } = {}) {
  const sessionIds = [...(options.sessionIds ?? ['s1', 's2', 's3'])];
  const uploads: UploadCall[] = [];
  const deps: ImportUploadDeps = {
    startSession: vi.fn(async () => ({ session_id: sessionIds.shift() ?? 'sx' })),
    uploadFile: vi.fn((sessionId: string, file: File, uploadOptions: UploadOptions) => {
      const call = { ...deferred<ImportFileResult>(), sessionId, file, options: uploadOptions };
      uploads.push(call);
      return call.promise;
    }),
    finishSession: options.finish ?? vi.fn(async (sessionId: string): Promise<ImportSession> => makeSession({ session_id: sessionId })),
    notify: vi.fn(),
  };
  const client = createTestClient();
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const hook = renderHook(() => useImportUpload(deps), { wrapper });
  return { deps, uploads, hook };
}

const files = (...names: string[]) => names.map((name) => new File(['data'], name, { lastModified: 1 }));
const phases = (hook: ReturnType<typeof setup>['hook']) => hook.result.current.items.map((item) => item.phase);

describe('useImportUpload', () => {
  test('starts a session once and uploads at most 3 files concurrently', async () => {
    const { deps, uploads, hook } = setup();
    act(() => hook.result.current.addFiles(files('1.pdf', '2.pdf', '3.pdf', '4.pdf', '5.pdf')));
    await waitFor(() => expect(uploads).toHaveLength(3));
    expect(deps.startSession).toHaveBeenCalledTimes(1);
    expect(uploads.map((call) => call.sessionId)).toEqual(['s1', 's1', 's1']);
    expect(phases(hook)).toEqual(['uploading', 'uploading', 'uploading', 'waiting', 'waiting']);

    await act(async () => uploads[0].resolve(fileResult('1.pdf')));
    await waitFor(() => expect(uploads).toHaveLength(4));
    expect(uploads[3].file.name).toBe('4.pdf');
    expect(hook.result.current.stats).toMatchObject({ done: 1, active: 4 });
  });

  test('tracks progress, switches to processing when fully uploaded and stores the result', async () => {
    const { uploads, hook } = setup();
    act(() => hook.result.current.addFiles(files('a.pdf')));
    await waitFor(() => expect(uploads).toHaveLength(1));
    act(() => uploads[0].options.onProgress?.(25, 100));
    expect(hook.result.current.items[0]).toMatchObject({ phase: 'uploading', progress: 25 });
    expect(hook.result.current.overallProgress).toBe(25);
    act(() => uploads[0].options.onProgress?.(100, 100));
    expect(hook.result.current.items[0].phase).toBe('processing');
    await act(async () => uploads[0].resolve(fileResult('a.pdf', { recognized_as: '订单明细' })));
    expect(hook.result.current.items[0]).toMatchObject({ phase: 'done', recognizedAs: '订单明细' });
  });

  test('finishes automatically when all files settle and refreshes with a notice after more files', async () => {
    const { deps, uploads, hook } = setup();
    act(() => hook.result.current.addFiles(files('a.pdf', 'b.pdf')));
    await waitFor(() => expect(uploads).toHaveLength(2));
    await act(async () => uploads[0].resolve(fileResult('a.pdf')));
    expect(deps.finishSession).not.toHaveBeenCalled();
    await act(async () => uploads[1].resolve(fileResult('b.pdf', { status: 'duplicate', existing_expense_id: 3 })));
    await waitFor(() => expect(hook.result.current.session?.session_id).toBe('s1'));
    expect(deps.finishSession).toHaveBeenCalledTimes(1);
    expect(hook.result.current.isSettled).toBe(true);
    const firstVersion = hook.result.current.sessionVersion;

    act(() => hook.result.current.addFiles(files('c.pdf')));
    expect(hook.result.current.isSettled).toBe(false);
    await waitFor(() => expect(uploads).toHaveLength(3));
    expect(uploads[2].sessionId).toBe('s1');
    await act(async () => uploads[2].resolve(fileResult('c.pdf')));
    await waitFor(() => expect(deps.finishSession).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(hook.result.current.sessionVersion).toBe(firstVersion + 1));
    expect(deps.notify).toHaveBeenCalledWith({ message: '新文件已加入，分组已刷新' });
    expect(deps.startSession).toHaveBeenCalledTimes(1);
  });

  test('ignores duplicate drops with a notice', async () => {
    const { deps, hook } = setup();
    act(() => hook.result.current.addFiles(files('a.pdf')));
    act(() => hook.result.current.addFiles(files('a.pdf', 'b.pdf')));
    expect(hook.result.current.items.map((item) => item.name)).toEqual(['a.pdf', 'b.pdf']);
    expect(deps.notify).toHaveBeenCalledWith({ color: 'yellow', message: '已忽略 1 个重复拖入的文件：a.pdf' });
    await waitFor(() => expect(deps.uploadFile).toHaveBeenCalledTimes(2));
  });

  test('failed upload shows the error and can be retried', async () => {
    const { uploads, hook } = setup();
    act(() => hook.result.current.addFiles(files('a.pdf')));
    await waitFor(() => expect(uploads).toHaveLength(1));
    await act(async () => uploads[0].reject(new ApiError('网络错误，上传失败', 0)));
    expect(hook.result.current.items[0]).toMatchObject({ phase: 'error', message: '网络错误，上传失败' });

    act(() => hook.result.current.retry(hook.result.current.items[0].id));
    await waitFor(() => expect(uploads).toHaveLength(2));
    await act(async () => uploads[1].resolve(fileResult('a.pdf')));
    expect(hook.result.current.items[0].phase).toBe('done');
  });

  test('cancel aborts the in-flight upload and keeps the item cancelled', async () => {
    const { uploads, hook } = setup();
    act(() => hook.result.current.addFiles(files('a.pdf')));
    await waitFor(() => expect(uploads).toHaveLength(1));
    act(() => hook.result.current.cancel(hook.result.current.items[0].id));
    expect(uploads[0].options.signal?.aborted).toBe(true);
    await act(async () => uploads[0].reject(new DOMException('上传已取消', 'AbortError')));
    expect(hook.result.current.items[0].phase).toBe('cancelled');
    expect(hook.result.current.isSettled).toBe(true);
  });

  test('restarts an expired session (404) once for concurrent uploads and retries them', async () => {
    const { deps, uploads, hook } = setup();
    act(() => hook.result.current.addFiles(files('a.pdf', 'b.pdf')));
    await waitFor(() => expect(uploads).toHaveLength(2));
    await act(async () => {
      uploads[0].reject(new ApiError('导入会话不存在或已过期', 404));
      uploads[1].reject(new ApiError('导入会话不存在或已过期', 404));
    });
    await waitFor(() => expect(uploads).toHaveLength(4));
    expect(deps.startSession).toHaveBeenCalledTimes(2);
    expect(uploads.slice(2).map((call) => call.sessionId)).toEqual(['s2', 's2']);
    expect(deps.notify).toHaveBeenCalledTimes(1);
    expect(deps.notify).toHaveBeenCalledWith({ color: 'yellow', message: '导入会话已过期，已自动重新开始' });
    await act(async () => {
      uploads[2].resolve(fileResult('a.pdf'));
      uploads[3].resolve(fileResult('b.pdf'));
    });
    await waitFor(() => expect(deps.finishSession).toHaveBeenCalledWith('s2'));
  });

  test('reports session start failures on each file', async () => {
    const { deps, hook } = setup();
    vi.mocked(deps.startSession).mockRejectedValueOnce(new ApiError('无法连接本地服务，请确认后端已启动', 0));
    act(() => hook.result.current.addFiles(files('a.pdf')));
    await waitFor(() => expect(hook.result.current.items[0].phase).toBe('error'));
    expect(hook.result.current.items[0].message).toBe('无法连接本地服务，请确认后端已启动');
  });

  test('finish failure is exposed and can be retried', async () => {
    const finish = vi.fn<ImportUploadDeps['finishSession']>()
      .mockRejectedValueOnce(new ApiError('分组失败', 500))
      .mockResolvedValueOnce(makeSession({ session_id: 's1' }));
    const { uploads, hook } = setup({ finish });
    act(() => hook.result.current.addFiles(files('a.pdf')));
    await waitFor(() => expect(uploads).toHaveLength(1));
    await act(async () => uploads[0].resolve(fileResult('a.pdf')));
    await waitFor(() => expect(hook.result.current.finishError).toBe('分组失败'));
    expect(hook.result.current.isFinishing).toBe(false);
    act(() => hook.result.current.refinish());
    await waitFor(() => expect(hook.result.current.session?.session_id).toBe('s1'));
    expect(hook.result.current.finishError).toBeNull();
  });

  test('reset aborts uploads and clears everything; next drop starts a new session', async () => {
    const { deps, uploads, hook } = setup();
    act(() => hook.result.current.addFiles(files('a.pdf')));
    await waitFor(() => expect(uploads).toHaveLength(1));
    act(() => hook.result.current.reset());
    expect(uploads[0].options.signal?.aborted).toBe(true);
    expect(hook.result.current.items).toEqual([]);
    expect(hook.result.current.session).toBeNull();

    act(() => hook.result.current.addFiles(files('a.pdf')));
    await waitFor(() => expect(uploads).toHaveLength(2));
    expect(uploads[1].sessionId).toBe('s2');
    expect(deps.startSession).toHaveBeenCalledTimes(2);
  });

  test('ignores an empty drop', () => {
    const { deps, hook } = setup();
    act(() => hook.result.current.addFiles([]));
    expect(hook.result.current.items).toEqual([]);
    expect(deps.startSession).not.toHaveBeenCalled();
  });
});
