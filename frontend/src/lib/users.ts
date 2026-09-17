import dayjs from 'dayjs';
import type { CurrentUser, UserRole } from '../api/types';

// 用户名、姓名规则与用户相关文案（与后端契约一致）。

export const USERNAME_MIN_LENGTH = 3;
export const USERNAME_MAX_LENGTH = 32;
export const DISPLAY_NAME_MAX_LENGTH = 32;

const USERNAME_PATTERN = /^[A-Za-z0-9_.-]+$/;

export const ROLE_LABELS: Readonly<Record<UserRole, string>> = { admin: '管理员', member: '普通用户' };

export const ROLE_OPTIONS: readonly { value: UserRole; label: string }[] = [
  { value: 'member', label: ROLE_LABELS.member },
  { value: 'admin', label: ROLE_LABELS.admin },
];

export const roleLabel = (role: UserRole): string => ROLE_LABELS[role];

/** 空串不报错（尚未输入）。 */
export function usernameError(username: string): string | null {
  if (!username) return null;
  if (username.length < USERNAME_MIN_LENGTH || username.length > USERNAME_MAX_LENGTH) {
    return `用户名需 ${USERNAME_MIN_LENGTH}–${USERNAME_MAX_LENGTH} 个字符`;
  }
  return USERNAME_PATTERN.test(username) ? null : '只能包含字母、数字、下划线、点、连字符';
}

export function isUsernameValid(username: string): boolean {
  return Boolean(username) && usernameError(username) === null;
}

/** 姓名按去除首尾空白后校验；新建时可留空（默认同用户名）。 */
export function displayNameError(displayName: string, options: { required?: boolean } = {}): string | null {
  const trimmed = displayName.trim();
  if (!trimmed) return options.required && displayName ? '请填写姓名' : null;
  return trimmed.length > DISPLAY_NAME_MAX_LENGTH ? `姓名最多 ${DISPLAY_NAME_MAX_LENGTH} 个字符` : null;
}

/** 侧边栏等处的当前用户标签：管理员带“（管理员）”。 */
export function userLabel(user: CurrentUser): string {
  return user.role === 'admin' ? `${user.display_name}（${ROLE_LABELS.admin}）` : user.display_name;
}

export function formatLastLogin(lastLoginAt: string | null): string {
  return lastLoginAt ? dayjs(lastLoginAt).format('YYYY-MM-DD HH:mm') : '从未登录';
}
