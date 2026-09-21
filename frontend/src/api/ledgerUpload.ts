// 搬迁包分片上传：File.slice 逐片计算摘要与上传，大文件不整体读进内存。
import { createSha256 } from '../lib/sha256';
import { UnauthorizedError } from './client';
import { backupApi, type ImportPreview } from './hooks/backup';

const MB = 1024 * 1024;
/** 设计文档约定每片 8 MB（后端可在登记时改为别的值） */
export const DEFAULT_PART_SIZE = 8 * MB;
/** 单片失败后的自动重试次数 */
export const PART_RETRY_LIMIT = 2;
const RETRY_DELAY_MS = 800;

const isAbort = (error: unknown) => error instanceof DOMException && error.name === 'AbortError';
const abortError = () => new DOMException('上传已取消', 'AbortError');

function throwIfAborted(signal: AbortSignal | undefined): void {
  if (signal?.aborted) throw abortError();
}

const wait = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

export interface HashOptions {
  readBytes?: number;
  onProgress?: (hashedBytes: number) => void;
  signal?: AbortSignal;
}

/** 逐片读取文件计算 SHA-256（十六进制）。 */
export async function hashFile(file: Blob, { readBytes = DEFAULT_PART_SIZE, onProgress, signal }: HashOptions = {}): Promise<string> {
  const hasher = createSha256();
  for (let start = 0; start < file.size; start += readBytes) {
    throwIfAborted(signal);
    const end = Math.min(start + readBytes, file.size);
    hasher.update(new Uint8Array(await file.slice(start, end).arrayBuffer()));
    onProgress?.(end);
  }
  return hasher.digestHex();
}

export interface UploadPartsOptions {
  partSize: number;
  onProgress?: (uploadedBytes: number) => void;
  signal?: AbortSignal;
  retryDelayMs?: number;
}

async function putPartWithRetry(uploadId: string, index: number, blob: Blob, options: UploadPartsOptions): Promise<void> {
  const { signal, retryDelayMs = RETRY_DELAY_MS } = options;
  for (let attempt = 0; ; attempt += 1) {
    throwIfAborted(signal);
    try {
      await backupApi.uploadPart(uploadId, index, blob, signal);
      return;
    } catch (error) {
      const isFinal = attempt >= PART_RETRY_LIMIT || isAbort(error) || error instanceof UnauthorizedError;
      if (isFinal) throw error;
      await wait(retryDelayMs * (attempt + 1));
    }
  }
}

/** 按顺序逐片上传；单片失败自动重试 PART_RETRY_LIMIT 次。 */
export async function uploadParts(uploadId: string, file: Blob, options: UploadPartsOptions): Promise<void> {
  const { partSize, onProgress } = options;
  const partCount = Math.max(1, Math.ceil(file.size / partSize));
  for (let index = 0; index < partCount; index += 1) {
    const end = Math.min((index + 1) * partSize, file.size);
    await putPartWithRetry(uploadId, index, file.slice(index * partSize, end), options);
    onProgress?.(end);
  }
}

export type UploadStage = 'hashing' | 'uploading' | 'analyzing';

export interface UploadPackageOptions {
  signal: AbortSignal;
  onStage: (stage: UploadStage) => void;
  /** 当前阶段的完成百分比 0–100 */
  onPercent: (percent: number) => void;
  /** 登记成功后立即告知 upload_id，便于取消时清理 */
  onCreated: (uploadId: string) => void;
}

const percentOf = (done: number, total: number) => (total > 0 ? Math.round((done / total) * 100) : 100);

/** 校验 → 登记 → 分片上传 → 服务端合并校验并返回预览。 */
export async function uploadLedgerPackage(file: File, options: UploadPackageOptions): Promise<ImportPreview> {
  const { signal, onStage, onPercent, onCreated } = options;
  const toPercent = (done: number) => onPercent(percentOf(done, file.size));

  onStage('hashing');
  const sha256 = await hashFile(file, { onProgress: toPercent, signal });
  throwIfAborted(signal);
  const created = await backupApi.createImport({ filename: file.name, size: file.size, part_size: DEFAULT_PART_SIZE, sha256 });
  onCreated(created.upload_id);

  onStage('uploading');
  onPercent(0);
  await uploadParts(created.upload_id, file, { partSize: created.part_size || DEFAULT_PART_SIZE, onProgress: toPercent, signal });

  onStage('analyzing');
  return backupApi.completeImport(created.upload_id, signal);
}
