import { Input, Modal, SegmentedControl, Select, Stack, Text, TextInput } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useState, type FormEvent } from 'react';
import { usePatchTenant, usePlans } from '../../api/hooks/platform';
import type { PlatformTenant, TenantPatch, TenantStatus } from '../../api/types';
import { FormError } from '../settings/users/FormError';
import { ModalActions } from '../settings/users/ModalActions';

const STATUS_OPTIONS = [
  { value: 'active', label: '启用' },
  { value: 'suspended', label: '停用' },
  { value: 'closed', label: '关闭' },
];

const STATUS_HINT: Record<TenantStatus, string> = {
  active: '正常使用。',
  suspended: '停用后成员只能登录查看与导出，不能新增与修改；随时可恢复。',
  closed: '关闭后不再提供服务，数据保留，可随时导出搬迁。',
};

interface EditForm {
  name: string;
  planCode: string;
  expiresOn: string;
  status: TenantStatus;
}

function toPatch(tenant: PlatformTenant, form: EditForm): TenantPatch {
  const expires = form.expiresOn || null;
  const plan = form.planCode || null;
  return {
    ...(form.name.trim() !== tenant.name ? { name: form.name.trim() } : {}),
    ...(plan !== (tenant.plan?.code ?? null) ? { plan_code: plan } : {}),
    ...(expires !== tenant.expires_on ? { expires_on: expires } : {}),
    ...(form.status !== tenant.status ? { status: form.status } : {}),
  };
}

/** 修改账套：改名、改套餐与到期日、停用恢复与关闭。 */
export function EditTenantModal({ tenant, onClose }: { tenant: PlatformTenant; onClose: () => void }) {
  const update = usePatchTenant();
  const { data: plans = [] } = usePlans();
  const [form, setForm] = useState<EditForm>({
    name: tenant.name,
    planCode: tenant.plan?.code ?? '',
    expiresOn: tenant.expires_on ?? '',
    status: tenant.status,
  });
  const patch = (next: Partial<EditForm>) => {
    setForm((current) => ({ ...current, ...next }));
    if (update.error) update.reset();
  };
  const changes = toPatch(tenant, form);
  const canSubmit = Boolean(form.name.trim()) && Object.keys(changes).length > 0;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit || update.isPending) return;
    update.mutate(
      { slug: tenant.slug, patch: changes },
      {
        onSuccess: () => {
          notifications.show({ color: 'ink', message: `已保存账套「${tenant.slug}」的修改` });
          onClose();
        },
      },
    );
  };

  return (
    <Modal opened onClose={onClose} title={`编辑账套：${tenant.slug}`}>
      <form onSubmit={submit} noValidate>
        <Stack gap="sm">
          <TextInput label="名称" data-autofocus value={form.name} onChange={(event) => patch({ name: event.currentTarget.value })} />
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
          <Input.Wrapper label="状态">
            <div>
              <SegmentedControl
                mt={4}
                size="xs"
                data={STATUS_OPTIONS}
                value={form.status}
                onChange={(value) => patch({ status: value as TenantStatus })}
              />
              <Text size="xs" c="dimmed" mt={4}>{STATUS_HINT[form.status]}</Text>
            </div>
          </Input.Wrapper>
          <FormError error={update.error} />
          <ModalActions submitLabel="保存" isSubmitting={update.isPending} canSubmit={canSubmit} onCancel={onClose} />
        </Stack>
      </form>
    </Modal>
  );
}
