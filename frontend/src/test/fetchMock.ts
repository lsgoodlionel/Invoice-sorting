import { vi } from 'vitest';

export interface RecordedCall {
  method: string;
  url: string;
  body: unknown;
}

type Handler = (call: RecordedCall) => { status?: number; data?: unknown; error?: string };

/** 以 "METHOD /api/path" 为键模拟后端信封响应；路径不含查询串。 */
export function mockFetch(routes: Record<string, Handler | unknown>) {
  const calls: RecordedCall[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? 'GET').toUpperCase();
    const body = typeof init?.body === 'string' ? (JSON.parse(init.body) as unknown) : init?.body;
    const call = { method, url, body };
    calls.push(call);
    const key = `${method} ${url.split('?')[0]}`;
    if (!(key in routes)) {
      return new Response(JSON.stringify({ ok: false, data: null, error: `未模拟 ${key}` }), { status: 404 });
    }
    const route = routes[key];
    const result = typeof route === 'function' ? (route as Handler)(call) : { data: route };
    const status = result.status ?? 200;
    const ok = status < 400;
    return new Response(JSON.stringify({ ok, data: ok ? (result.data ?? null) : null, error: ok ? null : result.error }), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });
  });
  vi.stubGlobal('fetch', fetchMock);
  return { calls, fetchMock };
}
