import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';
import { api } from '../client';
import type { AuthResult, AuthStatus, ChangePasswordInput } from '../types';
import { queryKeys } from './keys';

const AUTH_STATUS_STALE_MS = 60_000;

export const authApi = {
  status: () => api.get<AuthStatus>('/auth/status'),
  setup: (password: string) => api.post<AuthResult>('/auth/setup', { password }),
  login: (password: string) => api.post<AuthResult>('/auth/login', { password }),
  logout: () => api.post<null>('/auth/logout'),
  changePassword: (input: ChangePasswordInput) => api.post<null>('/auth/password', input),
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
