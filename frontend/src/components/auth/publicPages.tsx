import type { ReactNode } from 'react';
import { APPLY_PATH, REGISTER_PATH } from '../../lib/signup';
import { ApplyPage } from '../../pages/auth/ApplyPage';
import { RegisterPage } from '../../pages/auth/RegisterPage';

const TRAILING_SLASHES = /\/+$/;

/** 未登录也能打开的页面（仅多账套部署）：申请使用与凭注册码注册。 */
export function publicPageFor(pathname: string): ReactNode | null {
  const path = pathname.replace(TRAILING_SLASHES, '');
  if (path === APPLY_PATH) return <ApplyPage />;
  if (path === REGISTER_PATH) return <RegisterPage />;
  return null;
}
