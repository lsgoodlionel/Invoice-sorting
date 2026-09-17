import { Group, Stack, Text } from '@mantine/core';
import { useAuthStatus } from '../../api/hooks/auth';
import { LogoutButton } from '../auth/LogoutButton';
import { ChangePasswordForm } from './ChangePasswordForm';

export function SecuritySettings() {
  const { data } = useAuthStatus();
  if (!data) return null;

  if (!data.auth_enabled) {
    return (
      <Text size="sm" c="dimmed">
        当前未启用登录认证（服务端设置了 INVOICE_SORTING_AUTH_ENABLED=false），仅适合本机单人使用。
      </Text>
    );
  }

  return (
    <Stack gap="lg">
      <ChangePasswordForm />
      <Group gap="sm" align="center">
        <LogoutButton variant="outline" color="red" />
        <Text size="xs" c="dimmed">
          仅退出当前浏览器；修改密码会让其他设备退出。
        </Text>
      </Group>
    </Stack>
  );
}
