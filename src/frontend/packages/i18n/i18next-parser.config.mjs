const config = {
  customValueTemplate: {
    message: '${key}',
    description: '${description}',
  },
  input: ['../../apps/conversations/**/*.{ts,tsx}'],
  keepRemoved: false,
  keySeparator: false,
  nsSeparator: false,
  namespaceSeparator: false,
};

export default config;
