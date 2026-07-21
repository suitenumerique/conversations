import { useTranslation } from 'react-i18next';
import { BrowserRouter, Outlet, Route, Routes } from 'react-router';

import { AppProvider, productName } from '@/core/';
import { useCunninghamTheme } from '@/cunningham';
import { MainLayout, PageLayout } from '@/layouts';

import Page401 from './pages/401';
import Page403 from './pages/403';
import Page404 from './pages/404';
import ActivationPage from './pages/activation';
import ChatPage from './pages/chat';
import ChatConversationPage from './pages/chat/conversation';
import HomePage from './pages/home';
import LoginPage from './pages/login';
import UnauthorizedPage from './pages/unauthorized';

const MainLayoutRoute = () => (
  <MainLayout>
    <Outlet />
  </MainLayout>
);

const PageLayoutRoute = () => (
  <PageLayout withFooter={false}>
    <Outlet />
  </PageLayout>
);

const AppHead = () => {
  const { t } = useTranslation();
  const { componentTokens } = useCunninghamTheme();
  const favicon = (componentTokens as Record<string, unknown>).favicon as
    | { 'png-light': string; 'png-dark': string }
    | undefined;

  return (
    <>
      <title>{productName}</title>
      <meta property="og:title" content={productName} />
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
    </>
  );
};

export function App() {
  return (
    <BrowserRouter>
      <AppHead />
      <AppProvider>
        <Routes>
          <Route element={<MainLayoutRoute />}>
            <Route path="/" element={<ChatPage />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/chat/:id" element={<ChatConversationPage />} />
          </Route>
          <Route path="/home" element={<HomePage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/activation" element={<ActivationPage />} />
          <Route element={<PageLayoutRoute />}>
            <Route path="/401" element={<Page401 />} />
            <Route path="/403" element={<Page403 />} />
            <Route path="/unauthorized" element={<UnauthorizedPage />} />
            <Route path="*" element={<Page404 />} />
          </Route>
        </Routes>
      </AppProvider>
    </BrowserRouter>
  );
}
