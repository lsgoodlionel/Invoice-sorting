import { Alert } from '@mantine/core';
import { IconAlertTriangle, IconInfoCircle } from '@tabler/icons-react';

export type NoticeTone = 'warning' | 'danger';

const COLORS: Record<NoticeTone, string> = { warning: 'yellow', danger: 'red' };

/** 顶部提示条：黄条提醒、红条阻断，文案一律由后端给出（保证与后端判定一致）。 */
export function NoticeBar({ tone, message, label }: { tone: NoticeTone; message: string; label: string }) {
  if (!message) return null;
  const Icon = tone === 'danger' ? IconAlertTriangle : IconInfoCircle;
  return (
    <Alert
      color={COLORS[tone]}
      variant="light"
      radius={0}
      py={8}
      icon={<Icon size={16} stroke={1.8} />}
      role="status"
      aria-label={label}
      data-testid={`notice-${tone}`}
      styles={{ message: { fontSize: 'var(--mantine-font-size-sm)' } }}
    >
      {message}
    </Alert>
  );
}
