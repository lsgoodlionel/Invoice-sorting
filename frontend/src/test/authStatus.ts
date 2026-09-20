import type { AuthStatus, CurrentUser, TenantOption } from '../api/types';

export const ADMIN_USER: CurrentUser = { id: 1, username: 'admin', display_name: '管理员', role: 'admin' };
export const MEMBER_USER: CurrentUser = { id: 2, username: 'zhangsan', display_name: '张三', role: 'member' };

export const AUTHENTICATED: AuthStatus = { auth_enabled: true, password_set: true, authenticated: true, user: ADMIN_USER };
export const AUTHENTICATED_MEMBER: AuthStatus = { ...AUTHENTICATED, user: MEMBER_USER };
export const NEEDS_LOGIN: AuthStatus = { auth_enabled: true, password_set: true, authenticated: false, user: null };
export const NEEDS_SETUP: AuthStatus = { auth_enabled: true, password_set: false, authenticated: false, user: null };
export const AUTH_DISABLED: AuthStatus = { auth_enabled: false, password_set: false, authenticated: true, user: null };

// —— 多租户（SaaS）部署：单租户部署不返回 multi_tenant / tenant 两个字段 ——
export const ALPHA = { slug: 'alpha', name: '阿尔法账套' };
export const BETA = { slug: 'beta', name: '贝塔账套' };

export const SAAS_AUTHENTICATED: AuthStatus = { ...AUTHENTICATED, multi_tenant: true, tenant: ALPHA };
export const SAAS_NEEDS_LOGIN: AuthStatus = { ...NEEDS_LOGIN, multi_tenant: true, tenant: null };
/** 多账套首次启动：控制库为空，需要在网页上创建首个平台管理员 */
export const SAAS_NEEDS_SETUP: AuthStatus = { ...NEEDS_SETUP, multi_tenant: true, tenant: null };

export const TENANT_OPTIONS: TenantOption[] = [
  { ...ALPHA, is_current: true },
  { ...BETA, is_current: false },
];

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
