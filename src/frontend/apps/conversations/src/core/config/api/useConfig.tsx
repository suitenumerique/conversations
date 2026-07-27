import { useQuery } from '@tanstack/react-query';
import { Resource } from 'i18next';

import { APIError, errorCauses, fetchAPI } from '@/api';
import { BaseTheme } from '@/cunningham/';
import { FooterType } from '@/features/footer';
import { PostHogConf } from '@/services';

interface ThemeCustomization {
  footer?: FooterType;
  translations?: Resource;
}

export enum FeatureFlagState {
  ENABLED = 'enabled',
  DISABLED = 'disabled',
  DYNAMIC = 'dynamic',
}

interface FeatureFlags {
  [key: string]: FeatureFlagState;
}
export type BannerLevel = 'info' | 'warning' | 'alert';

export interface StatusBanner {
  level: BannerLevel;
  title: string;
  content: string;
}

export interface MaintenanceConfig {
  enabled: boolean;
  message?: string | null;
}

export interface ConfigResponse {
  ACTIVATION_REQUIRED: boolean;
  STATUS_PAGE_URL?: string | null;
  ENVIRONMENT: string;
  FEATURE_FLAGS: FeatureFlags;
  FRONTEND_CSS_URL?: string;
  FRONTEND_CONTACT_EMAIL?: string;
  FRONTEND_DOCUMENTATION_URL?: string;
  FRONTEND_HOMEPAGE_FEATURE_ENABLED?: boolean;
  FRONTEND_THEME?: BaseTheme;
  LANGUAGES: [string, string][];
  LANGUAGE_CODE: string;
  MEDIA_BASE_URL?: string;
  POSTHOG_KEY?: PostHogConf;
  SENTRY_DSN?: string;
  FILE_UPLOAD_MODE?: string;
  FRONTEND_SILENT_LOGIN_ENABLED?: boolean;
  theme_customization?: ThemeCustomization;
  status_banner?: StatusBanner;
  maintenance?: MaintenanceConfig | null;
  chat_upload_accept?: string;
  DOCS_BASE_URL?: string;
  project_files_max_count?: number;
  project_images_max_count?: number;
  attachment_max_size?: number;
}

const LOCAL_STORAGE_KEY = 'conversations_config';
const ONE_HOUR = 1000 * 60 * 60;
const FIVE_MINUTES = 1000 * 60 * 5;

// Read and parsed once per page load instead of on every render. `useConfig`
// has ~19 call sites, several of them in components that render continuously
// while a response streams, and both the localStorage read and the parse are
// synchronous main-thread work over a payload that carries the whole
// translation bundle. The result only ever seeds the query cache, so re-parsing
// it on later renders was pure waste.
let cachedConfig: ConfigResponse | undefined;
let hasReadCachedConfig = false;

function getCachedConfig() {
  if (hasReadCachedConfig) {
    return cachedConfig;
  }
  hasReadCachedConfig = true;

  try {
    const jsonString = localStorage.getItem(LOCAL_STORAGE_KEY);
    cachedConfig = jsonString
      ? (JSON.parse(jsonString) as ConfigResponse)
      : undefined;
  } catch {
    cachedConfig = undefined;
  }

  return cachedConfig;
}

function setCachedConfig(config: ConfigResponse) {
  // Keep the in-memory copy in step, so a query cache reset re-seeds from the
  // freshest config rather than the one read when the page loaded.
  cachedConfig = config;
  hasReadCachedConfig = true;
  localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(config));
}

export const getConfig = async (): Promise<ConfigResponse> => {
  const response = await fetchAPI(`config/`);

  if (!response.ok) {
    throw new APIError('Failed to get the doc', await errorCauses(response));
  }

  const config = response.json() as Promise<ConfigResponse>;
  setCachedConfig(await config);

  return config;
};

export const KEY_CONFIG = 'config';

// Force initial data to be considered stale. Any timestamp at least staleTime
// old does that, so computing it once when the module loads keeps it true.
const INITIAL_DATA_UPDATED_AT = Date.now() - ONE_HOUR;

export function useConfig() {
  return useQuery<ConfigResponse, APIError, ConfigResponse>({
    queryKey: [KEY_CONFIG],
    queryFn: () => getConfig(),
    initialData: getCachedConfig(),
    staleTime: ONE_HOUR,
    initialDataUpdatedAt: INITIAL_DATA_UPDATED_AT,
    refetchInterval: FIVE_MINUTES,
  });
}
