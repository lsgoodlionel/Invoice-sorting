import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import type { ImportConfirmResult, ImportConfirmRow, ImportSession } from '../types';
import { invalidateWorkflow } from './invalidate';

export const importsApi = {
  upload: (files: readonly File[]) => api.upload<ImportSession>('/imports', files),
  confirm: (sessionId: string, rows: readonly ImportConfirmRow[]) =>
    api.post<ImportConfirmResult>(`/imports/${encodeURIComponent(sessionId)}/confirm`, { rows }),
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
    mutationFn: ({ sessionId, rows }: { sessionId: string; rows: readonly ImportConfirmRow[] }) =>
      importsApi.confirm(sessionId, rows),
    onSuccess: () => invalidateWorkflow(client),
  });
}
