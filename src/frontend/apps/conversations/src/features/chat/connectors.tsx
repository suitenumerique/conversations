import { ReactNode } from 'react';

import { baseApiUrl } from '@/api';
import DatagouvIcon from '@/assets/icons/uikit-custom/datagouv.svg?react';
import { Icon } from '@/components';
import { ConnectorConfig } from '@/core/config/api/useConfig';

/** How a connector shows in the chat input: its labels, icon and chip style. */
export interface ConnectorPresentation {
  label: string;
  /** Chip text on mobile. */
  shortLabel: string;
  icon: ReactNode;
  chipClassName: string;
}

/**
 * Connectors with their own look. Any other connector the deployment declares
 * shows with its name and a generic icon, so adding one needs no frontend change.
 */
const CUSTOM_PRESENTATIONS: Record<string, ConnectorPresentation> = {
  datagouv: {
    label: 'DataGouv',
    shortLabel: 'Data',
    icon: <DatagouvIcon width={16} height={16} />,
    chipClassName: 'datagouv-chip',
  },
};

export const connectorPresentation = (
  connector: ConnectorConfig,
): ConnectorPresentation =>
  CUSTOM_PRESENTATIONS[connector.slug] ?? {
    label: connector.name,
    shortLabel: connector.name,
    icon: <Icon iconName="hub" $theme="neutral" $variation="tertiary" />,
    chipClassName: 'connector-chip',
  };

/** Whether switching the connector on goes through its authorization page. */
export const connectorNeedsLinking = (connector: ConnectorConfig): boolean =>
  connector.auth === 'user_oauth';

/**
 * Where the browser goes to link the user's account to the connector. The
 * backend sends it on to the authorization server, which sends it back here
 * with `?connector=<slug>&connector_status=linked|error`.
 */
export const connectorLinkUrl = (slug: string): string =>
  `${baseApiUrl()}connectors/${encodeURIComponent(slug)}/oauth/start/`;
