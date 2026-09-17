import type { ExpenseQuery, StatsQuery } from '../types';

export const queryKeys = {
  expenses: ['expenses'] as const,
  expenseList: (query: ExpenseQuery) => ['expenses', 'list', query] as const,
  expenseSearch: (q: string) => ['expenses', 'search', q] as const,
  expense: (id: number) => ['expenses', 'detail', id] as const,
  unbatchedExpenses: ['expenses', 'unbatched'] as const,
  unassigned: ['attachments', 'unassigned'] as const,
  candidates: ['attachments', 'candidates'] as const,
  attachmentCandidates: (id: number) => ['attachments', 'candidates', id] as const,
  batches: ['batches'] as const,
  batchList: (status?: string) => ['batches', 'list', status ?? 'all'] as const,
  batch: (id: number) => ['batches', 'detail', id] as const,
  stats: (query: StatsQuery) => ['stats', query] as const,
  dashboard: ['dashboard'] as const,
  settings: ['settings'] as const,
  categories: ['categories'] as const,
  projects: ['projects'] as const,
  checklistRules: ['checklist-rules'] as const,
  authStatus: ['auth', 'status'] as const,
  users: ['users'] as const,
};

/** 任何支出/附件/批次写操作后需要刷新的查询前缀。 */
export const WORKFLOW_KEYS = [
  queryKeys.expenses,
  queryKeys.unassigned,
  queryKeys.candidates,
  queryKeys.batches,
  queryKeys.dashboard,
  ['stats'] as const,
] as const;
