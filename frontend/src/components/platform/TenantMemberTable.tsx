import { Badge, Button, Group, Table, Text } from '@mantine/core';
import type { User } from '../../api/types';
import { roleLabel } from '../../lib/users';

export interface MemberHandlers {
  onResetPassword: (member: User) => void;
  onToggleActive: (member: User) => void;
}

function StatusBadge({ member }: { member: User }) {
  if (!member.is_active) return <Badge size="sm" variant="light" color="gray">已停用</Badge>;
  if (!member.has_password) return <Badge size="sm" variant="light" color="orange">未设置密码</Badge>;
  return <Badge size="sm" variant="light" color="ink">启用</Badge>;
}

function MemberRow({ member, onResetPassword, onToggleActive }: MemberHandlers & { member: User }) {
  return (
    <Table.Tr data-testid={`member-row-${member.id}`} style={{ opacity: member.is_active ? 1 : 0.6 }}>
      <Table.Td><Text size="sm" span className="num">{member.username}</Text></Table.Td>
      <Table.Td><Text size="sm" truncate maw={140}>{member.display_name}</Text></Table.Td>
      <Table.Td>
        <Badge size="sm" variant={member.role === 'admin' ? 'filled' : 'outline'} color={member.role === 'admin' ? 'ink' : 'gray'}>
          {roleLabel(member.role)}
        </Badge>
      </Table.Td>
      <Table.Td><StatusBadge member={member} /></Table.Td>
      <Table.Td>
        <Group gap={4} justify="flex-end" wrap="nowrap">
          <Button size="compact-xs" variant="subtle" aria-label={`重置 ${member.display_name} 的密码`} onClick={() => onResetPassword(member)}>
            重置密码
          </Button>
          <Button
            size="compact-xs"
            variant="subtle"
            color={member.is_active ? 'red' : undefined}
            aria-label={`${member.is_active ? '停用' : '启用'} ${member.display_name}`}
            onClick={() => onToggleActive(member)}
          >
            {member.is_active ? '停用' : '启用'}
          </Button>
        </Group>
      </Table.Td>
    </Table.Tr>
  );
}

/** 某账套的成员（平台视角）：只做加人、重置密码与停用恢复，角色调整仍在账套内完成。 */
export function TenantMemberTable({ members, ...handlers }: MemberHandlers & { members: readonly User[] }) {
  return (
    <div className="table-scroll">
      <Table className="ledger-table" miw={560}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>用户名</Table.Th>
            <Table.Th>姓名</Table.Th>
            <Table.Th>角色</Table.Th>
            <Table.Th>状态</Table.Th>
            <Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {members.map((member) => (
            <MemberRow key={member.id} member={member} {...handlers} />
          ))}
        </Table.Tbody>
      </Table>
    </div>
  );
}
