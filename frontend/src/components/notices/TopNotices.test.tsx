import { screen, waitFor } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import { mockFetch } from '../../test/fetchMock';
import { makeLicenseStatus, makeQuota } from '../../test/platformFixtures';
import { renderWithProviders } from '../../test/render';
import { TopNotices } from './TopNotices';

type Routes = Record<string, unknown>;

const OK_LICENSE = { 'GET /api/license/status': makeLicenseStatus() };
const OK_QUOTA = { 'GET /api/quota': makeQuota() };

function setup(routes: Routes) {
  const result = mockFetch({ ...OK_LICENSE, ...OK_QUOTA, ...routes });
  renderWithProviders(<TopNotices />);
  return result;
}

async function settle() {
  await waitFor(() => expect(screen.queryByText('载入中')).not.toBeInTheDocument());
}

describe('授权提示条', () => {
  test('宽限期显示黄条，文案直接用后端 message', async () => {
    setup({ 'GET /api/license/status': makeLicenseStatus({ state: 'grace', message: '授权已过期，处于宽限期。' }) });

    expect(await screen.findByText('授权已过期，处于宽限期。')).toBeInTheDocument();
    expect(screen.getByTestId('notice-warning')).toBeInTheDocument();
  });

  test('只读显示红条', async () => {
    setup({ 'GET /api/license/status': makeLicenseStatus({ state: 'readonly', message: '授权已过期并超过宽限期。' }) });

    expect(await screen.findByTestId('notice-danger')).toHaveTextContent('授权已过期并超过宽限期。');
  });

  test('正常授权与未配置授权都不显示', async () => {
    setup({ 'GET /api/license/status': makeLicenseStatus({ state: 'unlicensed_ok', message: '未配置授权密钥。' }) });
    await settle();

    expect(screen.queryByText('未配置授权密钥。')).not.toBeInTheDocument();
  });

  test('接口出错时静默隐藏，不打扰用户', async () => {
    setup({ 'GET /api/license/status': () => ({ status: 500, error: '服务器错误' }) });
    await settle();

    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});

describe('额度提示条', () => {
  test('账套只读时显示后端原文', async () => {
    setup({ 'GET /api/quota': makeQuota({ is_readonly: true, readonly_message: '账套已停用，系统当前为只读。' }) });

    expect(await screen.findByTestId('notice-danger')).toHaveTextContent('账套已停用，系统当前为只读。');
  });

  test('即将到期显示黄条', async () => {
    setup({ 'GET /api/quota': makeQuota({ expires_on: '2026-10-01', expires_in_days: 3 }) });

    expect(await screen.findByTestId('notice-warning')).toHaveTextContent('3 天后');
  });

  test('单账套部署（enforced=false）不显示', async () => {
    setup({ 'GET /api/quota': makeQuota({ enforced: false }) });
    await settle();

    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  test('额度接口尚未就绪（404）时静默隐藏', async () => {
    setup({ 'GET /api/quota': () => ({ status: 404, error: '没有找到' }) });
    await settle();

    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
