import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import type { User, UserCreate, UserPatch } from '../types';
import { queryKeys } from './keys';

export const usersApi = {
  list: () => api.get<User[]>('/users'),
  create: (input: UserCreate) => api.post<User>('/users', input),
  update: (id: number, patch: UserPatch) => api.patch<User>(`/users/${id}`, patch),
  resetPassword: (id: number, password: string) => api.post<null>(`/users/${id}/password`, { password }),
};

/** 用户列表（仅管理员调用）。 */
export const useUsers = () => useQuery({ queryKey: queryKeys.users, queryFn: usersApi.list });

/** 用户变更后刷新列表与当前用户（姓名、角色可能变化）。 */
function useRefreshUsers() {
  const client = useQueryClient();
  return async () => {
    await client.invalidateQueries({ queryKey: queryKeys.users });
    await client.invalidateQueries({ queryKey: queryKeys.authStatus });
  };
}

/** 错误由弹窗内联展示原文，不弹全局提示。 */
export function useCreateUser() {
  const refresh = useRefreshUsers();
  return useMutation({ mutationFn: usersApi.create, onSuccess: refresh, meta: { silent: true } });
}

export function useUpdateUser() {
  const refresh = useRefreshUsers();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: UserPatch }) => usersApi.update(id, patch),
    onSuccess: refresh,
    meta: { silent: true },
  });
}

export const useResetUserPassword = () =>
  useMutation({
    mutationFn: ({ id, password }: { id: number; password: string }) => usersApi.resetPassword(id, password),
    meta: { silent: true },
  });
