import { Button, Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useState, type FormEvent } from 'react';
import { ApiError, errorMessage } from '../../api/client';
import { useRefreshAuthStatus, useSetupPassword } from '../../api/hooks/auth';
import { AuthLayout } from '../../components/auth/AuthLayout';
import { NewPasswordFields } from '../../components/auth/NewPasswordFields';
import { isNewPasswordValid } from '../../lib/password';

const HTTP_CONFLICT = 409;

const isAlreadySet = (error: unknown) => error instanceof ApiError && error.status === HTTP_CONFLICT;

const INTRO = '首次使用请设置登录密码。设置后每次访问都需要输入此密码。请妥善保管，忘记后需在服务器上执行重置命令。';

/** 设置初始密码页：成功后刷新认证状态进入应用；已被设置过（409）则切到登录页。 */
export function SetupPasswordPage() {
  const setup = useSetupPassword();
  const refresh = useRefreshAuthStatus();
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const canSubmit = isNewPasswordValid(password, confirm);

  const onError = (error: unknown) => {
    if (!isAlreadySet(error)) return;
    notifications.show({ color: 'ink', title: '无法设置初始密码', message: '已被设置过，请登录' });
    void refresh();
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit || setup.isPending) return;
    setup.mutate(password, { onError });
  };

  const inlineError = setup.error && !isAlreadySet(setup.error) ? errorMessage(setup.error) : null;

  return (
    <AuthLayout title="欢迎使用发票账本" subtitle={INTRO}>
      <form onSubmit={submit} noValidate>
        <NewPasswordFields password={password} confirm={confirm} onPasswordChange={setPassword} onConfirmChange={setConfirm} autoFocus />
        {inlineError && (
          <Text size="sm" c="red.7" mt="sm" role="alert">
            {inlineError}
          </Text>
        )}
        <Button type="submit" variant="filled" fullWidth mt="md" loading={setup.isPending} disabled={!canSubmit}>
          设置并进入
        </Button>
      </form>
      <Text size="xs" className="auth-footnote auth-warning">
        尚未设置密码前任何人打开此页面都可以设置，请尽快完成。
      </Text>
    </AuthLayout>
  );
}
