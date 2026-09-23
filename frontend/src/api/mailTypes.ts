// 平台邮件设置（仅多账套 SaaS 部署）。形状与后端 invoice_sorting/mail_settings 的序列化一致。
// 任何响应都不含密码或其密文，只有 password_set 与无法解密时的提示。

export type MailTls = 'ssl' | 'starttls' | 'none';

/** env：由服务器环境变量配置（网页只读）；web：网页配置；none：未配置 */
export type MailSource = 'env' | 'web' | 'none';

export type MailCheckCategory =
  | 'ok'
  | 'connect'
  | 'timeout'
  | 'tls'
  | 'auth'
  | 'sender'
  | 'recipient'
  | 'password'
  | 'other';

export interface MailLastCheck {
  kind: 'connection' | 'email';
  ok: boolean;
  category: MailCheckCategory;
  message: string;
  checked_at: string | null;
  checked_by: string;
}

export interface MailSettings {
  source: MailSource;
  is_configured: boolean;
  host: string;
  port: number;
  tls: MailTls;
  username: string;
  sender: string;
  public_base_url: string;
  /** 有新申请待审批时提醒谁：英文逗号分隔，最多 5 个；留空表示不发提醒 */
  notify_emails: string;
  password_set: boolean;
  /** 非空表示已保存的密码无法解密（服务器密钥更换或丢失），需重新填写 */
  password_error: string;
  /** 环境变量只配了一半等配置问题；为空表示无 */
  warning?: string;
  updated_at: string | null;
  updated_by: string;
  last_check: MailLastCheck | null;
}

/** PATCH：password 缺省表示不改，空串表示清除。 */
export interface MailSettingsPatch {
  host?: string;
  port?: number;
  tls?: MailTls;
  username?: string;
  password?: string;
  sender?: string;
  public_base_url?: string;
  notify_emails?: string;
}

export interface MailCheckResult {
  ok: boolean;
  category: MailCheckCategory;
  message: string;
  checked_at: string | null;
}
