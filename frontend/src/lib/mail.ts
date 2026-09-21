import type { MailCheckCategory, MailLastCheck, MailSettings, MailSettingsPatch, MailTls } from '../api/mailTypes';

// 平台邮件设置：常用邮箱预设、加密方式默认端口、表单草稿与保存请求体的换算。

export interface MailPreset {
  value: string;
  label: string;
  host: string;
  port: number;
  tls: MailTls;
}

/** 常用邮箱的服务器参数（只含服务器，不涉及任何账号）。 */
export const MAIL_PRESETS: readonly MailPreset[] = [
  { value: 'qq', label: 'QQ 邮箱', host: 'smtp.qq.com', port: 465, tls: 'ssl' },
  { value: '163', label: '163 邮箱', host: 'smtp.163.com', port: 465, tls: 'ssl' },
  { value: 'exmail', label: '腾讯企业邮', host: 'smtp.exmail.qq.com', port: 465, tls: 'ssl' },
  { value: 'aliyun', label: '阿里企业邮', host: 'smtp.qiye.aliyun.com', port: 465, tls: 'ssl' },
  { value: 'gmail', label: 'Gmail', host: 'smtp.gmail.com', port: 587, tls: 'starttls' },
];

export const TLS_OPTIONS: { value: MailTls; label: string }[] = [
  { value: 'ssl', label: 'SSL/TLS（常用 465）' },
  { value: 'starttls', label: 'STARTTLS（常用 587）' },
  { value: 'none', label: '不加密（仅限内网中继）' },
];

const DEFAULT_PORTS: Partial<Record<MailTls, number>> = { ssl: 465, starttls: 587 };

export const PORT_MIN = 1;
export const PORT_MAX = 65535;

/** 切换加密方式时的端口：ssl → 465、starttls → 587；不加密保持原端口。 */
export const portForTls = (tls: MailTls, current: number): number => DEFAULT_PORTS[tls] ?? current;

/** 密码的三种操作：保持不变、填入新密码、清除已保存的密码。 */
export type PasswordAction = 'keep' | 'set' | 'clear';

export interface MailDraft {
  host: string;
  port: number;
  tls: MailTls;
  username: string;
  sender: string;
  public_base_url: string;
  password: string;
  passwordAction: PasswordAction;
}

export const toMailDraft = (settings: MailSettings): MailDraft => ({
  host: settings.host,
  port: settings.port,
  tls: settings.tls,
  username: settings.username,
  sender: settings.sender,
  public_base_url: settings.public_base_url,
  password: '',
  passwordAction: 'keep',
});

export const applyPreset = (draft: MailDraft, preset: MailPreset): MailDraft => ({
  ...draft,
  host: preset.host,
  port: preset.port,
  tls: preset.tls,
});

const FIELDS = ['host', 'port', 'tls', 'username', 'sender', 'public_base_url'] as const;

export const isDraftDirty = (draft: MailDraft, settings: MailSettings): boolean =>
  draft.passwordAction !== 'keep' || FIELDS.some((key) => draft[key] !== settings[key]);

export const isPortValid = (port: number): boolean => Number.isInteger(port) && port >= PORT_MIN && port <= PORT_MAX;

/** 保存请求体：密码只在「填了新密码」或「清除」时带上，其余情况缺省表示不改。 */
export function buildMailPatch(draft: MailDraft): MailSettingsPatch {
  const base: MailSettingsPatch = {
    host: draft.host.trim(),
    port: draft.port,
    tls: draft.tls,
    username: draft.username.trim(),
    sender: draft.sender.trim(),
    public_base_url: draft.public_base_url.trim(),
  };
  if (draft.passwordAction === 'clear') return { ...base, password: '' };
  if (draft.passwordAction === 'set' && draft.password) return { ...base, password: draft.password };
  return base;
}

const CHECK_KIND_LABELS: Record<MailLastCheck['kind'], string> = { connection: '测试连接', email: '测试邮件' };

const CATEGORY_LABELS: Record<MailCheckCategory, string> = {
  ok: '成功',
  connect: '连不上服务器',
  timeout: '连接超时',
  tls: 'TLS 握手失败',
  auth: '认证失败',
  sender: '发件人被拒',
  recipient: '收件人被拒',
  password: '密码需重新填写',
  other: '其他错误',
};

export const checkKindLabel = (kind: MailLastCheck['kind']): string => CHECK_KIND_LABELS[kind] ?? kind;
export const checkCategoryLabel = (category: MailCheckCategory): string => CATEGORY_LABELS[category] ?? category;
