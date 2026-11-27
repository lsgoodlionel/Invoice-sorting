import { screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import { TRAIN_DETAILS, makeAttachment, makeHotelEvidence, makeInvoice, makeLodgingInvoice, makeTransportInvoice } from '../../test/fixtures';
import { makeDetail } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { AmountComposition, LodgingBanner, TravelDateNotice, TripNotice } from './TravelInfo';

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

test('trip detail shows each leg and lodging cost with a recalculation warning', () => {
  renderWithProviders(<TripNotice expense={makeDetail({
    amount_cents: 70000,
    trip: {
      destination: '苏州', start: '2026-08-15', end: '2026-08-16',
      outbound_attachment_ids: [1], return_attachment_ids: [2],
      outbound_legs: 1, return_legs: 1,
      lodging_nights: 1, expected_nights: 1, lodging_records: 1, expected_records: 2, warnings: [],
      cost_lines: [
        { kind: 'outbound', label: '去程交通 上海 → 苏州', amount_cents: 10000, attachment_ids: [1] },
        { kind: 'return', label: '返程交通 苏州 → 上海', amount_cents: 12000, attachment_ids: [2] },
        { kind: 'lodging', label: '住宿 苏州酒店', amount_cents: 50000, attachment_ids: [3, 4] },
      ],
    },
  })} />);
  const notice = screen.getByTestId('trip-notice');
  expect(notice).toHaveTextContent('去程交通 上海 → 苏州');
  expect(notice).toHaveTextContent('返程交通 苏州 → 上海');
  expect(notice).toHaveTextContent('住宿 苏州酒店');
  expect(notice).toHaveTextContent('费用合计¥720.00');
  expect(notice).toHaveTextContent('清单总价与凭证费用合计不同');
});

test('trip detail keeps vouchers without recognized amounts visible', () => {
  renderWithProviders(<TripNotice expense={makeDetail({
    trip: {
      destination: '苏州', start: '2026-08-15', end: '2026-08-16',
      outbound_attachment_ids: [1], return_attachment_ids: [],
      outbound_legs: 1, return_legs: 0,
      lodging_nights: 1, expected_nights: 1, lodging_records: 0, expected_records: 2, warnings: ['待补充返程交通凭证'],
      cost_lines: [{ kind: 'outbound', label: '去程交通 上海 → 苏州', amount_cents: null, attachment_ids: [1] }],
    },
  })} />);
  const notice = screen.getByTestId('trip-notice');
  expect(notice).toHaveTextContent('去程交通 上海 → 苏州金额待补');
  expect(notice).toHaveTextContent('待补充返程交通凭证');
});
