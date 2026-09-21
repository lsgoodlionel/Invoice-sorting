import { Divider, Group, Stack, Text, Title } from '@mantine/core';
import { IconLock } from '@tabler/icons-react';
import type { ReactNode } from 'react';
import { useCurrentUser } from '../components/auth/CurrentUserContext';
import { CategoryManager } from '../components/settings/CategoryManager';
import { DiagnosticsSection } from '../components/settings/DiagnosticsSection';
import { GeneralSettings } from '../components/settings/GeneralSettings';
import { LedgerTransferSection } from '../components/settings/ledger/LedgerTransferSection';
import { ProjectManager } from '../components/settings/ProjectManager';
import { ReclassifySection } from '../components/settings/ReclassifySection';
import { RuleManager } from '../components/settings/RuleManager';
import { SecuritySettings } from '../components/settings/SecuritySettings';
import { UserManager } from '../components/settings/users/UserManager';

function Section({ label, isReadOnly = false, children }: { label: string; isReadOnly?: boolean; children: ReactNode }) {
  return (
    <Stack gap="xs">
      <Divider label={<span className="section-label">{label}</span>} labelPosition="left" />
      {isReadOnly && (
        <Group gap={4} c="dimmed">
          <IconLock size={12} stroke={1.6} aria-hidden="true" />
          <Text size="xs">仅管理员可修改</Text>
        </Group>
      )}
      {children}
    </Stack>
  );
}

/** 系统设置（基本、分类、凭证清单规则、备份、账本搬迁）仅管理员可改；经费项目与登录安全所有人可用。 */
export function SettingsPage() {
  const { isAdmin } = useCurrentUser();
  const isReadOnly = !isAdmin;
  return (
    <Stack gap="xl" className="page">
      <Title order={1} className="page-title">设置</Title>
      <Section label="基本" isReadOnly={isReadOnly}><GeneralSettings readOnly={isReadOnly} /></Section>
      <Section label="分类" isReadOnly={isReadOnly}><CategoryManager readOnly={isReadOnly} /></Section>
      <Section label="经费项目"><ProjectManager /></Section>
      <Section label="凭证清单规则" isReadOnly={isReadOnly}><RuleManager readOnly={isReadOnly} /></Section>
      {isAdmin && <Section label="分类整理"><ReclassifySection /></Section>}
      {isAdmin && <Section label="用户管理"><UserManager /></Section>}
      {isAdmin && <Section label="账本搬迁"><LedgerTransferSection /></Section>}
      {isAdmin && <Section label="运行日志与诊断"><DiagnosticsSection /></Section>}
      <Section label="登录与安全"><SecuritySettings /></Section>
    </Stack>
  );
}
