module.exports = {
  root: true,
  extends: ['conversations/playwright'],
  parserOptions: {
    tsconfigRootDir: __dirname,
    project: ['./tsconfig.json'],
  },
  ignorePatterns: ['node_modules'],
};
