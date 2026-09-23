import type { MailSettings } from '../api/mailTypes';

export function makeMailSettings(overrides: Partial<MailSettings> = {}): MailSettings {
  return {
    source: 'web',
    is_configured: true,
    host: 'smtp.example.com',
    port: 465,
    tls: 'ssl',
    username: 'robot@example.com',
    sender: '发票报销 <robot@example.com>',
    public_base_url: 'https://fp.example.com',
    notify_emails: 'ops@example.com',
    password_set: true,
    password_error: '',
    updated_at: '2026-09-21T09:00:00+08:00',
    updated_by: 'ops-admin',
    last_check: null,
    ...overrides,
  };
}

export const UNCONFIGURED_MAIL: MailSettings = makeMailSettings({
  source: 'none',
  is_configured: false,
  host: '',
  username: '',
  sender: '',
  public_base_url: '',
  notify_emails: '',
  password_set: false,
  updated_at: null,
  updated_by: '',
});
