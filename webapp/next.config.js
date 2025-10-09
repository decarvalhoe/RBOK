const { loadEnvConfig } = require('@next/env');

loadEnvConfig(process.cwd());

const nextConfig = {
  reactStrictMode: true,
};

module.exports = nextConfig;
