import { describe, expect, test } from 'vitest';
import { ApiError } from '../api/client';
import { describeError, isStaleDataError } from './errorGuide';

describe('describeError', () => {
  test('stale data (404/409) explains what happened and that the page refreshed', () => {
    const guide = describeError(new ApiError('附件已归属到记录 #43', 409), 'save');
    expect(guide.kind).toBe('stale');
    expect(guide.title).toBe('数据已变更');
    expect(guide.message).toContain('附件已归属到记录 #43');
    expect(guide.message).toContain('已自动刷新');
    expect(guide.shouldRefresh).toBe(true);

    const missing = describeError(new ApiError('支出记录不存在', 404), 'load');
    expect(missing.kind).toBe('stale');
    expect(missing.message).toContain('可能已被删除');
  });

  test('network errors tell the user how to check the service', () => {
    const guide = describeError(new ApiError('无法连接本地服务，请确认后端已启动', 0), 'load');
    expect(guide.kind).toBe('network');
    expect(guide.title).toBe('无法连接服务');
    expect(guide.message).toContain('systemctl status invoice-sorting');
    expect(guide.shouldRefresh).toBe(false);
  });

  test('server errors point to the logs', () => {
    const guide = describeError(new ApiError('请求失败（HTTP 500）', 500), 'save');
    expect(guide.kind).toBe('server');
    expect(guide.title).toBe('服务内部错误');
    expect(guide.message).toContain('journalctl -u invoice-sorting');
  });

  test('input problems keep the backend message and ask to adjust', () => {
    const guide = describeError(new ApiError('参数错误：body.amount_cents 必须大于等于 0', 422), 'save');
    expect(guide.kind).toBe('input');
    expect(guide.title).toBe('请检查填写内容');
    expect(guide.message).toContain('必须大于等于 0');
  });

  test('too large upload explains the limit', () => {
    const guide = describeError(new ApiError('文件过大', 413), 'save');
    expect(guide.kind).toBe('input');
    expect(guide.message).toContain('30MB');
  });

  test('titles depend on action for other errors', () => {
    expect(describeError(new Error('奇怪'), 'load').title).toBe('加载失败');
    expect(describeError(new Error('奇怪'), 'save').title).toBe('操作未完成');
  });

  test('same error produces the same dedupe key', () => {
    const first = describeError(new ApiError('无法连接本地服务，请确认后端已启动', 0), 'load');
    const second = describeError(new ApiError('无法连接本地服务，请确认后端已启动', 0), 'load');
    expect(first.dedupeKey).toBe(second.dedupeKey);
  });
});

describe('isStaleDataError', () => {
  test('only 404 and 409 api errors are stale', () => {
    expect(isStaleDataError(new ApiError('x', 404))).toBe(true);
    expect(isStaleDataError(new ApiError('x', 409))).toBe(true);
    expect(isStaleDataError(new ApiError('x', 500))).toBe(false);
    expect(isStaleDataError(new Error('x'))).toBe(false);
  });
});
