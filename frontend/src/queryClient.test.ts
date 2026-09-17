import { describe, expect, test } from 'vitest';
import { ApiError } from './api/client';
import { shouldNotify } from './queryClient';

describe('shouldNotify', () => {
  test('respects silent meta and handled status codes', () => {
    expect(shouldNotify(new Error('x'), undefined)).toBe(true);
    expect(shouldNotify(new Error('x'), { silent: true })).toBe(false);
    expect(shouldNotify(new ApiError('冲突', 409), { silentStatuses: [409] })).toBe(false);
    expect(shouldNotify(new ApiError('坏请求', 400), { silentStatuses: [409] })).toBe(true);
  });
});
