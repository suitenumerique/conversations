import dynamic from 'next/dynamic';

const Lottie = dynamic(() => import('lottie-react'), { ssr: false });
import searchingAnimation from '@/assets/lotties/searching';

interface LoaderProps {
  size?: number;
}

export function Loader({ size = 24 }: LoaderProps) {
  return (
    <div role="status">
      <Lottie
        animationData={searchingAnimation}
        loop
        autoplay
        style={{ width: size, height: size }}
      />
    </div>
  );
}
