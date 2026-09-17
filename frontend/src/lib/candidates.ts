// 匹配候选记录的展示文案（导入确认表、待归属建议共用）。
import type { MatchCandidate } from '../api/types';
import { formatCents, formatMoney, isForeignCurrency } from './money';

/** "#42 腾讯云 ¥298.00"；外币记录附原币金额。 */
export function candidateLabel(candidate: MatchCandidate): string {
  const hasOriginal = isForeignCurrency(candidate.currency) && candidate.original_amount_cents !== null;
  const amount = hasOriginal
    ? `${formatCents(candidate.amount_cents)}（${formatMoney(candidate.original_amount_cents, candidate.currency)}）`
    : formatCents(candidate.amount_cents);
  return [`#${candidate.expense_id}`, candidate.merchant, amount].filter(Boolean).join(' ');
}

export function candidateReasons(candidate: MatchCandidate): string {
  return candidate.reasons.join('、');
}

/** 操作下拉中的选项文字：挂到 #id 商家 ¥金额 · 分数 · 依据 */
export function candidateOptionLabel(candidate: MatchCandidate): string {
  const reasons = candidateReasons(candidate);
  return [`挂到 ${candidateLabel(candidate)}`, `${candidate.score} 分`, reasons].filter(Boolean).join(' · ');
}
