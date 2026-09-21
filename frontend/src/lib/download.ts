/** 用临时链接触发浏览器下载（同源地址，浏览器按响应头决定文件名）。 */
export function triggerDownload(url: string, filename = ''): void {
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.rel = 'noopener';
  document.body.appendChild(link);
  link.click();
  link.remove();
}
