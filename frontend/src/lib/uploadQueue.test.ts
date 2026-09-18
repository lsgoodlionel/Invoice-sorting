import { describe, expect, test } from 'vitest';
import type { ImportFileResult } from '../api/types';
import { makeAttachment, makeTransportInvoice } from '../test/fixtures';
import {
  EMPTY_UPLOAD_QUEUE,
  fileSignature,
  formatUploadSummary,
  findDuplicateFiles,
  isQueueSettled,
  selectOverallProgress,
  selectStartable,
  selectUploadStats,
  uploadQueueReducer,
  type UploadQueueAction,
  type UploadQueueState,
} from './uploadQueue';

const makeFile = (name: string, size = 100, lastModified = 1) =>
  new File(['x'.repeat(size)], name, { type: 'application/pdf', lastModified });

const fileA = makeFile('a.pdf', 100);
const fileB = makeFile('b.pdf', 300);
const fileC = makeFile('c.pdf', 600);

const reduce = (state: UploadQueueState, ...actions: UploadQueueAction[]) => actions.reduce(uploadQueueReducer, state);

const added = reduce(EMPTY_UPLOAD_QUEUE, {
  type: 'add',
  entries: [
    { id: 'a', file: fileA },
    { id: 'b', file: fileB },
    { id: 'c', file: fileC },
  ],
});

const phaseOf = (state: UploadQueueState, id: string) => state.items.find((item) => item.id === id)?.phase;

const result = (overrides: Partial<ImportFileResult> = {}): ImportFileResult => ({
  original_name: 'a.pdf',
  status: 'imported',
  attachment: makeAttachment({ id: 9, expense_id: null }),
  recognized_as: '发票',
  message: '',
  existing_expense_id: null,
  ...overrides,
});

describe('uploadQueueReducer add', () => {
  test('adds waiting items with file metadata', () => {
    expect(added.items).toHaveLength(3);
    expect(added.items[0]).toEqual({
      id: 'a', file: fileA, name: 'a.pdf', size: 100, phase: 'waiting', progress: 0,
      recognizedAs: '', message: '', attachmentId: null, existingExpenseId: null,
    });
  });

  test('ignores files with same name, size and lastModified (existing and within the batch)', () => {
    const twin = makeFile('a.pdf', 100);
    const changed = makeFile('a.pdf', 100, 2);
    const next = reduce(added, {
      type: 'add',
      entries: [{ id: 'd', file: twin }, { id: 'e', file: changed }, { id: 'f', file: changed }],
    });
    expect(next.items.map((item) => item.id)).toEqual(['a', 'b', 'c', 'e']);
    expect(added.items).toHaveLength(3);
  });

  test('findDuplicateFiles reports files already queued or repeated in the drop', () => {
    const twin = makeFile('a.pdf', 100);
    const fresh = makeFile('new.pdf');
    const freshTwin = makeFile('new.pdf');
    expect(findDuplicateFiles(added.items, [twin, fresh, freshTwin])).toEqual([twin, freshTwin]);
    expect(fileSignature(fileA)).toBe('a.pdf|100|1');
  });
});

describe('uploadQueueReducer lifecycle', () => {
  test('start → progress → uploaded → result imported', () => {
    let state = reduce(added, { type: 'start', id: 'a' });
    expect(phaseOf(state, 'a')).toBe('uploading');
    state = reduce(state, { type: 'progress', id: 'a', loaded: 33, total: 100 });
    expect(state.items[0].progress).toBe(33);
    state = reduce(state, { type: 'uploaded', id: 'a' });
    expect(state.items[0]).toMatchObject({ phase: 'processing', progress: 100 });
    state = reduce(state, { type: 'result', id: 'a', result: result({ message: '无法识别发票内容' }) });
    expect(state.items[0]).toMatchObject({ phase: 'done', recognizedAs: '发票', message: '无法识别发票内容', attachmentId: 9, recognizedDetail: '' });
  });

  test('result keeps travel summary of the imported attachment', () => {
    const ticket = makeAttachment({ id: 9, expense_id: null, invoice: makeTransportInvoice() });
    const state = reduce(added, { type: 'start', id: 'a' }, { type: 'uploaded', id: 'a' }, { type: 'result', id: 'a', result: result({ attachment: ticket }) });
    expect(state.items[0].recognizedDetail).toBe('火车 G7123 · 上海虹桥 → 苏州园区 · 08-15 · 张三');
  });

  test('progress clamps to 0-100, handles zero total and is ignored outside uploading', () => {
    const uploading = reduce(added, { type: 'start', id: 'a' });
    expect(reduce(uploading, { type: 'progress', id: 'a', loaded: 150, total: 100 }).items[0].progress).toBe(100);
    expect(reduce(uploading, { type: 'progress', id: 'a', loaded: 0, total: 0 }).items[0].progress).toBe(0);
    expect(reduce(added, { type: 'progress', id: 'a', loaded: 50, total: 100 })).toBe(added);
  });

  test('duplicate and error results', () => {
    const base = reduce(added, { type: 'start', id: 'a' }, { type: 'start', id: 'b' });
    const state = reduce(
      base,
      { type: 'result', id: 'a', result: result({ status: 'duplicate', attachment: null, message: '发票号码重复', existing_expense_id: 7 }) },
      { type: 'result', id: 'b', result: result({ status: 'error', attachment: null, recognized_as: '', message: '无法解析' }) },
    );
    expect(state.items[0]).toMatchObject({ phase: 'duplicate', message: '发票号码重复', existingExpenseId: 7, attachmentId: null, progress: 100 });
    expect(state.items[1]).toMatchObject({ phase: 'error', message: '无法解析' });
  });

  test('fail marks error; retry resets to waiting; retry ignored for other phases', () => {
    const failed = reduce(added, { type: 'start', id: 'a' }, { type: 'fail', id: 'a', message: '网络错误，上传失败' });
    expect(failed.items[0]).toMatchObject({ phase: 'error', message: '网络错误，上传失败' });
    const retried = reduce(failed, { type: 'retry', id: 'a' });
    expect(retried.items[0]).toMatchObject({ phase: 'waiting', progress: 0, message: '' });
    expect(reduce(added, { type: 'retry', id: 'a' })).toBe(added);
    expect(reduce(added, { type: 'fail', id: 'a', message: 'x' })).toBe(added);
  });

  test('cancel active items; cancelled can be retried; late results are ignored', () => {
    const cancelled = reduce(added, { type: 'start', id: 'a' }, { type: 'cancel', id: 'a' }, { type: 'cancel', id: 'b' });
    expect(phaseOf(cancelled, 'a')).toBe('cancelled');
    expect(phaseOf(cancelled, 'b')).toBe('cancelled');
    expect(reduce(cancelled, { type: 'result', id: 'a', result: result() })).toBe(cancelled);
    expect(reduce(cancelled, { type: 'cancel', id: 'a' })).toBe(cancelled);
    expect(phaseOf(reduce(cancelled, { type: 'retry', id: 'a' }), 'a')).toBe('waiting');
  });

  test('start and uploaded only apply to the right phase; unknown ids are no-ops', () => {
    expect(reduce(added, { type: 'uploaded', id: 'a' })).toBe(added);
    const uploading = reduce(added, { type: 'start', id: 'a' });
    expect(reduce(uploading, { type: 'start', id: 'a' })).toBe(uploading);
    expect(reduce(added, { type: 'start', id: 'zzz' })).toBe(added);
  });

  test('reset empties the queue', () => {
    expect(reduce(added, { type: 'reset' })).toEqual(EMPTY_UPLOAD_QUEUE);
  });
});

