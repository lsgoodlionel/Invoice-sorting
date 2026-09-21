import { Alert, Button } from '@mantine/core';
import { useEffect, useMemo, type ReactNode } from 'react';
import { useLocation } from 'react-router';
import { authEvents } from '../../api/authEvents';
import { errorMessage } from '../../api/client';
import { useAuthStatus, useRefreshAuthStatus } from '../../api/hooks/auth';
import { LoginPage } from '../../pages/auth/LoginPage';
import { SetupPasswordPage } from '../../pages/auth/SetupPasswordPage';
import { AuthLayout, AuthLoading } from './AuthLayout';
import { CurrentUserProvider, currentUserFromStatus } from './CurrentUserContext';
import { publicPageFor } from './publicPages';

function StatusError({ error, retrying, onRetry }: { error: unknown; retrying: boolean; onRetry: () => void }) {
  return (
    <AuthLayout title="暂时无法打开" subtitle="检查登录状态时出错。">
      <Alert color="red" variant="light">
        {errorMessage(error)}
      </Alert>
      <Button variant="filled" loading={retrying} onClick={onRetry}>
        重试
      </Button>
    </AuthLayout>
  );
}

/**
 * 按 /api/auth/status 决定显示应用、设置初始密码页或登录页；受保护请求 401 时自动刷新状态。
 * 进入应用后通过 useCurrentUser() 提供当前用户与是否管理员。
 * 多账套部署下，未登录访客可直接打开 /apply（申请使用）与 /register（凭注册码注册）。
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const { data, error, isFetching, refetch } = useAuthStatus();
  const refresh = useRefreshAuthStatus();
  const currentUser = useMemo(() => (data ? currentUserFromStatus(data) : null), [data]);
  const { pathname } = useLocation();

  useEffect(() => authEvents.subscribe(() => void refresh()), [refresh]);

  if (data && currentUser) {
    if (!data.auth_enabled || data.authenticated) {
      return <CurrentUserProvider value={currentUser}>{children}</CurrentUserProvider>;
    }
    const publicPage = data.multi_tenant && data.password_set ? publicPageFor(pathname) : null;
    if (publicPage) return publicPage;
    // 多账套部署的首次启动：设置的是平台管理员账号，不是某个账套的 admin
    return data.password_set ? <LoginPage /> : <SetupPasswordPage isPlatform={data.multi_tenant === true} />;
  }
  if (error) return <StatusError error={error} retrying={isFetching} onRetry={() => void refetch()} />;
  return <AuthLoading />;
}
