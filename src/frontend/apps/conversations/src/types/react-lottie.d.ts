declare module 'react-lottie' {
  import { Component } from 'react';

  interface LottieOptions {
    loop?: boolean;
    autoplay?: boolean;
    animationData: Record<string, unknown>;
    rendererSettings?: {
      preserveAspectRatio?: string;
    };
  }

  interface LottieProps {
    options: LottieOptions;
    height?: number | string;
    width?: number | string;
    isStopped?: boolean;
    isPaused?: boolean;
    speed?: number;
    direction?: number;
    segments?: number[];
    goToAndPlay?: number;
    goToAndStop?: number;
    lottieRef?: (ref: unknown) => void;
  }

  export default class Lottie extends Component<LottieProps> {}
}
