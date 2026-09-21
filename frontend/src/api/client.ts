import { authEvents } from './authEvents';
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

const HTTP_UNAUTHORIZED = 401;

/** 401：未登录、会话失效或尚未设置初始密码（message 为后端中文说明）。 */
export class UnauthorizedError extends ApiError {
  constructor(message: string) {
    super(message, HTTP_UNAUTHORIZED);
    this.name = 'UnauthorizedError';
  }
}

/** 这些端点的 401 是业务结果（如登录密码错误），不代表会话失效。 */
const AUTH_FORM_PATHS: readonly string[] = ['/auth/login', '/auth/setup'];

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

export interface UnwrapOptions {
  /** 401 时是否发布“认证失效”事件，默认 true */
  notifyUnauthorized?: boolean;
}

function unauthorized(body: unknown, notify: boolean): UnauthorizedError {
  if (notify) authEvents.emitUnauthorized();
  const message = isEnvelope(body) && body.error ? body.error : '请先登录';
  return new UnauthorizedError(message);
}

/**
 * 从已解析的响应体取信封数据：ok=false 或非 2xx 时抛出 ApiError（优先使用后端中文 error）；
 * 401 抛出 UnauthorizedError 并（默认）发布认证失效事件。
 */
export function unwrapEnvelope<T>(body: unknown, status: number, options: UnwrapOptions = {}): T {
  if (status === HTTP_UNAUTHORIZED) throw unauthorized(body, options.notifyUnauthorized ?? true);
  const isHttpOk = status >= 200 && status < 300;
  if (!isEnvelope(body)) {
    throw new ApiError(`${GENERIC_ERROR}（HTTP ${status}）`, status);
  }
  if (!body.ok || !isHttpOk) {
    throw new ApiError(body.error || `${GENERIC_ERROR}（HTTP ${status}）`, status);
  }
  return body.data as T;
}

/** 把响应文本解析为 JSON；空串或非法 JSON 返回 null。 */
export function parseJsonText(text: string): unknown {
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

/** 解析 fetch 响应的信封。 */
export async function parseEnvelope<T>(response: Response, options: UnwrapOptions = {}): Promise<T> {
  return unwrapEnvelope<T>(parseJsonText(await response.text()), response.status, options);
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  params?: QueryParams;
  json?: unknown;
  form?: FormData;
  /** 原样发送的二进制内容（如分片上传），Content-Type 为 application/octet-stream */
  blob?: Blob;
  signal?: AbortSignal;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', params, json, form, blob, signal } = options;
  const headers: Record<string, string> = { Accept: 'application/json' };
  let body: BodyInit | undefined;
  if (form) {
    body = form;
  } else if (blob) {
    headers['Content-Type'] = 'application/octet-stream';
    body = blob;
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
  return parseEnvelope<T>(response, { notifyUnauthorized: !AUTH_FORM_PATHS.includes(path) });
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
