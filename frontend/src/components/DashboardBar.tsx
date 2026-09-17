import { Group, Text, UnstyledButton } from '@mantine/core';
import { IconAlertTriangle, IconClockExclamation, IconFileAlert, IconPaperclip } from '@tabler/icons-react';
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router';
import { useDashboard } from '../api/hooks/dashboard';
import { expensesLink } from '../lib/expenseFilters';

interface ReminderProps {
  icon: ReactNode;
  label: string;
  count: number;
  onClick: () => void;
}

function Reminder({ icon, label, count, onClick }: ReminderProps) {
  if (count === 0) return null;
  return (
    <UnstyledButton onClick={onClick} className="reminder" aria-label={`${label} ${count}`}>
      <Group gap={6} wrap="nowrap">
        {icon}
        <Text size="sm">{label}</Text>
        <Text size="sm" fw={700} className="num">
          {count}
        </Text>
      </Group>
    </UnstyledButton>
  );
}

/** 顶部提醒条：缺项、超期未到账、久未开票、待归属附件。 */
export function DashboardBar() {
  const navigate = useNavigate();
  const { data } = useDashboard();
  if (!data) return null;
  const total =
    data.missing.length + data.overdue.length + data.spent_without_invoice.length + data.unassigned_count;
  if (total === 0) {
    return (
      <Text size="sm" c="dimmed">
        暂无待办提醒
      </Text>
    );
  }
  const firstOverdue = data.overdue[0];
  return (
    <Group gap="lg" wrap="nowrap" style={{ overflowX: 'auto' }}>
      <Reminder
        icon={<IconAlertTriangle size={16} color="var(--mantine-color-orange-7)" />}
        label="凭证缺项"
        count={data.missing.length}
        onClick={() => navigate(expensesLink({ missingOnly: true }))}
      />
      <Reminder
        icon={<IconClockExclamation size={16} color="var(--mantine-color-red-7)" />}
        label="超期未到账批次"
        count={data.overdue.length}
        onClick={() => navigate(firstOverdue ? `/batches?id=${firstOverdue.id}` : '/batches')}
      />
      <Reminder
        icon={<IconFileAlert size={16} color="var(--mantine-color-paper-7)" />}
        label="已支出久未开票"
        count={data.spent_without_invoice.length}
        onClick={() => navigate(expensesLink({ statuses: ['spent'] }))}
      />
      <Reminder
        icon={<IconPaperclip size={16} color="var(--mantine-color-ink-6)" />}
        label="待归属附件"
        count={data.unassigned_count}
        onClick={() => navigate('/collect#unassigned')}
      />
    </Group>
  );
}
