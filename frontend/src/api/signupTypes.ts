// 注册申请与推荐（仅多账套 SaaS 部署）。形状与后端 invoice_sorting/signup 的序列化一致。

export type ApplicationStatus = 'pending' | 'approved' | 'rejected' | 'registered';

/** 通知邮件状态：空串为尚未发信；skipped 为未配置 SMTP，由平台管理员手动转告。 */
export type MailStatus = '' | 'sent' | 'failed' | 'skipped';

export interface AccountRef {
  account_id: number;
  username: string;
  display_name: string;
}

// —— 公开：申请、推荐码校验、注册 ——

export interface SignupApplicationInput {
  name: string;
  email: string;
  /** 单位或身份 */
  identity: string;
  /** 使用需求简介 */
  needs: string;
  ledger_name?: string;
  /** 推荐码 */
  ref?: string;
  /** 诱饵字段：真人看不到、不会填写；非空时后端静默丢弃 */
  website: string;
}

export interface SignupApplicationReceipt {
  id: number;
  number: string;
  /** 推荐「直接注册」时为 approved（注册链接已发往邮箱） */
  status: ApplicationStatus;
  referrer_name: string | null;
  message: string;
}

/** GET /api/signup/referral/{code} */
export interface ReferralCheck {
  code: string;
  referrer_name: string;
  require_approval: boolean;
}

/** GET /api/signup/register?code= */
export interface RegisterCodeInfo {
  email: string;
  name: string;
  ledger_name: string;
  expires_at: string | null;
}

export interface RegisterInput {
  code: string;
  email: string;
  username: string;
  password: string;
  display_name?: string;
}

// —— 登录用户：我的推荐 ——

export interface MyReferralItem {
  id: number;
  email_masked: string;
  status: ApplicationStatus;
  created_at: string;
  registered_at: string | null;
}

export interface MyReferrals {
  /** 推荐资格被停用时为 null */
  code: string | null;
  /** 配置了 PUBLIC_BASE_URL 时是完整地址，否则是站内路径 */
  link: string | null;
  is_disabled: boolean;
  require_approval: boolean;
  monthly_quota: number;
  used_this_month: number;
  total: number;
  referrals: MyReferralItem[];
}

// —— 平台管理员：申请审批、推荐记录、注册设置 ——

export interface ApprovedTenantPlan {
  slug: string;
  name: string;
  plan_code: string | null;
  expires_on: string | null;
}

export interface PlatformApplication {
  id: number;
  number: string;
  name: string;
  email: string;
  identity: string;
  needs: string;
  ledger_name: string;
  status: ApplicationStatus;
  referrer: AccountRef | null;
  is_auto_approved: boolean;
  reviewer: AccountRef | null;
  reviewed_at: string | null;
  reject_reason: string;
  approved: ApprovedTenantPlan | null;
  code_expires_at: string | null;
  mail_status: MailStatus;
  mail_error: string;
  mail_sent_at: string | null;
  tenant: { slug: string; name: string } | null;
  registered_at: string | null;
  is_purged: boolean;
  created_at: string;
}

export interface PlatformApplicationPage {
  items: PlatformApplication[];
  total: number;
  page: number;
  page_size: number;
  counts: Record<ApplicationStatus, number>;
}

/** 一次通知的结果；没发出去时附上注册链接与通知文字（只在这次响应里给出）。 */
export interface MailDelivery {
  mail_status: MailStatus;
  mail_error: string;
  link: string | null;
  text: string | null;
}

export interface ReviewResult {
  application: PlatformApplication;
  notice: MailDelivery;
}

/** 全部可选：不填则后端自动生成标识、用期望账本名、默认免费套餐、长期有效。 */
export interface ApproveInput {
  slug?: string;
  name?: string;
  plan_code?: string;
  expires_on?: string;
}

export interface RejectInput {
  reason: string;
}

export interface PlatformReferral {
  application_id: number;
  number: string;
  referrer: AccountRef | null;
  is_referrer_disabled: boolean;
  referee_email: string;
  tenant: { slug: string; name: string } | null;
  status: ApplicationStatus;
  is_auto_approved: boolean;
  created_at: string;
  registered_at: string | null;
}

export interface PlatformReferralPage {
  items: PlatformReferral[];
  total: number;
  page: number;
  page_size: number;
}

export interface SignupSettings {
  /** true：推荐注册也需审批；false：直接注册（超出每月名额自动转审批） */
  require_approval: boolean;
  monthly_referral_quota: number;
  code_valid_days: number;
  is_mail_configured: boolean;
  updated_at: string | null;
}

export type SignupSettingsPatch = Partial<Pick<SignupSettings, 'require_approval' | 'monthly_referral_quota' | 'code_valid_days'>>;
