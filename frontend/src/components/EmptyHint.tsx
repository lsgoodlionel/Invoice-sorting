import { Stack, Text } from '@mantine/core';
import type { ReactNode } from 'react';

interface EmptyHintProps {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}

export function EmptyHint({ title, description, action }: EmptyHintProps) {
  return (
    <Stack align="center" gap={6} py={48} px="md" style={{ borderTop: '1px dashed var(--paper-line-strong)' }}>
      <Text fw={600}>{title}</Text>
      {description && (
        <Text size="sm" c="dimmed" ta="center" maw={420}>
          {description}
        </Text>
      )}
      {action}
    </Stack>
  );
}
