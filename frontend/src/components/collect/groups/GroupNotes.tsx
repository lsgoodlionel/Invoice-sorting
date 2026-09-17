import { Badge, Group, Stack, Text } from '@mantine/core';
import { IconAlertTriangle } from '@tabler/icons-react';

interface GroupNotesProps {
  linkReasons: readonly string[];
  warnings: readonly string[];
  problems: readonly string[];
}

/** 关联依据徽标、黄色提醒与红色待处理问题。 */
export function GroupNotes({ linkReasons, warnings, problems }: GroupNotesProps) {
  if (linkReasons.length + warnings.length + problems.length === 0) return null;
  return (
    <Stack gap={4}>
      {linkReasons.length > 0 && (
        <Group gap={4} data-testid="link-reasons">
          <Text size="xs" c="dimmed">关联依据</Text>
          {linkReasons.map((reason) => (
            <Badge key={reason} size="sm" radius="xs" variant="outline" color="ink">{reason}</Badge>
          ))}
        </Group>
      )}
      {warnings.map((warning) => (
        <Text key={warning} size="xs" className="group-warning">
          <IconAlertTriangle size={12} /> {warning}
        </Text>
      ))}
      {problems.map((problem) => (
        <Text key={problem} size="xs" c="red" data-testid="group-problem">{problem}</Text>
      ))}
    </Stack>
  );
}
