import type {
  Attachment,
  BatchDetail,
  ChecklistItem,
  EvidenceData,
  ExpenseDetail,
  ExpenseSummary,
  ImportGroup,
  ImportSession,
  InvoiceData,
  MatchCandidate,
  Project,
  StatusEvent,
  User,
} from '../api/types';

export function makeExpense(overrides: Partial<ExpenseSummary> = {}): ExpenseSummary {
  return {
    id: 1,
    spent_on: '2026-09-15',
    amount_cents: 96000,
    merchant: '京东某店',
    summary: '鼠标×2',
    category_id: 2,
    category_name: '易耗品',
    category_color: '#1F5F4A',
    project_id: null,
    project_name: null,
    status: 'invoiced',
    status_label: '已开票',
    status_manual: false,
    missing_count: 0,
    batch_id: null,
    batch_name: null,
    attachment_count: 1,
    invoice_no: null,
    region_name: '',
    is_nonlocal: false,
    invoice_exempt: false,
    currency: 'CNY',
    original_amount_cents: null,
    created_by: null,
    ...overrides,
  };
}

export function makeAttachment(overrides: Partial<Attachment> = {}): Attachment {
  return {
    id: 10,
    expense_id: 1,
    kind: 'invoice',
    kind_label: '发票',
    original_name: '发票_123.pdf',
    file_name: '发票_123.pdf',
    mime: 'application/pdf',
    size: 20480,
    created_at: '2026-09-15T10:00:00+08:00',
    url: '/api/attachments/10/file',
    invoice: null,
    evidence: null,
    file_key: '',
    uploaded_by: null,
    ...overrides,
  };
}

export function makeInvoice(overrides: Partial<InvoiceData> = {}): InvoiceData {
  return {
    invoice_no: '26312000000123456789',
    issued_on: '2026-09-15',
    total_cents: 96000,
    tax_cents: 11044,
    seller_name: '京东某店',
    seller_tax_id: '91110000000000000X',
    buyer_name: '某大学',
    buyer_tax_id: '12310000000000000Y',
    item_summary: '鼠标',
    invoice_type: '电子发票（普通发票）',
    parser: 'pdf',
    confirmed: false,
    tax_category: '计算机配套产品',
    region_name: '上海',
    is_nonlocal: false,
    order_no: '',
    detail_platform: false,
    buyer_mismatch: false,
    details: null,
    ...overrides,
  };
}

export function makeChecklistItem(overrides: Partial<ChecklistItem> = {}): ChecklistItem {
  return {
    id: 100,
    attachment_kind: 'invoice',
    kind_label: '发票',
    level: 'required',
    state: 'present',
    reason: '',
    hint: '',
    ...overrides,
  };
}

export function makeDetail(overrides: Partial<ExpenseDetail> = {}): ExpenseDetail {
  return {
    ...makeExpense(),
    pay_method: '微信',
    is_online: true,
    note: '',
    void_reason: '',
    sent_on: null,
    reimbursed_on: null,
    reimbursed_cents: 0,
    folder_path: '',
    route_hint: '',
    attachments: [],
    checklist: [],
    timeline: [],
    created_at: '2026-09-15T10:00:00+08:00',
    updated_at: '2026-09-15T10:00:00+08:00',
    ...overrides,
  };
}

export function makeEvidence(overrides: Partial<EvidenceData> = {}): EvidenceData {
  return {
    doc_type: 'order',
    recognizer: 'app_store_order',
    amount_cents: 2000,
    currency: 'USD',
    cny_cents: null,
    occurred_on: '2026-06-28',
    merchant: 'Apple',
    item_name: 'Claude Pro - Monthly',
    order_no: 'MSD3K2L9QX1234',
    card_last4: '',
    is_foreign: true,
    confirmed: false,
    details: null,
    ...overrides,
  };
}

export function makeCandidate(overrides: Partial<MatchCandidate> = {}): MatchCandidate {
  return {
    expense_id: 42,
    spent_on: '2026-09-11',
    merchant: '腾讯云',
    amount_cents: 29800,
    currency: 'CNY',
    original_amount_cents: null,
    status: 'spent',
    missing_kinds: ['invoice'],
    score: 85,
    reasons: ['金额相同', '日期相差 1 天'],
    ...overrides,
  };
}

