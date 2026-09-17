import { Alert, Button } from '@mantine/core';
import { useEffect, useMemo, type ReactNode } from 'react';
import { authEvents } from '../../api/authEvents';
import { errorMessage } from '../../api/client';
import { useAuthStatus, useRefreshAuthStatus } from '../../api/hooks/auth';
import { LoginPage } from '../../pages/auth/LoginPage';
import { SetupPasswordPage } from '../../pages/auth/SetupPasswordPage';
import { AuthLayout, AuthLoading } from './AuthLayout';
import { CurrentUserProvider, currentUserFromStatus } from './CurrentUserContext';

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
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const { data, error, isFetching, refetch } = useAuthStatus();
  const refresh = useRefreshAuthStatus();
  const currentUser = useMemo(() => (data ? currentUserFromStatus(data) : null), [data]);

  useEffect(() => authEvents.subscribe(() => void refresh()), [refresh]);

  if (data && currentUser) {
    if (!data.auth_enabled || data.authenticated) {
      return <CurrentUserProvider value={currentUser}>{children}</CurrentUserProvider>;
    }
    return data.password_set ? <LoginPage /> : <SetupPasswordPage />;
  }
  if (error) return <StatusError error={error} retrying={isFetching} onRetry={() => void refetch()} />;
  return <AuthLoading />;
}
