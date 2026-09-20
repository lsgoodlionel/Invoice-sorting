import { Button, Group, Stack, Table, Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconPackage } from '@tabler/icons-react';
import { useState } from 'react';
import { useDeletePlan, usePlans } from '../../api/hooks/platform';
import type { Plan } from '../../api/types';
import { FormError } from '../settings/users/FormError';
import { PlanModal } from './PlanModal';

const INTRO = '额度填 0 表示不限制。已被账套使用的套餐不能删除，请先给账套改用其他套餐。';

function PlanRow({ plan, onEdit, onDelete }: { plan: Plan; onEdit: (plan: Plan) => void; onDelete: (plan: Plan) => void }) {
  return (
    <Table.Tr data-testid={`plan-row-${plan.code}`}>
      <Table.Td><Text size="sm" span className="num">{plan.code}</Text></Table.Td>
      <Table.Td><Text size="sm">{plan.name}</Text></Table.Td>
      <Table.Td><Text size="sm" className="num">{plan.max_users || '不限'}</Text></Table.Td>
      <Table.Td><Text size="sm" className="num">{plan.max_storage_mb || '不限'}</Text></Table.Td>
      <Table.Td><Text size="sm" className="num">{plan.max_expenses_per_month || '不限'}</Text></Table.Td>
      <Table.Td>
        <Group gap={4} justify="flex-end" wrap="nowrap">
          <Button size="compact-xs" variant="subtle" aria-label={`编辑套餐 ${plan.code}`} onClick={() => onEdit(plan)}>编辑</Button>
          <Button size="compact-xs" variant="subtle" color="red" aria-label={`删除套餐 ${plan.code}`} onClick={() => onDelete(plan)}>删除</Button>
        </Group>
      </Table.Td>
    </Table.Tr>
  );
}

/** 套餐管理：新建、改额度、删除（被引用时后端会明确拒绝）。 */
export function PlanManager() {
  const { data: plans = [], isLoading } = usePlans();
  const remove = useDeletePlan();
  const [editing, setEditing] = useState<Plan | null>(null);
  const [isCreating, setCreating] = useState(false);

  const deletePlan = (plan: Plan) =>
    remove.mutate(plan.id, {
      onSuccess: () => notifications.show({ color: 'ink', message: `已删除套餐「${plan.name || plan.code}」` }),
    });

  return (
    <Stack gap="sm">
      <Group justify="space-between" gap="xs">
        <Text size="xs" c="dimmed">{INTRO}</Text>
        <Button size="xs" variant="filled" leftSection={<IconPackage size={14} stroke={1.6} />} onClick={() => setCreating(true)}>
          新建套餐
        </Button>
      </Group>
      <FormError error={remove.error} />
      {!isLoading && (
        <div className="table-scroll">
          <Table className="ledger-table" miw={680}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>代码</Table.Th>
                <Table.Th>名称</Table.Th>
                <Table.Th>用户数</Table.Th>
                <Table.Th>存储 MB</Table.Th>
                <Table.Th>月记录数</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {plans.map((plan) => (
                <PlanRow key={plan.id} plan={plan} onEdit={setEditing} onDelete={deletePlan} />
              ))}
            </Table.Tbody>
          </Table>
        </div>
      )}
      {isCreating && <PlanModal onClose={() => setCreating(false)} />}
      {editing && <PlanModal plan={editing} onClose={() => setEditing(null)} />}
    </Stack>
  );
}
