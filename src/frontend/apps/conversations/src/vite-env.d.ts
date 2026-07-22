// Asset and env typings for the Vite build. `vite/client` is deliberately not
// referenced: it types `*.svg` as a URL string, whereas `vite-plugin-svgr` is
// configured here to turn every `.svg` import into a React component.

declare module '*.svg' {
  import * as React from 'react';

  const ReactComponent: React.FunctionComponent<
    React.SVGProps<SVGSVGElement> & {
      title?: string;
    }
  >;

  export default ReactComponent;
}

declare module '*.svg?url' {
  const src: string;
  export default src;
}

declare module '*.png' {
  const src: string;
  export default src;
}

declare module '*.css';

interface ImportMetaEnv {
  readonly DEV: boolean;
  readonly PROD: boolean;
  readonly MODE: string;
  readonly VITE_API_ORIGIN?: string;
  readonly VITE_PRODUCT_NAME?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
