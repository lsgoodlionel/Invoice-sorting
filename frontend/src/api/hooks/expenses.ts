import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import type {
  AttachmentKind,
  ExpenseCreate,
  ExpenseDetail,
  ExpenseListResult,
  ExpensePatch,
  ExpenseQuery,
  ExpenseStatus,
  ExpenseSummary,
} from '../types';
import { invalidateWorkflow } from './invalidate';
import { queryKeys } from './keys';

const SEARCH_PAGE_SIZE = 20;
/** 后端 page_size 上限，加入批次时一次取全部未分批记录 */
const UNBATCHED_PAGE_SIZE = 500;

export const expensesApi = {
  list: (query: ExpenseQuery) => api.get<ExpenseListResult>('/expenses', { ...query }),
  get: (id: number) => api.get<ExpenseDetail>(`/expenses/${id}`),
  create: (input: ExpenseCreate) => api.post<ExpenseDetail>('/expenses', input),
  update: (id: number, patch: ExpensePatch) => api.patch<ExpenseDetail>(`/expenses/${id}`, patch),
  remove: (id: number) => api.del<null>(`/expenses/${id}`),
  setStatus: (id: number, status: ExpenseStatus | null, note?: string) =>
    api.post<ExpenseDetail>(`/expenses/${id}/status`, note === undefined ? { status } : { status, note }),
  upload: (id: number, files: readonly File[], kind?: AttachmentKind) =>
    api.upload<ExpenseDetail>(`/expenses/${id}/attachments`, files, kind ? { kind } : {}),
};

export function useExpenseList(query: ExpenseQuery) {
  return useQuery({
    queryKey: queryKeys.expenseList(query),
    queryFn: () => expensesApi.list(query),
    placeholderData: keepPreviousData,
  });
}

export function useExpenseSearch(q: string) {
  return useQuery({
    queryKey: queryKeys.expenseSearch(q),
    queryFn: async (): Promise<ExpenseSummary[]> =>
      (await expensesApi.list({ q: q || undefined, page_size: SEARCH_PAGE_SIZE })).items,
    placeholderData: keepPreviousData,
  });
}

/** 未分批记录（用于“添加记录到批次”），仅在 enabled 时请求。 */
export function useUnbatchedExpenses(enabled: boolean) {
  const query: ExpenseQuery = { unbatched: true, page_size: UNBATCHED_PAGE_SIZE };
  return useQuery({
    queryKey: queryKeys.unbatchedExpenses,
    queryFn: async (): Promise<ExpenseSummary[]> => (await expensesApi.list(query)).items,
    enabled,
  });
}

export function useExpense(id: number | null) {
  return useQuery({
    queryKey: queryKeys.expense(id ?? 0),
    queryFn: () => expensesApi.get(id as number),
    enabled: id !== null,
  });
}

/** 写操作通用：成功后用返回的详情写入缓存并刷新工作流相关查询。 */
function useDetailMutation<TVars>(fn: (vars: TVars) => Promise<ExpenseDetail>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: async (detail) => {
      client.setQueryData(queryKeys.expense(detail.id), detail);
      await invalidateWorkflow(client);
    },
  });
}

export const useCreateExpense = () => useDetailMutation((input: ExpenseCreate) => expensesApi.create(input));

export const useUpdateExpense = (id: number) =>
  useDetailMutation((patch: ExpensePatch) => expensesApi.update(id, patch));

export const useSetExpenseStatus = (id: number) =>
  useDetailMutation(({ status, note }: { status: ExpenseStatus | null; note?: string }) =>
    expensesApi.setStatus(id, status, note),
  );

export const useUploadExpenseAttachments = (id: number) =>
  useDetailMutation(({ files, kind }: { files: readonly File[]; kind?: AttachmentKind }) =>
    expensesApi.upload(id, files, kind),
  );

/** 清单行拖放补传：不传 kind，由后端自动识别类型。 */
export const useUploadToExpense = () =>
  useDetailMutation(({ id, files }: { id: number; files: readonly File[] }) => expensesApi.upload(id, files));

export function useDeleteExpense() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => expensesApi.remove(id),
    onSuccess: () => invalidateWorkflow(client),
  });
}
