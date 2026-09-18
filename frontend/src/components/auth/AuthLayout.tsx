import { Stack, Text, Title } from '@mantine/core';
import type { ReactNode } from 'react';

interface AuthLayoutProps {
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}

export const BRAND_NAME = '发票账本';

/** 账本印章：品牌标记，纯装饰。 */
function BrandSeal() {
  return (
    <span className="auth-seal" aria-hidden="true">
      账
    </span>
  );
}

/** 登录/设置密码页的居中纸质卡片。 */
export function AuthLayout({ title, subtitle, children, footer }: AuthLayoutProps) {
  return (
    <main className="auth-screen">
      <div className="auth-stack">
        <section className="auth-card" aria-labelledby="auth-title">
          <header className="auth-header">
            <BrandSeal />
            <Stack gap={2}>
              <Text className="auth-brand">{BRAND_NAME}</Text>
              <Title order={1} id="auth-title" className="auth-title">
                {title}
              </Title>
            </Stack>
          </header>
          {subtitle && (
            <Text size="sm" c="dimmed" lh={1.7} mb="lg">
              {subtitle}
            </Text>
          )}
          {children}
          {footer && <div className="auth-footnote">{footer}</div>}
        </section>
        <Text className="auth-colophon">个人发票 · 报销过程管理</Text>
      </div>
    </main>
  );
}

export function AuthLoading() {
  return (
    <main className="auth-screen">
      <div role="status" aria-label="正在检查登录状态" className="auth-loading">
        <BrandSeal />
        <span className="auth-loading-rule" aria-hidden="true" />
      </div>
    </main>
  );
}
