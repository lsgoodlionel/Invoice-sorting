import { beforeEach, describe, expect, test, vi } from 'vitest';
import { FakeXhr, installFakeXhr, lastXhr } from '../test/fakeXhr';
import { makeAttachment } from '../test/fixtures';
import { ApiError } from './client';
import type { ImportFileResult } from './types';
import { UPLOAD_NETWORK_ERROR, uploadImportFile } from './upload';

const file = new File(['%PDF-1.4'], '发票.pdf', { type: 'application/pdf' });

const fileResult: ImportFileResult = {
  original_name: '发票.pdf',
  status: 'imported',
  attachment: makeAttachment({ id: 3, expense_id: null }),
  recognized_as: '发票',
  message: '',
  existing_expense_id: null,
};

describe('uploadImportFile', () => {
  beforeEach(() => {
    installFakeXhr();
  });

  test('posts a single file as multipart to the session endpoint and resolves envelope data', async () => {
    const promise = uploadImportFile('s 1', file);
    const xhr = lastXhr();
    expect(xhr.method).toBe('POST');
    expect(xhr.url).toBe('/api/imports/s%201/files');
    expect(xhr.headers).toEqual({ Accept: 'application/json' });
    const body = xhr.body as FormData;
    expect(body).toBeInstanceOf(FormData);
    expect((body.get('file') as File).name).toBe('发票.pdf');
    xhr.respond(200, { ok: true, data: fileResult, error: null });
    await expect(promise).resolves.toEqual(fileResult);
  });

  test('reports upload progress only when length is computable', async () => {
    const onProgress = vi.fn();
    const promise = uploadImportFile('s', file, { onProgress });
    const xhr = lastXhr();
    xhr.emitProgress(4, 8);
    xhr.emitProgress(1, 0, false);
    xhr.emitProgress(8, 8);
    expect(onProgress.mock.calls).toEqual([[4, 8], [8, 8]]);
    xhr.respond(200, { ok: true, data: fileResult, error: null });
    await promise;
  });

  test('ok=false envelope throws ApiError with backend message and status', async () => {
    const promise = uploadImportFile('s', file);
    lastXhr().respond(404, { ok: false, data: null, error: '导入会话不存在或已过期' });
    const error = await promise.catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ message: '导入会话不存在或已过期', status: 404 });
  });

  test('non-envelope response throws generic ApiError with HTTP status', async () => {
    const promise = uploadImportFile('s', file);
    lastXhr().respond(502, '<html>bad gateway</html>');
    await expect(promise).rejects.toMatchObject({ name: 'ApiError', message: '请求失败（HTTP 502）', status: 502 });
  });

  test('network failure throws a Chinese ApiError', async () => {
    const promise = uploadImportFile('s', file);
    lastXhr().failNetwork();
    await expect(promise).rejects.toMatchObject({ name: 'ApiError', message: UPLOAD_NETWORK_ERROR, status: 0 });
    expect(UPLOAD_NETWORK_ERROR).toBe('网络错误，上传失败');
  });

  test('aborting the signal aborts the request and rejects with AbortError', async () => {
    const controller = new AbortController();
    const promise = uploadImportFile('s', file, { signal: controller.signal });
    controller.abort();
    await expect(promise).rejects.toMatchObject({ name: 'AbortError' });
    expect(lastXhr().isAborted).toBe(true);
  });

  test('an already aborted signal rejects without sending', async () => {
    const controller = new AbortController();
    controller.abort();
    await expect(uploadImportFile('s', file, { signal: controller.signal })).rejects.toMatchObject({ name: 'AbortError' });
    expect(FakeXhr.instances).toHaveLength(0);
  });
});
