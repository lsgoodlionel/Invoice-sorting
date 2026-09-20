import { useQuery } from '@tanstack/react-query';
import { api } from '../client';
import type { LicenseStatus } from '../types';
import { queryKeys } from './keys';

const LICENSE_STALE_MS = 5 * 60_000;

export const licenseApi = {
  status: () => api.get<LicenseStatus>('/license/status'),
};

/**
 * 私有化授权状态（顶部提示条）。
 * 失败时静默：授权提示不应该打断正常使用，也不弹全局错误。
 */
export const useLicenseStatus = () =>
  useQuery({
    queryKey: queryKeys.licenseStatus,
    queryFn: licenseApi.status,
    staleTime: LICENSE_STALE_MS,
    retry: false,
    meta: { silent: true },
  });
