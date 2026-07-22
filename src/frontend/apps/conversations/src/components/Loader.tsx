import { Suspense, lazy } from 'react';

import searchingAnimation from '@/assets/lotties/searching';

const Lottie = lazy(() => import('lottie-react'));

export function Loader() {
  return (
    <div role="status">
      <Suspense fallback={null}>
        <Lottie
          animationData={searchingAnimation}
          loop
          autoplay
          style={{ width: 24, height: 24 }}
        />
      </Suspense>
    </div>
  );
}
