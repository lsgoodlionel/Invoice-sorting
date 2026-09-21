import { describe, expect, test } from 'vitest';
import type { MailSettings } from '../api/mailTypes';
import { MAIL_PRESETS, applyPreset, buildMailPatch, isDraftDirty, isPortValid, portForTls, toMailDraft } from './mail';

const SETTINGS: MailSettings = {
  source: 'web',
  is_configured: true,
  host: 'smtp.example.com',
  port: 465,
  tls: 'ssl',
  username: 'robot@example.com',
  sender: 'robot@example.com',
  public_base_url: 'https://fp.example.com',
  password_set: true,
  password_error: '',
  updated_at: null,
  updated_by: '',
  last_check: null,
};

describe('邮件设置草稿', () => {
  test('预设只填服务器参数，不动账号', () => {
    const gmail = MAIL_PRESETS.find((preset) => preset.value === 'gmail')!;
    const next = applyPreset(toMailDraft(SETTINGS), gmail);
    expect([next.host, next.port, next.tls]).toEqual(['smtp.gmail.com', 587, 'starttls']);
    expect(next.username).toBe('robot@example.com');
  });

  test('加密方式对应默认端口，不加密保持原端口', () => {
    expect(portForTls('ssl', 25)).toBe(465);
    expect(portForTls('starttls', 465)).toBe(587);
    expect(portForTls('none', 2525)).toBe(2525);
  });

  test('密码缺省不改、清除为空串、填了才带新值', () => {
    const draft = toMailDraft(SETTINGS);
    expect(buildMailPatch(draft)).not.toHaveProperty('password');
    expect(buildMailPatch({ ...draft, passwordAction: 'clear' }).password).toBe('');
    expect(buildMailPatch({ ...draft, passwordAction: 'set', password: 'code' }).password).toBe('code');
    expect(buildMailPatch({ ...draft, passwordAction: 'set', password: '' })).not.toHaveProperty('password');
  });

  test('改了任一字段或密码即为未保存', () => {
    const draft = toMailDraft(SETTINGS);
    expect(isDraftDirty(draft, SETTINGS)).toBe(false);
    expect(isDraftDirty({ ...draft, port: 587 }, SETTINGS)).toBe(true);
    expect(isDraftDirty({ ...draft, passwordAction: 'clear' }, SETTINGS)).toBe(true);
  });

  test('端口范围 1–65535', () => {
    expect(isPortValid(1)).toBe(true);
    expect(isPortValid(0)).toBe(false);
    expect(isPortValid(65536)).toBe(false);
  });
});
