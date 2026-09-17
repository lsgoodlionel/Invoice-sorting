import { Button, Checkbox, Group, Stack, Table, Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useState } from 'react';
import { useApplyReclassify, useReclassifyPreview, type ReclassifyItem } from '../../api/hooks/reclassify';
import { formatCents } from '../../lib/money';

interface SuggestionTableProps {
  items: readonly ReclassifyItem[];
  selected: ReadonlySet<number>;
  onToggle: (expenseId: number) => void;
}

function SuggestionTable({ items, selected, onToggle }: SuggestionTableProps) {
  return (
    <Table className="ledger-table">
      <Table.Thead>
        <Table.Tr>
          <Table.Th w={40} />
          <Table.Th>日期</Table.Th>
          <Table.Th>商家 · 摘要</Table.Th>
          <Table.Th ta="right">金额</Table.Th>
          <Table.Th>分类</Table.Th>
          <Table.Th>依据</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {items.map((item) => (
          <Table.Tr key={item.expense_id} data-testid={`reclassify-row-${item.expense_id}`}>
            <Table.Td>
              <Checkbox
                aria-label={`改正 #${item.expense_id}`}
                checked={selected.has(item.expense_id)}
                onChange={() => onToggle(item.expense_id)}
              />
            </Table.Td>
            <Table.Td className="num">{item.spent_on}</Table.Td>
            <Table.Td>
              <Text size="sm" truncate maw={320}>{item.merchant}</Text>
              <Text size="xs" c="dimmed" truncate maw={320}>{item.summary}</Text>
            </Table.Td>
            <Table.Td ta="right" className="num">{formatCents(item.amount_cents)}</Table.Td>
            <Table.Td><Text size="sm">{`${item.current_category_name || '未分类'} → ${item.suggested_category_name}`}</Text></Table.Td>
            <Table.Td><Text size="xs" c="dimmed">{item.basis}</Text></Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  );
}

/** 按最新分类规则检查已有记录，管理员勾选确认后批量改正（不写入分类记忆）。 */
export function ReclassifySection() {
  const [includeSent, setIncludeSent] = useState(false);
  const [items, setItems] = useState<readonly ReclassifyItem[] | null>(null);
  const [selected, setSelected] = useState<ReadonlySet<number>>(new Set());
  const preview = useReclassifyPreview();
  const apply = useApplyReclassify();

  const check = () =>
    preview.mutate(includeSent, {
      onSuccess: (result) => {
        setItems(result);
        setSelected(new Set(result.map((item) => item.expense_id)));
      },
    });

  const toggle = (expenseId: number) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(expenseId)) next.delete(expenseId);
      else next.add(expenseId);
      return next;
    });

  const submit = () => {
    const changes = (items ?? [])
      .filter((item) => selected.has(item.expense_id))
      .map((item) => ({ expense_id: item.expense_id, category_id: item.suggested_category_id }));
    apply.mutate(changes, {
      onSuccess: ({ updated }) => {
        notifications.show({ color: 'ink', message: `已改正 ${updated} 条记录的分类` });
        setItems((current) => (current ?? []).filter((item) => !selected.has(item.expense_id)));
        setSelected(new Set());
      },
    });
  };

  return (
    <Stack gap="sm">
      <Text size="sm" c="dimmed">
        分类规则调整后（如新增“图书”分类、修正商家记忆），用最新规则检查已有记录。只列出依据可靠（文件名分类词、发票税收分类、手动修改过的商品）或尚未分类的建议，勾选确认后改正。
      </Text>
      <Group gap="md">
        <Checkbox label="包含已外发、已报销的记录" checked={includeSent} onChange={(event) => setIncludeSent(event.currentTarget.checked)} />
        <Button variant="outline" loading={preview.isPending} onClick={check}>检查分类</Button>
        {items && items.length > 0 && (
          <Button disabled={selected.size === 0} loading={apply.isPending} onClick={submit}>
            {`改正所选 ${selected.size} 条`}
          </Button>
        )}
      </Group>
      {items && items.length === 0 && <Text size="sm">所有记录的分类都与最新规则一致</Text>}
      {items && items.length > 0 && <SuggestionTable items={items} selected={selected} onToggle={toggle} />}
    </Stack>
  );
}
