import { Alert, Button, CopyButton, Group, Modal, Stack, Text } from '@mantine/core';
import { useState } from 'react';
import { useCreateInvite } from '../../../api/hooks/invites';
import type { Invite, UserRole } from '../../../api/types';
import { FormError } from './FormError';
import { RoleControl } from './RoleControl';

const INTRO = '把邀请码发给对方，对方在登录页点“有邀请码？加入账套”即可加入本账套。';

function InviteCode({ invite }: { invite: Invite }) {
  return (
    <Alert color="ink" variant="light" title="邀请码已生成">
      <Stack gap={6}>
        <Text size="lg" fw={600} className="num" data-testid="invite-code">
          {invite.code}
        </Text>
        <Text size="xs" c="dimmed">
          仅可使用一次{invite.expires_on ? `，${invite.expires_on} 前有效` : ''}
        </Text>
        <CopyButton value={invite.code}>
          {({ copied, copy }) => (
            <div>
              <Button size="compact-xs" variant="outline" onClick={copy}>
                {copied ? '已复制' : '复制邀请码'}
              </Button>
            </div>
          )}
        </CopyButton>
      </Stack>
    </Alert>
  );
}

/** 生成本账套的邀请码（仅多租户部署暴露入口）。 */
export function InviteModal({ onClose }: { onClose: () => void }) {
  const create = useCreateInvite();
  const [role, setRole] = useState<UserRole>('member');
  const invite = create.data ?? null;

  const changeRole = (next: UserRole) => {
    setRole(next);
    if (create.error) create.reset();
  };

  return (
    <Modal opened onClose={onClose} title="生成邀请码">
      <Stack gap="sm">
        <Text size="xs" c="dimmed">{INTRO}</Text>
        <RoleControl value={role} onChange={changeRole} />
        {invite && <InviteCode invite={invite} />}
        <FormError error={create.error} />
        <Group justify="flex-end">
          <Button variant="subtle" onClick={onClose}>关闭</Button>
          <Button variant="filled" loading={create.isPending} onClick={() => create.mutate({ role })}>
            {invite ? '再生成一个' : '生成邀请码'}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
