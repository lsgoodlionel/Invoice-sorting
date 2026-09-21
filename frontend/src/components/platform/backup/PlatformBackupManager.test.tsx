import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import { mockFetch } from '../../../test/fetchMock';
import { renderWithProviders } from '../../../test/render';
import { PlatformBackupManager } from './PlatformBackupManager';

const BACKUPS = [
  { name: 'platform-20260921-101500.db', size: 2 * 1024 * 1024, created_at: '2026-09-21T10:15:00+08:00' },
  { name: 'platform-20260920-090842.db', size: 1024 * 1024, created_at: '2026-09-20T09:08:42+08:00' },
];

const filledButtons = () => document.querySelectorAll('.mantine-Button-root[data-variant="filled"]');

describe('平台数据库备份', () => {
  test('说明备份内容、密码哈希风险与 secret.key', async () => {
    mockFetch({ 'GET /api/platform/backups': { items: [] } });
    renderWithProviders(<PlatformBackupManager />);

    expect(await screen.findByText('还没有平台数据库备份。')).toBeInTheDocument();
    expect(screen.getByText(/全部账号、账套、套餐、授权与邮件设置/)).toBeInTheDocument();
    expect(screen.getByText(/含全部账号的密码哈希，请妥善保管/)).toBeInTheDocument();
    expect(screen.getByText(/secret\.key/)).toBeInTheDocument();
    expect(screen.getByText(/与各账套的「备份与搬迁」无关/)).toBeInTheDocument();
    expect(filledButtons()).toHaveLength(1);
  });

  test('列出备份的时间、大小与下载链接', async () => {
    mockFetch({ 'GET /api/platform/backups': { items: BACKUPS } });
    renderWithProviders(<PlatformBackupManager />);

    const table = await screen.findByRole('table', { name: '平台数据库备份' });
    expect(within(table).getByText('2026-09-21 10:15')).toBeInTheDocument();
    expect(within(table).getByText('2.0 MB')).toBeInTheDocument();
    expect(within(table).getByLabelText('下载 platform-20260920-090842.db'))
      .toHaveAttribute('href', '/api/platform/backups/platform-20260920-090842.db');
  });

  test('点击「备份平台数据库」后刷新列表并显示服务端提示', async () => {
    const user = userEvent.setup();
    let backups = BACKUPS.slice(1);
    const { calls } = mockFetch({
      'GET /api/platform/backups': () => ({ data: { items: backups } }),
      'POST /api/platform/backups': () => {
        backups = BACKUPS;
        return { data: { ...BACKUPS[0], notice: '服务器上只保留最近 10 份平台备份' } };
      },
    });
    renderWithProviders(<PlatformBackupManager />);
    expect(await screen.findByText('2026-09-20 09:08')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '备份平台数据库' }));

    expect(await screen.findByText('2026-09-21 10:15')).toBeInTheDocument();
    expect(screen.getByText('服务器上只保留最近 10 份平台备份')).toBeInTheDocument();
    expect(calls.filter((call) => call.method === 'POST' && call.url === '/api/platform/backups')).toHaveLength(1);
    await waitFor(() => expect(calls.filter((call) => call.method === 'GET' && call.url === '/api/platform/backups').length).toBeGreaterThanOrEqual(2));
  });

  test('备份失败时就地显示原因', async () => {
    mockFetch({
      'GET /api/platform/backups': { items: [] },
      'POST /api/platform/backups': () => ({ status: 500, error: '磁盘空间不足' }),
    });
    renderWithProviders(<PlatformBackupManager />);

    await userEvent.click(await screen.findByRole('button', { name: '备份平台数据库' }));

    expect(await screen.findByText('磁盘空间不足')).toBeInTheDocument();
  });
});
