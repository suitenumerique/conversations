import { useEffect } from 'react';

import { productName } from '@/core';

/**
 * Overrides the tab title for the lifetime of a page, restoring the product
 * name on unmount.
 *
 * Set imperatively rather than by rendering a `<title>`: React 19 hoists title
 * tags but does not deduplicate them, so a second one would sit next to the
 * one App renders and the browser would keep whichever came first.
 */
export const useDocumentTitle = (title: string) => {
  useEffect(() => {
    document.title = title;

    return () => {
      document.title = productName;
    };
  }, [title]);
};
