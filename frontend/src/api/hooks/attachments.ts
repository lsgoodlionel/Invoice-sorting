import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import type {
  Attachment,
  AttachmentBulkAssign,
  AttachmentKind,
  ChecklistState,
  CreateExpensesResult,
  ExpenseDetail,
  MatchCandidate,
} from '../types';
import { invalidateWorkflow } from './invalidate';
import { queryKeys } from './keys';

export interface AttachmentPatch {
  kind?: AttachmentKind;
  expense_id?: number | null;
}

export const attachmentsApi = {
  unassigned: () => api.get<Attachment[]>('/attachments/unassigned'),
  update: (id: number, patch: AttachmentPatch) => api.patch<Attachment>(`/attachments/${id}`, patch),
  remove: (id: number) => api.del<null>(`/attachments/${id}`),
  bulkDelete: (ids: readonly number[]) => api.post<{ deleted: number }>('/attachments/bulk-delete', { ids }),
  bulkAssign: (input: AttachmentBulkAssign) => api.post<Attachment[]>('/attachments/bulk-assign', input),
  createExpenses: (ids: readonly number[]) => api.post<CreateExpensesResult>('/attachments/create-expenses', { ids }),
  reparse: (ids: readonly number[]) => api.post<Attachment[]>('/attachments/reparse', { ids }),
  candidates: (id: number) => api.get<MatchCandidate[]>(`/attachments/${id}/candidates`),
  thumbnailUrl: (id: number) => `/api/attachments/${id}/thumbnail`,
  fileUrl: (id: number) => `/api/attachments/${id}/file`,
  setChecklistState: (id: number, state: Exclude<ChecklistState, 'present'>, reason?: string) =>
    api.patch<ExpenseDetail>(`/checklist-items/${id}`, reason === undefined ? { state } : { state, reason }),
};

const UNASSIGNED_REFRESH_MS = 30_000;

export function useUnassignedAttachments() {
  return useQuery({
    queryKey: queryKeys.unassigned,
    queryFn: attachmentsApi.unassigned,
    // 收件箱会在后台自动处理文件：切回页面时与定时刷新，减少“数据已变更”
    refetchOnWindowFocus: true,
    refetchInterval: UNASSIGNED_REFRESH_MS,
  });
}

/** 待归属附件的候选记录；enabled 为 false 时不请求（懒加载）。 */
export function useAttachmentCandidates(id: number, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.attachmentCandidates(id),
    queryFn: () => attachmentsApi.candidates(id),
    enabled,
  });
}

export function useUpdateAttachment() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: AttachmentPatch }) => attachmentsApi.update(id, patch),
    onSuccess: () => invalidateWorkflow(client),
  });
}

export function useDeleteAttachment() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => attachmentsApi.remove(id),
    onSuccess: () => invalidateWorkflow(client),
  });
}

export function useBulkDeleteAttachments() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (ids: readonly number[]) => attachmentsApi.bulkDelete(ids),
    onSuccess: () => invalidateWorkflow(client),
  });
}

export function useBulkAssignAttachments() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: AttachmentBulkAssign) => attachmentsApi.bulkAssign(input),
    onSuccess: () => invalidateWorkflow(client),
  });
}

export function useCreateExpensesFromAttachments() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (ids: readonly number[]) => attachmentsApi.createExpenses(ids),
    onSuccess: () => invalidateWorkflow(client),
  });
}

export function useReparseAttachments() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (ids: readonly number[]) => attachmentsApi.reparse(ids),
    onSuccess: () => invalidateWorkflow(client),
  });
}

export function useSetChecklistState() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, state, reason }: { id: number; state: 'missing' | 'not_needed'; reason?: string }) =>
      attachmentsApi.setChecklistState(id, state, reason),
    onSuccess: async (detail) => {
      client.setQueryData(queryKeys.expense(detail.id), detail);
      await invalidateWorkflow(client);
    },
  });
}
