import { Alert, Badge, Loader, Stack, Tabs, Title } from '@mantine/core';
import { useState } from 'react';
import { Navigate, useSearchParams } from 'react-router';
import { usePendingApplicationCount } from '../api/hooks/platformSignup';
import { PlatformBackupManager } from '../components/platform/backup/PlatformBackupManager';
import { LicenseManager } from '../components/platform/LicenseManager';
import { MailSettingsManager } from '../components/platform/mail/MailSettingsManager';
import { PlanManager } from '../components/platform/PlanManager';
import { ApplicationManager } from '../components/platform/signup/ApplicationManager';
import { ReferralManager } from '../components/platform/signup/ReferralManager';
import { PlatformOverviewStrip } from '../components/platform/PlatformOverviewStrip';
import { TenantManager } from '../components/platform/TenantManager';
import { usePlatformAccess } from '../components/platform/usePlatformAccess';

const INTRO = '开通与维护账套、套餐与私有化授权，审批注册申请，配置通知邮件，备份平台数据库。这里的操作会影响所有客户，请谨慎。';
const DEFAULT_TAB = 'tenants';
const MAIL_TAB = 'mail';
const TAB_PARAM = 'tab';
/** 允许从地址栏直达的页签（提醒邮件里的链接用 ?tab=applications） */
const TABS = ['tenants', 'plans', 'licenses', 'applications', 'referrals', MAIL_TAB, 'backups'] as const;

/** 「申请」页签：有待审批时显示数量角标。 */
function ApplicationsTab() {
  const pending = usePendingApplicationCount();
  const badge = pending > 0 && (
    <Badge size="xs" color="red" circle aria-label={`${pending} 条待审批`} data-testid="pending-badge">{pending}</Badge>
  );
  return <Tabs.Tab value="applications" rightSection={badge}>申请</Tabs.Tab>;
}

const initialTab = (value: string | null): string =>
  TABS.find((name) => name === value) ?? DEFAULT_TAB;

/** 平台运营后台：仅平台管理员可见，其他账号直接回到记录清单。 */
export function PlatformPage() {
  const { canSeePlatform, isChecking } = usePlatformAccess();
  const [params] = useSearchParams();
  const [tab, setTab] = useState<string>(() => initialTab(params.get(TAB_PARAM)));
  if (isChecking) return <Loader size="sm" m="xl" />;
  if (!canSeePlatform) return <Navigate to="/expenses" replace />;

  return (
    <Stack gap="lg" className="page">
      <Title order={1} className="page-title">平台运营</Title>
      <Alert color="ink" variant="light" py={8}>{INTRO}</Alert>
      <PlatformOverviewStrip />
      <Tabs value={tab} onChange={(value) => setTab(value ?? DEFAULT_TAB)} keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="tenants">账套</Tabs.Tab>
          <Tabs.Tab value="plans">套餐</Tabs.Tab>
          <Tabs.Tab value="licenses">授权</Tabs.Tab>
          <ApplicationsTab />
          <Tabs.Tab value="referrals">推荐</Tabs.Tab>
          <Tabs.Tab value={MAIL_TAB}>邮件</Tabs.Tab>
          <Tabs.Tab value="backups">平台备份</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="tenants" pt="md"><TenantManager /></Tabs.Panel>
        <Tabs.Panel value="plans" pt="md"><PlanManager /></Tabs.Panel>
        <Tabs.Panel value="licenses" pt="md"><LicenseManager /></Tabs.Panel>
        <Tabs.Panel value="applications" pt="md"><ApplicationManager onOpenMail={() => setTab(MAIL_TAB)} /></Tabs.Panel>
        <Tabs.Panel value="referrals" pt="md"><ReferralManager /></Tabs.Panel>
        <Tabs.Panel value={MAIL_TAB} pt="md"><MailSettingsManager /></Tabs.Panel>
        <Tabs.Panel value="backups" pt="md"><PlatformBackupManager /></Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
