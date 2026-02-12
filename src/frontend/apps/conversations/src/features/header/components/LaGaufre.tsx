// import { Gaufre } from '@gouvfr-lasuite/integration';
import { Button } from '@openfun/cunningham-react';
import Script from 'next/script';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';

import { useCunninghamTheme } from '@/cunningham';

declare global {
  interface Window {
    _lasuite_widget?: unknown[];
  }
}

export const LaGaufre = () => {
  const { t } = useTranslation();
  const { isDarkMode } = useCunninghamTheme();

  useEffect(() => {
    const wrapper = document.querySelector('[data-gaufre-button-wrapper]');
    const button = wrapper?.querySelector('button') as HTMLButtonElement;
    if (button && !button.id) {
      button.id = 'gaufre_button';
      button.setAttribute('aria-expanded', 'false');
    }

    const applyStyles = () => {
      const shadowHost = document.querySelector(
        '#lasuite-widget-lagaufre-shadow',
      );
      if (!shadowHost?.shadowRoot) return;

      const shadowRoot = shadowHost.shadowRoot;

      // Injecter les styles dans le shadow DOM
      let styleElement = shadowRoot.querySelector('#c__la-gaufre-styles');
      if (!styleElement) {
        styleElement = document.createElement('style');
        styleElement.id = 'c__la-gaufre-styles';
        shadowRoot.appendChild(styleElement);
      }

      (styleElement as HTMLStyleElement).textContent = `
        .c__la-gaufre {
          z-index: 1000000000;
          background-color: var(--c--contextuals--background--surface--primary) !important;
          border-color: var(--c--contextuals--border--surface--primary);
          #more-apps {
            border-color: var(--c--contextuals--border--surface--primary);
            color: var(--c--contextuals--content--semantic--neutral--tertiary);
          }
          #show-more-button:hover {
            color: var(--c--contextuals--content--semantic--neutral--tertiary);
            background-color: var(--c--contextuals--background--semantic--neutral--tertiary);
          }
          .service-card:hover {
            background-color: var(--c--contextuals--background--semantic--overlay--primary);
          }
          .service-name {
            font-weight: 500;
            color: var(--c--contextuals--content--semantic--brand--tertiary) !important;
          }
        }
      `;

      const wrapperDialog = shadowRoot.querySelector(
        '.wrapper-dialog',
      ) as HTMLElement;
      if (wrapperDialog) {
        wrapperDialog.classList.add('c__la-gaufre');
      }
    };

    setTimeout(applyStyles, 500);
    // Réessayer périodiquement au cas où le widget se charge plus tard
    const interval = setInterval(applyStyles, 1000);
    return () => clearInterval(interval);
  }, [isDarkMode]);

  return (
    <>
      <div data-gaufre-button-wrapper>
        <Button
          variant="tertiary"
          className="!w-10 !h-10 !p-0 !min-w-0"
          aria-label="Les services de LaSuite"
          aria-expanded="false"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 18 18"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <defs>
              <path
                fill="var(--c--contextuals--content--semantic--brand--tertiary)"
                id="square"
                d="M2.7959 0.5C3.26483 0.5 3.49956 0.49985 3.68848 0.564453C4.03934 0.684581 4.31542 0.960658 4.43555 1.31152C4.50015 1.50044 4.5 1.73517 4.5 2.2041V2.7959C4.5 3.26483 4.50015 3.49956 4.43555 3.68848C4.31542 4.03934 4.03934 4.31542 3.68848 4.43555C3.49956 4.50015 3.26483 4.5 2.7959 4.5H2.2041C1.73517 4.5 1.50044 4.50015 1.31152 4.43555C0.960658 4.31542 0.684581 4.03934 0.564453 3.68848C0.49985 3.49956 0.5 3.26483 0.5 2.7959V2.2041C0.5 1.73517 0.49985 1.50044 0.564453 1.31152C0.684581 0.960658 0.960658 0.684581 1.31152 0.564453C1.50044 0.49985 1.73517 0.5 2.2041 0.5H2.7959Z"
              />
            </defs>
            <use href="#square" transform="translate(0, 0)" />
            <use href="#square" transform="translate(6.5, 0)" />
            <use href="#square" transform="translate(13, 0)" />
            <use href="#square" transform="translate(0, 6.5)" />
            <use href="#square" transform="translate(6.5, 6.5)" />
            <use href="#square" transform="translate(13, 6.5)" />
            <use href="#square" transform="translate(0, 13)" />
            <use href="#square" transform="translate(6.5, 13)" />
            <use href="#square" transform="translate(13, 13)" />
          </svg>
        </Button>
      </div>
      <Script
        src="https://static.suite.anct.gouv.fr/widgets/lagaufre.js"
        strategy="lazyOnload"
        onLoad={() => {
          const button = document.getElementById('gaufre_button');
          if (button) {
            window._lasuite_widget = window._lasuite_widget || [];
            window._lasuite_widget.push([
              'lagaufre',
              'init',
              {
                api: 'https://lasuite.numerique.gouv.fr/api/services',
                label: 'Services de la Suite numérique',
                closeLabel: 'Fermer le menu',
                headerLabel: 'À propos',
                backgroundColor: isDarkMode ? '#2B303D !important' : '#fff',
                background: isDarkMode
                  ? 'linear-gradient(rgba(62, 93, 281, 0.1) 0, rgba(43, 48, 61, 0.1) 48px)'
                  : 'linear-gradient(#f1f2fd, rgba(255, 255, 255, 1) 48px, #FFF 0%',
                headerLogo: '/assets/lasuite.svg',
                headerUrl: 'https://lasuite.numerique.gouv.fr',
                loadingText: 'Chargement…',
                newWindowLabelSuffix: ' (nouvelle fenêtre)',
                fontFamily: 'Marianne',
                buttonElement: button,
                viewMoreLabel: t('More apps'),
                viewLessLabel: t('Fewer apps'),
                position: () => ({
                  backgroundColor: isDarkMode ? '#1E1E1E' : '#fff',
                  position: 'fixed',
                  top: 65,
                  right: 20,
                }),
              },
            ]);
          }
        }}
      />
    </>
  );
};
