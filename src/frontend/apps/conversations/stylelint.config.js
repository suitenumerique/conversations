module.exports = {
  extends: ['stylelint-config-standard', 'stylelint-prettier/recommended'],
  rules: {
    'custom-property-pattern': null,
    'selector-class-pattern': null,
    'no-descending-specificity': null,
    'keyframe-block-no-duplicate-selectors': null,
  },
  ignoreFiles: ['out/**/*'],
};
