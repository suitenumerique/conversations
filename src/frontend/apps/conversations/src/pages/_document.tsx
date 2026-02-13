import { Head, Html, Main, NextScript } from 'next/document';

export default function RootLayout() {
  return (
    <Html>
      <Head>
        <link rel="manifest" href="/manifest.json" />
        <meta name="theme-color" content="#1B2E5F" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="default" />
        <meta name="apple-mobile-web-app-title" content="Assistant" />
        <meta name="mobile-web-app-capable" content="yes" />
        <meta name="msapplication-TileColor" content="#1B2E5F" />
        <meta name="msapplication-tap-highlight" content="no" />
        <link
          rel="apple-touch-icon"
          sizes="180x180"
          href="/assets/apple-touch-icon.png"
        />
      </Head>
      <body suppressHydrationWarning={process.env.NODE_ENV === 'development'}>
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
