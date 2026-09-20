import { Button, Group, Stack, Text } from '@mantine/core';
import { IconTicket, IconUserPlus } from '@tabler/icons-react';
import { useState } from 'react';
import { useAuthStatus } from '../../../api/hooks/auth';
import { useUsers } from '../../../api/hooks/users';
import type { User } from '../../../api/types';
import { useCurrentUser } from '../../auth/CurrentUserContext';
import { CreateUserModal } from './CreateUserModal';
import { InviteModal } from './InviteModal';
import { EditUserModal } from './EditUserModal';
import { ResetPasswordModal } from './ResetPasswordModal';
import { UserTable } from './UserTable';
import { useToggleUserActive } from './useToggleUserActive';

type UserDialog =
  | { type: 'create' }
  | { type: 'invite' }
  | { type: 'edit'; user: User }
  | { type: 'password'; user: User }
  | null;

/**
 * 用户管理（仅管理员）：添加用户、修改姓名与角色、重置密码、启用/停用。
 * 多租户部署额外提供邀请码入口；单租户部署不暴露。
 */
export function UserManager() {
  const { data: users = [], isLoading } = useUsers();
  const { data: status } = useAuthStatus();
  const { user: me } = useCurrentUser();
  const [dialog, setDialog] = useState<UserDialog>(null);
  const toggleActive = useToggleUserActive();
  const close = () => setDialog(null);
  const currentUserId = me?.id ?? null;

  return (
    <Stack gap="xs">
      <Group justify="space-between" gap="xs">
        <Text size="xs" c="dimmed">所有用户共用同一账本，记录会显示上传人与操作人。停用后该用户立即退出登录。</Text>
        <Group gap="xs">
          {status?.multi_tenant && (
            <Button size="xs" variant="subtle" leftSection={<IconTicket size={14} stroke={1.6} />} onClick={() => setDialog({ type: 'invite' })}>
              邀请码
            </Button>
          )}
          <Button size="xs" variant="outline" leftSection={<IconUserPlus size={14} stroke={1.6} />} onClick={() => setDialog({ type: 'create' })}>
            添加用户
          </Button>
        </Group>
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
      {dialog?.type === 'invite' && <InviteModal onClose={close} />}
      {dialog?.type === 'edit' && <EditUserModal user={dialog.user} isSelf={dialog.user.id === currentUserId} onClose={close} />}
      {dialog?.type === 'password' && <ResetPasswordModal user={dialog.user} onClose={close} />}
    </Stack>
  );
}
