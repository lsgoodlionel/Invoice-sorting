import { screen, within } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import { mockFetch } from '../../test/fetchMock';
import { makeAttachment } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { AttachmentList } from './AttachmentList';

const attachments = [
  makeAttachment({ id: 10, original_name: '发票.pdf', uploaded_by: { id: 2, display_name: '张三' } }),
  makeAttachment({ id: 11, original_name: '订单.png', uploaded_by: null }),
];

describe('AttachmentList uploader', () => {
  test('shows uploader and time, inbox when uploader is empty', () => {
    mockFetch({});
    renderWithProviders(<AttachmentList attachments={attachments} />);
    expect(within(screen.getByTestId('attachment-uploader-10')).getByText(/^上传：张三 · 09-15 \d{2}:00$/)).toBeInTheDocument();
    expect(within(screen.getByTestId('attachment-uploader-11')).getByText(/^上传：收件箱 · 09-15 \d{2}:00$/)).toBeInTheDocument();
  });

  test('only shows upload time when auth is disabled', () => {
    mockFetch({});
    renderWithProviders(<AttachmentList attachments={attachments.slice(1)} />, {
      currentUser: { user: null, isAdmin: true, authEnabled: false },
    });
    expect(within(screen.getByTestId('attachment-uploader-11')).getByText(/^上传 · 09-15 \d{2}:00$/)).toBeInTheDocument();
    expect(screen.queryByText(/收件箱/)).not.toBeInTheDocument();
  });
});
