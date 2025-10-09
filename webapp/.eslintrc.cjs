module.exports = {
  root: true,
  parser: '@typescript-eslint/parser',
  plugins: ['@typescript-eslint', 'tailwindcss'],
  extends: [
    'next/core-web-vitals',
    'plugin:@typescript-eslint/recommended',
    'plugin:tailwindcss/recommended',
    'plugin:prettier/recommended',
  ],
  rules: {
    'tailwindcss/no-custom-classname': 'off',
  },
  settings: {
    tailwindcss: {
      config: 'tailwind.config.js',
    },
  },
};
