/**
 * Service Worker Registration
 * Registers the service worker for PWA functionality
 */

export function registerServiceWorker() {
  if (
    typeof window !== 'undefined' &&
    'serviceWorker' in navigator &&
    process.env.NODE_ENV === 'production'
  ) {
    window.addEventListener('load', () => {
      const swUrl = '/sw.js';
      let refreshing = false;

      navigator.serviceWorker
        .register(swUrl)
        .then((registration) => {
          // Check for updates every hour
          setInterval(() => {
            registration.update();
          }, 60 * 60 * 1000);

          // Handle updates
          registration.addEventListener('updatefound', () => {
            const newWorker = registration.installing;
            if (newWorker) {
              newWorker.addEventListener('statechange', () => {
                if (
                  newWorker.state === 'installed' &&
                  navigator.serviceWorker.controller
                ) {
                  // New service worker available, prompt user to refresh
                  if (
                    window.confirm(
                      'New version available! Would you like to update?'
                    )
                  ) {
                    newWorker.postMessage({ type: 'SKIP_WAITING' });
                    refreshing = true;
                    globalThis.window.location.reload();
                  }
                }
              });
            }
          });
        })
        .catch(() => {
          // Service worker registration failed; app continues to work without PWA features
        });

      // Handle service worker updates (skip reload if we already triggered one)
      navigator.serviceWorker.addEventListener('controllerchange', () => {
        if (!refreshing) {
          refreshing = true;
          globalThis.window.location.reload();
        }
      });
    });
  }
}

