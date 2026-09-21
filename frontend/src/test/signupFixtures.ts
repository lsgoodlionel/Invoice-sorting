import type {
  PlatformApplication,
  PlatformApplicationPage,
  PlatformReferral,
  ReviewResult,
  SignupSettings,
} from '../api/signupTypes';

export function makeApplication(overrides: Partial<PlatformApplication> = {}): PlatformApplication {
  return {
    id: 1,
    number: 'SQ000001',
    name: '张三',
    email: 'zhang.san@example.com',
    identity: '某某大学经济学院',
    needs: '课题组差旅报销，约 5 人使用',
    ledger_name: '',
    status: 'pending',
    referrer: null,
    is_auto_approved: false,
    reviewer: null,
    reviewed_at: null,
    reject_reason: '',
    approved: null,
    code_expires_at: null,
    mail_status: '',
    mail_error: '',
    mail_sent_at: null,
    tenant: null,
    registered_at: null,
    is_purged: false,
    created_at: '2026-09-21T09:30:00+08:00',
    ...overrides,
  };
}

export function makeApplicationPage(items: PlatformApplication[], pending = items.length): PlatformApplicationPage {
  return {
    items,
    total: items.length,
    page: 1,
    page_size: 20,
    counts: { pending, approved: 0, rejected: 0, registered: 0 },
  };
}

export function makeReview(application: PlatformApplication, notice: Partial<ReviewResult['notice']> = {}): ReviewResult {
  return { application, notice: { mail_status: 'sent', mail_error: '', link: null, text: null, ...notice } };
}

export function makeReferral(overrides: Partial<PlatformReferral> = {}): PlatformReferral {
  return {
    application_id: 1,
    number: 'SQ000001',
    referrer: { account_id: 7, username: 'lisi', display_name: '李四' },
    is_referrer_disabled: false,
    referee_email: 'wangwu@example.com',
    tenant: { slug: 'wangwu', name: '王五的账本' },
    status: 'registered',
    is_auto_approved: false,
    created_at: '2026-09-15T10:00:00+08:00',
    registered_at: '2026-09-16T10:00:00+08:00',
    ...overrides,
  };
}

export const SIGNUP_SETTINGS: SignupSettings = {
  require_approval: true,
  monthly_referral_quota: 5,
  code_valid_days: 7,
  is_mail_configured: true,
  updated_at: null,
};
