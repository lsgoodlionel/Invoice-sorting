// 分文件导入的上传队列：纯函数 reducer 与选择器。
import type { ImportFileResult } from '../api/types';
import { attachmentTravelSummary } from './travelDetails';

export type UploadPhase = 'waiting' | 'uploading' | 'processing' | 'done' | 'duplicate' | 'error' | 'cancelled';

export interface UploadItem {
  id: string;
  file: File;
  name: string;
  size: number;
  phase: UploadPhase;
  /** 上传百分比 0-100 */
  progress: number;
  recognizedAs: string;
  /** 识别为的补充信息（酒店订单 / 交通行程摘要），无则 "" */
  recognizedDetail?: string;
  message: string;
  attachmentId: number | null;
  existingExpenseId: number | null;
}

export interface UploadQueueState {
  items: readonly UploadItem[];
}

export interface UploadEntry {
  id: string;
  file: File;
}

export type UploadQueueAction =
  | { type: 'add'; entries: readonly UploadEntry[] }
  | { type: 'start'; id: string }
  | { type: 'progress'; id: string; loaded: number; total: number }
  | { type: 'uploaded'; id: string }
  | { type: 'result'; id: string; result: ImportFileResult }
  | { type: 'fail'; id: string; message: string }
  | { type: 'retry'; id: string }
  | { type: 'cancel'; id: string }
  | { type: 'reset' };

export const EMPTY_UPLOAD_QUEUE: UploadQueueState = { items: [] };

const ACTIVE_PHASES: readonly UploadPhase[] = ['waiting', 'uploading', 'processing'];
const IN_FLIGHT_PHASES: readonly UploadPhase[] = ['uploading', 'processing'];
const RETRYABLE_PHASES: readonly UploadPhase[] = ['error', 'cancelled'];
const FULL_PROGRESS = 100;

export const isActivePhase = (phase: UploadPhase) => ACTIVE_PHASES.includes(phase);

/** 文件名 + 大小 + 修改时间相同视为同一文件。 */
export function fileSignature(file: File): string {
  return `${file.name}|${file.size}|${file.lastModified}`;
}

/** 生成“是否首次出现”判断：已在队列中或本批次已出现过的文件返回 false。 */
function createFirstSeenFilter(items: readonly UploadItem[]): (file: File) => boolean {
  const seen = new Set(items.map((item) => fileSignature(item.file)));
  return (file) => {
    const signature = fileSignature(file);
    if (seen.has(signature)) return false;
    seen.add(signature);
    return true;
  };
}

/** 返回本次拖入中会被忽略的文件（已在队列中，或同批次重复）。 */
export function findDuplicateFiles(items: readonly UploadItem[], files: readonly File[]): File[] {
  const isFirstSeen = createFirstSeenFilter(items);
  return files.filter((file) => !isFirstSeen(file));
}

function newItem({ id, file }: UploadEntry): UploadItem {
  return {
    id, file, name: file.name, size: file.size, phase: 'waiting', progress: 0,
    recognizedAs: '', message: '', attachmentId: null, existingExpenseId: null,
  };
}

function addEntries(state: UploadQueueState, entries: readonly UploadEntry[]): UploadQueueState {
  const isFirstSeen = createFirstSeenFilter(state.items);
  const fresh = entries.filter((entry) => isFirstSeen(entry.file)).map(newItem);
  return fresh.length === 0 ? state : { items: [...state.items, ...fresh] };
}

/** 仅当条目处于允许的阶段时应用更新，否则原样返回 state。 */
function updateItem(
  state: UploadQueueState,
  id: string,
  allowed: readonly UploadPhase[],
  patch: (item: UploadItem) => Partial<UploadItem>,
): UploadQueueState {
  const target = state.items.find((item) => item.id === id);
  if (!target || !allowed.includes(target.phase)) return state;
  return { items: state.items.map((item) => (item === target ? { ...item, ...patch(item) } : item)) };
}

function percent(loaded: number, total: number): number {
  if (total <= 0) return 0;
  return Math.min(FULL_PROGRESS, Math.max(0, Math.round((loaded / total) * FULL_PROGRESS)));
}

const RESULT_PHASE: Record<ImportFileResult['status'], UploadPhase> = { imported: 'done', duplicate: 'duplicate', error: 'error' };

