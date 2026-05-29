import { StatusBanner } from '@/core/config/api/useConfig';

import { Banner } from './Banner';

interface BannerStackProps {
  banners: StatusBanner[];
}

export const BannerStack = ({ banners }: BannerStackProps) => {
  if (!banners?.length) {
    return null;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {banners.map((banner, i) => (
        <Banner key={i} {...banner} />
      ))}
    </div>
  );
};
