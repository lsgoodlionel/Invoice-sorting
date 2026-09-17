import { Divider, Stack, Title } from '@mantine/core';
import type { ReactNode } from 'react';
import { CategoryManager } from '../components/settings/CategoryManager';
import { GeneralSettings } from '../components/settings/GeneralSettings';
import { ProjectManager } from '../components/settings/ProjectManager';
import { RuleManager } from '../components/settings/RuleManager';
import { SecuritySettings } from '../components/settings/SecuritySettings';

function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Stack gap="xs">
      <Divider label={<span className="section-label">{label}</span>} labelPosition="left" />
      {children}
    </Stack>
  );
}

export function SettingsPage() {
  return (
    <Stack gap="xl" className="page">
      <Title order={1} className="page-title">设置</Title>
      <Section label="基本"><GeneralSettings /></Section>
      <Section label="分类"><CategoryManager /></Section>
      <Section label="经费项目"><ProjectManager /></Section>
      <Section label="凭证清单规则"><RuleManager /></Section>
      <Section label="登录与安全"><SecuritySettings /></Section>
    </Stack>
  );
}
