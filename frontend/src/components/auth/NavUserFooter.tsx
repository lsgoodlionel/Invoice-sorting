import { Group, Stack, Text } from '@mantine/core';
import { IconUserCircle } from '@tabler/icons-react';
import { userLabel } from '../../lib/users';
import { useCurrentUser } from './CurrentUserContext';
import { LogoutButton } from './LogoutButton';

/** 侧边栏底部：当前用户“姓名（管理员）”与退出登录；关闭认证时不显示。 */
export function NavUserFooter() {
  const { user, authEnabled } = useCurrentUser();
  if (!authEnabled) return null;
  return (
    <Stack gap={2} mt="auto" mb="xs" className="nav-user">
      {user && (
        <Group gap={6} px="sm" wrap="nowrap" title={`登录账户：${user.username}`}>
          <IconUserCircle size={16} stroke={1.6} className="nav-user-icon" aria-hidden="true" />
          <Text size="sm" fw={500} truncate data-testid="nav-current-user">
            {userLabel(user)}
          </Text>
        </Group>
      )}
      <LogoutButton variant="subtle" color="gray" size="xs" justify="flex-start" className="nav-logout" />
    </Stack>
  );
}
