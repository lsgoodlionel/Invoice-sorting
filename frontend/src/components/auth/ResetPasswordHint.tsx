import { ActionIcon, CopyButton, Group, Stack, Text, Tooltip } from '@mantine/core';
import { IconCheck, IconCopy } from '@tabler/icons-react';

const RESET_COMMANDS = [
  {
    label: '服务器',
    command:
      'sudo -u invoice env INVOICE_SORTING_DATA_DIR=/var/lib/invoice-sorting /opt/invoice-sorting/app/backend/.venv/bin/invoice-sorting reset-password',
  },
  { label: '本机运行', command: 'backend/.venv/bin/invoice-sorting reset-password' },
] as const;

const COPIED_TIMEOUT_MS = 1500;

function CommandLine({ label, command }: { label: string; command: string }) {
  return (
    <Stack gap={2}>
      <Text size="xs" c="dimmed">
        {label}：
      </Text>
      <Group gap={6} wrap="nowrap" align="flex-start">
        <code className="auth-command">{command}</code>
        <CopyButton value={command} timeout={COPIED_TIMEOUT_MS}>
          {({ copied, copy }) => (
            <Tooltip label={copied ? '已复制' : '复制'} withArrow>
              <ActionIcon variant="subtle" color={copied ? 'ink' : 'gray'} onClick={copy} aria-label={copied ? `已复制${label}命令` : `复制${label}命令`}>
                {copied ? <IconCheck size={14} /> : <IconCopy size={14} />}
              </ActionIcon>
            </Tooltip>
          )}
        </CopyButton>
      </Group>
    </Stack>
  );
}

export function ResetPasswordHint() {
  return (
    <Stack gap={6} className="auth-footnote">
      <Text size="xs" c="dimmed">
        忘记密码请联系管理员重置；管理员 admin 忘记密码时在服务器执行：
      </Text>
      {RESET_COMMANDS.map((item) => (
        <CommandLine key={item.label} label={item.label} command={item.command} />
      ))}
    </Stack>
  );
}
