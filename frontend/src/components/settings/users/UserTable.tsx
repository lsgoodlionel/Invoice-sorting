import { Badge, Button, Group, Table, Text, Tooltip } from '@mantine/core';
import type { User } from '../../../api/types';
import { formatLastLogin, roleLabel } from '../../../lib/users';

export interface UserRowHandlers {
  onEdit: (user: User) => void;
  onResetPassword: (user: User) => void;
  onToggleActive: (user: User) => void;
}

interface UserTableProps extends UserRowHandlers {
  users: readonly User[];
  currentUserId: number | null;
}

const TABLE_MIN_WIDTH = 760;
const SELF_DEACTIVATE_HINT = '不能停用当前登录的账户';

function StatusBadge({ user }: { user: User }) {
  if (!user.is_active) return <Badge size="sm" variant="light" color="gray">已停用</Badge>;
  if (!user.has_password) {
    return <Badge size="sm" variant="light" color="orange" title="重置密码后才能登录">未设置密码</Badge>;
  }
  return <Badge size="sm" variant="light" color="ink">启用</Badge>;
}

function ActiveToggle({ user, isSelf, onToggleActive }: { user: User; isSelf: boolean; onToggleActive: (user: User) => void }) {
  if (!user.is_active) {
    return <Button size="compact-xs" variant="subtle" aria-label={`启用 ${user.display_name}`} onClick={() => onToggleActive(user)}>启用</Button>;
  }
  return (
    <Tooltip label={SELF_DEACTIVATE_HINT} disabled={!isSelf} withArrow>
      <span>
        <Button size="compact-xs" variant="subtle" color="red" disabled={isSelf} aria-label={`停用 ${user.display_name}`} onClick={() => onToggleActive(user)}>
          停用
        </Button>
      </span>
    </Tooltip>
  );
}

function UserRow({ user, isSelf, onEdit, onResetPassword, onToggleActive }: UserRowHandlers & { user: User; isSelf: boolean }) {
  return (
    <Table.Tr data-testid={`user-row-${user.id}`} style={{ opacity: user.is_active ? 1 : 0.6 }}>
      <Table.Td>
        <Text size="sm" span className="num">{user.username}</Text>
        {isSelf && <Text size="xs" c="dimmed" span>（我）</Text>}
      </Table.Td>
      <Table.Td><Text size="sm" truncate maw={160}>{user.display_name}</Text></Table.Td>
      <Table.Td>
        <Badge size="sm" variant={user.role === 'admin' ? 'filled' : 'outline'} color={user.role === 'admin' ? 'ink' : 'gray'}>{roleLabel(user.role)}</Badge>
      </Table.Td>
      <Table.Td><StatusBadge user={user} /></Table.Td>
      <Table.Td><Text size="xs" c="dimmed" className="num">{formatLastLogin(user.last_login_at)}</Text></Table.Td>
      <Table.Td>
        <Group gap={4} justify="flex-end" wrap="nowrap">
          <Button size="compact-xs" variant="subtle" aria-label={`编辑 ${user.display_name}`} onClick={() => onEdit(user)}>编辑</Button>
          <Button size="compact-xs" variant="subtle" aria-label={`重置 ${user.display_name} 的密码`} onClick={() => onResetPassword(user)}>重置密码</Button>
          <ActiveToggle user={user} isSelf={isSelf} onToggleActive={onToggleActive} />
        </Group>
      </Table.Td>
    </Table.Tr>
  );
}

export function UserTable({ users, currentUserId, ...handlers }: UserTableProps) {
  return (
    <div className="table-scroll">
      <Table className="ledger-table" miw={TABLE_MIN_WIDTH}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>用户名</Table.Th><Table.Th>姓名</Table.Th><Table.Th>角色</Table.Th><Table.Th>状态</Table.Th><Table.Th>最近登录</Table.Th><Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {users.map((user) => (
            <UserRow key={user.id} user={user} isSelf={user.id === currentUserId} {...handlers} />
          ))}
        </Table.Tbody>
      </Table>
    </div>
  );
}
