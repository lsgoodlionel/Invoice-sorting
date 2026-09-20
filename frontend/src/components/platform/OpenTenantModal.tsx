import { Alert, Modal, Select, Stack, Switch, Text, TextInput } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useState, type FormEvent } from 'react';
import { useOpenTenant, usePlans } from '../../api/hooks/platform';
import type { OpenedTenant, TenantCreateInput } from '../../api/types';
import { isNewPasswordValid } from '../../lib/password';
import { FormError } from '../settings/users/FormError';
import { ModalActions } from '../settings/users/ModalActions';
import { NewPasswordFields } from '../auth/NewPasswordFields';
import { SLUG_HINT, isSlugValid, slugError } from './tenantForm';

interface OpenForm {
  slug: string;
  name: string;
  planCode: string;
  expiresOn: string;
  adminUsername: string;
  password: string;
  confirm: string;
  withInvite: boolean;
}

const EMPTY: OpenForm = {
  slug: '',
  name: '',
  planCode: '',
  expiresOn: '',
  adminUsername: '',
  password: '',
  confirm: '',
  withInvite: false,
};

function toPayload(form: OpenForm): TenantCreateInput {
  const shared = {
    slug: form.slug.trim(),
    name: form.name.trim() || form.slug.trim(),
    ...(form.planCode ? { plan_code: form.planCode } : {}),
    ...(form.expiresOn ? { expires_on: form.expiresOn } : {}),
  };
  if (form.withInvite) return { ...shared, with_invite: true };
  return { ...shared, admin_username: form.adminUsername.trim(), admin_password: form.password };
}

function isValid(form: OpenForm): boolean {
  if (!isSlugValid(form.slug.trim())) return false;
  if (form.withInvite) return true;
  return form.adminUsername.trim().length >= 3 && isNewPasswordValid(form.password, form.confirm);
}

function OpenedHint({ tenant }: { tenant: OpenedTenant }) {
  if (!tenant.invite) return null;
  return (
    <Alert color="ink" variant="light" title="管理员邀请码已生成">
      <Text size="sm" fw={600} className="num" data-testid="opened-invite">{tenant.invite.code}</Text>
      <Text size="xs" c="dimmed">把邀请码发给客户，对方在登录页「有邀请码？加入账套」即可成为该账套管理员。</Text>
    </Alert>
  );
}

/** 开通账套：标识 + 名称 + 套餐 + 到期日，并指定首个管理员或签发邀请码。 */
export function OpenTenantModal({ onClose }: { onClose: () => void }) {
  const open = useOpenTenant();
  const { data: plans = [] } = usePlans();
  const [form, setForm] = useState<OpenForm>(EMPTY);
  const patch = (next: Partial<OpenForm>) => {
    setForm((current) => ({ ...current, ...next }));
    if (open.error) open.reset();
  };
  const canSubmit = isValid(form);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit || open.isPending) return;
    open.mutate(toPayload(form), {
      onSuccess: (created) => {
        notifications.show({ color: 'ink', message: `已开通账套「${created.name}」` });
        if (!created.invite) onClose();
      },
    });
  };

  return (
    <Modal opened onClose={onClose} title="开通账套" size="lg">
      <form onSubmit={submit} noValidate>
        <Stack gap="sm">
          <TextInput
            label="账套标识"
            description={SLUG_HINT}
            data-autofocus
            value={form.slug}
            error={slugError(form.slug)}
            onChange={(event) => patch({ slug: event.currentTarget.value })}
          />
          <TextInput label="名称" placeholder="例如：某某学院" value={form.name} onChange={(event) => patch({ name: event.currentTarget.value })} />
          <Select
            label="套餐"
            placeholder="不指定（按免费套餐）"
            data={plans.map((plan) => ({ value: plan.code, label: plan.name || plan.code }))}
            value={form.planCode || null}
            clearable
            onChange={(value) => patch({ planCode: value ?? '' })}
          />
          <TextInput
            label="到期日"
            type="date"
            description="留空表示长期有效"
            value={form.expiresOn}
            onChange={(event) => patch({ expiresOn: event.currentTarget.value })}
          />
          <Switch
            label="改为签发管理员邀请码（不在这里建账号）"
            checked={form.withInvite}
            onChange={(event) => patch({ withInvite: event.currentTarget.checked })}
          />
          {!form.withInvite && (
            <>
              <TextInput
                label="首个管理员用户名"
                autoComplete="off"
                value={form.adminUsername}
                onChange={(event) => patch({ adminUsername: event.currentTarget.value })}
              />
              <NewPasswordFields
                password={form.password}
                confirm={form.confirm}
                onPasswordChange={(password) => patch({ password })}
                onConfirmChange={(confirm) => patch({ confirm })}
                passwordLabel="初始密码"
              />
            </>
          )}
          {open.data && <OpenedHint tenant={open.data} />}
          <FormError error={open.error} />
          <ModalActions submitLabel="开通账套" isSubmitting={open.isPending} canSubmit={canSubmit} onCancel={onClose} />
        </Stack>
      </form>
    </Modal>
  );
}
