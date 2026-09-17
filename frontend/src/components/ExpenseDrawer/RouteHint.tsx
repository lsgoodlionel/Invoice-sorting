import { Accordion, ActionIcon, CopyButton, Group, Text, Tooltip } from '@mantine/core';
import { IconCheck, IconCopy } from '@tabler/icons-react';

export function RouteHint({ text }: { text: string }) {
  if (!text.trim()) return null;
  return (
    <Accordion variant="default" chevronPosition="left">
      <Accordion.Item value="route">
        <Accordion.Control>办理路径</Accordion.Control>
        <Accordion.Panel>
          <Group align="flex-start" wrap="nowrap">
            <Text size="sm" style={{ whiteSpace: 'pre-wrap', flex: 1 }}>{text}</Text>
            <CopyButton value={text}>
              {({ copied, copy }) => (
                <Tooltip label={copied ? '已复制' : '复制'}>
                  <ActionIcon variant="subtle" onClick={copy} aria-label="复制办理路径">
                    {copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
                  </ActionIcon>
                </Tooltip>
              )}
            </CopyButton>
          </Group>
        </Accordion.Panel>
      </Accordion.Item>
    </Accordion>
  );
}
