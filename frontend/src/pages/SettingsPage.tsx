import { Box, Group, Stack, Text, Title } from '@mantine/core';
import { IconLock } from '@tabler/icons-react';
import type { ReactNode } from 'react';
import { useSearchParams } from 'react-router';
import { useAuthStatus } from '../api/hooks/auth';
import { useCurrentUser } from '../components/auth/CurrentUserContext';
import { CategoryManager } from '../components/settings/CategoryManager';
import { DiagnosticsSection } from '../components/settings/DiagnosticsSection';
import { GeneralSettings } from '../components/settings/GeneralSettings';
import { LedgerTransferSection } from '../components/settings/ledger/LedgerTransferSection';
import { ProjectManager } from '../components/settings/ProjectManager';
import { ReferralSection } from '../components/settings/referral/ReferralSection';
import { ReclassifySection } from '../components/settings/ReclassifySection';
import { RuleManager } from '../components/settings/RuleManager';
import { SecuritySettings } from '../components/settings/SecuritySettings';
import { SettingsSelectNav, SettingsSideNav } from '../components/settings/SettingsNav';
import { UserManager } from '../components/settings/users/UserManager';
import {
  resolveSection,
  visibleSections,
  type SettingsSectionDef,
  type SettingsSectionKey,
} from '../lib/settingsSections';

const SECTION_PARAM = 'section';

function renderSection(key: SettingsSectionKey, isReadOnly: boolean): ReactNode {
  switch (key) {
    case 'general': return <GeneralSettings readOnly={isReadOnly} />;
    case 'categories': return <CategoryManager readOnly={isReadOnly} />;
    case 'projects': return <ProjectManager />;
    case 'rules': return <RuleManager readOnly={isReadOnly} />;
    case 'reclassify': return <ReclassifySection />;
    case 'users': return <UserManager />;
    case 'referral': return <ReferralSection />;
    case 'security': return <SecuritySettings />;
    case 'ledger': return <LedgerTransferSection />;
    case 'diagnostics': return <DiagnosticsSection />;
  }
}

function SectionHeader({ section, isReadOnly }: { section: SettingsSectionDef; isReadOnly: boolean }) {
  return (
    <Stack gap={4} className="settings-section-header">
      <Title order={2} id={`settings-${section.key}`} className="settings-section-title">{section.label}</Title>
      <Text size="sm" c="dimmed">{section.description}</Text>
      {isReadOnly && section.isAdminEditable && (
        <Group gap={4} c="dimmed">
          <IconLock size={12} stroke={1.6} aria-hidden="true" />
          <Text size="xs">仅管理员可修改</Text>
        </Group>
      )}
    </Stack>
  );
}

/**
 * 设置：左侧分组导航（窄屏为下拉），右侧一次只显示一个分区；当前分区记在地址栏 ?section=。
 * 系统设置仅管理员可改；经费项目与登录安全所有人可用；推荐好友只在多账套部署出现。
 */
export function SettingsPage() {
  const { isAdmin, user } = useCurrentUser();
  const { data: status } = useAuthStatus();
  const [params, setParams] = useSearchParams();
  const canRefer = Boolean(status?.multi_tenant && status.auth_enabled && user);
  const sections = visibleSections({ isAdmin, canRefer });
  const active = resolveSection(params.get(SECTION_PARAM), sections);
  const isReadOnly = !isAdmin;

  const select = (key: SettingsSectionKey) =>
    setParams((current) => {
      const next = new URLSearchParams(current);
      next.set(SECTION_PARAM, key);
      return next;
    });

  return (
    <Stack gap="lg" className="page">
      <Title order={1} className="page-title">设置</Title>
      <Box hiddenFrom="sm">
        <SettingsSelectNav sections={sections} active={active.key} onSelect={select} />
      </Box>
      <div className="settings-layout">
        <Box visibleFrom="sm">
          <SettingsSideNav sections={sections} active={active.key} onSelect={select} />
        </Box>
        <section className="settings-content" aria-labelledby={`settings-${active.key}`}>
          <SectionHeader section={active} isReadOnly={isReadOnly} />
          {renderSection(active.key, isReadOnly)}
        </section>
      </div>
    </Stack>
  );
}
