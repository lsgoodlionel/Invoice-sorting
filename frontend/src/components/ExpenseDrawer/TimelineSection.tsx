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

/** 状态未变的事件（如“并入交通票 ¥xx，金额更新为 ¥yy”）以备注为正文。 */
function EventText({ event }: { event: StatusEvent }) {
  const isNoteOnly = event.from_status === event.to_status && Boolean(event.note);
  if (isNoteOnly) {
    return (
      <Text size="sm" className="timeline-note num">
        {event.note}
        <Text span size="xs" c="dimmed">{eventSource(event)}</Text>
      </Text>
    );
  }
  return (
    <Text size="sm">
      {event.from_status ? `${STATUS_META[event.from_status].label} → ` : '创建 → '}
      {STATUS_META[event.to_status].label}
      <Text span size="xs" c="dimmed">{eventSource(event)}</Text>
      {event.note && <Text span size="xs" c="dimmed"> {event.note}</Text>}
    </Text>
  );
}

export function TimelineSection({ events }: { events: readonly StatusEvent[] }) {
  if (events.length === 0) return <Text size="sm" c="dimmed">暂无记录</Text>;
  return (
    <Stack gap={4}>
      {events.map((event) => (
        <Group key={event.id} gap="sm" wrap="nowrap" align="baseline" data-testid={`timeline-event-${event.id}`}>
          <Text size="xs" c="dimmed" className="num" w={110}>{dayjs(event.at).format('YYYY-MM-DD HH:mm')}</Text>
          <EventText event={event} />
        </Group>
      ))}
    </Stack>
  );
}
