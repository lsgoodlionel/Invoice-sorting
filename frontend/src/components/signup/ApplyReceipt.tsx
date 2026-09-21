import { Anchor, Stack, Text } from '@mantine/core';
import { Link } from 'react-router';
import type { SignupApplicationReceipt } from '../../api/signupTypes';
import { AuthLayout } from '../auth/AuthLayout';

const PENDING_HINT = '审批结果会发到你的邮箱，请留意查收（也可能在垃圾邮件里）。';
const APPROVED_HINT = '注册链接已发到你的邮箱，请在有效期内打开链接完成注册。';

/** 申请提交成功：显示申请编号与后续说明。 */
export function ApplyReceipt({ receipt, email }: { receipt: SignupApplicationReceipt; email: string }) {
  const footer = <Anchor component={Link} to="/" size="xs">返回登录</Anchor>;
  return (
    <AuthLayout title="申请已提交" footer={footer}>
      <Stack gap="sm">
        <div className="signup-receipt">
          <Text size="xs" c="dimmed">申请编号</Text>
          <Text size="xl" fw={600} className="num" data-testid="application-no">{receipt.number}</Text>
        </div>
        <Text size="sm" lh={1.7}>{receipt.status === 'approved' ? APPROVED_HINT : PENDING_HINT}</Text>
        <Text size="xs" c="dimmed">邮箱：{email}</Text>
      </Stack>
    </AuthLayout>
  );
}
