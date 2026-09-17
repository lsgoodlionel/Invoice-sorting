import { useQuery } from '@tanstack/react-query';
import { api } from '../client';
import type { Dashboard } from '../types';
import { queryKeys } from './keys';

const DASHBOARD_REFRESH_MS = 60_000;

export const dashboardApi = {
  get: () => api.get<Dashboard>('/dashboard'),
};

export function useDashboard() {
  return useQuery({
    queryKey: queryKeys.dashboard,
    queryFn: dashboardApi.get,
    refetchInterval: DASHBOARD_REFRESH_MS,
  });
}
