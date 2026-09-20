import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import type {
  LicenseInput,
  LicensePatch,
  LicenseRecord,
  OpenedTenant,
  Plan,
  PlanInput,
  PlanPatch,
  PlatformOverview,
  PlatformTenant,
  PlatformTenantPage,
  TenantCreateInput,
  TenantPatch,
} from '../types';
import { PLATFORM_KEYS, queryKeys, type PlatformTenantQuery } from './keys';

const OVERVIEW_STALE_MS = 60_000;

export const platformApi = {
  overview: () => api.get<PlatformOverview>('/platform/overview'),
  tenants: (query: PlatformTenantQuery) =>
    api.get<PlatformTenantPage>('/platform/tenants', { q: query.q, page: query.page }),
  openTenant: (input: TenantCreateInput) => api.post<OpenedTenant>('/platform/tenants', input),
  patchTenant: (slug: string, patch: TenantPatch) =>
    api.patch<PlatformTenant>(`/platform/tenants/${slug}`, patch),
  plans: () => api.get<Plan[]>('/platform/plans'),
  createPlan: (input: PlanInput) => api.post<Plan>('/platform/plans', input),
  updatePlan: (id: number, patch: PlanPatch) => api.patch<Plan>(`/platform/plans/${id}`, patch),
  deletePlan: (id: number) => api.del<null>(`/platform/plans/${id}`),
  licenses: () => api.get<LicenseRecord[]>('/platform/licenses'),
  issueLicense: (input: LicenseInput) => api.post<LicenseRecord>('/platform/licenses', input),
  updateLicense: (id: number, patch: LicensePatch) =>
    api.patch<LicenseRecord>(`/platform/licenses/${id}`, patch),
  unbindLicense: (id: number) => api.post<LicenseRecord>(`/platform/licenses/${id}/unbind`),
  deleteLicense: (id: number) => api.del<null>(`/platform/licenses/${id}`),
};

/** 平台概览；同时用来判断当前账号是不是平台管理员（403 即不是）。 */
export const usePlatformOverview = (enabled: boolean) =>
  useQuery({
    queryKey: queryKeys.platformOverview,
    queryFn: platformApi.overview,
    enabled,
    staleTime: OVERVIEW_STALE_MS,
    retry: false,
    meta: { silent: true },
  });

/** 任一平台写操作后刷新全部平台查询（账套、成员、套餐、授权互相影响）。 */
function useRefreshPlatform() {
  const client = useQueryClient();
  return async () => {
    await Promise.all(PLATFORM_KEYS.map((key) => client.invalidateQueries({ queryKey: key })));
  };
}

export const usePlatformTenants = (query: PlatformTenantQuery) =>
  useQuery({ queryKey: queryKeys.platformTenants(query), queryFn: () => platformApi.tenants(query) });

export function useOpenTenant() {
  const refresh = useRefreshPlatform();
  return useMutation({ mutationFn: platformApi.openTenant, onSuccess: refresh, meta: { silent: true } });
}

export function usePatchTenant() {
  const refresh = useRefreshPlatform();
  return useMutation({
    mutationFn: ({ slug, patch }: { slug: string; patch: TenantPatch }) =>
      platformApi.patchTenant(slug, patch),
    onSuccess: refresh,
    meta: { silent: true },
  });
}

export const usePlans = (enabled = true) =>
  useQuery({ queryKey: queryKeys.platformPlans, queryFn: platformApi.plans, enabled });

export function useCreatePlan() {
  const refresh = useRefreshPlatform();
  return useMutation({ mutationFn: platformApi.createPlan, onSuccess: refresh, meta: { silent: true } });
}

export function useUpdatePlan() {
  const refresh = useRefreshPlatform();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: PlanPatch }) => platformApi.updatePlan(id, patch),
    onSuccess: refresh,
    meta: { silent: true },
  });
}

export function useDeletePlan() {
  const refresh = useRefreshPlatform();
  return useMutation({ mutationFn: platformApi.deletePlan, onSuccess: refresh, meta: { silent: true } });
}

export const useLicenseRecords = (enabled = true) =>
  useQuery({ queryKey: queryKeys.platformLicenses, queryFn: platformApi.licenses, enabled });

export function useIssueLicense() {
  const refresh = useRefreshPlatform();
  return useMutation({ mutationFn: platformApi.issueLicense, onSuccess: refresh, meta: { silent: true } });
}

export function useUpdateLicense() {
  const refresh = useRefreshPlatform();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: LicensePatch }) =>
      platformApi.updateLicense(id, patch),
    onSuccess: refresh,
    meta: { silent: true },
  });
}

export function useUnbindLicense() {
  const refresh = useRefreshPlatform();
  return useMutation({ mutationFn: platformApi.unbindLicense, onSuccess: refresh, meta: { silent: true } });
}

export function useDeleteLicense() {
  const refresh = useRefreshPlatform();
  return useMutation({ mutationFn: platformApi.deleteLicense, onSuccess: refresh, meta: { silent: true } });
}
