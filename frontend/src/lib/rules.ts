// 凭证清单规则的条件描述。
import type { ChecklistCondition } from '../api/types';
import { formatCents } from './money';

export function describeCondition(condition: ChecklistCondition): string {
  const parts: string[] = [];
  if (condition.amount_gte !== undefined && condition.amount_gte !== null) parts.push(`金额 ≥ ${formatCents(condition.amount_gte)}`);
  if (condition.amount_lt !== undefined && condition.amount_lt !== null) parts.push(`金额 < ${formatCents(condition.amount_lt)}`);
  if (condition.is_online) parts.push('仅网购');
  return parts.length ? parts.join('，') : '始终';
}

/** 构造条件对象：省略空值，不带 undefined 键。 */
export function buildCondition(input: { amountGte: number | null; amountLt: number | null; isOnlineOnly: boolean }): ChecklistCondition {
  return {
    ...(input.amountGte !== null ? { amount_gte: input.amountGte } : {}),
    ...(input.amountLt !== null ? { amount_lt: input.amountLt } : {}),
    ...(input.isOnlineOnly ? { is_online: true } : {}),
  };
}
