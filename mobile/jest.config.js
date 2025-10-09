module.exports = {
  preset: 'react-native',
  transform: {
    '^.+\\.(js|jsx|ts|tsx)$': 'babel-jest',
  },
  setupFilesAfterEnv: ['<rootDir>/jest.setup.ts'],
  transformIgnorePatterns: [
    'node_modules/(?!(react-native|@react-native|@react-navigation|@tanstack/react-query|@tanstack/react-query-persist-client|@tanstack/query-sync-storage-persister|react-native-mmkv|react-native-gesture-handler)/)'
  ],
  testPathIgnorePatterns: ['<rootDir>/node_modules/'],
  moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx', 'json', 'node'],
  moduleNameMapper: {
    '^react-native-reanimated$': '<rootDir>/jest.reanimated-mock.js',
  },
  collectCoverageFrom: [
    '<rootDir>/src/**/*.{ts,tsx}',
    '!<rootDir>/src/**/__tests__/**',
    '!<rootDir>/src/**/types.ts',
  ],
  coverageDirectory: '<rootDir>/coverage',
  coverageReporters: ['text', 'text-summary', 'lcov'],
  coverageThreshold: {
    global: {
      branches: 50,
      functions: 60,
      lines: 60,
      statements: 60,
    },
  },
};
