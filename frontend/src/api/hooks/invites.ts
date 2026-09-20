import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import type { Invite, InviteCreate } from '../types';
import { queryKeys } from './keys';

export const invitesApi = {
  list: () => api.get<Invite[]>('/invites'),
  create: (input: InviteCreate) => api.post<Invite>('/invites', input),
};

/** 本账套的邀请码（仅管理员；单租户部署不暴露入口）。 */
export const useInvites = (enabled: boolean) =>
  useQuery({ queryKey: queryKeys.invites, queryFn: invitesApi.list, enabled, meta: { silent: true } });

/** 生成邀请码；错误由弹窗内联展示原文。 */
export function useCreateInvite() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: invitesApi.create,
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.invites }),
    meta: { silent: true },
  });
}
