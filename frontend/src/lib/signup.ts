import type {
  ApplicationStatus,
  MailDelivery,
  MailStatus,
  MyReferrals,
  SignupApplicationInput,
} from '../api/signupTypes';

// 注册申请与推荐：表单规则、链接、脱敏与文案（长度上限与后端 signup/constants.py 一致）。

export const APPLY_PATH = '/apply';
export const REGISTER_PATH = '/register';

export const APPLY_NAME_MAX = 32;
export const APPLY_IDENTITY_MAX = 100;
export const APPLY_NEEDS_MAX = 1000;
export const APPLY_LEDGER_NAME_MAX = 100;
export const REJECT_REASON_MAX = 200;
export const CODE_VALID_DAYS_MIN = 1;
export const CODE_VALID_DAYS_MAX = 30;
export const REFERRAL_QUOTA_MAX = 1000;

const EMAIL_PATTERN = /^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$/;
const SLUG_BASE_MAX = 40;
const FALLBACK_SLUG = 'ledger';

export interface ApplyForm {
  name: string;
  email: string;
  identity: string;
  needs: string;
  ledgerName: string;
  /** 诱饵字段：隐藏在界面外，真人不会填 */
  website: string;
}

export const EMPTY_APPLY_FORM: ApplyForm = { name: '', email: '', identity: '', needs: '', ledgerName: '', website: '' };

export const isEmailValid = (email: string): boolean => EMAIL_PATTERN.test(email.trim());

/** 未输入时不提示；只校验格式。 */
export function applyFormErrors(form: ApplyForm): { email: string | null } {
  const email = form.email.trim();
  return { email: email && !isEmailValid(email) ? '请填写有效的邮箱地址' : null };
}

export function isApplyFormComplete(form: ApplyForm): boolean {
  const required = [form.name, form.identity, form.needs];
  return required.every((value) => value.trim().length > 0) && isEmailValid(form.email);
}

export function toApplicationPayload(form: ApplyForm, referralCode: string | null): SignupApplicationInput {
  const ledgerName = form.ledgerName.trim();
  return {
    name: form.name.trim(),
    email: form.email.trim().toLowerCase(),
    identity: form.identity.trim(),
    needs: form.needs.trim(),
    ...(ledgerName ? { ledger_name: ledgerName } : {}),
    ...(referralCode ? { ref: referralCode } : {}),
    website: form.website,
  };
}

/** 邮箱脱敏：z***@example.com；已脱敏的保持不变。 */
export function maskEmail(email: string): string {
  const at = email.indexOf('@');
  if (at <= 0 || at === email.length - 1) return '***';
  return `${email[0]}***${email.slice(at)}`;
}

/** 与后端一致的标识前缀（后端留空时会再加随机后缀）。 */
export function suggestSlug(email: string): string {
  const local = (email.split('@')[0] ?? '').toLowerCase();
  const base = local.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, SLUG_BASE_MAX).replace(/-+$/, '');
  return base || FALLBACK_SLUG;
}

/** 后端未配置 PUBLIC_BASE_URL 时给的是站内路径，这里补上当前站点地址。 */
export const absoluteUrl = (link: string, origin: string): string => (link.startsWith('/') ? `${origin}${link}` : link);

export function referralLink(referrals: Pick<MyReferrals, 'code' | 'link'>, origin: string): string | null {
  if (referrals.link) return absoluteUrl(referrals.link, origin);
  if (!referrals.code) return null;
  return `${origin}${APPLY_PATH}?ref=${encodeURIComponent(referrals.code)}`;
}

/** 通知没发出去（未配置 SMTP 或发送失败）：需要管理员手动转告。 */
export const isUndelivered = (status: MailStatus): boolean => status === 'failed' || status === 'skipped';

/** 手动转告用的链接与文字：站内路径补全为完整地址。 */
export function manualNotice(delivery: MailDelivery, origin: string): { link: string | null; text: string } {
  const raw = delivery.link ?? '';
  const link = raw ? absoluteUrl(raw, origin) : null;
  const text = delivery.text ?? '';
  return { link, text: raw && link && raw !== link ? text.replace(raw, link) : text };
}

export const APPLICATION_STATUS_LABELS: Readonly<Record<ApplicationStatus, string>> = {
  pending: '待审批',
  approved: '已批准待注册',
  rejected: '已否决',
  registered: '已注册',
};

/** 推荐人自己看到的状态文案。 */
export const REFERRAL_STATUS_LABELS: Readonly<Record<ApplicationStatus, string>> = {
  ...APPLICATION_STATUS_LABELS,
  approved: '待注册',
};

export const APPLICATION_STATUS_COLORS: Readonly<Record<ApplicationStatus, string>> = {
  pending: 'orange',
  approved: 'blue',
  rejected: 'gray',
  registered: 'ink',
};

export const MAIL_STATUS_LABELS: Readonly<Record<MailStatus, string>> = {
  '': '尚未发信',
  sent: '已发送',
  failed: '发送失败',
  skipped: '未配置邮件服务，未发送',
};

/** 显示用的时间：2026-09-21 10:00。 */
export const formatDateTime = (value: string | null): string => (value ? value.slice(0, 16).replace('T', ' ') : '—');
