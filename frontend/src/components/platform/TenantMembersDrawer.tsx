import { Button, Divider, Drawer, Group, Stack, Text } from '@mantine/core';
import { IconUserPlus } from '@tabler/icons-react';
import { useState, type ReactNode } from 'react';
import { useDeleteTenantMember, useTenantMembers, useUpdateTenantMember } from '../../api/hooks/platformMembers';
import type { PlatformTenant, User } from '../../api/types';
import { useDeleteUserConfirm } from '../settings/users/useDeleteUserConfirm';
import { AddTenantMemberModal } from './AddTenantMemberModal';
import { TenantExportSection } from './TenantExportSection';
import { TenantInviteSection } from './TenantInviteSection';
import { TenantMemberTable } from './TenantMemberTable';
import { TenantPasswordModal } from './TenantPasswordModal';

type Dialog = { type: 'add' } | { type: 'password'; member: User } | null;

function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Stack gap="xs">
      <Divider label={<span className="section-label">{label}</span>} labelPosition="left" />
      {children}
    </Stack>
  );
}

/** 单个账套的运营抽屉：成员、邀请码与数据导出。 */
export function TenantMembersDrawer({ tenant, onClose }: { tenant: PlatformTenant; onClose: () => void }) {
  const slug = tenant.slug;
  const { data: members = [], isLoading } = useTenantMembers(slug);
  const update = useUpdateTenantMember(slug);
  const confirmDelete = useDeleteUserConfirm(useDeleteTenantMember(slug), { scope: 'tenant', tenantLabel: `账套「${tenant.name}」` });
  const [dialog, setDialog] = useState<Dialog>(null);
  const close = () => setDialog(null);

  return (
    <Drawer opened onClose={onClose} position="right" size="lg" title={`账套运营：${tenant.name}`}>
      <Stack gap="lg">
        <Section label="成员">
          <Group justify="space-between">
            <Text size="xs" c="dimmed">停用或移出后该成员立即退出登录；账套至少保留一名管理员。</Text>
            <Button
              size="xs"
              variant="filled"
              leftSection={<IconUserPlus size={14} stroke={1.6} />}
              onClick={() => setDialog({ type: 'add' })}
            >
              添加成员
            </Button>
          </Group>
          {!isLoading && (
            <TenantMemberTable
              members={members}
              onResetPassword={(member) => setDialog({ type: 'password', member })}
              onToggleActive={(member) => update.mutate({ id: member.id, patch: { is_active: !member.is_active } })}
              onDelete={confirmDelete}
            />
          )}
        </Section>
        <Section label="邀请码"><TenantInviteSection slug={slug} /></Section>
        <Section label="导出账套"><TenantExportSection slug={slug} /></Section>
      </Stack>
      {dialog?.type === 'add' && <AddTenantMemberModal slug={slug} onClose={close} />}
      {dialog?.type === 'password' && (
        <TenantPasswordModal slug={slug} member={dialog.member} onClose={close} />
      )}
    </Drawer>
  );
}
