import { Badge, Group, Stack, Text } from '@mantine/core';
import type { ReactNode } from 'react';
import type { PlatformApplication } from '../../../api/signupTypes';
import {
  APPLICATION_STATUS_COLORS,
  APPLICATION_STATUS_LABELS,
  MAIL_STATUS_LABELS,
  formatDateTime,
} from '../../../lib/signup';

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Group gap="md" align="flex-start" wrap="nowrap">
      <Text size="xs" c="dimmed" w={88} style={{ flex: 'none' }}>{label}</Text>
      <div style={{ minWidth: 0, flex: 1 }}>{children}</div>
    </Group>
  );
}

function referrerText(application: PlatformApplication): string {
  const referrer = application.referrer;
  if (!referrer) return '无（自行申请）';
  const auto = application.is_auto_approved ? '，直接注册' : '';
  return `由 ${referrer.display_name}（${referrer.username}）推荐${auto}`;
}

function reviewText(application: PlatformApplication): string {
  if (!application.reviewed_at) return '—';
  return `${application.reviewer?.display_name ?? '系统'} · ${formatDateTime(application.reviewed_at)}`;
}

function tenantText(application: PlatformApplication): string | null {
  if (application.tenant) return `${application.tenant.name}（${application.tenant.slug}）已开通`;
  const plan = application.approved;
  if (!plan) return null;
  const extra = [plan.plan_code, plan.expires_on && `到期 ${plan.expires_on}`].filter(Boolean).join(' · ');
  return `${plan.name}（${plan.slug}）${extra ? ` · ${extra}` : ''}`;
}

/** 申请的全部资料（仅平台管理员可见）。 */
export function ApplicationDetails({ application }: { application: PlatformApplication }) {
  const tenant = tenantText(application);
  return (
    <Stack gap={8} data-testid="application-details">
      <Row label="申请编号"><Text size="sm" className="num">{application.number}</Text></Row>
      <Row label="状态">
        <Badge size="sm" variant="light" color={APPLICATION_STATUS_COLORS[application.status]}>
          {APPLICATION_STATUS_LABELS[application.status]}
        </Badge>
      </Row>
      <Row label="姓名"><Text size="sm">{application.name}</Text></Row>
      <Row label="邮箱"><Text size="sm" className="num">{application.email}</Text></Row>
      <Row label="单位或身份"><Text size="sm">{application.identity}</Text></Row>
      <Row label="使用需求"><Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>{application.needs}</Text></Row>
      <Row label="期望账本名称"><Text size="sm">{application.ledger_name || '—'}</Text></Row>
      <Row label="推荐人"><Text size="sm">{referrerText(application)}</Text></Row>
      <Row label="提交时间"><Text size="sm" className="num">{formatDateTime(application.created_at)}</Text></Row>
      <Row label="审批"><Text size="sm">{reviewText(application)}</Text></Row>
      {tenant && <Row label="账套"><Text size="sm">{tenant}</Text></Row>}
      {application.code_expires_at && application.status === 'approved' && (
        <Row label="链接有效期"><Text size="sm" className="num">{formatDateTime(application.code_expires_at)}</Text></Row>
      )}
      {application.reject_reason && <Row label="否决原因"><Text size="sm">{application.reject_reason}</Text></Row>}
      {application.status !== 'pending' && (
        <Row label="通知邮件">
          <Text size="sm">{MAIL_STATUS_LABELS[application.mail_status]}</Text>
          {application.mail_error && <Text size="xs" c="red.7">{application.mail_error}</Text>}
        </Row>
      )}
      {application.is_purged && <Row label="资料"><Text size="sm" c="dimmed">已按规定清除</Text></Row>}
    </Stack>
  );
}
