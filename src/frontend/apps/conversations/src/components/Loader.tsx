import dynamic from 'next/dynamic';

import searchingAnimation from '@/assets/lotties/searching';

const Lottie = dynamic(() => import('lottie-react'), { ssr: false });

export function Loader() {
  return (
    <div role="status">
      <Lottie
        animationData={searchingAnimation}
        loop
        autoplay
        style={{ width: 24, height: 24 }}
      />
    </div>
  );
}