export function makeGroup(overrides: Partial<ImportGroup> = {}): ImportGroup {
  return {
    group_id: 'g1',
    attachments: [makeAttachment({ id: 10, expense_id: null, invoice: makeInvoice() })],
    link_reasons: [],
    summary: {
      spent_on: '2026-09-15',
      amount_cents: 96000,
      currency: 'CNY',
      original_amount_cents: null,
      merchant: '京东某店',
      summary: '鼠标',
      category_id: 1,
      is_online: false,
      invoice_exempt: false,
    },
    match: null,
    candidates: [],
    suggested_action: 'create',
    warnings: [],
    ...overrides,
  };
}

export function makeSession(overrides: Partial<ImportSession> = {}): ImportSession {
  return { session_id: 'sess-1', groups: [makeGroup()], duplicates: [], errors: [], notices: [], ...overrides };
}

export function makeBatch(overrides: Partial<BatchDetail> = {}): BatchDetail {
  return {
    id: 5,
    name: '9月第1批',
    project_id: null,
    project_name: null,
    status: 'draft',
    status_label: '待外发',
    sent_on: null,
    sent_via: '',
    receiver: '',
    external_no: '',
    received_on: null,
    received_cents: 0,
    note: '',
    created_at: '2026-09-15T10:00:00+08:00',
    item_count: 0,
    total_cents: 0,
    missing_item_count: 0,
    created_by: null,
    expenses: [],
    exports: [],
    ...overrides,
  };
}

export function makeProject(overrides: Partial<Project> = {}): Project {
  return { id: 1, code: 'KY-01', name: '科研A', owner: '', active: true, ...overrides };
}

export function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: 2,
    username: 'zhangsan',
    display_name: '张三',
    role: 'member',
    is_active: true,
    has_password: true,
    created_at: '2026-09-01T09:00:00+08:00',
    last_login_at: '2026-09-15T10:05:00+08:00',
    ...overrides,
  };
}

export function makeStatusEvent(overrides: Partial<StatusEvent> = {}): StatusEvent {
  return {
    id: 1,
    from_status: null,
    to_status: 'spent',
    is_manual: false,
    note: '',
    at: '2026-09-15T10:00:00+08:00',
    actor: null,
    ...overrides,
  };
}

/** 携程酒店订单（hotel_booking）。 */
export function makeHotelEvidence(overrides: Partial<EvidenceData> = {}): EvidenceData {
  return makeEvidence({
    doc_type: 'order', recognizer: 'hotel_booking', amount_cents: 72000, currency: 'CNY', cny_cents: 72000,
    occurred_on: '2026-08-16', merchant: '苏州园区阳澄湖泰康万豪酒店', item_name: '苏州园区阳澄湖泰康万豪酒店 08-15–08-16 1晚1间',
    order_no: '1132548283006095', is_foreign: false,
    details: {
      city: '苏州', hotel: '苏州园区阳澄湖泰康万豪酒店', check_in: '2026-08-15', check_out: '2026-08-16',
      nights: '1', rooms: '1', guest: '李欣', platform: '携程',
    },
    ...overrides,
  });
}

export const TRAIN_DETAILS: Readonly<Record<string, string>> = {
  date: '2026-08-15', from: '上海虹桥', to: '苏州园区', vehicle: 'train', number: 'G7123', passenger: '张三',
};

/** 住宿发票（酒店）。 */
export function makeLodgingInvoice(overrides: Partial<InvoiceData> = {}): InvoiceData {
  return makeInvoice({
    total_cents: 72000, seller_name: '苏州泰康万豪酒店有限公司', item_summary: '住宿费', tax_category: '住宿服务', ...overrides,
  });
}

/** 交通票发票（铁路电子客票）。 */
export function makeTransportInvoice(overrides: Partial<InvoiceData> = {}): InvoiceData {
  return makeInvoice({
    total_cents: 15250, seller_name: '中国铁路上海局集团有限公司', item_summary: '铁路旅客运输服务', tax_category: '旅客运输服务',
    invoice_type: '电子发票（铁路电子客票）', details: { ...TRAIN_DETAILS }, ...overrides,
  });
}
