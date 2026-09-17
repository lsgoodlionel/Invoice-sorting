import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import type { ImportConfirmInput, ImportConfirmResult, ImportSession } from '../types';
import { invalidateWorkflow } from './invalidate';

export const importsApi = {
  upload: (files: readonly File[]) => api.upload<ImportSession>('/imports', files),
  confirm: (sessionId: string, input: ImportConfirmInput) =>
    api.post<ImportConfirmResult>(`/imports/${encodeURIComponent(sessionId)}/confirm`, input),
};

export function useImportFiles() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (files: readonly File[]) => importsApi.upload(files),
    onSuccess: () => invalidateWorkflow(client),
  });
}

export function useConfirmImport() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ sessionId, input }: { sessionId: string; input: ImportConfirmInput }) =>
      importsApi.confirm(sessionId, input),
    onSuccess: () => invalidateWorkflow(client),
  });
}
