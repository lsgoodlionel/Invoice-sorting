import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import type { MyReferrals } from '../signupTypes';
import { queryKeys } from './keys';

// 登录用户的推荐链接（仅多账套部署）。

export const referralsApi = {
  me: () => api.get<MyReferrals>('/referrals/me'),
  reset: () => api.post<MyReferrals>('/referrals/me/reset'),
};

/** 我的推荐码与推荐记录；首次打开时后端自动生成推荐码。 */
export const useMyReferrals = (enabled: boolean) =>
  useQuery({ queryKey: queryKeys.myReferrals, queryFn: referralsApi.me, enabled, meta: { silent: true } });

/** 重置推荐码：旧链接立即失效，直接用返回值替换缓存。 */
export function useResetReferral() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: referralsApi.reset,
    onSuccess: (next) => client.setQueryData(queryKeys.myReferrals, next),
    meta: { silent: true },
  });
}
