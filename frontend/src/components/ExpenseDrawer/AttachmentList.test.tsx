import { screen, within } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import { mockFetch } from '../../test/fetchMock';
import { makeAttachment, makeEvidence, makeHotelEvidence, makeTransportInvoice, TRAIN_DETAILS } from '../../test/fixtures';
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

  test('shows travel summaries for hotel order, transport evidence and transport invoice', () => {
    mockFetch({});
    renderWithProviders(
      <AttachmentList
        attachments={[
          makeAttachment({ id: 20, kind: 'order', evidence: makeHotelEvidence() }),
          makeAttachment({ id: 21, kind: 'transport', kind_label: '往来交通凭证', evidence: makeEvidence({ recognizer: 'transport_booking', details: { ...TRAIN_DETAILS, number: 'G7124' } }) }),
          makeAttachment({ id: 22, invoice: makeTransportInvoice() }),
        ]}
      />,
    );
    expect(screen.getByTestId('evidence-20')).toHaveTextContent('酒店订单 · 苏州园区阳澄湖泰康万豪酒店 · 08-15 至 08-16 · 1晚1间 · ¥720.00 · 携程 · 订单号 1132548283006095');
    expect(screen.getByTestId('evidence-21')).toHaveTextContent('火车 G7124 · 上海虹桥 → 苏州园区 · 08-15 · 张三');
    expect(screen.getByTestId('travel-22')).toHaveTextContent('火车 G7123 · 上海虹桥 → 苏州园区 · 08-15 · 张三');
  });
});
