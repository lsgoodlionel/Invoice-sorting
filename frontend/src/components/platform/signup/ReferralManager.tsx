import { Divider, Stack } from '@mantine/core';
import type { ReactNode } from 'react';
import { ReferralRecords } from './ReferralRecords';
import { SignupSettingsForm } from './SignupSettingsForm';

function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Stack gap="xs">
      <Divider label={<span className="section-label">{label}</span>} labelPosition="left" />
      {children}
    </Stack>
  );
}

/** 平台 → 推荐：推荐记录与注册设置。 */
export function ReferralManager() {
  return (
    <Stack gap="lg">
      <Section label="推荐记录"><ReferralRecords /></Section>
      <Section label="注册设置"><SignupSettingsForm /></Section>
    </Stack>
  );
}
