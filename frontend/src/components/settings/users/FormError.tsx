import { Text } from '@mantine/core';
import { errorMessage } from '../../../api/client';

/** 后端错误原文（如 400 约束、409 用户名已存在），显示在表单底部。 */
export function FormError({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <Text size="sm" c="red.7" role="alert">
      {errorMessage(error)}
    </Text>
  );
}
