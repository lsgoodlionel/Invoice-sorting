import { describe, expect, test } from 'vitest';
import { PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, confirmError, passwordError, passwordStrength } from './password';

describe('passwordError', () => {
  test('rejects passwords outside 8-128 characters', () => {
    expect(passwordError('')).toBeNull();
    expect(passwordError('a'.repeat(PASSWORD_MIN_LENGTH - 1))).toBe('密码至少 8 位');
    expect(passwordError('a'.repeat(PASSWORD_MIN_LENGTH))).toBeNull();
    expect(passwordError('a'.repeat(PASSWORD_MAX_LENGTH))).toBeNull();
    expect(passwordError('a'.repeat(PASSWORD_MAX_LENGTH + 1))).toBe('密码最多 128 位');
  });
});

describe('confirmError', () => {
  test('reports mismatch only after confirmation is typed', () => {
    expect(confirmError('abcdefgh', '')).toBeNull();
    expect(confirmError('abcdefgh', 'abcdefgx')).toBe('两次输入的密码不一致');
    expect(confirmError('abcdefgh', 'abcdefgh')).toBeNull();
  });
});

describe('passwordStrength', () => {
  test('scores by length and character variety', () => {
    expect(passwordStrength('').level).toBe('none');
    expect(passwordStrength('abcdefgh').level).toBe('weak');
    expect(passwordStrength('abcdefgh12').level).toBe('medium');
    expect(passwordStrength('Abcdefgh12!xyz').level).toBe('strong');
  });
});
