import type { LicenseRecord, PlatformTenant, QuotaStatus, TenantStatus } from '../api/types';

const KB = 1024;
const UNITS = ['B', 'KB', 'MB', 'GB', 'TB'] as const;
const DECIMALS = 1;

/** 人类可读的存储大小（1.5 GB）。 */
export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
  let value = bytes;
  let unit = 0;
  while (value >= KB && unit < UNITS.length - 1) {
    value /= KB;
    unit += 1;
  }
  return `${unit === 0 ? value : value.toFixed(DECIMALS)} ${UNITS[unit]}`;
}

export const TENANT_STATUS_LABELS: Record<TenantStatus, string> = {
  active: '启用',
  suspended: '已停用',
  closed: '已关闭',
};

export const TENANT_STATUS_COLORS: Record<TenantStatus, string> = {
  active: 'ink',
  suspended: 'orange',
  closed: 'gray',
};

export const tenantStatusLabel = (status: TenantStatus): string =>
  TENANT_STATUS_LABELS[status] ?? status;

/** 账套是否已过期（到期日在今天之前）。 */
export function isExpired(tenant: PlatformTenant, today = new Date()): boolean {
  if (!tenant.expires_on) return false;
  return tenant.expires_on < today.toISOString().slice(0, 10);
}

export const licenseRecordLabel = (record: LicenseRecord): string =>
  record.status === 'revoked' ? '已吊销' : '有效';

/** 提示条：即将到期的天数阈值（含）。 */
export const EXPIRY_WARNING_DAYS = 14;

export interface QuotaNotice {
  tone: 'warning' | 'danger';
  message: string;
}

/**
 * 额度提示条的文案；不需要提示时返回 null。
 * 优先级：只读（最严重）→ 已达上限 → 即将到期。单账套部署（enforced=false）永不提示。
 */
export function quotaNotice(quota: QuotaStatus | undefined): QuotaNotice | null {
  if (!quota?.enforced) return null;
  if (quota.is_readonly) return { tone: 'danger', message: quota.readonly_message };
  const exceeded = quota.limits.filter((line) => line.is_exceeded);
  if (exceeded.length > 0) return { tone: 'danger', message: exceededMessage(exceeded) };
  return expiryNotice(quota);
}

function exceededMessage(exceeded: QuotaStatus['limits']): string {
  const detail = exceeded
    .map((line) => `${line.label}已达上限（${line.used}/${line.limit} ${line.unit}）`)
    .join('；');
  return `${detail}。请联系平台管理员升级套餐。`;
}

function expiryNotice(quota: QuotaStatus): QuotaNotice | null {
  const days = quota.expires_in_days;
  if (days === null || days === undefined || days > EXPIRY_WARNING_DAYS) return null;
  const when = days <= 0 ? '今天' : `${days} 天后`;
  return {
    tone: 'warning',
    message: `订阅将于${when}（${quota.expires_on}）到期，到期后账套将转为只读。请联系平台管理员续期。`,
  };
}
