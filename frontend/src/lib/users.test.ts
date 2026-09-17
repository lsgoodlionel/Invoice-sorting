import { describe, expect, test } from 'vitest';
import { displayNameError, formatLastLogin, roleLabel, userLabel, usernameError } from './users';

describe('usernameError', () => {
  test('accepts letters, digits, underscore, dot and hyphen within 3–32 chars', () => {
    expect(usernameError('')).toBeNull();
    expect(usernameError('zhang.san-01_a')).toBeNull();
    expect(usernameError('ab')).toBe('用户名需 3–32 个字符');
    expect(usernameError('a'.repeat(33))).toBe('用户名需 3–32 个字符');
    expect(usernameError('张三abc')).toBe('只能包含字母、数字、下划线、点、连字符');
  });
});

describe('displayNameError', () => {
  test('limits to 32 characters and optionally requires a value', () => {
    expect(displayNameError('')).toBeNull();
    expect(displayNameError('  ', { required: true })).toBe('请填写姓名');
    expect(displayNameError('名'.repeat(33))).toBe('姓名最多 32 个字符');
  });
});

describe('labels', () => {
  test('role and user labels', () => {
    expect(roleLabel('admin')).toBe('管理员');
    expect(roleLabel('member')).toBe('普通用户');
    expect(userLabel({ id: 1, username: 'admin', display_name: '王五', role: 'admin' })).toBe('王五（管理员）');
    expect(userLabel({ id: 2, username: 'zs', display_name: '张三', role: 'member' })).toBe('张三');
  });

  test('last login falls back to never', () => {
    expect(formatLastLogin(null)).toBe('从未登录');
    expect(formatLastLogin('2026-09-15T10:05:00+08:00')).toMatch(/^2026-09-15 \d{2}:05$/);
  });
});
