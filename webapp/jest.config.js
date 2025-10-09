/* eslint-disable @typescript-eslint/no-var-requires */
const nextJest = require('next/jest');

const createJestConfig = nextJest({
  dir: './',
});

const customJestConfig = {
  setupFilesAfterEnv: ['<rootDir>/jest.setup.ts'],
  testEnvironment: 'jsdom',
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/$1',
  },
  collectCoverageFrom: [
    '<rootDir>/{app,components,lib}/**/*.{ts,tsx}',
    '!<rootDir>/.next/**',
    '!<rootDir>/app/**/layout.tsx',
    '!<rootDir>/app/**/page.tsx',
    '!<rootDir>/**/types.ts',
  ],
  coverageDirectory: '<rootDir>/coverage',
  coverageReporters: ['text', 'text-summary', 'lcov'],
  coverageThreshold: {
    global: {
      branches: 60,
      functions: 50,
      lines: 70,
      statements: 70,
    },
  },
};

module.exports = createJestConfig(customJestConfig);
