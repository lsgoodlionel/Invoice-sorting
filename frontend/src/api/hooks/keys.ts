import type { ExpenseQuery, StatsQuery } from '../types';

export const queryKeys = {
  expenses: ['expenses'] as const,
  expenseList: (query: ExpenseQuery) => ['expenses', 'list', query] as const,
  expenseSearch: (q: string) => ['expenses', 'search', q] as const,
  expense: (id: number) => ['expenses', 'detail', id] as const,
  unbatchedExpenses: (query: ExpenseQuery) => ['expenses', 'unbatched', query] as const,
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
  authTenants: ['auth', 'tenants'] as const,
  users: ['users'] as const,
  invites: ['invites'] as const,
  licenseStatus: ['license', 'status'] as const,
  quota: ['quota'] as const,
  platformOverview: ['platform', 'overview'] as const,
  platformTenants: (query: PlatformTenantQuery) => ['platform', 'tenants', query] as const,
  platformMembers: (slug: string) => ['platform', 'members', slug] as const,
  platformInvites: (slug: string) => ['platform', 'invites', slug] as const,
  platformPlans: ['platform', 'plans'] as const,
  platformLicenses: ['platform', 'licenses'] as const,
};

/** 平台账套列表的查询条件（搜索词 + 页码）。 */
export interface PlatformTenantQuery {
  q: string;
  page: number;
}

/** 账套、成员、套餐变更后需要刷新的平台查询前缀。 */
export const PLATFORM_KEYS = [['platform']] as const;

/** 任何支出/附件/批次写操作后需要刷新的查询前缀。 */
export const WORKFLOW_KEYS = [
  queryKeys.expenses,
  queryKeys.unassigned,
  queryKeys.candidates,
  queryKeys.batches,
  queryKeys.dashboard,
  ['stats'] as const,
] as const;
