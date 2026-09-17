// 开票地区：徽标、描述与省级简称列表。
import type { Attachment } from '../api/types';

/** 31 个省级行政区简称（不含港澳台），与后端税务机关代码映射一致。 */
export const CHINA_REGIONS: readonly string[] = [
  '北京', '天津', '河北', '山西', '内蒙古', '辽宁', '吉林', '黑龙江', '上海', '江苏', '浙江',
  '安徽', '福建', '江西', '山东', '河南', '湖北', '湖南', '广东', '广西', '海南', '重庆',
  '四川', '贵州', '云南', '西藏', '陕西', '甘肃', '青海', '宁夏', '新疆',
];

export const DEFAULT_LOCAL_REGION = '上海';

export const REGION_HELP = '按发票号码中的税务机关代码识别；外地发票需附网购订单截图（京东、当当、圆迈等已带明细平台可免）';

export interface RegionBadgeMeta {
  label: string;
  color: 'orange' | 'gray';
}

export function regionBadge(regionName: string, isNonlocal: boolean): RegionBadgeMeta | null {
  if (!regionName) return null;
  return isNonlocal ? { label: `外地·${regionName}`, color: 'orange' } : { label: regionName, color: 'gray' };
}

export function describeRegion(regionName: string, isNonlocal: boolean): string {
  if (!regionName) return '未知';
  return `${regionName}（${isNonlocal ? '外地' : '本地'}）`;
}

export function collectOrderNos(attachments: readonly Attachment[]): string[] {
  const orderNos = attachments.map((item) => item.invoice?.order_no ?? '').filter((orderNo) => orderNo !== '');
  return [...new Set(orderNos)];
}
