import { screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import { makeAttachment, makeDetail, makeInvoice } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { AttachmentList } from './AttachmentList';
import { InvoiceMeta } from './InvoiceMeta';

const invoiceAttachment = makeAttachment({ id: 10, invoice: makeInvoice({ region_name: '北京', is_nonlocal: true, order_no: 'JD20260915' }) });

describe('invoice region and order info', () => {
  test('InvoiceMeta shows region with nonlocal marker and order numbers', () => {
    renderWithProviders(<InvoiceMeta expense={makeDetail({ region_name: '北京', is_nonlocal: true, attachments: [invoiceAttachment] })} />);
    expect(screen.getByTestId('invoice-meta')).toHaveTextContent('开票地区：北京（外地）');
    expect(screen.getByTestId('invoice-meta')).toHaveTextContent('订单号：JD20260915');
  });

  test('InvoiceMeta renders nothing without invoice info', () => {
    renderWithProviders(<InvoiceMeta expense={makeDetail()} />);
    expect(screen.queryByTestId('invoice-meta')).not.toBeInTheDocument();
  });

  test('AttachmentList shows region and order number on invoice rows', () => {
    renderWithProviders(<AttachmentList attachments={[invoiceAttachment, makeAttachment({ id: 11, kind: 'order', invoice: null, original_name: 'o.png' })]} />);
    expect(screen.getByText('外地·北京')).toBeInTheDocument();
    expect(screen.getByText('订单号 JD20260915')).toBeInTheDocument();
  });
});
