import { Modal, NumberInput, Stack, TextInput } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useState, type FormEvent } from 'react';
import { useCreatePlan, useUpdatePlan } from '../../api/hooks/platform';
import type { Plan } from '../../api/types';
import { FormError } from '../settings/users/FormError';
import { ModalActions } from '../settings/users/ModalActions';

const CODE_PATTERN = /^[A-Za-z0-9_-]{1,30}$/;
const QUOTA_MAX = 1_000_000;

interface PlanForm {
  code: string;
  name: string;
  maxUsers: number;
  maxStorageMb: number;
  maxExpenses: number;
}

function initial(plan?: Plan): PlanForm {
  return {
    code: plan?.code ?? '',
    name: plan?.name ?? '',
    maxUsers: plan?.max_users ?? 0,
    maxStorageMb: plan?.max_storage_mb ?? 0,
    maxExpenses: plan?.max_expenses_per_month ?? 0,
  };
}

/** 新建或修改套餐；代码创建后不可改（账套按代码绑定）。 */
export function PlanModal({ plan, onClose }: { plan?: Plan; onClose: () => void }) {
  const create = useCreatePlan();
  const update = useUpdatePlan();
  const [form, setForm] = useState<PlanForm>(initial(plan));
  const action = plan ? update : create;
  const patch = (next: Partial<PlanForm>) => {
    setForm((current) => ({ ...current, ...next }));
    if (action.error) action.reset();
  };
  const canSubmit = Boolean(plan) || CODE_PATTERN.test(form.code.trim());

  const done = () => {
    notifications.show({ color: 'ink', message: plan ? '已保存套餐' : `已新建套餐「${form.name || form.code}」` });
    onClose();
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit || action.isPending) return;
    const limits = {
      name: form.name.trim() || form.code.trim(),
      max_users: form.maxUsers,
      max_storage_mb: form.maxStorageMb,
      max_expenses_per_month: form.maxExpenses,
    };
    if (plan) update.mutate({ id: plan.id, patch: limits }, { onSuccess: done });
    else create.mutate({ code: form.code.trim(), ...limits }, { onSuccess: done });
  };

  const quota = (label: string, value: number, key: keyof PlanForm) => (
    <NumberInput
      label={label}
      description="0 表示不限制"
      min={0}
      max={QUOTA_MAX}
      value={value}
      onChange={(next) => patch({ [key]: Number(next) || 0 } as Partial<PlanForm>)}
    />
  );

  return (
    <Modal opened onClose={onClose} title={plan ? `编辑套餐：${plan.code}` : '新建套餐'}>
      <form onSubmit={submit} noValidate>
        <Stack gap="sm">
          {!plan && (
            <TextInput
              label="代码"
              description="字母、数字、下划线或连字符，例如 team"
              data-autofocus
              value={form.code}
              onChange={(event) => patch({ code: event.currentTarget.value })}
            />
          )}
          <TextInput label="名称" value={form.name} onChange={(event) => patch({ name: event.currentTarget.value })} />
          {quota('用户数上限', form.maxUsers, 'maxUsers')}
          {quota('存储上限（MB）', form.maxStorageMb, 'maxStorageMb')}
          {quota('每月新增记录上限', form.maxExpenses, 'maxExpenses')}
          <FormError error={action.error} />
          <ModalActions submitLabel={plan ? '保存' : '新建套餐'} isSubmitting={action.isPending} canSubmit={canSubmit} onCancel={onClose} />
        </Stack>
      </form>
    </Modal>
  );
}
