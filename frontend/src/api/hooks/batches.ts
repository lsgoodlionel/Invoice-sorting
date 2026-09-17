import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import type {
  Batch,
  BatchCreate,
  BatchDetail,
  BatchItemsChange,
  BatchPatch,
  BatchReceived,
  BatchSent,
  BatchStatus,
  ExportLayout,
  ExportRecord,
} from '../types';
import { invalidateWorkflow } from './invalidate';
import { queryKeys } from './keys';

export const batchesApi = {
  list: (status?: BatchStatus) => api.get<Batch[]>('/batches', { status }),
  get: (id: number) => api.get<BatchDetail>(`/batches/${id}`),
  create: (input: BatchCreate) => api.post<BatchDetail>('/batches', input),
  update: (id: number, patch: BatchPatch) => api.patch<BatchDetail>(`/batches/${id}`, patch),
  remove: (id: number) => api.del<null>(`/batches/${id}`),
  changeItems: (id: number, change: BatchItemsChange) => api.post<BatchDetail>(`/batches/${id}/items`, change),
  exportZip: (id: number, layout: ExportLayout) => api.post<ExportRecord>(`/batches/${id}/export`, { layout }),
  markSent: (id: number, input: BatchSent) => api.post<BatchDetail>(`/batches/${id}/sent`, input),
  markReceived: (id: number, input: BatchReceived) => api.post<BatchDetail>(`/batches/${id}/received`, input),
  reopen: (id: number) => api.post<BatchDetail>(`/batches/${id}/reopen`, {}),
  exportFileUrl: (exportId: number) => `/api/exports/${exportId}/file`,
  removeExport: (exportId: number) => api.del<null>(`/exports/${exportId}`),
};

export function useBatchList(status?: BatchStatus) {
  return useQuery({ queryKey: queryKeys.batchList(status), queryFn: () => batchesApi.list(status) });
}

export function useBatch(id: number | null) {
  return useQuery({
    queryKey: queryKeys.batch(id ?? 0),
    queryFn: () => batchesApi.get(id as number),
    enabled: id !== null,
  });
}

const CONFLICT_STATUS = 409;

function useBatchMutation<TVars, TResult>(fn: (vars: TVars) => Promise<TResult>, silentStatuses?: number[]) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => invalidateWorkflow(client),
    meta: silentStatuses ? { silentStatuses } : undefined,
  });
}

export const useCreateBatch = () => useBatchMutation((input: BatchCreate) => batchesApi.create(input));
export const useUpdateBatch = (id: number) => useBatchMutation((patch: BatchPatch) => batchesApi.update(id, patch));
export const useDeleteBatch = () => useBatchMutation((id: number) => batchesApi.remove(id));
export const useBatchItems = () =>
  useBatchMutation(
    ({ id, change }: { id: number; change: BatchItemsChange }) => batchesApi.changeItems(id, change),
    [CONFLICT_STATUS],
  );
export const useExportBatch = (id: number) =>
  useBatchMutation((layout: ExportLayout) => batchesApi.exportZip(id, layout));
export const useMarkBatchSent = (id: number) => useBatchMutation((input: BatchSent) => batchesApi.markSent(id, input));
export const useMarkBatchReceived = (id: number) =>
  useBatchMutation((input: BatchReceived) => batchesApi.markReceived(id, input));
export const useReopenBatch = (id: number) => useBatchMutation(() => batchesApi.reopen(id));
export const useDeleteExport = () => useBatchMutation((exportId: number) => batchesApi.removeExport(exportId));
