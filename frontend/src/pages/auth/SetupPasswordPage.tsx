import { Button, Stack, Text, TextInput } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useState, type FormEvent } from 'react';
import { ApiError, errorMessage } from '../../api/client';
import { useRefreshAuthStatus, useSetupPassword } from '../../api/hooks/auth';
import type { SetupInput } from '../../api/types';
import { AuthLayout } from '../../components/auth/AuthLayout';
import { NewPasswordFields } from '../../components/auth/NewPasswordFields';
import { isNewPasswordValid } from '../../lib/password';
import { DEFAULT_USERNAME, saveRememberedUsername } from '../../lib/rememberedUsername';
import { isUsernameValid, usernameError } from '../../lib/users';

const HTTP_CONFLICT = 409;

const isAlreadySet = (error: unknown) => error instanceof ApiError && error.status === HTTP_CONFLICT;

/** 单账套设置的是本账本的管理员；多账套首次启动设置的是平台管理员。 */
const COPY = {
  single: {
    title: '设置初始密码',
    intro: `为管理员账户 ${DEFAULT_USERNAME} 设置初始密码。设置后可在「设置 → 用户管理」中添加其他用户。`,
    note: '尚未设置密码前任何人打开此页面都可以设置，请尽快完成。',
    conflict: '已被设置过，请登录',
  },
  platform: {
    title: '设置平台管理员',
    intro: '这是平台管理员账号，用于开通与管理各账套。设置后可从左侧导航进入「平台」，在那里开通账套并指定各账套的管理员。',
    note: '尚未设置前任何人打开此页面都可以设置，请尽快完成。',
    conflict: '平台管理员已被创建过，请登录',
  },
} as const;

/**
 * 首次设置页：成功后刷新认证状态进入应用；已被设置过（409）则切到登录页。
 * 多账套部署（isPlatform）允许自定义平台管理员用户名，默认 admin。
 */
export function SetupPasswordPage({ isPlatform = false }: { isPlatform?: boolean }) {
  const copy = isPlatform ? COPY.platform : COPY.single;
  const setup = useSetupPassword();
  const refresh = useRefreshAuthStatus();
  const [username, setUsername] = useState(DEFAULT_USERNAME);
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const name = username.trim();
  const canSubmit = isNewPasswordValid(password, confirm) && (!isPlatform || isUsernameValid(name));

  const onError = (error: unknown) => {
    if (!isAlreadySet(error)) return;
    notifications.show({ color: 'ink', title: '无法设置初始密码', message: copy.conflict });
    void refresh();
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit || setup.isPending) return;
    // 单账套部署固定为内置管理员 admin，请求体保持只有 password
    const payload: SetupInput = isPlatform ? { username: name, password } : { password };
    setup.mutate(payload, {
      onError,
      onSuccess: () => saveRememberedUsername(isPlatform ? name : DEFAULT_USERNAME),
    });
  };

  const inlineError = setup.error && !isAlreadySet(setup.error) ? errorMessage(setup.error) : null;
  const footer = (
    <Text size="xs" className="auth-warning">
      {copy.note}
    </Text>
  );

  return (
    <AuthLayout title={copy.title} subtitle={copy.intro} footer={footer}>
      <form onSubmit={submit} noValidate>
        <Stack gap="xs">
          {isPlatform ? (
            <TextInput
              label="用户名"
              description="平台管理员的登录账号，可自定义"
              name="username"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              value={username}
              error={usernameError(name)}
              onChange={(event) => setUsername(event.currentTarget.value)}
            />
          ) : (
            /* 只读用户名便于浏览器密码管理器保存 admin 账户 */
            <TextInput label="用户名" name="username" autoComplete="username" value={DEFAULT_USERNAME} readOnly />
          )}
          <NewPasswordFields password={password} confirm={confirm} onPasswordChange={setPassword} onConfirmChange={setConfirm} autoFocus={!isPlatform} />
        </Stack>
        {inlineError && (
          <Text size="sm" c="red.7" mt="sm" role="alert">
            {inlineError}
          </Text>
        )}
        <Button type="submit" variant="filled" fullWidth size="md" mt="xl" loading={setup.isPending} disabled={!canSubmit}>
          设置并进入
        </Button>
      </form>
    </AuthLayout>
  );
}
