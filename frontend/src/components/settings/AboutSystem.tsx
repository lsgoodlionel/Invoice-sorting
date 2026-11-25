import { Alert, Anchor, Badge, Button, Group, Paper, Stack, Text, Title } from '@mantine/core';
import { IconDownload, IconExternalLink } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../api/client';

interface AboutInfo {
  name: string;
  version: string;
  deployment: string;
  manual_url: string;
}

export function AboutSystem() {
  const { data, isPending, isError } = useQuery({
    queryKey: ['system-about'],
    queryFn: () => api.get<AboutInfo>('/system/about'),
    staleTime: 5 * 60 * 1000,
  });
  const manualUrl = data?.manual_url ?? '/system-manual.pdf';

  return (
    <Stack gap="lg">
      <Paper withBorder p="lg" radius="md">
        <Stack gap="xs">
          <Group justify="space-between" align="center">
            <Title order={3}>{data?.name ?? '发票账本'}</Title>
            {data && <Badge variant="light">v{data.version}</Badge>}
          </Group>
          <Text size="sm" c="dimmed">收集凭证、跟进报销清单、生成批次资料包并查看统计。</Text>
          {isPending && <Text size="sm">正在读取系统信息…</Text>}
          {isError && <Alert color="red">系统信息读取失败，请稍后刷新页面。</Alert>}
          {data && <Text size="sm">部署形态：{data.deployment} · 当前安装版本：v{data.version}</Text>}
          <Text size="xs" c="dimmed">版本以当前运行的服务为准；说明书随安装包提供，升级后请重新打开本页。</Text>
        </Stack>
      </Paper>
      <Paper withBorder p="lg" radius="md">
        <Stack gap="md">
          <div>
            <Title order={3}>系统操作说明书</Title>
            <Text size="sm" c="dimmed">涵盖功能、用户与管理员操作、安装部署、设置、备份恢复、升级回滚、卸载与故障处理。</Text>
          </div>
          <Group>
            <Button component="a" href={manualUrl} download="发票账本-系统操作说明书.pdf" leftSection={<IconDownload size={16} />}>下载 PDF</Button>
            <Anchor href={manualUrl} target="_blank" rel="noopener noreferrer"><IconExternalLink size={16} /> 在新窗口打开</Anchor>
          </Group>
          <iframe className="system-manual-preview" title="系统操作说明书在线预览" src={`${manualUrl}#toolbar=1`} />
          <Text size="xs" c="dimmed">若浏览器不支持内嵌 PDF，可使用“在新窗口打开”或下载后查看。</Text>
        </Stack>
      </Paper>
    </Stack>
  );
}
