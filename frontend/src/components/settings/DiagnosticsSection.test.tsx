import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import { AUTHENTICATED } from '../../test/authStatus';
import { mockFetch } from '../../test/fetchMock';
import { renderWithProviders } from '../../test/render';
import { DiagnosticsSection } from './DiagnosticsSection';

const BASE_STATUS = {
  upload_enabled: false,
  repo: '',
  app: 'invoice-sorting',
  instance: 'srv1',
  log_file: '/var/lib/invoice-sorting/日志/app.log',
  last: null,
  throttle: { daily_used: 0, daily_remaining: 5, tracked_fingerprints: 0 },
};

const REPORT = {
  created_at: '2026-09-20T12:30:00+08:00',
  reason: 'manual',
  fingerprint: '',
  package: 'diag_srv1_20260920-123000_nofp.zip',
  size: 2048,
  residue: [],
  is_truncated: false,
  is_uploaded: false,
  repo_path: '',
  message: '未配置日志仓库或令牌，诊断包只保存在本机。',
};

function routes(status: unknown, collect: unknown = REPORT) {
  return mockFetch({
    'GET /api/auth/status': AUTHENTICATED,
    'GET /api/diagnostics/status': status,
    'POST /api/diagnostics/collect': collect,
  });
}

describe('DiagnosticsSection', () => {
  test('shows that packages stay local when upload is not configured', async () => {
    routes(BASE_STATUS);
    renderWithProviders(<DiagnosticsSection />);

    expect(await screen.findByText('不上传（只存本机）')).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: '同时上传到日志仓库' })).toBeDisabled();
  });

  test('collect posts upload=false when upload is not configured', async () => {
    const { calls } = routes(BASE_STATUS);
    renderWithProviders(<DiagnosticsSection />);

    await userEvent.click(await screen.findByRole('button', { name: '生成诊断包' }));

    await waitFor(() => {
      const posted = calls.find((call) => call.url === '/api/diagnostics/collect');
      expect(posted?.body).toEqual({ upload: false, reason: 'manual' });
    });
  });

  test('upload checkbox is usable once the server has a log repo', async () => {
    const { calls } = routes({ ...BASE_STATUS, upload_enabled: true, repo: 'owner/logs' });
    renderWithProviders(<DiagnosticsSection />);

    expect(await screen.findByText('自动上传到 owner/logs')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('checkbox', { name: '同时上传到日志仓库' }));
    await userEvent.click(screen.getByRole('button', { name: '生成诊断包' }));

    await waitFor(() => {
      const posted = calls.find((call) => call.url === '/api/diagnostics/collect');
      expect(posted?.body).toEqual({ upload: true, reason: 'manual' });
    });
  });

  test('shows the last package and its size', async () => {
    routes({ ...BASE_STATUS, last: { ...REPORT, fingerprint: 'abcd1234ef567890' } });
    renderWithProviders(<DiagnosticsSection />);

    expect(await screen.findByText(/diag_srv1_20260920-123000_nofp\.zip/)).toBeInTheDocument();
    expect(screen.getByText(/2 KB/)).toBeInTheDocument();
    expect(screen.getByText(/abcd1234ef567890/)).toBeInTheDocument();
  });

  test('warns when the self check refused to upload', async () => {
    routes({ ...BASE_STATUS, upload_enabled: true, repo: 'owner/logs', last: { ...REPORT, residue: ['邮箱'] } });
    renderWithProviders(<DiagnosticsSection />);

    expect(await screen.findByText(/自检发现疑似未脱敏内容（邮箱）/)).toBeInTheDocument();
  });
});
