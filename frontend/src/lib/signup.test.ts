import { describe, expect, test } from 'vitest';
import {
  EMPTY_APPLY_FORM,
  absoluteUrl,
  applyFormErrors,
  isApplyFormComplete,
  isUndelivered,
  manualNotice,
  maskEmail,
  referralLink,
  suggestSlug,
  toApplicationPayload,
} from './signup';

const FILLED = { ...EMPTY_APPLY_FORM, name: ' 张三 ', email: ' ZS@Example.com ', identity: '某某大学', needs: '课题组报销' };

describe('maskEmail', () => {
  test('只保留本地部分首字母与域名', () => {
    expect(maskEmail('zhangsan@example.com')).toBe('z***@example.com');
  });

  test('已脱敏的邮箱保持不变', () => {
    expect(maskEmail('z***@example.com')).toBe('z***@example.com');
  });

  test('不是邮箱时整体打码', () => {
    expect(maskEmail('abc')).toBe('***');
    expect(maskEmail('abc@')).toBe('***');
  });
});

describe('申请表校验', () => {
  test('空表不完整，但未输入时不提示错误', () => {
    expect(isApplyFormComplete(EMPTY_APPLY_FORM)).toBe(false);
    expect(applyFormErrors(EMPTY_APPLY_FORM).email).toBeNull();
  });

  test('邮箱格式错误时提示', () => {
    expect(applyFormErrors({ ...FILLED, email: 'not-mail' }).email).toBe('请填写有效的邮箱地址');
    expect(isApplyFormComplete({ ...FILLED, email: 'a@b' })).toBe(false);
  });

  test('必填齐全即可提交，期望账本名称选填', () => {
    expect(isApplyFormComplete(FILLED)).toBe(true);
  });

  test('只有空白的需求简介不算填写', () => {
    expect(isApplyFormComplete({ ...FILLED, needs: '   ' })).toBe(false);
  });
});

describe('toApplicationPayload', () => {
  test('去首尾空白、邮箱转小写，选填项为空时不传', () => {
    expect(toApplicationPayload(FILLED, null)).toEqual({
      name: '张三',
      email: 'zs@example.com',
      identity: '某某大学',
      needs: '课题组报销',
      website: '',
    });
  });

  test('带期望账本名称与推荐码', () => {
    const payload = toApplicationPayload({ ...FILLED, ledgerName: '课题组账本' }, 'REF1');
    expect(payload.ledger_name).toBe('课题组账本');
    expect(payload.ref).toBe('REF1');
  });
});

describe('suggestSlug', () => {
  test('取邮箱本地部分并规范为账套标识', () => {
    expect(suggestSlug('Zhang.San_01@example.com')).toBe('zhang-san-01');
  });

  test('本地部分没有可用字符时给出兜底', () => {
    expect(suggestSlug('张三@example.com')).toBe('ledger');
  });
});

describe('链接', () => {
  test('站内路径补全为完整地址，完整地址原样返回', () => {
    expect(absoluteUrl('/apply?ref=A', 'http://local')).toBe('http://local/apply?ref=A');
    expect(absoluteUrl('https://x.test/a', 'http://local')).toBe('https://x.test/a');
  });

  test('推荐链接：优先后端 link，否则按推荐码拼出，停用时为空', () => {
    expect(referralLink({ code: 'AB', link: '/apply?ref=AB' }, 'http://local')).toBe('http://local/apply?ref=AB');
    expect(referralLink({ code: 'A B', link: null }, 'http://local')).toBe('http://local/apply?ref=A%20B');
    expect(referralLink({ code: null, link: null }, 'http://local')).toBeNull();
  });
});

describe('手动转告', () => {
  test('未配置或发送失败才需要手动转告', () => {
    expect(isUndelivered('skipped')).toBe(true);
    expect(isUndelivered('failed')).toBe(true);
    expect(isUndelivered('sent')).toBe(false);
    expect(isUndelivered('')).toBe(false);
  });

  test('通知文字里的站内链接补全为完整地址', () => {
    const notice = manualNotice(
      { mail_status: 'skipped', mail_error: '', link: '/register?code=C1', text: '请打开：\n/register?code=C1\n' },
      'https://fp.test',
    );
    expect(notice.link).toBe('https://fp.test/register?code=C1');
    expect(notice.text).toBe('请打开：\nhttps://fp.test/register?code=C1\n');
  });

  test('否决通知没有链接', () => {
    expect(manualNotice({ mail_status: 'failed', mail_error: 'x', link: null, text: '未通过' }, 'o')).toEqual({ link: null, text: '未通过' });
  });
});
