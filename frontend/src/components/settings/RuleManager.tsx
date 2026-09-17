import { Badge, Button, Group, Stack, Table, Text } from '@mantine/core';
import { modals } from '@mantine/modals';
import { useState } from 'react';
import { useCategories, useChecklistRules, useRemoveRule } from '../../api/hooks/settings';
import type { ChecklistRule } from '../../api/types';
import { describeCondition } from '../../lib/rules';
import { ATTACHMENT_KIND_LABELS } from '../../lib/status';
import { RuleModal } from './RuleModal';

/** readOnly：非管理员只读，隐藏新增、编辑与删除。 */
export function RuleManager({ readOnly = false }: { readOnly?: boolean }) {
  const { data: rules = [] } = useChecklistRules();
  const { data: categories = [] } = useCategories();
  const remove = useRemoveRule();
  const [editing, setEditing] = useState<ChecklistRule | 'new' | null>(null);
  const categoryName = (id: number | null) => (id === null ? '通用' : (categories.find((c) => c.id === id)?.name ?? `#${id}`));
  const confirmRemove = (rule: ChecklistRule) =>
    modals.openConfirmModal({
      title: '删除规则',
      children: <Text size="sm">删除后相关记录的凭证清单会重新计算。</Text>,
      labels: { confirm: '删除', cancel: '取消' },
      confirmProps: { color: 'red' },
      onConfirm: () => remove.mutate(rule.id),
    });
  return (
    <Stack gap="xs">
      <Group justify="space-between">
        <Text size="xs" c="dimmed">规则只做提醒，以学校现行规定为准。</Text>
        {!readOnly && <Button size="xs" variant="outline" onClick={() => setEditing('new')}>新增规则</Button>}
      </Group>
      <div className="table-scroll">
        <Table className="ledger-table" miw={720}>
          <Table.Thead><Table.Tr><Table.Th>分类</Table.Th><Table.Th>附件类型</Table.Th><Table.Th>级别</Table.Th><Table.Th>条件</Table.Th><Table.Th>提示</Table.Th><Table.Th /></Table.Tr></Table.Thead>
          <Table.Tbody>
            {rules.map((rule) => (
              <Table.Tr key={rule.id}>
                <Table.Td>{categoryName(rule.category_id)}</Table.Td>
                <Table.Td>{ATTACHMENT_KIND_LABELS[rule.attachment_kind]}</Table.Td>
                <Table.Td><Badge size="sm" variant={rule.level === 'required' ? 'light' : 'outline'} color={rule.level === 'required' ? 'ink' : 'gray'}>{rule.level === 'required' ? '必需' : '建议'}</Badge></Table.Td>
                <Table.Td><Text size="xs" className="num">{describeCondition(rule.condition)}</Text></Table.Td>
                <Table.Td><Text size="xs" c="dimmed" truncate maw={240} title={rule.hint}>{rule.hint}</Text></Table.Td>
                <Table.Td>
                  {!readOnly && (
                    <Group gap={4} justify="flex-end" wrap="nowrap">
                      <Button size="compact-xs" variant="subtle" onClick={() => setEditing(rule)}>编辑</Button>
                      <Button size="compact-xs" variant="subtle" color="red" onClick={() => confirmRemove(rule)}>删除</Button>
                    </Group>
                  )}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </div>
      <RuleModal editing={editing} onClose={() => setEditing(null)} />
    </Stack>
  );
}
