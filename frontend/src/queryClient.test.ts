import { describe, expect, test, vi } from 'vitest';
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

describe('shouldRetry stale data', () => {
  test('does not retry 404 or 409 because the data changed elsewhere', () => {
    expect(shouldRetry(0, new ApiError('附件已归属到记录 #43', 409))).toBe(false);
    expect(shouldRetry(0, new ApiError('支出记录不存在', 404))).toBe(false);
  });
});

describe('createQueryClient error handling', () => {
  test('stale query errors refresh other workflow data silently, without looping', async () => {
    const { createQueryClient } = await import('./queryClient');
    const { notifications } = await import('@mantine/notifications');
    const show = vi.spyOn(notifications, 'show');
    const client = createQueryClient();
    const invalidate = vi.spyOn(client, 'invalidateQueries');

    const failing = () => Promise.reject(new ApiError('附件已归属到记录 #43', 409));
    await client.fetchQuery({ queryKey: ['attachments', 'candidates', 43], queryFn: failing }).catch(() => undefined);
    await client.fetchQuery({ queryKey: ['attachments', 'candidates', 44], queryFn: failing }).catch(() => undefined);

    expect(show).not.toHaveBeenCalled();
    const refreshed = invalidate.mock.calls.map((call) => JSON.stringify(call[0]?.queryKey));
    expect(refreshed).toContain(JSON.stringify(['attachments', 'unassigned']));
    // 节流：短时间内多次过期错误只刷新一轮
    expect(refreshed.filter((key) => key === JSON.stringify(['attachments', 'unassigned']))).toHaveLength(1);
    show.mockRestore();
  });

  test('stale mutation errors explain and refresh', async () => {
    const { createQueryClient } = await import('./queryClient');
    const { notifications } = await import('@mantine/notifications');
    const show = vi.spyOn(notifications, 'show');
    const client = createQueryClient();
    const invalidate = vi.spyOn(client, 'invalidateQueries');

    const mutation = client.getMutationCache().build(client, {
      mutationFn: () => Promise.reject(new ApiError('文件“a.png”：已归属到记录 #43，请刷新后重试', 409)),
    });
    await mutation.execute(undefined).catch(() => undefined);

    expect(show).toHaveBeenCalledWith(expect.objectContaining({ title: '数据已变更' }));
    expect(invalidate).toHaveBeenCalled();
    show.mockRestore();
  });

  test('network query errors notify once with guidance', async () => {
    const { createQueryClient } = await import('./queryClient');
    const { notifications } = await import('@mantine/notifications');
    const show = vi.spyOn(notifications, 'show');
    const client = createQueryClient();
    const failing = () => Promise.reject(new ApiError('无法连接本地服务，请确认后端已启动', 0));

    await client.fetchQuery({ queryKey: ['expenses'], queryFn: failing, retry: false }).catch(() => undefined);

    expect(show).toHaveBeenCalledWith(expect.objectContaining({ title: '无法连接服务', id: expect.any(String) }));
    show.mockRestore();
  });
});
