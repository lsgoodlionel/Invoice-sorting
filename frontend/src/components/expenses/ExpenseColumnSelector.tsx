import { Button, Checkbox, Menu, Stack } from '@mantine/core';
import { IconColumns3 } from '@tabler/icons-react';
import { EXPENSE_COLUMN_OPTIONS, type ExpenseColumnKey } from '../../lib/expenseColumns';

export function ExpenseColumnSelector({ value, onChange }: { value: readonly ExpenseColumnKey[]; onChange: (value: ExpenseColumnKey[]) => void }) {
  const toggle = (key: ExpenseColumnKey) => {
    if (value.includes(key)) {
      if (value.length > 1) onChange(value.filter((item) => item !== key));
    } else {
      onChange([...value, key]);
    }
  };
  return (
    <Menu closeOnItemClick={false} position="bottom-end" shadow="md">
      <Menu.Target><Button size="xs" variant="default" leftSection={<IconColumns3 size={14} />}>显示列</Button></Menu.Target>
      <Menu.Dropdown>
        <Stack gap={2} p={6}>
          {EXPENSE_COLUMN_OPTIONS.map((option) => (
            <Checkbox
              key={option.value}
              size="xs"
              label={option.label}
              checked={value.includes(option.value)}
              onChange={() => toggle(option.value)}
            />
          ))}
        </Stack>
      </Menu.Dropdown>
    </Menu>
  );
}
