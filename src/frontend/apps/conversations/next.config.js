const crypto = require('crypto');

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
    rules: {
      '*.svg': {
        loaders: ['@svgr/webpack'],
        as: '*.js',
      },
    },
    resolveAlias: {
      'micromark-extension-math': 'micromark-extension-llm-math',
    },
  },
};

module.exports = nextConfig;
