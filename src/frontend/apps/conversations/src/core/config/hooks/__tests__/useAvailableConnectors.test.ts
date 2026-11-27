import { renderHook } from '@testing-library/react';

import type { ConnectorConfig } from '../../api/useConfig';
import {
  connectorDescription,
  useAvailableConnectors,
} from '../useAvailableConnectors';

const mockConfig = vi.fn();
vi.mock('../../api/useConfig', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/useConfig')>()),
  useConfig: () => ({ data: mockConfig() as unknown }),
}));

const mockFlagActivated = vi.fn();
vi.mock('@/libs', () => ({
  useAnalytics: () => ({
    isFeatureFlagActivated: (flag: string) =>
      mockFlagActivated(flag) as boolean,
  }),
}));

const connector = (overrides: Partial<ConnectorConfig>): ConnectorConfig => ({
  slug: 'sofia',
  name: 'SofIA',
  description: null,
  icon: null,
  feature_flag: null,
  ...overrides,
});

const available = () =>
  renderHook(() => useAvailableConnectors()).result.current.map(
    ({ slug }) => slug,
  );

beforeEach(() => {
  vi.clearAllMocks();
  mockFlagActivated.mockReturnValue(false);
});

describe('useAvailableConnectors', () => {
  it('lists nothing when the deployment declares nothing', () => {
    mockConfig.mockReturnValue({ FEATURE_FLAGS: {} });

    expect(available()).toEqual([]);
  });

  it('lists nothing before the config is loaded', () => {
    mockConfig.mockReturnValue(undefined);

    expect(available()).toEqual([]);
  });

  it('keeps a connector without a flag, in declaration order', () => {
    mockConfig.mockReturnValue({
      FEATURE_FLAGS: {},
      connectors: [
        connector({ slug: 'sofia' }),
        connector({ slug: 'geo', name: 'GeoContext' }),
      ],
    });

    expect(available()).toEqual(['sofia', 'geo']);
  });

  it('applies each connector flag like any feature flag', () => {
    mockConfig.mockReturnValue({
      FEATURE_FLAGS: {
        'datagouv-connector': 'enabled',
        'docs-connector': 'disabled',
        'beta-connector': 'dynamic',
      },
      connectors: [
        connector({ slug: 'datagouv', feature_flag: 'datagouv-connector' }),
        connector({ slug: 'docs', feature_flag: 'docs-connector' }),
        connector({ slug: 'beta', feature_flag: 'beta-connector' }),
        connector({ slug: 'unknown', feature_flag: 'missing-flag' }),
      ],
    });
    mockFlagActivated.mockImplementation(
      (flag: string) => flag === 'beta-connector',
    );

    expect(available()).toEqual(['datagouv', 'beta']);
  });
});

describe('connectorDescription', () => {
  const described = connector({
    description: { en: 'Open data.', fr: 'Données ouvertes.' },
  });

  it('reads the description in the user language', () => {
    expect(connectorDescription(described, 'fr')).toBe('Données ouvertes.');
  });

  it('falls back from a regional code to its language', () => {
    expect(connectorDescription(described, 'fr-fr')).toBe('Données ouvertes.');
  });

  it('falls back to English, then to any language given', () => {
    expect(connectorDescription(described, 'nl')).toBe('Open data.');
    expect(
      connectorDescription(
        connector({ description: { fr: 'Données ouvertes.' } }),
        'nl',
      ),
    ).toBe('Données ouvertes.');
  });

  it('has nothing to show without a description', () => {
    expect(connectorDescription(connector({}), 'fr')).toBeUndefined();
  });
});
