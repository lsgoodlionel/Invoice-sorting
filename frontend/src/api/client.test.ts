import { describe, expect, test, vi } from 'vitest';
import { mockFetch } from '../test/fetchMock';
import { api, ApiError, apiUrl, buildQuery, errorMessage, parseEnvelope, request } from './client';

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

describe('buildQuery', () => {
  test('skips empty values and joins arrays', () => {
    expect(buildQuery({ a: 1, b: undefined, c: null, d: '', e: [], f: ['spent', 'sent'], g: false })).toBe('?a=1&f=spent%2Csent&g=false');
    expect(buildQuery()).toBe('');
    expect(apiUrl('/stats', { q: '京东' })).toBe(`/api/stats?q=${encodeURIComponent('京东')}`);
  });
});

describe('parseEnvelope', () => {
  test('returns data when ok', async () => {
    await expect(parseEnvelope(json({ ok: true, data: { id: 1 }, error: null }))).resolves.toEqual({ id: 1 });
  });

  test('throws ApiError with backend Chinese message and status', async () => {
    const error = await parseEnvelope(json({ ok: false, data: null, error: '记录缺少必需凭证' }, 409)).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ message: '记录缺少必需凭证', status: 409 });
  });

  test('ok=false with 200 still throws', async () => {
    await expect(parseEnvelope(json({ ok: false, data: null, error: '失败' }))).rejects.toThrow('失败');
  });

  test('non-envelope body throws generic error with status', async () => {
    await expect(parseEnvelope(new Response('<html>', { status: 502 }))).rejects.toThrow('请求失败（HTTP 502）');
    await expect(parseEnvelope(new Response('', { status: 500 }))).rejects.toMatchObject({ status: 500 });
    await expect(parseEnvelope(json({ ok: false, data: null, error: null }, 422))).rejects.toThrow('HTTP 422');
  });
});

describe('request', () => {
  test('sends JSON body and method', async () => {
    const { calls } = mockFetch({ 'PATCH /api/expenses/3': { id: 3 } });
    await expect(api.patch('/expenses/3', { merchant: 'x' })).resolves.toEqual({ id: 3 });
    expect(calls[0]).toMatchObject({ method: 'PATCH', body: { merchant: 'x' } });
  });

  test('covers get/post/put/del helpers', async () => {
    const { calls } = mockFetch({ 'GET /api/a': 1, 'POST /api/b': 2, 'PUT /api/c': 3, 'DELETE /api/d': null });
    expect(await api.get('/a', { x: 1 })).toBe(1);
    expect(await api.post('/b')).toBe(2);
    expect(await api.put('/c', {})).toBe(3);
    expect(await api.del('/d')).toBeNull();
    expect(calls.map((c) => c.url)).toEqual(['/api/a?x=1', '/api/b', '/api/c', '/api/d']);
  });

  test('upload sends multipart form with files and fields', async () => {
    const { calls } = mockFetch({ 'POST /api/expenses/1/attachments': { id: 1 } });
    const file = new File(['x'], 'a.pdf', { type: 'application/pdf' });
    await api.upload('/expenses/1/attachments', [file, file], { kind: 'order' });
    const form = calls[0].body as FormData;
    expect(form.getAll('files')).toHaveLength(2);
    expect(form.get('kind')).toBe('order');
  });

  test('network failure becomes friendly ApiError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    await expect(request('/x')).rejects.toMatchObject({ status: 0, message: '无法连接本地服务，请确认后端已启动' });
  });

  test('abort errors are rethrown unchanged', async () => {
    const abort = new DOMException('aborted', 'AbortError');
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(abort));
    await expect(request('/x')).rejects.toBe(abort);
  });
});

describe('errorMessage', () => {
  test('extracts message or falls back', () => {
    expect(errorMessage(new Error('坏了'))).toBe('坏了');
    expect(errorMessage('x')).toBe('请求失败');
  });
});
