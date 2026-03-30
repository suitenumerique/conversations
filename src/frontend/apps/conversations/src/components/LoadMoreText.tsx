import { Icon, IconSize } from '@gouvfr-lasuite/ui-kit';
import { useTranslation } from 'react-i18next';

import { Box } from './Box';
import { Text } from './Text';

type LoadMoreTextProps = {
  ['data-testid']?: string;
};

export const LoadMoreText = ({
  'data-testid': dataTestId,
}: LoadMoreTextProps) => {
  const { t } = useTranslation();

  return (
    <Box
      data-testid={dataTestId}
      $direction="row"
      $align="center"
      $gap="0.4rem"
      $padding={{ horizontal: '2xs', vertical: 'sm' }}
      className="--docs--load-more"
    >
      <Icon name="arrow_downward" color="800" size={IconSize.MEDIUM} />
      <Text $theme="primary" $variation="800">
        {t('Load more')}
      </Text>
    </Box>
  );
};
