import Lottie from 'react-lottie';

import searchingAnimation from '@/assets/lotties/searching';

export const Loader = () => {
  const LoaderOptions = {
    loop: true,
    autoplay: true,
    animationData: searchingAnimation,
    rendererSettings: {
      preserveAspectRatio: 'xMidYMid slice',
    },
  } as const;

  return (
    <div>
      <Lottie options={LoaderOptions} height={24} width={24} />
    </div>
  );
};
