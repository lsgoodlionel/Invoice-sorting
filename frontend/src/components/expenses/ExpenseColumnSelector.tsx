import { ActionIcon, Button, Checkbox, Group, Menu, Stack, Text } from '@mantine/core';
import { IconArrowDown, IconArrowUp, IconColumns3 } from '@tabler/icons-react';
import { useEffect, useState } from 'react';
import { DEFAULT_EXPENSE_TABLE_PREFERENCES, EXPENSE_COLUMN_OPTIONS, type ExpenseColumnKey, type ExpenseTablePreferences } from '../../lib/expenseColumns';

export function ExpenseColumnSelector({ value, onSave }: { value: ExpenseTablePreferences; onSave: (value: ExpenseTablePreferences) => void }) {
  const [draft, setDraft] = useState<ExpenseTablePreferences>(value);
  useEffect(() => setDraft(value), [value]);
  const toggle = (key: ExpenseColumnKey) => {
    if (draft.visible.includes(key)) {
      if (draft.visible.length > 1) setDraft({ ...draft, visible: draft.visible.filter((item) => item !== key) });
    } else {
      setDraft({ ...draft, visible: [...draft.visible, key] });
    }
  };
  const move = (index: number, offset: -1 | 1) => {
    const target = index + offset;
    if (target < 0 || target >= draft.order.length) return;
    const order = [...draft.order];
    [order[index], order[target]] = [order[target], order[index]];
    setDraft({ ...draft, order });
  };
  const labels = Object.fromEntries(EXPENSE_COLUMN_OPTIONS.map((item) => [item.value, item.label])) as Record<ExpenseColumnKey, string>;
  return (
    <Menu closeOnItemClick={false} position="bottom-end" shadow="md">
      <Menu.Target><Button size="xs" variant="default" leftSection={<IconColumns3 size={14} />}>列设置</Button></Menu.Target>
      <Menu.Dropdown>
        <Stack gap={4} p={6} miw={260}>
          <Text size="xs" c="dimmed">勾选显示；上下调整排列。拖动表头右边缘调整列宽。</Text>
          {draft.order.map((key, index) => (
            <Group key={key} gap={4} wrap="nowrap">
              <Checkbox size="xs" label={labels[key]} checked={draft.visible.includes(key)} onChange={() => toggle(key)} style={{ flex: 1 }} />
              <ActionIcon size="xs" variant="subtle" aria-label={`上移${labels[key]}`} disabled={index === 0} onClick={() => move(index, -1)}><IconArrowUp size={13} /></ActionIcon>
              <ActionIcon size="xs" variant="subtle" aria-label={`下移${labels[key]}`} disabled={index === draft.order.length - 1} onClick={() => move(index, 1)}><IconArrowDown size={13} /></ActionIcon>
            </Group>
          ))}
          <Group justify="space-between" mt={4}>
            <Button size="xs" variant="subtle" onClick={() => setDraft({ ...DEFAULT_EXPENSE_TABLE_PREFERENCES, order: [...DEFAULT_EXPENSE_TABLE_PREFERENCES.order], visible: [...DEFAULT_EXPENSE_TABLE_PREFERENCES.visible], widths: { ...DEFAULT_EXPENSE_TABLE_PREFERENCES.widths } })}>恢复默认</Button>
            <Button size="xs" onClick={() => onSave(draft)}>保存设置</Button>
          </Group>
        </Stack>
      </Menu.Dropdown>
    </Menu>
  );
}
