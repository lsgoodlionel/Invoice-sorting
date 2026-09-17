import { notifications } from '@mantine/notifications';
import { useUploadToExpense } from '../../api/hooks/expenses';
import { uploadResultMessage } from '../../lib/evidence';

/** 清单行拖放补传：上传后提示识别出的类型；失败由全局错误提示处理。 */
export function useRowUpload() {
  const upload = useUploadToExpense();
  return (expenseId: number, files: File[]) =>
    upload.mutate(
      { id: expenseId, files },
      {
        onSuccess: (detail) =>
          notifications.show({ color: 'ink', title: '补传完成', message: uploadResultMessage(detail, files.length) }),
      },
    );
}
