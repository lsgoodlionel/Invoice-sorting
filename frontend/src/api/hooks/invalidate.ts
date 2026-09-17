import type { QueryClient } from '@tanstack/react-query';
import { WORKFLOW_KEYS } from './keys';

export function invalidateWorkflow(client: QueryClient): Promise<void> {
  return Promise.all(WORKFLOW_KEYS.map((queryKey) => client.invalidateQueries({ queryKey }))).then(() => undefined);
}
