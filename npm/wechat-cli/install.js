#!/usr/bin/env node
'use strict';

const fs = require('fs');
const metadata = require('./package-metadata.json');
const PLATFORM_PACKAGES = metadata.platform_packages;
const ROOT_PACKAGE = metadata.root_package;

const platformKey = `${process.platform}-${process.arch}`;
const pkg = PLATFORM_PACKAGES[platformKey];

if (!pkg) {
  console.log(`wechat-cli: no published binary package for ${platformKey}, skipping postinstall`);
  console.log(`wechat-cli: wrapper package is ${ROOT_PACKAGE}`);
  process.exit(0);
}

// Try to find and chmod the binary
const ext = process.platform === 'win32' ? '.exe' : '';

try {
  const binaryPath = require.resolve(`${pkg}/bin/wechat-cli${ext}`);
  if (process.platform !== 'win32') {
    fs.chmodSync(binaryPath, 0o755);
    console.log(`wechat-cli: set executable permission for ${platformKey}`);
  }
} catch {
  // Platform package was not installed (npm --no-optional or unsupported)
  console.log(`wechat-cli: optional platform package ${pkg} was not installed for ${platformKey}`);
  console.log(`wechat-cli: this usually means npm skipped optionalDependencies for ${ROOT_PACKAGE}`);
  console.log(`wechat-cli: reinstall the wrapper package, for example: npm install -g --force ${ROOT_PACKAGE}`);
}
