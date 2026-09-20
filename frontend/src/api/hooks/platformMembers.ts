import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import type { ExportJob, Invite, InviteCreate, PlatformMemberInput, User, UserPatch } from '../types';
import { queryKeys } from './keys';

const base = (slug: string) => `/platform/tenants/${slug}`;

export const platformMembersApi = {
  list: (slug: string) => api.get<User[]>(`${base(slug)}/members`),
  add: (slug: string, input: PlatformMemberInput) => api.post<User>(`${base(slug)}/members`, input),
  update: (slug: string, id: number, patch: UserPatch) =>
    api.patch<User>(`${base(slug)}/members/${id}`, patch),
  resetPassword: (slug: string, id: number, password: string) =>
    api.post<null>(`${base(slug)}/members/${id}/password`, { password }),
  invites: (slug: string) => api.get<Invite[]>(`${base(slug)}/invites`),
  createInvite: (slug: string, input: InviteCreate) =>
    api.post<Invite>(`${base(slug)}/invites`, input),
  startExport: (slug: string) => api.post<ExportJob>(`${base(slug)}/export`),
  exportStatus: (slug: string, job: string) =>
    api.get<ExportJob>(`${base(slug)}/export/${job}/status`),
};

/** 某账套的成员（平台管理员视角）。 */
export const useTenantMembers = (slug: string) =>
  useQuery({ queryKey: queryKeys.platformMembers(slug), queryFn: () => platformMembersApi.list(slug) });

export const useTenantInvites = (slug: string) =>
  useQuery({
    queryKey: queryKeys.platformInvites(slug),
    queryFn: () => platformMembersApi.invites(slug),
    meta: { silent: true },
  });

function useRefreshTenant(slug: string) {
  const client = useQueryClient();
  return async () => {
    await client.invalidateQueries({ queryKey: queryKeys.platformMembers(slug) });
    await client.invalidateQueries({ queryKey: ['platform', 'tenants'] });
  };
}

export function useAddTenantMember(slug: string) {
  const refresh = useRefreshTenant(slug);
  return useMutation({
    mutationFn: (input: PlatformMemberInput) => platformMembersApi.add(slug, input),
    onSuccess: refresh,
    meta: { silent: true },
  });
}

export function useUpdateTenantMember(slug: string) {
  const refresh = useRefreshTenant(slug);
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: UserPatch }) =>
      platformMembersApi.update(slug, id, patch),
    onSuccess: refresh,
    meta: { silent: true },
  });
}

export function useResetTenantMemberPassword(slug: string) {
  return useMutation({
    mutationFn: ({ id, password }: { id: number; password: string }) =>
      platformMembersApi.resetPassword(slug, id, password),
    meta: { silent: true },
  });
}

export function useCreateTenantInvite(slug: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: InviteCreate) => platformMembersApi.createInvite(slug, input),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.platformInvites(slug) }),
    meta: { silent: true },
  });
}
