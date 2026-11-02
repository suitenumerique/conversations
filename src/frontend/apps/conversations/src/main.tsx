// First on purpose: modules run in import order, and dependencies need the
// polyfills in place.
// eslint-disable-next-line import-x/order
import '@/utils/polyfills';

import '@gouvfr-lasuite/ui-kit/style';
import { createRoot } from 'react-dom/client';

import '@/i18n/initI18n';

import { App } from './App';
import './globals.css';

const root = document.getElementById('root');

if (!root) {
  throw new Error('Missing #root element in index.html');
}

createRoot(root).render(<App />);
