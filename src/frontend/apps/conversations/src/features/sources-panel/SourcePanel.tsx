import { createContext, type PropsWithChildren, useContext } from 'react';

/** Réexport legacy pour compatibilité ; préférer `SourcePanel` + `useSourcePanelAnchor`. */
export const SourcesPanelAnchorContext = createContext<HTMLDivElement | null>(
  null,
);

type SourcePanelProps = PropsWithChildren<{
  anchor: HTMLDivElement | null;
}>;

export function SourcePanel({ anchor, children }: SourcePanelProps) {
  return (
    <SourcesPanelAnchorContext.Provider value={anchor}>
      {children}
    </SourcesPanelAnchorContext.Provider>
  );
}

export function useSourcePanelAnchor(): HTMLDivElement | null {
  return useContext(SourcesPanelAnchorContext);
}

/** @deprecated Utiliser `useSourcePanelAnchor`. */
export const useSourcesPanelAnchor = useSourcePanelAnchor;
