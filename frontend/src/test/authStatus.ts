import type { AuthStatus } from '../api/types';

export const AUTHENTICATED: AuthStatus = { auth_enabled: true, password_set: true, authenticated: true };
export const NEEDS_LOGIN: AuthStatus = { auth_enabled: true, password_set: true, authenticated: false };
export const NEEDS_SETUP: AuthStatus = { auth_enabled: true, password_set: false, authenticated: false };
export const AUTH_DISABLED: AuthStatus = { auth_enabled: false, password_set: false, authenticated: true };

/** 可变的 GET /api/auth/status 模拟：用于模拟登录、设置、会话失效后的状态变化。 */
export function authStatusRoute(initial: AuthStatus) {
  let current = initial;
  return {
    route: () => ({ data: current }),
    set: (next: AuthStatus) => {
      current = next;
    },
  };
}
