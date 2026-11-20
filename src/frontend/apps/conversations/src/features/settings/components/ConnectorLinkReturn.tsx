import { useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router';

import { useToast } from '@/components/ToastProvider';
import { useConfig } from '@/core';
import { KEY_AUTH } from '@/features/auth/api/useAuthQuery';
import { connectorPresentation } from '@/features/chat/connectors';

/**
 * Tells the user how linking a connector went, when the authorization server
 * sends the browser back with `?connector=<slug>&connector_status=…`, then
 * drops those parameters from the URL. Renders nothing.
 */
export const ConnectorLinkReturn = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const { data: conf } = useConfig();
  const { showToast } = useToast();
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const status = searchParams.get('connector_status');
  const slug = searchParams.get('connector');

  useEffect(() => {
    // Wait for the config, so the toast can name the connector.
    if (!status || !conf) {
      return;
    }

    const connector = conf.CONNECTORS?.find((c) => c.slug === slug);
    const name = connector ? connectorPresentation(connector).label : slug;
    if (status === 'linked') {
      showToast(
        'success',
        t('{{name}} is connected.', { name }),
        undefined,
        5000,
      );
      void queryClient.invalidateQueries({ queryKey: [KEY_AUTH] });
    } else {
      showToast(
        'error',
        name
          ? t('{{name}} could not be connected.', { name })
          : t('The connector could not be connected.'),
        'error',
        5000,
      );
    }

    setSearchParams(
      (params) => {
        params.delete('connector');
        params.delete('connector_status');
        return params;
      },
      { replace: true },
    );
  }, [status, slug, conf, showToast, t, queryClient, setSearchParams]);

  return null;
};
