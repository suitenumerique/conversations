const crypto = require('crypto');
const path = require('path');

const buildId = crypto.randomBytes(256).toString('hex').slice(0, 8);

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  trailingSlash: true,
  images: {
    unoptimized: true,
  },
  compiler: {
    styledComponents: true,
  },
  generateBuildId: () => buildId,
  env: {
    NEXT_PUBLIC_BUILD_ID: buildId,
  },
  turbopack: {
    root: path.resolve(__dirname, '../..'),
    rules: {
      '*.svg': {
        loaders: ['@svgr/webpack'],
        as: '*.js',
      },
    },
    resolveAlias: {
      'micromark-extension-math': 'micromark-extension-llm-math',
      '@gouvfr-lasuite/cunningham-react': '@gouvfr-lasuite/cunningham-react',
      '@gouvfr-lasuite/ui-kit/node_modules/@gouvfr-lasuite/cunningham-react':
        '@gouvfr-lasuite/cunningham-react',
    },
  },
  webpack: (config) => {
    config.resolve.alias = {
      ...(config.resolve.alias || {}),
      '@gouvfr-lasuite/cunningham-react': path.resolve(
        __dirname,
        '../../node_modules/@gouvfr-lasuite/cunningham-react',
      ),
      '@gouvfr-lasuite/ui-kit/node_modules/@gouvfr-lasuite/cunningham-react':
        path.resolve(
          __dirname,
          '../../node_modules/@gouvfr-lasuite/cunningham-react',
        ),
    };
    return config;
  },
};

module.exports = nextConfig;
