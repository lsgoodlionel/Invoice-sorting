// 待归属附件：勾选状态与批量操作结果文案。
import type { Attachment, CreateExpensesResult } from '../api/types';

export function toggleId(selected: readonly number[], id: number): number[] {
  return selected.includes(id) ? selected.filter((item) => item !== id) : [...selected, id];
}

export function toggleAllIds(items: readonly Attachment[], checked: boolean): number[] {
  return checked ? items.map((item) => item.id) : [];
}

/** 去掉已不在列表中的勾选（操作后列表刷新时使用）。 */
export function pruneSelection(selected: readonly number[], items: readonly Attachment[]): number[] {
  const ids = new Set(items.map((item) => item.id));
  return selected.filter((id) => ids.has(id));
}

export function isInvoiceAttachment(item: Attachment): boolean {
  return item.kind === 'invoice';
}

export function selectedInvoiceIds(selected: readonly number[], items: readonly Attachment[]): number[] {
  return items.filter((item) => selected.includes(item.id) && isInvoiceAttachment(item)).map((item) => item.id);
}

export function summarizeCreateResult(result: CreateExpensesResult): string {
  return `新建 ${result.created.length} 条、挂到已有 ${result.attached.length} 条、跳过 ${result.skipped.length} 条`;
}
