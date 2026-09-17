// 登录密码规则（与后端一致：8–128 个字符）与纯前端强度提示。
export const PASSWORD_MIN_LENGTH = 8;
export const PASSWORD_MAX_LENGTH = 128;

const LONG_PASSWORD_LENGTH = 12;

/** 空串不报错（尚未输入）；否则校验长度。 */
export function passwordError(password: string): string | null {
  if (!password) return null;
  if (password.length < PASSWORD_MIN_LENGTH) return `密码至少 ${PASSWORD_MIN_LENGTH} 位`;
  if (password.length > PASSWORD_MAX_LENGTH) return `密码最多 ${PASSWORD_MAX_LENGTH} 位`;
  return null;
}

export function confirmError(password: string, confirm: string): string | null {
  if (!confirm) return null;
  return password === confirm ? null : '两次输入的密码不一致';
}

export function isNewPasswordValid(password: string, confirm: string): boolean {
  return Boolean(password) && password === confirm && passwordError(password) === null;
}

export type StrengthLevel = 'none' | 'weak' | 'medium' | 'strong';

export interface PasswordStrength {
  level: StrengthLevel;
  label: string;
  /** 0–100，用于进度条 */
  percent: number;
}

const CHAR_CLASSES: readonly RegExp[] = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/];

const STRENGTHS: Readonly<Record<StrengthLevel, PasswordStrength>> = {
  none: { level: 'none', label: '', percent: 0 },
  weak: { level: 'weak', label: '弱', percent: 33 },
  medium: { level: 'medium', label: '中', percent: 66 },
  strong: { level: 'strong', label: '强', percent: 100 },
};

/** 按长度与字符种类粗略估计强度，仅作提示，不强制。 */
export function passwordStrength(password: string): PasswordStrength {
  if (!password) return STRENGTHS.none;
  const kinds = CHAR_CLASSES.filter((pattern) => pattern.test(password)).length;
  const lengthScore = password.length >= LONG_PASSWORD_LENGTH ? 2 : password.length >= PASSWORD_MIN_LENGTH ? 1 : 0;
  const score = lengthScore + kinds;
  if (score >= 5) return STRENGTHS.strong;
  if (score >= 3) return STRENGTHS.medium;
  return STRENGTHS.weak;
}
