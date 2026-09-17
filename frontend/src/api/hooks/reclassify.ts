import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import type { ExpenseStatus } from '../types';
import { invalidateWorkflow } from './invalidate';

export interface ReclassifyItem {
  expense_id: number;
  spent_on: string;
  merchant: string;
  summary: string;
  amount_cents: number;
  status: ExpenseStatus;
  current_category_id: number | null;
  current_category_name: string;
  suggested_category_id: number;
  suggested_category_name: string;
  basis: string;
}

export interface ReclassifyChange {
  expense_id: number;
  category_id: number;
}

export const reclassifyApi = {
  preview: (includeSent: boolean) =>
    api.get<ReclassifyItem[]>('/reclassify/preview', includeSent ? { include_sent: true } : undefined),
  apply: (changes: readonly ReclassifyChange[]) => api.post<{ updated: number }>('/reclassify/apply', { changes }),
};

/** 预览按需触发（管理员点击“检查分类”时才请求），所以用 mutation 而不是自动查询。 */
export function useReclassifyPreview() {
  return useMutation({ mutationFn: (includeSent: boolean) => reclassifyApi.preview(includeSent) });
}

export function useApplyReclassify() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (changes: readonly ReclassifyChange[]) => reclassifyApi.apply(changes),
    onSuccess: () => invalidateWorkflow(client),
  });
}
