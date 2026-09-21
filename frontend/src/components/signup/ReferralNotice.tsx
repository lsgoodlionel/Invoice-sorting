import { Alert, Text } from '@mantine/core';

interface ReferralNoticeProps {
  referrerName: string | null;
  isInvalid: boolean;
}

const INVALID_HINT = '这个推荐链接无效或已失效。你仍可以直接提交申请，由平台审核。';

/** 推荐人（来自链接，不可修改），或推荐码无效时的友好提示。 */
export function ReferralNotice({ referrerName, isInvalid }: ReferralNoticeProps) {
  if (isInvalid) {
    return (
      <Alert color="orange" variant="light" mb="md" data-testid="referral-invalid">
        <Text size="sm">{INVALID_HINT}</Text>
      </Alert>
    );
  }
  if (!referrerName) return null;
  return (
    <Alert color="ink" variant="light" mb="md" data-testid="referral-by">
      <Text size="sm">
        由 <Text span fw={600}>{referrerName}</Text> 推荐
      </Text>
    </Alert>
  );
}
