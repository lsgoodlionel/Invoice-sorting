import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query';
import { notifications } from '@mantine/notifications';
import { ApiError, UnauthorizedError, errorMessage } from './api/client';

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

/** 查询失败重试一次；401 不重试，尽快回到登录页。 */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  return !(error instanceof UnauthorizedError) && failureCount < MAX_QUERY_RETRIES;
}

/** 全局错误提示：查询与写操作失败统一显示后端中文 error。 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    queryCache: new QueryCache({
      onError: (error, query) => {
        if (shouldNotify(error, query.meta)) notifyError(error, '加载失败');
      },
    }),
    mutationCache: new MutationCache({
      onError: (error, _vars, _ctx, mutation) => {
        if (shouldNotify(error, mutation.meta)) notifyError(error);
      },
    }),
    defaultOptions: {
      queries: { retry: shouldRetry, refetchOnWindowFocus: false, staleTime: 5_000 },
      mutations: { retry: 0 },
    },
  });
}
