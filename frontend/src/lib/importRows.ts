// 导入确认表：会话行 → 可编辑草稿 → confirm 请求体。
import type { ImportAction, ImportConfirmRow, ImportRow, ImportSession } from '../api/types';

export interface ImportDraft {
  rowId: string;
  action: ImportAction;
  matchExpenseId: number | null;
  spentOn: string | null;
  amountCents: number | null;
  merchant: string;
  summary: string;
  categoryId: number | null;
  projectId: number | null;
}

export function draftFromRow(row: ImportRow): ImportDraft {
  return {
    rowId: row.row_id,
    action: row.match ? 'attach' : 'create',
    matchExpenseId: row.match?.expense_id ?? null,
    spentOn: row.suggested.spent_on,
    amountCents: row.suggested.amount_cents,
    merchant: row.suggested.merchant,
    summary: row.suggested.summary,
    categoryId: row.suggested.category_id,
    projectId: null,
  };
}

export function draftsFromSession(session: ImportSession): ImportDraft[] {
  return session.rows.map(draftFromRow);
}

export function updateDraft(drafts: readonly ImportDraft[], rowId: string, patch: Partial<ImportDraft>): ImportDraft[] {
  return drafts.map((draft) => (draft.rowId === rowId ? { ...draft, ...patch } : draft));
}

/** 返回该行的校验问题；跳过的行不校验。 */
export function draftProblems(draft: ImportDraft): string[] {
  if (draft.action === 'skip') return [];
  const problems: string[] = [];
  if (!draft.spentOn) problems.push('缺少日期');
  if (draft.amountCents === null || draft.amountCents <= 0) problems.push('缺少金额');
  if (!draft.merchant.trim()) problems.push('缺少销售方');
  if (draft.action === 'attach' && draft.matchExpenseId === null) problems.push('缺少目标支出');
  return problems;
}

export function toConfirmRow(draft: ImportDraft): ImportConfirmRow {
  return {
    row_id: draft.rowId,
    action: draft.action,
    ...(draft.action === 'attach' && draft.matchExpenseId !== null ? { expense_id: draft.matchExpenseId } : {}),
    spent_on: draft.spentOn ?? '',
    amount_cents: draft.amountCents ?? 0,
    merchant: draft.merchant.trim(),
    summary: draft.summary.trim(),
    category_id: draft.categoryId,
    ...(draft.projectId !== null ? { project_id: draft.projectId } : {}),
  };
}

export interface ImportTally {
  create: number;
  attach: number;
  skip: number;
  invalid: number;
}

export function tallyDrafts(drafts: readonly ImportDraft[]): ImportTally {
  return drafts.reduce<ImportTally>(
    (tally, draft) => ({
      ...tally,
      [draft.action]: tally[draft.action] + 1,
      invalid: tally.invalid + (draftProblems(draft).length > 0 ? 1 : 0),
    }),
    { create: 0, attach: 0, skip: 0, invalid: 0 },
  );
}
