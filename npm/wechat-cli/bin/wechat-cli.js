#!/usr/bin/env node

const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const metadata = require('../package-metadata.json');
const PLATFORM_PACKAGES = metadata.platform_packages;
const ROOT_PACKAGE = metadata.root_package;

const platformKey = `${process.platform}-${process.arch}`;
const ext = process.platform === 'win32' ? '.exe' : '';

function getBinaryPath() {
  if (process.env.WECHAT_CLI_BINARY) {
    return process.env.WECHAT_CLI_BINARY;
  }

  const pkg = PLATFORM_PACKAGES[platformKey];
  if (!pkg) {
    console.error(`wechat-cli: unsupported platform ${platformKey}`);
    console.error(`Published wrapper package: ${ROOT_PACKAGE}`);
    console.error(`Supported platforms: ${Object.keys(PLATFORM_PACKAGES).join(', ')}`);
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
  console.error(`Expected optional dependency: ${pkg}`);
  console.error(`Reinstall the wrapper package so npm can fetch the matching binary: ${ROOT_PACKAGE}`);
  console.error(`Example: npm install -g --force ${ROOT_PACKAGE}`);
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
