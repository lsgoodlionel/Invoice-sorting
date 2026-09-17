import { afterEach, describe, expect, test, vi } from 'vitest';
import { installFakeXhr, lastXhr } from '../test/fakeXhr';
import { mockFetch } from '../test/fetchMock';
import { authEvents } from './authEvents';
import { ApiError, UnauthorizedError, api } from './client';
import { authApi } from './hooks/auth';
import { uploadImportFile } from './upload';

let unsubscribe: () => void = () => undefined;
afterEach(() => unsubscribe());

function listen() {
  const listener = vi.fn();
  unsubscribe = authEvents.subscribe(listener);
  return listener;
}

describe('401 handling', () => {
  test('protected request 401 throws UnauthorizedError and emits unauthorized event', async () => {
    mockFetch({ 'GET /api/expenses': () => ({ status: 401, error: '请先登录' }) });
    const listener = listen();
    const error = await api.get('/expenses').catch((e: unknown) => e);
    expect(error).toBeInstanceOf(UnauthorizedError);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as UnauthorizedError).message).toBe('请先登录');
    expect((error as UnauthorizedError).status).toBe(401);
    expect(listener).toHaveBeenCalledTimes(1);
  });

  test('wrong password on login does not emit unauthorized event', async () => {
    mockFetch({ 'POST /api/auth/login': () => ({ status: 401, error: '密码错误' }) });
    const listener = listen();
    await expect(authApi.login({ username: 'admin', password: 'wrongpass' })).rejects.toThrow('密码错误');
    expect(listener).not.toHaveBeenCalled();
  });

  test('XHR upload 401 throws UnauthorizedError and emits event', async () => {
    installFakeXhr();
    const listener = listen();
    const promise = uploadImportFile('s', new File(['x'], 'a.pdf'));
    lastXhr().respond(401, { ok: false, data: null, error: '请先设置初始密码' });
    await expect(promise).rejects.toBeInstanceOf(UnauthorizedError);
    expect(listener).toHaveBeenCalledTimes(1);
  });
});

describe('authApi', () => {
  test('sends contract payloads', async () => {
    const status = { auth_enabled: true, password_set: true, authenticated: false, user: null };
    const { calls } = mockFetch({
      'GET /api/auth/status': status,
      'POST /api/auth/setup': { authenticated: true },
      'POST /api/auth/login': { authenticated: true },
      'POST /api/auth/logout': null,
      'POST /api/auth/password': null,
    });
    await expect(authApi.status()).resolves.toEqual(status);
    await authApi.setup('password1');
    await authApi.login({ username: 'zhangsan', password: 'password1' });
    await authApi.logout();
    await authApi.changePassword({ current_password: 'old-pass1', new_password: 'new-pass1' });
    expect(calls.map((c) => [c.method, c.url, c.body])).toEqual([
      ['GET', '/api/auth/status', undefined],
      ['POST', '/api/auth/setup', { password: 'password1' }],
      ['POST', '/api/auth/login', { username: 'zhangsan', password: 'password1' }],
      ['POST', '/api/auth/logout', undefined],
      ['POST', '/api/auth/password', { current_password: 'old-pass1', new_password: 'new-pass1' }],
    ]);
  });
});
