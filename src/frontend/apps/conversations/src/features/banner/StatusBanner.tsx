import { useConfig } from '@/core/config';

import { Banner } from './Banner';

export const StatusBanner = () => {
  const { data: config } = useConfig();
  const banner = config?.status_banner;

  if (!banner) {
    return null;
  }

  return <Banner {...banner} />;
};
