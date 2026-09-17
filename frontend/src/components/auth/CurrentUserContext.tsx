import { createContext, useContext, type ReactNode } from 'react';
import type { AuthStatus, CurrentUser } from '../../api/types';

export interface CurrentUserValue {
  /** 当前登录用户；关闭认证时为 null */
  user: CurrentUser | null;
  /** 管理员，或关闭认证（所有端点放行） */
  isAdmin: boolean;
  authEnabled: boolean;
}

/** AuthGate 之外默认无权限（fail closed）。 */
const ANONYMOUS: CurrentUserValue = { user: null, isAdmin: false, authEnabled: true };

const CurrentUserContext = createContext<CurrentUserValue>(ANONYMOUS);

export function currentUserFromStatus(status: AuthStatus): CurrentUserValue {
  const user = status.user ?? null;
  return { user, isAdmin: !status.auth_enabled || user?.role === 'admin', authEnabled: status.auth_enabled };
}

export function CurrentUserProvider({ value, children }: { value: CurrentUserValue; children: ReactNode }) {
  return <CurrentUserContext.Provider value={value}>{children}</CurrentUserContext.Provider>;
}

export const useCurrentUser = (): CurrentUserValue => useContext(CurrentUserContext);
