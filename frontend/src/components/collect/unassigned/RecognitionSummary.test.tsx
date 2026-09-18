import { screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import { makeAttachment, makeEvidence, makeHotelEvidence, makeTransportInvoice, TRAIN_DETAILS } from '../../../test/fixtures';
import { renderWithProviders } from '../../../test/render';
import { RecognitionSummary } from './RecognitionSummary';

describe('RecognitionSummary travel details', () => {
  test('hotel order shows hotel summary with order tail', () => {
    renderWithProviders(<RecognitionSummary attachment={makeAttachment({ kind: 'order', evidence: makeHotelEvidence() })} />);
    expect(screen.getByText('酒店订单 · 苏州园区阳澄湖泰康万豪酒店 · 08-15 至 08-16 · 1晚1间 · ¥720.00 · 携程 · 订单号 …006095')).toBeInTheDocument();
  });

  test('transport evidence shows the trip', () => {
    const ticket = makeAttachment({ kind: 'transport', evidence: makeEvidence({ doc_type: 'unknown', recognizer: 'transport_booking', details: { ...TRAIN_DETAILS } }) });
    renderWithProviders(<RecognitionSummary attachment={ticket} />);
    expect(screen.getByText('火车 G7123 · 上海虹桥 → 苏州园区 · 08-15 · 张三')).toBeInTheDocument();
  });

  test('transport invoice appends the trip after invoice facts', () => {
    renderWithProviders(<RecognitionSummary attachment={makeAttachment({ invoice: makeTransportInvoice() })} />);
    expect(screen.getByText('2026-09-15 · 中国铁路上海局集团有限公司 · ¥152.50 · 火车 G7123 · 上海虹桥 → 苏州园区 · 08-15 · 张三')).toBeInTheDocument();
  });
});
