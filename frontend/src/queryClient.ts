import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query';
import { notifications } from '@mantine/notifications';
import { ApiError, errorMessage } from './api/client';

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

export function shouldNotify(error: unknown, meta: AppMeta | undefined): boolean {
  if (meta?.silent) return false;
  if (error instanceof ApiError && meta?.silentStatuses?.includes(error.status)) return false;
  return true;
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
      queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 5_000 },
      mutations: { retry: 0 },
    },
  });
}
