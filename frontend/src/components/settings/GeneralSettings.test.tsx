import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import { mockFetch } from '../../test/fetchMock';
import { renderWithProviders } from '../../test/render';
import { GeneralSettings } from './GeneralSettings';

const settings = {
  buyer_name: '某大学', buyer_tax_id: 'X1', overdue_days: 30, local_region: '上海',
  detail_platforms: ['京东', '当当'], data_dir: '/d', inbox_dir: '/d/收件箱',
};

describe('GeneralSettings', () => {
  test('saves local region and detail platforms', async () => {
    const user = userEvent.setup();
    const { calls } = mockFetch({ 'GET /api/settings': settings, 'PUT /api/settings': settings });
    renderWithProviders(<GeneralSettings />);
    expect(await screen.findByDisplayValue('某大学')).toBeInTheDocument();
    expect(screen.getByText('京东')).toBeInTheDocument();
    expect(screen.getByText(/外地发票若销售方属于这些平台，不再要求订单截图/)).toBeInTheDocument();

    await user.click(document.querySelector('input[aria-label="本地地区"]') as HTMLInputElement);
    await user.click(await screen.findByRole('option', { name: '北京' }));
    const tags = document.querySelector('input[aria-label="已带明细平台"]') as HTMLInputElement;
    await user.type(tags, '圆迈{Enter}');

    await user.click(screen.getByRole('button', { name: '保存设置' }));
    await waitFor(() => expect(calls.some((c) => c.method === 'PUT')).toBe(true));
    expect(calls.find((c) => c.method === 'PUT')?.body).toEqual({
      buyer_name: '某大学', buyer_tax_id: 'X1', overdue_days: 30, local_region: '北京', detail_platforms: ['京东', '当当', '圆迈'],
    });
  });
});
