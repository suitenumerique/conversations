import '@gouvfr-lasuite/ui-kit/style';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import '@/i18n/initI18n';

import { App } from './App';
import './globals.css';

createRoot(document.getElementById('root') as HTMLElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
