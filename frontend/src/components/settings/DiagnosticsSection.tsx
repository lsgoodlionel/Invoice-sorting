import { Alert, Badge, Button, Checkbox, Group, Stack, Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconAlertTriangle } from '@tabler/icons-react';
import { useState } from 'react';
import {
  useCollectDiagnostics,
  useDiagnosticsStatus,
  type DiagnosticsReport,
  type DiagnosticsStatus,
} from '../../api/hooks/diagnostics';

const KIB = 1024;

function formatSize(bytes: number): string {
  if (bytes < KIB) return `${bytes} B`;
  if (bytes < KIB * KIB) return `${Math.round(bytes / KIB)} KB`;
  return `${(bytes / KIB / KIB).toFixed(1)} MB`;
}

function UploadBadge({ status }: { status: DiagnosticsStatus }) {
  if (!status.upload_enabled) return <Badge variant="light" color="gray">不上传（只存本机）</Badge>;
  return <Badge variant="light" color="ink">{`自动上传到 ${status.repo}`}</Badge>;
}

function LastPackage({ report }: { report: DiagnosticsReport }) {
  return (
    <Stack gap={2}>
      <Text size="sm">
        {`最近一次：${report.package}（${formatSize(report.size)}）`}
        {report.fingerprint && ` · 故障指纹 ${report.fingerprint}`}
      </Text>
      {report.message && <Text size="xs" c="dimmed">{report.message}</Text>}
      {report.repo_path && <Text size="xs" c="dimmed">{`仓库内路径：${report.repo_path}`}</Text>}
      {report.residue.length > 0 && (
        <Alert color="red" variant="light" icon={<IconAlertTriangle size={16} />}>
          {`自检发现疑似未脱敏内容（${report.residue.join('、')}），已拒绝上传，请联系开发人员。`}
        </Alert>
      )}
    </Stack>
  );
}

/**
 * 生成脱敏诊断包（仅管理员）。
 *
 * 默认只保存在服务器本机；只有服务端配置了日志仓库与令牌时，“同时上传”才可勾选。
 */
export function DiagnosticsSection() {
  const [shouldUpload, setShouldUpload] = useState(false);
  const { data: status } = useDiagnosticsStatus();
  const collect = useCollectDiagnostics();

  const submit = () =>
    collect.mutate(
      { upload: shouldUpload && Boolean(status?.upload_enabled) },
      {
        onSuccess: (report) =>
          notifications.show({ color: 'ink', title: '诊断包已生成', message: report.package }),
      },
    );

  return (
    <Stack gap="sm">
      <Text size="sm" c="dimmed">
        服务出问题时生成一个诊断包交给开发：里面是版本、系统与磁盘信息、日志尾部，以及环境变量的名字和“已设置/未设置”。
        邮箱、手机号、证件号、卡号、发票号、金额、商家与人名、密钥令牌密码都会替换成占位符，打包后还会再自检一遍。
      </Text>
      <Group gap="md">
        <Button variant="outline" loading={collect.isPending} onClick={submit}>
          生成诊断包
        </Button>
        <Checkbox
          label="同时上传到日志仓库"
          disabled={!status?.upload_enabled}
          checked={shouldUpload && Boolean(status?.upload_enabled)}
          onChange={(event) => setShouldUpload(event.currentTarget.checked)}
        />
        {status && <UploadBadge status={status} />}
      </Group>
      {status && <Text size="xs" c="dimmed">{`日志文件：${status.log_file}`}</Text>}
      {status?.last && <LastPackage report={status.last} />}
    </Stack>
  );
}
