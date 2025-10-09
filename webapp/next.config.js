/* eslint-disable @typescript-eslint/no-var-requires */
const { loadEnvConfig } = require('@next/env');

loadEnvConfig(process.cwd());

const nextConfig = {
  reactStrictMode: true,
};

module.exports = nextConfig;
