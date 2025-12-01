import dynamic from 'next/dynamic';

const Lottie = dynamic(() => import('lottie-react'), { ssr: false });
import searchingAnimation from '@/assets/lotties/searching';

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
