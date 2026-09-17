import { Button, Divider, Group, Stack, Text } from '@mantine/core';
import { IconPlus } from '@tabler/icons-react';
import type { ExpenseSummary } from '../../api/types';
import { BatchExpensesTable } from './BatchExpensesTable';

interface BatchItemsSectionProps {
  expenses: readonly ExpenseSummary[];
  count: number;
  isDraft: boolean;
  onAdd: () => void;
  onOpen: (id: number) => void;
  onRemove: (id: number) => void;
}

function BatchItemsEmpty({ isDraft, onAdd }: { isDraft: boolean; onAdd: () => void }) {
  return (
    <Stack align="center" gap={8} py={36} px="md" data-testid="batch-items-empty" style={{ borderTop: '1px dashed var(--paper-line-strong)' }}>
      <Text fw={600}>批次里还没有记录</Text>
      {isDraft && (
        <Button variant="filled" leftSection={<IconPlus size={14} />} onClick={onAdd}>添加记录</Button>
      )}
      <Text size="sm" c="dimmed" ta="center">也可以在清单页勾选记录后点『加入批次』</Text>
    </Stack>
  );
}

/** 批次“记录”分区：标题旁“添加记录”（草稿且非空时），空批次显示引导。 */
export function BatchItemsSection({ expenses, count, isDraft, onAdd, onOpen, onRemove }: BatchItemsSectionProps) {
  const isEmpty = expenses.length === 0;
  return (
    <Stack gap="xs">
      <Group gap="sm" wrap="nowrap">
        <Divider style={{ flex: 1 }} label={<span className="section-label">记录 {count}</span>} labelPosition="left" />
        {isDraft && !isEmpty && (
          <Button size="xs" variant="light" leftSection={<IconPlus size={12} />} onClick={onAdd}>添加记录</Button>
        )}
      </Group>
      {isEmpty ? (
        <BatchItemsEmpty isDraft={isDraft} onAdd={onAdd} />
      ) : (
        <BatchExpensesTable expenses={expenses} canRemove={isDraft} onOpen={onOpen} onRemove={onRemove} />
      )}
    </Stack>
  );
}
