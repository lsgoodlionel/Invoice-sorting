import { useQuery } from '@tanstack/react-query';
import { api } from '../client';
import type { QuotaStatus } from '../types';
import { queryKeys } from './keys';

const QUOTA_STALE_MS = 60_000;

export const quotaApi = {
  status: () => api.get<QuotaStatus>('/quota'),
};

/**
 * 套餐额度与账套状态（顶部提示条）。
 * 单账套部署返回 enforced=false；接口不存在或出错时静默隐藏，不打扰用户。
 */
export const useQuotaStatus = () =>
  useQuery({
    queryKey: queryKeys.quota,
    queryFn: quotaApi.status,
    staleTime: QUOTA_STALE_MS,
    retry: false,
    meta: { silent: true },
  });
