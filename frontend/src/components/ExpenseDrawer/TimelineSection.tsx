import { Group, Stack, Text } from '@mantine/core';
import dayjs from 'dayjs';
import type { StatusEvent } from '../../api/types';
import { eventActorLabel } from '../../lib/operator';
import { STATUS_META } from '../../lib/status';

/** “（手动 · 张三）”“（自动 · 系统）” */
function eventSource(event: StatusEvent): string {
  const mode = event.is_manual ? '手动' : '自动';
  const actor = eventActorLabel(event);
  return actor ? `（${mode} · ${actor}）` : `（${mode}）`;
}

export function TimelineSection({ events }: { events: readonly StatusEvent[] }) {
  if (events.length === 0) return <Text size="sm" c="dimmed">暂无记录</Text>;
  return (
    <Stack gap={4}>
      {events.map((event) => (
        <Group key={event.id} gap="sm" wrap="nowrap" align="baseline">
          <Text size="xs" c="dimmed" className="num" w={110}>{dayjs(event.at).format('YYYY-MM-DD HH:mm')}</Text>
          <Text size="sm">
            {event.from_status ? `${STATUS_META[event.from_status].label} → ` : '创建 → '}
            {STATUS_META[event.to_status].label}
            <Text span size="xs" c="dimmed">{eventSource(event)}</Text>
            {event.note && <Text span size="xs" c="dimmed"> {event.note}</Text>}
          </Text>
        </Group>
      ))}
    </Stack>
  );
}
