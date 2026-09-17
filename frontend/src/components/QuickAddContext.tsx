import { createContext, useContext } from 'react';

export interface QuickAddContextValue {
  openQuickAdd: () => void;
}

export const QuickAddContext = createContext<QuickAddContextValue>({ openQuickAdd: () => undefined });

export const useQuickAdd = () => useContext(QuickAddContext);
