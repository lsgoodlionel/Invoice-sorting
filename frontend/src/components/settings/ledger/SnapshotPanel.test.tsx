import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import { mockFetch } from '../../../test/fetchMock';
import { renderWithProviders } from '../../../test/render';
import { SnapshotPanel } from './SnapshotPanel';

const SNAPSHOTS = [
  { name: 'invoice_20260921_101500.db', kind: 'manual', size: 2_560_000, created_at: '2026-09-21T10:15:00+08:00' },
  { name: 'upgrade_20260920_090842.db', kind: 'upgrade', size: 2_400_000, created_at: '2026-09-20T09:08:42+08:00' },
];

describe('数据库快照', () => {
  test('写清楚不含附件、不能替代完整备份', async () => {
    mockFetch({ 'GET /api/backup/snapshots': [] });
    renderWithProviders(<SnapshotPanel />);

    expect(await screen.findByText('还没有快照。')).toBeInTheDocument();
    expect(screen.getByText('不含发票和凭证附件')).toBeInTheDocument();
    expect(screen.getByText(/不能替代完整备份/)).toBeInTheDocument();
  });

  test('列出手动与升级前的快照并提供下载链接', async () => {
    mockFetch({ 'GET /api/backup/snapshots': SNAPSHOTS });
    renderWithProviders(<SnapshotPanel />);

    expect(await screen.findByText('2026-09-21 10:15')).toBeInTheDocument();
    expect(screen.getByText('手动')).toBeInTheDocument();
    expect(screen.getByText('升级前自动')).toBeInTheDocument();
    expect(screen.getByLabelText('下载快照 upgrade_20260920_090842.db'))
      .toHaveAttribute('href', '/api/backup/snapshots/upgrade_20260920_090842.db');
  });

  test('创建快照后刷新列表', async () => {
    const user = userEvent.setup();
    let snapshots: typeof SNAPSHOTS = [];
    const { calls } = mockFetch({
      'GET /api/backup/snapshots': () => ({ data: snapshots }),
      'POST /api/backup': () => {
        snapshots = SNAPSHOTS.slice(0, 1);
        return { data: { file: '/d/备份/invoice_20260921_101500.db', name: 'invoice_20260921_101500.db' } };
      },
    });
    renderWithProviders(<SnapshotPanel />);

    await user.click(await screen.findByRole('button', { name: '创建数据库快照' }));

    expect(await screen.findByText('2026-09-21 10:15')).toBeInTheDocument();
    await waitFor(() => expect(calls.filter((c) => c.url === '/api/backup/snapshots').length).toBeGreaterThanOrEqual(2));
  });
});
