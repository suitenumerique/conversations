import type { AppProps } from 'next/app';
import Head from 'next/head';
import { useTranslation } from 'react-i18next';

import { AppProvider, productName } from '@/core/';
import { useCunninghamTheme } from '@/cunningham';
import '@/i18n/initI18n';
import { NextPageWithLayout } from '@/types/next';

import './globals.css';

type AppPropsWithLayout = AppProps & {
  Component: NextPageWithLayout;
};

export default function App({ Component, pageProps }: AppPropsWithLayout) {
  const getLayout = Component.getLayout ?? ((page) => page);
  const { t } = useTranslation();
  const { componentTokens } = useCunninghamTheme();
  const favicon = componentTokens['favicon'];

  return (
    <>
      <Head>
        <title>{productName}</title>
        <meta property="og:title" content={productName} key="title" />
        <meta
          name="description"
          content={t(
            `${productName}: Your new companion to use AI efficiently, intuitively, and securely.`,
          )}
        />
        <link rel="icon" href={favicon['ico']} sizes="any" />
        <link rel="icon" href={favicon['png-light']} type="image/png" />
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
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>
      <AppProvider>{getLayout(<Component {...pageProps} />)}</AppProvider>
    </>
  );
}
