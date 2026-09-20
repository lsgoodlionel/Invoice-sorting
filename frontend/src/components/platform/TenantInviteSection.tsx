import { Alert, Button, CopyButton, Group, Stack, Text } from '@mantine/core';
import { IconTicket } from '@tabler/icons-react';
import { useState } from 'react';
import { useCreateTenantInvite } from '../../api/hooks/platformMembers';
import type { UserRole } from '../../api/types';
import { FormError } from '../settings/users/FormError';
import { RoleControl } from '../settings/users/RoleControl';

const INTRO = '把邀请码发给对方，对方在登录页「有邀请码？加入账套」即可加入该账套。';

/** 为指定账套签发邀请码（平台视角）。 */
export function TenantInviteSection({ slug }: { slug: string }) {
  const create = useCreateTenantInvite(slug);
  const [role, setRole] = useState<UserRole>('member');
  const invite = create.data ?? null;

  const changeRole = (next: UserRole) => {
    setRole(next);
    if (create.error) create.reset();
  };

  return (
    <Stack gap="xs">
      <Text size="xs" c="dimmed">{INTRO}</Text>
      <RoleControl value={role} onChange={changeRole} />
      {invite && (
        <Alert color="ink" variant="light" title="邀请码已生成">
          <Group gap="sm">
            <Text size="sm" fw={600} className="num" data-testid="tenant-invite-code">{invite.code}</Text>
            <CopyButton value={invite.code}>
              {({ copied, copy }) => (
                <Button size="compact-xs" variant="outline" onClick={copy}>{copied ? '已复制' : '复制'}</Button>
              )}
            </CopyButton>
          </Group>
          <Text size="xs" c="dimmed">仅可使用一次{invite.expires_on ? `，${invite.expires_on} 前有效` : ''}</Text>
        </Alert>
      )}
      <FormError error={create.error} />
      <Group>
        <Button
          size="xs"
          variant="outline"
          loading={create.isPending}
          leftSection={<IconTicket size={14} stroke={1.6} />}
          onClick={() => create.mutate({ role })}
        >
          {invite ? '再生成一个' : '生成邀请码'}
        </Button>
      </Group>
    </Stack>
  );
}
