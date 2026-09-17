// 带上传进度的单文件上传（fetch 无上传进度事件，这里用 XMLHttpRequest）。
import { ApiError, apiUrl, parseJsonText, unwrapEnvelope } from './client';
import type { ImportFileResult } from './types';

export const UPLOAD_NETWORK_ERROR = '网络错误，上传失败';

export interface UploadOptions {
  onProgress?: (loaded: number, total: number) => void;
  signal?: AbortSignal;
}

const abortError = () => new DOMException('上传已取消', 'AbortError');

/** 以 multipart 发送表单并解析统一信封；支持进度回调与取消。 */
export function postFormWithProgress<T>(path: string, form: FormData, options: UploadOptions = {}): Promise<T> {
  const { onProgress, signal } = options;
  return new Promise<T>((resolve, reject) => {
    if (signal?.aborted) {
      reject(abortError());
      return;
    }
    const xhr = new XMLHttpRequest();
    const onAbortSignal = () => xhr.abort();
    const cleanup = () => signal?.removeEventListener('abort', onAbortSignal);

    xhr.open('POST', apiUrl(path));
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(event.loaded, event.total);
    };
    xhr.onload = () => {
      cleanup();
      try {
        resolve(unwrapEnvelope<T>(parseJsonText(xhr.responseText), xhr.status));
      } catch (error) {
        reject(error);
      }
    };
    xhr.onerror = () => {
      cleanup();
      reject(new ApiError(UPLOAD_NETWORK_ERROR, 0));
    };
    xhr.onabort = () => {
      cleanup();
      reject(abortError());
    };
    signal?.addEventListener('abort', onAbortSignal);
    xhr.send(form);
  });
}

export function uploadImportFile(sessionId: string, file: File, options: UploadOptions = {}): Promise<ImportFileResult> {
  const form = new FormData();
  form.append('file', file);
  return postFormWithProgress<ImportFileResult>(`/imports/${encodeURIComponent(sessionId)}/files`, form, options);
}
