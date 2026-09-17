import { MutationCache, QueryCache, QueryClient, type QueryKey } from '@tanstack/react-query';
import { notifications } from '@mantine/notifications';
import { ApiError, UnauthorizedError, errorMessage } from './api/client';
import { WORKFLOW_KEYS } from './api/hooks/keys';
import { describeError, isStaleDataError, type ErrorAction } from './lib/errorGuide';

export interface AppMeta extends Record<string, unknown> {
  /** 不显示全局错误提示 */
  silent?: boolean;
  /** 这些 HTTP 状态码由调用方自行处理 */
  silentStatuses?: readonly number[];
}

declare module '@tanstack/react-query' {
  interface Register {
    queryMeta: AppMeta;
    mutationMeta: AppMeta;
  }
}

export function notifyError(error: unknown, title = '操作失败'): void {
  notifications.show({ color: 'red', title, message: errorMessage(error) });
}

const MAX_QUERY_RETRIES = 1;

/** 401 由 AuthGate 切换到登录/设置页处理，不弹通用错误提示。 */
export function shouldNotify(error: unknown, meta: AppMeta | undefined): boolean {
  if (meta?.silent || error instanceof UnauthorizedError) return false;
  if (error instanceof ApiError && meta?.silentStatuses?.includes(error.status)) return false;
  return true;
}

/** 查询失败重试一次；401 不重试（尽快回到登录页），404/409 不重试（数据已在别处变更）。 */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof UnauthorizedError || isStaleDataError(error)) return false;
  return failureCount < MAX_QUERY_RETRIES;
}

const REFRESH_THROTTLE_MS = 3_000;

/** 带说明的错误提示：相同错误用同一 id，避免重复弹出多条。 */
function notifyWithGuide(error: unknown, action: ErrorAction): void {
  const guide = describeError(error, action);
  notifications.show({ id: guide.dedupeKey, color: guide.kind === 'stale' ? 'yellow' : 'red', title: guide.title, message: guide.message, autoClose: guide.kind === 'stale' ? 6_000 : 10_000 });
}

function sameKey(first: QueryKey, second: QueryKey): boolean {
  return JSON.stringify(first) === JSON.stringify(second);
}

/** 数据已在别处变更时刷新业务列表；节流，并跳过出错的查询本身以免循环。 */
function createStaleRefresher(getClient: () => QueryClient) {
  let lastRefreshAt = -Infinity;
  return (failedKey?: QueryKey) => {
    const nowMs = Date.now();
    if (nowMs - lastRefreshAt < REFRESH_THROTTLE_MS) return;
    lastRefreshAt = nowMs;
    const client = getClient();
    WORKFLOW_KEYS.forEach((queryKey) => {
      void client.invalidateQueries({
        queryKey,
        predicate: (query) => failedKey === undefined || !sameKey(query.queryKey, failedKey),
      });
    });
  };
}

/**
 * 全局错误处理：
 * - 查询遇到 404/409（数据已在别处变更）：不打扰用户，静默刷新相关列表；
 * - 写操作遇到 404/409：提示发生了什么并刷新；
 * - 其他错误：按类型说明原因与处理方法，相同提示只显示一条。
 */
export function createQueryClient(): QueryClient {
  let client: QueryClient | undefined;
  const refreshStale = createStaleRefresher(() => client as QueryClient);
  client = new QueryClient({
    queryCache: new QueryCache({
      onError: (error, query) => {
        if (isStaleDataError(error)) {
          refreshStale(query.queryKey);
          return;
        }
        if (shouldNotify(error, query.meta)) notifyWithGuide(error, 'load');
      },
    }),
    mutationCache: new MutationCache({
      onError: (error, _vars, _ctx, mutation) => {
        if (isStaleDataError(error)) refreshStale();
        if (shouldNotify(error, mutation.meta)) notifyWithGuide(error, 'save');
      },
    }),
    defaultOptions: {
      queries: { retry: shouldRetry, refetchOnWindowFocus: false, staleTime: 5_000 },
      mutations: { retry: 0 },
    },
  });
  return client;
}
