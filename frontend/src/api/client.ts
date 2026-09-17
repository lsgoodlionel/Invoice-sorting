import type { ApiEnvelope } from './types';

export const API_BASE = '/api';

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export type QueryValue = string | number | boolean | readonly (string | number)[] | null | undefined;
export type QueryParams = Readonly<Record<string, QueryValue>>;

/** 构造查询字符串：忽略 undefined/null/空串/空数组，数组用逗号连接。 */
export function buildQuery(params: QueryParams = {}): string {
  const pairs = Object.entries(params).flatMap(([key, value]): [string, string][] => {
    if (value === undefined || value === null || value === '') return [];
    if (Array.isArray(value)) return value.length === 0 ? [] : [[key, value.join(',')]];
    return [[key, String(value)]];
  });
  if (pairs.length === 0) return '';
  return `?${new URLSearchParams(pairs).toString()}`;
}

export function apiUrl(path: string, params?: QueryParams): string {
  return `${API_BASE}${path}${buildQuery(params)}`;
}

function isEnvelope(value: unknown): value is ApiEnvelope<unknown> {
  return typeof value === 'object' && value !== null && 'ok' in value;
}

const GENERIC_ERROR = '请求失败';
const NETWORK_ERROR = '无法连接本地服务，请确认后端已启动';

async function readJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

/** 解析信封：ok=false 或非 2xx 时抛出 ApiError（优先使用后端中文 error）。 */
export async function parseEnvelope<T>(response: Response): Promise<T> {
  const body = await readJson(response);
  if (!isEnvelope(body)) {
    throw new ApiError(`${GENERIC_ERROR}（HTTP ${response.status}）`, response.status);
  }
  if (!body.ok || !response.ok) {
    throw new ApiError(body.error || `${GENERIC_ERROR}（HTTP ${response.status}）`, response.status);
  }
  return body.data as T;
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  params?: QueryParams;
  json?: unknown;
  form?: FormData;
  signal?: AbortSignal;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', params, json, form, signal } = options;
  const headers: Record<string, string> = { Accept: 'application/json' };
  let body: BodyInit | undefined;
  if (form) {
    body = form;
  } else if (json !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(json);
  }
  let response: Response;
  try {
    response = await fetch(apiUrl(path, params), { method, headers, body, signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new ApiError(NETWORK_ERROR, 0);
  }
  return parseEnvelope<T>(response);
}

export const api = {
  get: <T>(path: string, params?: QueryParams) => request<T>(path, { params }),
  post: <T>(path: string, json?: unknown) => request<T>(path, { method: 'POST', json }),
  patch: <T>(path: string, json: unknown) => request<T>(path, { method: 'PATCH', json }),
  put: <T>(path: string, json: unknown) => request<T>(path, { method: 'PUT', json }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  upload: <T>(path: string, files: readonly File[], fields: Readonly<Record<string, string>> = {}) => {
    const form = new FormData();
    files.forEach((file) => form.append('files', file));
    Object.entries(fields).forEach(([key, value]) => form.append(key, value));
    return request<T>(path, { method: 'POST', form });
  },
};

export function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return GENERIC_ERROR;
}
