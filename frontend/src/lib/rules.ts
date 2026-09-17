// 凭证清单规则的条件描述与编码。
import type { ChecklistCondition } from '../api/types';
import { formatCents } from './money';

export interface ConditionSwitches {
  isOnlineOnly: boolean;
  isNonlocalOnly: boolean;
  excludeDetailPlatform: boolean;
}

export interface ConditionInput extends ConditionSwitches {
  amountGte: number | null;
  amountLt: number | null;
}

function isSet(value: number | null | undefined): value is number {
  return value !== undefined && value !== null;
}

function describeFlags(condition: ChecklistCondition): string[] {
  const parts: string[] = [];
  if (condition.is_online) parts.push('仅网购');
  if (condition.is_nonlocal === true) parts.push('仅外地发票');
  if (condition.is_nonlocal === false) parts.push('仅本地发票');
  if (condition.detail_platform === false) parts.push('排除已带明细平台');
  if (condition.detail_platform === true) parts.push('仅已带明细平台');
  return parts;
}

export function describeCondition(condition: ChecklistCondition): string {
  const parts = [
    ...(isSet(condition.amount_gte) ? [`金额 ≥ ${formatCents(condition.amount_gte)}`] : []),
    ...(isSet(condition.amount_lt) ? [`金额 < ${formatCents(condition.amount_lt)}`] : []),
    ...describeFlags(condition),
  ];
  return parts.length ? parts.join('，') : '始终';
}

/** 构造条件对象：省略空值，不带 undefined 键。 */
export function buildCondition(input: ConditionInput): ChecklistCondition {
  return {
    ...(input.amountGte !== null ? { amount_gte: input.amountGte } : {}),
    ...(input.amountLt !== null ? { amount_lt: input.amountLt } : {}),
    ...(input.isOnlineOnly ? { is_online: true } : {}),
    ...(input.isNonlocalOnly ? { is_nonlocal: true } : {}),
    ...(input.excludeDetailPlatform ? { detail_platform: false } : {}),
  };
}

/** 从已保存的条件读回弹窗中的开关状态。 */
export function conditionSwitches(condition: ChecklistCondition): ConditionSwitches {
  return {
    isOnlineOnly: condition.is_online === true,
    isNonlocalOnly: condition.is_nonlocal === true,
    excludeDetailPlatform: condition.detail_platform === false,
  };
}
