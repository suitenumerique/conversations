import type { AppProps } from 'next/app';
import Head from 'next/head';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';

import { AppProvider, productName } from '@/core/';
import { useCunninghamTheme } from '@/cunningham';
import '@/i18n/initI18n';
import { NextPageWithLayout } from '@/types/next';
import { registerServiceWorker } from '@/utils/registerServiceWorker';

import './globals.css';

type AppPropsWithLayout = AppProps & {
  Component: NextPageWithLayout;
};

export default function App({ Component, pageProps }: AppPropsWithLayout) {
  const getLayout = Component.getLayout ?? ((page) => page);
  const { t } = useTranslation();
  const { componentTokens } = useCunninghamTheme();
  const favicon = (componentTokens as Record<string, unknown>).favicon as
    | { 'png-light': string; 'png-dark': string }
    | undefined;

  useEffect(() => {
    registerServiceWorker();
  }, []);

  return (
    <>
      <Head>
        <title>{productName}</title>
        <meta property="og:title" content={productName} key="title" />
        <meta
          name="description"
          content={t(
            `${productName}: ${t('Your new companion to use AI efficiently, intuitively, and securely.')}`,
          )}
        />
        {favicon && (
          <>
            <link
              rel="icon"
              href={favicon['png-light']}
              type="image/png"
              sizes="any"
            />
            <link
              rel="icon"
              href={favicon['png-light']}
              type="image/png"
              media="(prefers-color-scheme: light)"
            />
            <link
              rel="icon"
              href={favicon['png-dark']}
              type="image/png"
              media="(prefers-color-scheme: dark)"
            />
          </>
        )}
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>
      <AppProvider>{getLayout(<Component {...pageProps} />)}</AppProvider>
    </>
  );
}
