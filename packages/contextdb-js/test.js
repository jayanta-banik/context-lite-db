const assert = require("node:assert/strict");
const { resolveBinaryPath } = require("./index");

assert.ok(resolveBinaryPath());
console.log("contextdb-js binary resolution ok");
