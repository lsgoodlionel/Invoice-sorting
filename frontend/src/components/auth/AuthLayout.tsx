import { Stack, Text, Title } from '@mantine/core';
import type { ReactNode } from 'react';

interface AuthLayoutProps {
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
}

export const BRAND_NAME = '发票账本';

/** 登录/设置密码页的居中纸质卡片。 */
export function AuthLayout({ title, subtitle, children }: AuthLayoutProps) {
  return (
    <main className="auth-screen">
      <section className="auth-card" aria-labelledby="auth-title">
        <Stack gap="lg">
          <Stack gap={6}>
            <Text className="auth-brand">{BRAND_NAME} · 个人报销</Text>
            <Title order={1} id="auth-title" className="auth-title">
              {title}
            </Title>
            {subtitle && (
              <Text size="sm" c="dimmed" lh={1.7}>
                {subtitle}
              </Text>
            )}
          </Stack>
          {children}
        </Stack>
      </section>
    </main>
  );
}

export function AuthLoading() {
  return (
    <main className="auth-screen">
      <div role="status" aria-label="正在检查登录状态" className="auth-loading">
        <Text className="auth-loading-brand">{BRAND_NAME}</Text>
        <span className="auth-loading-rule" aria-hidden="true" />
      </div>
    </main>
  );
}
