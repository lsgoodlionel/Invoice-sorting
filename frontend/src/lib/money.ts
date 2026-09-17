// 金额工具：所有运算基于整数“分”与字符串，禁止浮点乘法。

const YUAN_PATTERN = /^(-)?(\d*)(?:\.(\d*))?$/;
const CENTS_PER_YUAN = 100;

function groupThousands(digits: string): string {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/** 96000 → "¥960.00"；-12345 → "-¥123.45"；null → "—" */
export function formatCents(cents: number | null | undefined, options: { symbol?: boolean } = {}): string {
  if (cents === null || cents === undefined || !Number.isFinite(cents)) return '—';
  const { symbol = true } = options;
  const whole = Math.trunc(cents);
  const isNegative = whole < 0;
  const abs = Math.abs(whole);
  const yuan = Math.floor(abs / CENTS_PER_YUAN);
  const fen = abs % CENTS_PER_YUAN;
  const body = `${groupThousands(String(yuan))}.${String(fen).padStart(2, '0')}`;
  return `${isNegative ? '-' : ''}${symbol ? '¥' : ''}${body}`;
}

export const DEFAULT_CURRENCY = 'CNY';

const CURRENCY_SYMBOLS: Readonly<Record<string, string>> = {
  CNY: '¥',
  USD: 'US$',
  EUR: '€',
  GBP: '£',
  HKD: 'HK$',
  JPY: 'JP¥',
};

export const CURRENCY_OPTIONS: readonly { value: string; label: string }[] = [
  { value: 'CNY', label: '人民币 CNY' },
  { value: 'USD', label: '美元 USD' },
  { value: 'EUR', label: '欧元 EUR' },
  { value: 'GBP', label: '英镑 GBP' },
  { value: 'HKD', label: '港币 HKD' },
  { value: 'JPY', label: '日元 JPY' },
];

function normalizeCurrency(currency: string | null | undefined): string {
  return (currency ?? '').trim().toUpperCase() || DEFAULT_CURRENCY;
}

/** 币种符号：USD → "US$"；未知币种返回 ISO 代码。 */
export function currencySymbol(currency: string | null | undefined): string {
  const code = normalizeCurrency(currency);
  return CURRENCY_SYMBOLS[code] ?? code;
}

export function isForeignCurrency(currency: string | null | undefined): boolean {
  return normalizeCurrency(currency) !== DEFAULT_CURRENCY;
}

/** 按币种格式化：(2000, "USD") → "US$20.00"；未知币种 → "SGD 5.00"。 */
export function formatMoney(cents: number | null | undefined, currency: string | null | undefined): string {
  const plain = formatCents(cents, { symbol: false });
  if (plain === '—') return plain;
  const code = normalizeCurrency(currency);
  const symbol = CURRENCY_SYMBOLS[code] ?? `${code} `;
  return plain.startsWith('-') ? `-${symbol}${plain.slice(1)}` : `${symbol}${plain}`;
}

/** 分 → 元字符串（用于输入框），96000 → "960.00" */
export function centsToYuanString(cents: number | null | undefined): string {
  if (cents === null || cents === undefined) return '';
  return formatCents(cents, { symbol: false }).replace(/,/g, '');
}

/**
 * 元字符串 → 分。"1,234.5" → 123450；"0.1" → 10；非法输入返回 null。
 * 超过两位小数时按第三位四舍五入（绝对值方向）。
 */
export function parseYuanToCents(input: string | number | null | undefined): number | null {
  if (input === null || input === undefined) return null;
  const normalized = String(input).trim().replace(/[¥￥,，\s]/g, '');
  const match = YUAN_PATTERN.exec(normalized);
  if (!match) return null;
  const [, sign, intPart = '', fracPart = ''] = match;
  if (intPart === '' && fracPart === '') return null;
  const fen = `${fracPart}000`.slice(0, 2);
  const roundUp = Number(fracPart.charAt(2) || '0') >= 5 ? 1 : 0;
  const cents = Number(intPart || '0') * CENTS_PER_YUAN + Number(fen) + roundUp;
  if (!Number.isSafeInteger(cents)) return null;
  return sign && cents !== 0 ? -cents : cents;
}

export function sumCents(values: readonly number[]): number {
  return values.reduce((total, value) => total + value, 0);
}
