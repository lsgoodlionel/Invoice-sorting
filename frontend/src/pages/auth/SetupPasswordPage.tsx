import { Button, Stack, Text, TextInput } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useState, type FormEvent } from 'react';
import { ApiError, errorMessage } from '../../api/client';
import { useRefreshAuthStatus, useSetupPassword } from '../../api/hooks/auth';
import { AuthLayout } from '../../components/auth/AuthLayout';
import { NewPasswordFields } from '../../components/auth/NewPasswordFields';
import { isNewPasswordValid } from '../../lib/password';
import { DEFAULT_USERNAME, saveRememberedUsername } from '../../lib/rememberedUsername';

const HTTP_CONFLICT = 409;

const isAlreadySet = (error: unknown) => error instanceof ApiError && error.status === HTTP_CONFLICT;

const INTRO = `为管理员账户 ${DEFAULT_USERNAME} 设置初始密码。设置后可在「设置 → 用户管理」中添加其他用户。请妥善保管，忘记后需在服务器上执行重置命令。`;

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
    setup.mutate(password, { onError, onSuccess: () => saveRememberedUsername(DEFAULT_USERNAME) });
  };

  const inlineError = setup.error && !isAlreadySet(setup.error) ? errorMessage(setup.error) : null;

  return (
    <AuthLayout title="欢迎使用发票账本" subtitle={INTRO}>
      <form onSubmit={submit} noValidate>
        <Stack gap="xs">
          {/* 只读用户名便于浏览器密码管理器保存 admin 账户 */}
          <TextInput label="用户名" name="username" autoComplete="username" value={DEFAULT_USERNAME} readOnly />
          <NewPasswordFields password={password} confirm={confirm} onPasswordChange={setPassword} onConfirmChange={setConfirm} autoFocus />
        </Stack>
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
