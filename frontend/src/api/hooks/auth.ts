import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';
import { api } from '../client';
import type { AuthResult, AuthStatus, ChangePasswordInput, JoinInput, LoginInput, SetupInput, TenantOption } from '../types';
import { queryKeys } from './keys';

const AUTH_STATUS_STALE_MS = 60_000;

export const authApi = {
  status: () => api.get<AuthStatus>('/auth/status'),
  setup: (input: SetupInput) => api.post<AuthResult>('/auth/setup', input),
  login: (input: LoginInput) => api.post<AuthResult>('/auth/login', input),
  logout: () => api.post<null>('/auth/logout'),
  changePassword: (input: ChangePasswordInput) => api.post<null>('/auth/password', input),
  join: (input: JoinInput) => api.post<AuthResult>('/auth/join', input),
  tenants: () => api.get<TenantOption[]>('/auth/tenants'),
  switchTenant: (slug: string) => api.post<AuthResult>('/auth/switch-tenant', { slug }),
};

/** 认证状态；失败由 AuthGate 自行展示，不弹全局提示。 */
export const useAuthStatus = () =>
  useQuery({
    queryKey: queryKeys.authStatus,
    queryFn: authApi.status,
    staleTime: AUTH_STATUS_STALE_MS,
    retry: false,
    meta: { silent: true },
  });

/** 刷新认证状态（不打断正在进行的请求）。 */
export function useRefreshAuthStatus() {
  const client = useQueryClient();
  return useCallback(
    () => client.invalidateQueries({ queryKey: queryKeys.authStatus }, { cancelRefetch: false }),
    [client],
  );
}

export function useSetupPassword() {
  const refresh = useRefreshAuthStatus();
  return useMutation({ mutationFn: authApi.setup, onSuccess: refresh, meta: { silent: true } });
}

export function useLogin() {
  const refresh = useRefreshAuthStatus();
  return useMutation({ mutationFn: authApi.login, onSuccess: refresh, meta: { silent: true } });
}

export const useChangePassword = () => useMutation({ mutationFn: authApi.changePassword, meta: { silent: true } });

/** 退出后先刷新认证状态回到登录页，再清掉业务数据缓存。 */
export function useLogout() {
  const client = useQueryClient();
  const refresh = useRefreshAuthStatus();
  return useMutation({
    mutationFn: authApi.logout,
    onSuccess: async () => {
      await refresh();
      client.removeQueries({ predicate: (query) => query.queryKey[0] !== queryKeys.authStatus[0] });
    },
  });
}

/** 当前账号可进入的账套；仅多租户部署调用（单租户部署该接口 404）。 */
export const useAccountTenants = (enabled: boolean) =>
  useQuery({
    queryKey: queryKeys.authTenants,
    queryFn: authApi.tenants,
    enabled,
    staleTime: AUTH_STATUS_STALE_MS,
    retry: false,
    meta: { silent: true },
  });

/** 邀请码加入账套；与登录一样，成功后刷新认证状态进入应用。 */
export function useJoinTenant() {
  const refresh = useRefreshAuthStatus();
  return useMutation({ mutationFn: authApi.join, onSuccess: refresh, meta: { silent: true } });
}

/** 切换账套：换了账本，除认证状态外的缓存全部丢弃，避免显示上一个账套的数据。 */
export function useSwitchTenant() {
  const client = useQueryClient();
  const refresh = useRefreshAuthStatus();
  return useMutation({
    mutationFn: authApi.switchTenant,
    onSuccess: async () => {
      await refresh();
      client.removeQueries({ predicate: (query) => query.queryKey[0] !== queryKeys.authStatus[0] });
    },
    meta: { silent: true },
  });
}
