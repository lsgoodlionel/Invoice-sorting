import { Alert, Anchor, Button, Stack, Text } from '@mantine/core';
import { Link } from 'react-router';
import { APPLY_PATH } from '../../lib/signup';
import { AuthLayout } from '../auth/AuthLayout';

const HINT = '注册链接只能使用一次，并有有效期。过期或已使用后，请重新提交申请。';

/** 注册码缺失、无效、过期或已使用：说明原因并给出重新申请入口。 */
export function RegisterUnavailable({ message }: { message: string }) {
  const footer = <Anchor component={Link} to="/" size="xs">已有账号？直接登录</Anchor>;
  return (
    <AuthLayout title="注册链接不可用" footer={footer}>
      <Stack gap="md">
        <Alert color="orange" variant="light" role="alert">{message}</Alert>
        <Text size="sm" c="dimmed" lh={1.7}>{HINT}</Text>
        <Button component={Link} to={APPLY_PATH} variant="filled" fullWidth size="md">重新申请</Button>
      </Stack>
    </AuthLayout>
  );
}
