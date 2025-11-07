const crypto = require('crypto');

const { InjectManifest } = require('workbox-webpack-plugin');

const buildId = crypto.randomBytes(256).toString('hex').slice(0, 8);

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  trailingSlash: true,
  images: {
    unoptimized: true,
  },
  compiler: {
    // Enables the styled-components SWC transform
    styledComponents: true,
  },
  generateBuildId: () => buildId,
  env: {
    NEXT_PUBLIC_BUILD_ID: buildId,
  },
  webpack(config, { isServer, dev, webpack }) {
    // Only configure service worker for client-side builds in production
    if (!isServer && !dev) {
      const path = require('path');
      config.plugins.push(
        new InjectManifest({
          swSrc: path.join(__dirname, 'public', 'sw.src.js'),
          swDest: path.join(__dirname, 'public', 'sw.js'), // Output compiled SW to public, Next.js will copy to out/
          exclude: [
            /\.map$/,
            /manifest$/,
            /\.htaccess$/,
            /service-worker\.js$/,
            /sw\.js$/,
          ],
          // Maximum file size to cache in bytes (5MB)
          maximumFileSizeToCacheInBytes: 5 * 1024 * 1024,
          // Compile the service worker with webpack
          compileSrc: true,
        })
      );
    }

    // Grab the existing rule that handles SVG imports
    const fileLoaderRule = config.module.rules.find((rule) =>
      rule.test?.test?.('.svg'),
    );

    config.module.rules.push(
      // Reapply the existing rule, but only for svg imports ending in ?url
      {
        ...fileLoaderRule,
        test: /\.svg$/i,
        resourceQuery: /url/, // *.svg?url
      },
      // Convert all other *.svg imports to React components
      {
        test: /\.svg$/i,
        issuer: fileLoaderRule.issuer,
        resourceQuery: { not: [...fileLoaderRule.resourceQuery.not, /url/] }, // exclude if *.svg?url
        use: ['@svgr/webpack'],
      },
    );

    // Modify the file loader rule to ignore *.svg, since we have it handled now.
    fileLoaderRule.exclude = /\.svg$/i;

    // Formula rendering in markdown, replace dollar-sign with \(...\) and \[...\]
    // https://github.com/remarkjs/remark-math/issues/39#issuecomment-2636184992
    config.resolve.alias['micromark-extension-math'] =
      'micromark-extension-llm-math';

    return config;
  },
};

module.exports = nextConfig;
