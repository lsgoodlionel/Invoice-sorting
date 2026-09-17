import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { api, apiUrl } from '../client';
import type { Stats, StatsQuery } from '../types';
import { queryKeys } from './keys';

export const statsApi = {
  get: (query: StatsQuery) => api.get<Stats>('/stats', { ...query }),
  exportUrl: (query: StatsQuery) => apiUrl('/stats/export', { ...query }),
};

export function useStats(query: StatsQuery) {
  return useQuery({
    queryKey: queryKeys.stats(query),
    queryFn: () => statsApi.get(query),
    placeholderData: keepPreviousData,
  });
}
