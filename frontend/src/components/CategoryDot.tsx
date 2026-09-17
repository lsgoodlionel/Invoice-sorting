import { Box, Group, Text } from '@mantine/core';

interface CategoryDotProps {
  color: string | null | undefined;
  name?: string | null;
}

const FALLBACK_COLOR = '#B9B1A0';

export function CategoryDot({ color, name }: CategoryDotProps) {
  return (
    <Group gap={6} wrap="nowrap">
      <Box
        aria-hidden
        w={8}
        h={8}
        style={{ borderRadius: '50%', flex: 'none', background: color || FALLBACK_COLOR }}
      />
      {name !== undefined && (
        <Text size="sm" c={name ? undefined : 'dimmed'} truncate>
          {name || '未分类'}
        </Text>
      )}
    </Group>
  );
}
