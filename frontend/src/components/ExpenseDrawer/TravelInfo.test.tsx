import { screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import { TRAIN_DETAILS, makeAttachment, makeHotelEvidence, makeInvoice, makeLodgingInvoice, makeTransportInvoice } from '../../test/fixtures';
import { makeDetail } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { AmountComposition, LodgingBanner, TravelDateNotice } from './TravelInfo';

const lodging = makeAttachment({ id: 1, invoice: makeLodgingInvoice() });
const order = makeAttachment({ id: 2, kind: 'order', evidence: makeHotelEvidence() });
const train1 = makeAttachment({ id: 3, invoice: makeTransportInvoice({ total_cents: 15250 }) });
const train2 = makeAttachment({
  id: 4,
  invoice: makeTransportInvoice({
    total_cents: 15250,
    details: { ...TRAIN_DETAILS, date: '2026-08-16', number: 'G7124', from: '苏州园区', to: '上海虹桥' },
  }),
});

describe('LodgingBanner', () => {
  test('shows lodging info from the hotel order', () => {
    renderWithProviders(<LodgingBanner attachments={[lodging, order]} />);
    expect(screen.getByTestId('lodging-banner')).toHaveTextContent('苏州 · 苏州园区阳澄湖泰康万豪酒店 · 08-15 入住 → 08-16 离店 · 1晚1间 · 入住人 李欣');
  });

  test('renders nothing without a hotel order', () => {
    renderWithProviders(<LodgingBanner attachments={[makeAttachment({ invoice: makeInvoice() })]} />);
    expect(screen.queryByTestId('lodging-banner')).not.toBeInTheDocument();
  });
});

describe('TravelDateNotice', () => {
  test('prompts for an order or statement when lodging dates are missing', () => {
    renderWithProviders(<TravelDateNotice expense={makeDetail({ travel_dates_missing: true })} />);
    expect(screen.getByText('住宿时间待完善')).toBeInTheDocument();
    expect(screen.getByText(/开票日期不会用于往返交通自动关联/)).toBeInTheDocument();
  });
});

describe('AmountComposition', () => {
  test('shows lodging and transport breakdown', () => {
    renderWithProviders(<AmountComposition amountCents={102500} attachments={[lodging, order, train1, train2]} />);
    expect(screen.getByTestId('amount-composition')).toHaveTextContent('¥1,025.00 = 住宿 ¥720.00 + 交通 2 张 ¥305.00');
    expect(screen.queryByText(/与凭证净额.*不一致/)).not.toBeInTheDocument();
  });

  test('warns when the amount differs from invoice total', () => {
    renderWithProviders(<AmountComposition amountCents={100000} attachments={[lodging, train1, train2]} />);
    expect(screen.getByText('与凭证净额 ¥1,025.00 不一致')).toBeInTheDocument();
  });

  test('renders nothing without transport invoices', () => {
    renderWithProviders(<AmountComposition amountCents={72000} attachments={[lodging, order]} />);
    expect(screen.queryByTestId('amount-composition')).not.toBeInTheDocument();
  });
});
