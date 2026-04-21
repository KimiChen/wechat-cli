#!/usr/bin/env node

const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const PLATFORM_PACKAGES = {
  'darwin-arm64': '@canghe_ai/wechat-cli-darwin-arm64',
  'darwin-x64': '@canghe_ai/wechat-cli-darwin-x64',
  'linux-x64': '@canghe_ai/wechat-cli-linux-x64',
  'linux-arm64': '@canghe_ai/wechat-cli-linux-arm64',
  'win32-x64': '@canghe_ai/wechat-cli-win32-x64',
};

const platformKey = `${process.platform}-${process.arch}`;
const ext = process.platform === 'win32' ? '.exe' : '';

function getBinaryPath() {
  if (process.env.WECHAT_CLI_BINARY) {
    return process.env.WECHAT_CLI_BINARY;
  }

  const pkg = PLATFORM_PACKAGES[platformKey];
  if (!pkg) {
    console.error(`wechat-cli: unsupported platform ${platformKey}`);
    process.exit(1);
  }

  try {
    return require.resolve(`${pkg}/bin/wechat-cli${ext}`);
  } catch {}

  try {
    const modPath = path.join(
      path.dirname(require.resolve(`${pkg}/package.json`)),
      `bin/wechat-cli${ext}`
    );
    if (fs.existsSync(modPath)) {
      return modPath;
    }
  } catch {}

  console.error(`wechat-cli: binary not found for ${platformKey}`);
  console.error(`Missing platform package: ${pkg}`);
  console.error('Try: npm install --force @canghe_ai/wechat-cli');
  process.exit(1);
}

try {
  execFileSync(getBinaryPath(), process.argv.slice(2), {
    stdio: 'inherit',
    env: { ...process.env },
  });
} catch (e) {
  if (e && e.status != null) {
    process.exit(e.status);
  }
  throw e;
}
