import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import type { ImportConfirmInput, ImportConfirmResult, ImportSession, ImportStartResult } from '../types';
import { uploadImportFile } from '../upload';
import { invalidateWorkflow } from './invalidate';

const sessionPath = (sessionId: string) => `/imports/${encodeURIComponent(sessionId)}`;

/** 分文件导入：start → 逐个上传文件（带进度）→ finish 分组 → confirm。 */
export const importsApi = {
  start: () => api.post<ImportStartResult>('/imports/start'),
  uploadFile: uploadImportFile,
  finish: (sessionId: string) => api.post<ImportSession>(`${sessionPath(sessionId)}/finish`),
  confirm: (sessionId: string, input: ImportConfirmInput) =>
    api.post<ImportConfirmResult>(`${sessionPath(sessionId)}/confirm`, input),
};

export function useConfirmImport() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ sessionId, input }: { sessionId: string; input: ImportConfirmInput }) =>
      importsApi.confirm(sessionId, input),
    onSuccess: () => invalidateWorkflow(client),
  });
}
