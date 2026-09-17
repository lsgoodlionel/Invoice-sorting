import { describe, expect, test } from 'vitest';
import { ApiError, UnauthorizedError } from './api/client';
import { shouldNotify, shouldRetry } from './queryClient';

describe('shouldNotify', () => {
  test('respects silent meta and handled status codes', () => {
    expect(shouldNotify(new Error('x'), undefined)).toBe(true);
    expect(shouldNotify(new Error('x'), { silent: true })).toBe(false);
    expect(shouldNotify(new ApiError('冲突', 409), { silentStatuses: [409] })).toBe(false);
    expect(shouldNotify(new ApiError('坏请求', 400), { silentStatuses: [409] })).toBe(true);
  });

  test('never notifies for 401 unauthorized errors', () => {
    expect(shouldNotify(new UnauthorizedError('请先登录'), undefined)).toBe(false);
  });
});

describe('shouldRetry', () => {
  test('retries once except for unauthorized errors', () => {
    expect(shouldRetry(0, new ApiError('坏', 500))).toBe(true);
    expect(shouldRetry(1, new ApiError('坏', 500))).toBe(false);
    expect(shouldRetry(0, new UnauthorizedError('请先登录'))).toBe(false);
  });
});
