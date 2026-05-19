declare module '*.svg' {
  import * as React from 'react';

  const ReactComponent: React.FunctionComponent<
    React.SVGProps<SVGSVGElement> & {
      title?: string;
    }
  >;

  export default ReactComponent;
}

namespace NodeJS {
  interface ProcessEnv {
    NEXT_PUBLIC_PRODUCT_NAME?: string;
    NEXT_PUBLIC_API_ORIGIN?: string;
  }
}
