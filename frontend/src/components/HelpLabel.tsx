import { Group, Tooltip } from '@mantine/core';
import { IconHelpCircle } from '@tabler/icons-react';

const TOOLTIP_WIDTH = 280;

/** 表头/标签旁带问号说明。 */
export function HelpLabel({ label, help }: { label: string; help: string }) {
  return (
    <Group gap={4} wrap="nowrap" component="span">
      {label}
      <Tooltip label={help} multiline w={TOOLTIP_WIDTH} withArrow>
        <span role="img" aria-label={`${label}说明`} tabIndex={0} style={{ display: 'inline-flex', cursor: 'help' }}>
          <IconHelpCircle size={14} stroke={1.6} />
        </span>
      </Tooltip>
    </Group>
  );
}