describe('selectors', () => {
  const mixed = reduce(
    added,
    { type: 'start', id: 'a' },
    { type: 'progress', id: 'a', loaded: 50, total: 100 },
    { type: 'start', id: 'b' },
    { type: 'uploaded', id: 'b' },
  );

  test('stats count phases', () => {
    const state = reduce(
      EMPTY_UPLOAD_QUEUE,
      { type: 'add', entries: ['1', '2', '3', '4', '5', '6'].map((id) => ({ id, file: makeFile(`${id}.pdf`) })) },
      { type: 'start', id: '1' }, { type: 'result', id: '1', result: result() },
      { type: 'start', id: '2' }, { type: 'result', id: '2', result: result({ status: 'duplicate' }) },
      { type: 'start', id: '3' }, { type: 'fail', id: '3', message: 'x' },
      { type: 'cancel', id: '4' },
      { type: 'start', id: '5' },
    );
    expect(selectUploadStats(state)).toEqual({ total: 6, done: 1, duplicate: 1, failed: 1, cancelled: 1, active: 2 });
  });

  test('overall progress is byte weighted; processing counts as 100%', () => {
    // a: 100B at 50%, b: 300B processing (100%), c: 600B waiting (0%)
    expect(selectOverallProgress(mixed)).toBe(35);
    expect(selectOverallProgress(EMPTY_UPLOAD_QUEUE)).toBe(0);
  });

  test('overall progress weights empty files as 1 byte', () => {
    const state = reduce(EMPTY_UPLOAD_QUEUE, { type: 'add', entries: [{ id: 'z', file: new File([], 'z.pdf') }] }, { type: 'start', id: 'z' }, { type: 'uploaded', id: 'z' });
    expect(selectOverallProgress(state)).toBe(100);
  });

  test('isQueueSettled requires items and no active phases', () => {
    expect(isQueueSettled(EMPTY_UPLOAD_QUEUE)).toBe(false);
    expect(isQueueSettled(mixed)).toBe(false);
    const settled = reduce(mixed, { type: 'cancel', id: 'a' }, { type: 'result', id: 'b', result: result() }, { type: 'cancel', id: 'c' });
    expect(isQueueSettled(settled)).toBe(true);
  });

  test('selectStartable respects the concurrency limit', () => {
    expect(selectStartable(added, 3).map((item) => item.id)).toEqual(['a', 'b', 'c']);
    expect(selectStartable(added, 2).map((item) => item.id)).toEqual(['a', 'b']);
    expect(selectStartable(mixed, 3).map((item) => item.id)).toEqual(['c']);
    expect(selectStartable(mixed, 2)).toEqual([]);
  });
});

describe('formatUploadSummary', () => {
  const stats = { total: 12, done: 7, duplicate: 1, failed: 1, cancelled: 0, active: 3 };

  test('in progress', () => {
    expect(formatUploadSummary(stats, false)).toBe('正在导入 12 个文件 · 已完成 7 · 重复 1 · 失败 1');
  });

  test('settled, with cancelled count when present', () => {
    expect(formatUploadSummary({ ...stats, done: 10, active: 0 }, true)).toBe('导入完成：新增 10 · 重复 1 · 失败 1');
    expect(formatUploadSummary({ ...stats, cancelled: 2 }, true)).toBe('导入完成：新增 7 · 重复 1 · 失败 1 · 已取消 2');
  });
});
