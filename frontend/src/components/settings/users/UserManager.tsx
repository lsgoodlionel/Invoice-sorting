import { Button, Group, Stack, Text } from '@mantine/core';
import { IconUserPlus } from '@tabler/icons-react';
import { useState } from 'react';
import { useUsers } from '../../../api/hooks/users';
import type { User } from '../../../api/types';
import { useCurrentUser } from '../../auth/CurrentUserContext';
import { CreateUserModal } from './CreateUserModal';
import { EditUserModal } from './EditUserModal';
import { ResetPasswordModal } from './ResetPasswordModal';
import { UserTable } from './UserTable';
import { useToggleUserActive } from './useToggleUserActive';

type UserDialog = { type: 'create' } | { type: 'edit'; user: User } | { type: 'password'; user: User } | null;

/** 用户管理（仅管理员）：添加用户、修改姓名与角色、重置密码、启用/停用。 */
export function UserManager() {
  const { data: users = [], isLoading } = useUsers();
  const { user: me } = useCurrentUser();
  const [dialog, setDialog] = useState<UserDialog>(null);
  const toggleActive = useToggleUserActive();
  const close = () => setDialog(null);
  const currentUserId = me?.id ?? null;

  return (
    <Stack gap="xs">
      <Group justify="space-between" gap="xs">
        <Text size="xs" c="dimmed">所有用户共用同一账本，记录会显示上传人与操作人。停用后该用户立即退出登录。</Text>
        <Button size="xs" variant="outline" leftSection={<IconUserPlus size={14} stroke={1.6} />} onClick={() => setDialog({ type: 'create' })}>
          添加用户
        </Button>
      </Group>
      {!isLoading && (
        <UserTable
          users={users}
          currentUserId={currentUserId}
          onEdit={(user) => setDialog({ type: 'edit', user })}
          onResetPassword={(user) => setDialog({ type: 'password', user })}
          onToggleActive={toggleActive}
        />
      )}
      {dialog?.type === 'create' && <CreateUserModal onClose={close} />}
      {dialog?.type === 'edit' && <EditUserModal user={dialog.user} isSelf={dialog.user.id === currentUserId} onClose={close} />}
      {dialog?.type === 'password' && <ResetPasswordModal user={dialog.user} onClose={close} />}
    </Stack>
  );
}
