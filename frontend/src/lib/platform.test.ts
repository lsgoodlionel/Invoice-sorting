import { describe, expect, test } from 'vitest';
import { makeQuota } from '../test/platformFixtures';
import { formatBytes, quotaNotice, tenantStatusLabel } from './platform';
import { isSlugValid, slugError } from '../components/platform/tenantForm';

describe('formatBytes', () => {
  test('shows plain bytes below 1 KB', () => {
    expect(formatBytes(512)).toBe('512 B');
  });

  test('scales up to MB and GB with one decimal', () => {
    expect(formatBytes(1024 * 1024 * 3)).toBe('3.0 MB');
    expect(formatBytes(1024 * 1024 * 1024 * 2.5)).toBe('2.5 GB');
  });

  test('treats missing or negative sizes as zero', () => {
    expect(formatBytes(0)).toBe('0 B');
    expect(formatBytes(Number.NaN)).toBe('0 B');
  });
});

describe('tenantStatusLabel', () => {
  test('translates each status', () => {
    expect(tenantStatusLabel('active')).toBe('启用');
    expect(tenantStatusLabel('suspended')).toBe('已停用');
    expect(tenantStatusLabel('closed')).toBe('已关闭');
  });
});

describe('slug validation', () => {
  test('accepts lowercase letters, digits and hyphens', () => {
    expect(isSlugValid('alpha-1')).toBe(true);
  });

  test('rejects uppercase, dots and leading hyphen', () => {
    expect(isSlugValid('Alpha')).toBe(false);
    expect(isSlugValid('a.b')).toBe(false);
    expect(isSlugValid('-a')).toBe(false);
  });

  test('says nothing while the field is still empty', () => {
    expect(slugError('   ')).toBeNull();
    expect(slugError('Alpha')).toContain('小写字母');
  });
});

describe('quotaNotice', () => {
  test('stays hidden when quota is not enforced', () => {
    expect(quotaNotice(makeQuota({ enforced: false }))).toBeNull();
    expect(quotaNotice(undefined)).toBeNull();
  });

  test('stays hidden while everything is within limits', () => {
    expect(quotaNotice(makeQuota())).toBeNull();
  });

  test('shows the backend wording when the tenant is read-only', () => {
    const quota = makeQuota({ is_readonly: true, readonly_reason: 'tenant_suspended', readonly_message: '账套已停用。' });

    expect(quotaNotice(quota)).toEqual({ tone: 'danger', message: '账套已停用。' });
  });

  test('lists every exceeded limit with used and total', () => {
    const limits = makeQuota().limits.map((line) =>
      line.key === 'users' ? { ...line, used: 10, is_exceeded: true } : line,
    );

    const notice = quotaNotice(makeQuota({ limits }));

    expect(notice?.tone).toBe('danger');
    expect(notice?.message).toContain('成员数量已达上限（10/10 人）');
  });

  test('warns two weeks before the subscription expires', () => {
    const notice = quotaNotice(makeQuota({ expires_on: '2026-10-01', expires_in_days: 9 }));

    expect(notice?.tone).toBe('warning');
    expect(notice?.message).toContain('9 天后');
  });

  test('keeps quiet when the expiry is still far away', () => {
    expect(quotaNotice(makeQuota({ expires_on: '2027-10-01', expires_in_days: 90 }))).toBeNull();
  });

  test('read-only wins over an upcoming expiry', () => {
    const quota = makeQuota({ expires_in_days: 0, is_readonly: true, readonly_message: '订阅已到期。' });

    expect(quotaNotice(quota)?.message).toBe('订阅已到期。');
  });
});
