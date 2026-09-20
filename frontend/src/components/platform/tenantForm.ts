const SLUG_PATTERN = /^[a-z0-9][a-z0-9-]{0,49}$/;

export const SLUG_HINT = '小写字母、数字与连字符，开通后不可更改；也是子域名前缀';
export const SLUG_ERROR = '只能使用小写字母、数字与连字符，且以字母或数字开头';

export const isSlugValid = (slug: string): boolean => SLUG_PATTERN.test(slug);

/** 空串不提示（还没开始填）。 */
export const slugError = (slug: string): string | null => {
  const value = slug.trim();
  if (!value) return null;
  return isSlugValid(value) ? null : SLUG_ERROR;
};
