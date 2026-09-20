import { Stack } from '@mantine/core';
import { LicenseNotice } from './LicenseNotice';
import { QuotaNotice } from './QuotaNotice';

/** 应用顶部的提示条区域：授权状态在上，账套额度在下；都没有时不占位。 */
export function TopNotices() {
  return (
    <Stack gap={2}>
      <LicenseNotice />
      <QuotaNotice />
    </Stack>
  );
}