function applyResult(result: ImportFileResult): Partial<UploadItem> {
  return {
    phase: RESULT_PHASE[result.status],
    progress: FULL_PROGRESS,
    recognizedAs: result.recognized_as,
    recognizedDetail: result.attachment ? (attachmentTravelSummary(result.attachment) ?? '') : '',
    message: result.message,
    attachmentId: result.attachment?.id ?? null,
    existingExpenseId: result.existing_expense_id,
  };
}

export function uploadQueueReducer(state: UploadQueueState, action: UploadQueueAction): UploadQueueState {
  switch (action.type) {
    case 'add':
      return addEntries(state, action.entries);
    case 'start':
      return updateItem(state, action.id, ['waiting'], () => ({ phase: 'uploading', progress: 0, message: '' }));
    case 'progress':
      return updateItem(state, action.id, ['uploading'], () => ({ progress: percent(action.loaded, action.total) }));
    case 'uploaded':
      return updateItem(state, action.id, ['uploading'], () => ({ phase: 'processing', progress: FULL_PROGRESS }));
    case 'result':
      return updateItem(state, action.id, IN_FLIGHT_PHASES, () => applyResult(action.result));
    case 'fail':
      return updateItem(state, action.id, IN_FLIGHT_PHASES, () => ({ phase: 'error', message: action.message }));
    case 'retry':
      return updateItem(state, action.id, RETRYABLE_PHASES, () => ({
        phase: 'waiting', progress: 0, message: '', recognizedAs: '', attachmentId: null, existingExpenseId: null,
      }));
    case 'cancel':
      return updateItem(state, action.id, ACTIVE_PHASES, () => ({ phase: 'cancelled' }));
    case 'reset':
      return EMPTY_UPLOAD_QUEUE;
  }
}

export interface UploadStats {
  total: number;
  done: number;
  duplicate: number;
  failed: number;
  cancelled: number;
  /** 等待、上传中、识别中 */
  active: number;
}

export function selectUploadStats(state: UploadQueueState): UploadStats {
  const count = (phases: readonly UploadPhase[]) => state.items.filter((item) => phases.includes(item.phase)).length;
  return {
    total: state.items.length,
    done: count(['done']),
    duplicate: count(['duplicate']),
    failed: count(['error']),
    cancelled: count(['cancelled']),
    active: count(ACTIVE_PHASES),
  };
}

const itemProgress = (item: UploadItem) => (item.phase === 'waiting' || item.phase === 'uploading' ? item.progress : FULL_PROGRESS);

/** 按字节加权的整体进度（0-100）；识别中与已结束的文件计为 100%。 */
export function selectOverallProgress(state: UploadQueueState): number {
  const weights = state.items.map((item) => Math.max(item.size, 1));
  const totalWeight = weights.reduce((sum, weight) => sum + weight, 0);
  if (totalWeight === 0) return 0;
  const weighted = state.items.reduce((sum, item, index) => sum + itemProgress(item) * weights[index], 0);
  return Math.round(weighted / totalWeight);
}

/** 队列非空且没有等待/上传中/识别中的文件。 */
export function isQueueSettled(state: UploadQueueState): boolean {
  return state.items.length > 0 && !state.items.some((item) => isActivePhase(item.phase));
}

/** 在并发上限内可以开始上传的等待文件（按加入顺序）。 */
export function selectStartable(state: UploadQueueState, concurrency: number): UploadItem[] {
  const inFlight = state.items.filter((item) => IN_FLIGHT_PHASES.includes(item.phase)).length;
  const slots = Math.max(0, concurrency - inFlight);
  return state.items.filter((item) => item.phase === 'waiting').slice(0, slots);
}

/** 上传面板顶部汇总文字。 */
export function formatUploadSummary(stats: UploadStats, isSettled: boolean): string {
  const cancelled = stats.cancelled > 0 ? ` · 已取消 ${stats.cancelled}` : '';
  const tail = `重复 ${stats.duplicate} · 失败 ${stats.failed}${cancelled}`;
  if (isSettled) return `导入完成：新增 ${stats.done} · ${tail}`;
  return `正在导入 ${stats.total} 个文件 · 已完成 ${stats.done} · ${tail}`;
}
