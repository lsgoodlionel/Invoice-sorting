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
