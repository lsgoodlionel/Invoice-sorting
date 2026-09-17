import { createTheme, type MantineColorsTuple } from '@mantine/core';

// 墨绿：强调色，shade 6 = #1F5F4A
const ink: MantineColorsTuple = [
  '#EEF5F2',
  '#D9E8E2',
  '#B0D0C3',
  '#84B6A2',
  '#5F9F86',
  '#3E7F66',
  '#1F5F4A',
  '#1A5040',
  '#144034',
  '#0D2F26',
];

// 暖纸灰：替代默认冷灰
const paper: MantineColorsTuple = [
  '#FAF8F3',
  '#F3EFE6',
  '#E7E1D4',
  '#D6CFBF',
  '#B9B1A0',
  '#968E7E',
  '#736C5E',
  '#565045',
  '#3A362F',
  '#1F1D19',
];

export const CJK_FONT_STACK =
  '-apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC", "Helvetica Neue", Arial, sans-serif';

export const theme = createTheme({
  primaryColor: 'ink',
  primaryShade: 6,
  colors: { ink, paper },
  black: '#1F2420',
  white: '#FFFFFF',
  fontFamily: CJK_FONT_STACK,
  fontFamilyMonospace: '"SF Mono", "JetBrains Mono", Menlo, Consolas, monospace',
  headings: { fontFamily: CJK_FONT_STACK, fontWeight: '600' },
  defaultRadius: 'sm',
  radius: { xs: '2px', sm: '3px', md: '4px', lg: '6px', xl: '8px' },
  shadows: {
    xs: '0 1px 0 rgba(31, 36, 32, 0.06)',
    sm: '0 1px 2px rgba(31, 36, 32, 0.08)',
    md: '0 4px 14px rgba(31, 36, 32, 0.10)',
  },
  focusRing: 'auto',
  cursorType: 'pointer',
  components: {
    Button: { defaultProps: { variant: 'default' } },
    Drawer: { defaultProps: { position: 'right', size: 640 } },
    Table: { defaultProps: { verticalSpacing: 6, horizontalSpacing: 'sm' } },
    Badge: { defaultProps: { radius: 'sm' } },
    Tooltip: { defaultProps: { openDelay: 300 } },
  },
});
