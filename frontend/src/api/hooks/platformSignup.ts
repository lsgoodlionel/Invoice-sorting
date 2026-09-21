import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import type {
  ApproveInput,
  PlatformApplicationPage,
  PlatformReferralPage,
  RejectInput,
  ReviewResult,
  SignupSettings,
  SignupSettingsPatch,
} from '../signupTypes';
import { queryKeys, type PlatformApplicationQuery, type PlatformReferralQuery } from './keys';

// 平台管理员：注册申请审批、推荐记录与注册设置。

export const platformSignupApi = {
  applications: (query: PlatformApplicationQuery) =>
    api.get<PlatformApplicationPage>('/platform/applications', { status: query.status, q: query.q, page: query.page }),
  approve: (id: number, input: ApproveInput) =>
    api.post<ReviewResult>(`/platform/applications/${id}/approve`, input),
  reject: (id: number, input: RejectInput) =>
    api.post<ReviewResult>(`/platform/applications/${id}/reject`, input),
  resend: (id: number) => api.post<ReviewResult>(`/platform/applications/${id}/resend`),
  referrals: (query: PlatformReferralQuery) =>
    api.get<PlatformReferralPage>('/platform/referrals', { q: query.q, page: query.page }),
  setReferrerDisabled: (accountId: number, isDisabled: boolean) =>
    api.patch<{ account_id: number; is_disabled: boolean }>(`/platform/referrers/${accountId}`, { is_disabled: isDisabled }),
  settings: () => api.get<SignupSettings>('/platform/signup-settings'),
  patchSettings: (patch: SignupSettingsPatch) => api.patch<SignupSettings>('/platform/signup-settings', patch),
};

const PENDING_QUERY: PlatformApplicationQuery = { status: 'pending', q: '', page: 1 };
const APPLICATIONS_PREFIX = ['platform', 'applications'] as const;
const REFERRALS_PREFIX = ['platform', 'referrals'] as const;

export const usePlatformApplications = (query: PlatformApplicationQuery) =>
  useQuery({
    queryKey: queryKeys.platformApplications(query),
    queryFn: () => platformSignupApi.applications(query),
  });

/** 待审批数（页签角标）：与默认的「待审批」筛选共用同一个缓存。 */
export function usePendingApplicationCount(): number {
  const { data } = useQuery({
    queryKey: queryKeys.platformApplications(PENDING_QUERY),
    queryFn: () => platformSignupApi.applications(PENDING_QUERY),
    meta: { silent: true },
  });
  return data?.counts?.pending ?? data?.total ?? 0;
}

function useRefreshApplications() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: APPLICATIONS_PREFIX });
}

export function useApproveApplication() {
  const refresh = useRefreshApplications();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: ApproveInput }) => platformSignupApi.approve(id, input),
    onSuccess: refresh,
    meta: { silent: true },
  });
}

export function useRejectApplication() {
  const refresh = useRefreshApplications();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: RejectInput }) => platformSignupApi.reject(id, input),
    onSuccess: refresh,
    meta: { silent: true },
  });
}

export function useResendApplicationEmail() {
  const refresh = useRefreshApplications();
  return useMutation({ mutationFn: platformSignupApi.resend, onSuccess: refresh, meta: { silent: true } });
}

export const usePlatformReferrals = (query: PlatformReferralQuery) =>
  useQuery({ queryKey: queryKeys.platformReferrals(query), queryFn: () => platformSignupApi.referrals(query) });

/** 停用或恢复某人的推荐资格；停用后其推荐链接立即失效。 */
export function useSetReferrerDisabled() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ accountId, isDisabled }: { accountId: number; isDisabled: boolean }) =>
      platformSignupApi.setReferrerDisabled(accountId, isDisabled),
    onSuccess: () => client.invalidateQueries({ queryKey: REFERRALS_PREFIX }),
  });
}

export const useSignupSettings = () =>
  useQuery({ queryKey: queryKeys.platformSignupSettings, queryFn: platformSignupApi.settings });

export function usePatchSignupSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: platformSignupApi.patchSettings,
    onSuccess: (next) => client.setQueryData(queryKeys.platformSignupSettings, next),
    meta: { silent: true },
  });
}
