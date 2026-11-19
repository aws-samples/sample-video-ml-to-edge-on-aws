# Third-party licenses

This sample commits no third-party code. The packages below are downloaded at build or
run time and pinned by version, and some are bundled into the deployed assets: the gateway
wheels in the site asset and the validation Lambda layer. These Python files also pin
every package by hash: `requirements-dev.txt`, `requirements-train.txt`,
`ml/train/requirements.txt`, `scripts/requirements/gateway.txt` and
`scripts/requirements/validation-layer.txt`. `requirements-docs.in` and the checkov
version in the CI files pin by version only. The root `requirements.txt` includes the two hash-locked
development files.

## Copyleft components

- **FFmpeg** (libavcodec, libavformat, libavutil, libswresample, libswscale),
  LGPL-2.1-or-later: shared libraries inside the `opencv-python-headless` wheel, in the
  validation Lambda layer and on each gateway. They are dynamically linked and unmodified;
  the licence text ships in the wheel (`cv2/LICENSE-3RD-PARTY.txt`).
- **libgfortran**, GPL-3.0-or-later WITH GCC-exception-3.1: the GCC runtime library inside
  the `numpy` and `opencv-python-headless` wheels, in the validation Lambda layer and on
  each gateway. The GCC Runtime Library Exception permits this use.
- **libquadmath**, LGPL-2.1-or-later: inside the x86_64 `numpy` and `opencv-python-headless`
  wheels that the training job and the CI tests install at run time; the sample does not
  distribute it.
- **npm `case`** 1.6.3, `(MIT OR GPL-3.0-or-later)`: bundled inside `aws-cdk-lib`; the
  sample uses it under MIT.

## Gateway wheels (site/wheels, Python 3.12 arm64; scripts/requirements/gateway.txt)

| Package | Version | License | Bundled components |
|---|---|---|---|
| flatbuffers | 25.12.19 | Apache-2.0 |  |
| numpy | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | Bundles OpenBLAS (BSD-3-Clause), LAPACK (BSD-3-Clause-Attribution), libgfortran (GPL-3.0-or-later WITH GCC-exception-3.1) |
| onnxruntime | 1.31.0 | MIT | ThirdPartyNotices.txt in the wheel |
| opencv-python-headless | 5.0.0.93 | Apache-2.0 | Bundles FFmpeg libavcodec/libavformat/libavutil/libswresample/libswscale (LGPL-2.1-or-later), libaom (BSD-2-Clause), libavif (BSD-2-Clause), libdrm (MIT), libvpx (BSD-3-Clause), OpenSSL libssl/libcrypto (OpenSSL/SSLeay), libpng (Libpng), OpenBLAS (BSD-3-Clause), libgfortran (GPL-3.0-or-later WITH GCC-exception-3.1); cv2/LICENSE-3RD-PARTY.txt in the wheel |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |  |
| protobuf | 7.36.2 | BSD-3-Clause |  |

## Validation Lambda layer (infra/layers/opencv, Python 3.12 arm64; scripts/requirements/validation-layer.txt)

| Package | Version | License | Bundled components |
|---|---|---|---|
| numpy | 2.2.6 | BSD-3-Clause | Bundles OpenBLAS, LAPACK, libgfortran (GPL-3.0-or-later WITH GCC-exception-3.1) |
| opencv-python-headless | 4.10.0.84 | Apache-2.0 | Same bundled libraries as above, FFmpeg under LGPL-2.1-or-later |

## Training job (installed by SageMaker AI at run time; ml/train/requirements.txt, not distributed by the sample)

| Package | Version | License | Bundled components |
|---|---|---|---|
| flatbuffers | 25.12.19 | Apache-2.0 |  |
| ml-dtypes | 0.6.0 | Apache-2.0 |  |
| numpy | 2.5.3 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | Bundles OpenBLAS (BSD-3-Clause), libgfortran (GPL-3.0-or-later WITH GCC-exception-3.1), libquadmath (LGPL-2.1-or-later) |
| onnx | 1.23.2 | Apache-2.0 |  |
| onnxruntime | 1.31.0 | MIT |  |
| opencv-python-headless | 5.0.0.93 | Apache-2.0 | Bundled libraries as in the gateway wheels; the x86_64 wheel also bundles libquadmath (LGPL-2.1-or-later) |
| packaging | 24.2 | Apache-2.0 OR BSD-2-Clause |  |
| protobuf | 6.33.6 | BSD-3-Clause |  |
| typing-extensions | 4.16.0 | PSF-2.0 |  |

## Tests and CI (requirements-dev.txt, requirements-train.txt; not distributed)

`requirements-train.txt` holds every package of `requirements-dev.txt` plus those noted
"training tests".

| Package | Version | License | Note |
|---|---|---|---|
| boto3 | 1.43.113 | Apache-2.0 |  |
| botocore | 1.43.113 | Apache-2.0 |  |
| colorama | 0.4.6 | BSD-3-Clause | Windows only |
| filelock | 4.2.6 | MIT | training tests |
| flatbuffers | 25.12.19 | Apache-2.0 |  |
| fsspec | 2026.9.0 | BSD-3-Clause | training tests |
| iniconfig | 2.3.1 | MIT |  |
| jinja2 | 3.1.6 | BSD-3-Clause | training tests |
| jmespath | 1.1.0 | MIT |  |
| markupsafe | 3.0.4 | BSD-3-Clause | training tests |
| ml-dtypes | 0.6.0 | Apache-2.0 |  |
| mpmath | 1.3.0 | BSD-3-Clause | training tests |
| networkx | 3.7 | BSD-3-Clause | training tests |
| numpy | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | bundled components as in the gateway wheels |
| onnx | 1.23.2 | Apache-2.0 |  |
| onnxruntime | 1.31.0 | MIT |  |
| opencv-python-headless | 5.0.0.93 | Apache-2.0 | bundled components as in the gateway wheels |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |  |
| pluggy | 1.6.0 | MIT |  |
| protobuf | 7.36.2 | BSD-3-Clause |  |
| pygments | 2.21.0 | BSD-2-Clause |  |
| pytest | 9.1.1 | MIT |  |
| python-dateutil | 2.9.0.post0 | Apache-2.0 AND BSD-3-Clause |  |
| s3transfer | 0.19.2 | Apache-2.0 |  |
| setuptools | 84.2.1 | MIT | training tests |
| six | 1.17.0 | MIT |  |
| sympy | 1.14.0 | BSD-3-Clause | training tests |
| torch | 2.14.1 (CPU build off macOS) | Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0 AND MIT | training tests |
| typing-extensions | 4.16.0 | PSF-2.0 |  |
| urllib3 | 2.8.0 | MIT |  |

## CI gate and documentation tools (not distributed)

| Package | Version | Source | License |
|---|---|---|---|
| checkov | 3.3.1 | `CHECKOV_VERSION` in `.github/workflows/ci.yml` | Apache-2.0 |
| diagrams | 0.25.1 | `requirements-docs.in` | MIT |
| pillow | 13.0.0 | `requirements-docs.in` | MIT-CMU |

Redrawing the diagram also needs the Graphviz `dot` binary (EPL-1.0) from the operating
system's package manager.

## npm runtime dependencies of the CDK app (infra/package-lock.json)

| Package | Version | License | Note |
|---|---|---|---|
| @aws-cdk/asset-awscli-v1 | 2.2.292 | Apache-2.0 |  |
| @aws-cdk/asset-node-proxy-agent-v6 | 2.1.3 | Apache-2.0 |  |
| @aws-cdk/cloud-assembly-api | 2.2.6 | Apache-2.0 | bundled in aws-cdk-lib |
| @aws-cdk/cloud-assembly-schema | 54.26.0 | Apache-2.0 |  |
| @aws/cloudformation-validate | 1.12.1 | Apache-2.0 | bundled in aws-cdk-lib |
| @balena/dockerignore | 1.0.2 | Apache-2.0 | bundled in aws-cdk-lib |
| aws-cdk-lib | 2.273.0 | Apache-2.0 |  |
| balanced-match | 4.0.4 | MIT | bundled in aws-cdk-lib |
| brace-expansion | 5.0.12 | MIT | bundled in aws-cdk-lib |
| case | 1.6.3 | (MIT OR GPL-3.0-or-later) | bundled in aws-cdk-lib; dual-licensed, used under MIT |
| constructs | 10.8.1 | Apache-2.0 |  |
| fs-extra | 11.3.6 | MIT | bundled in aws-cdk-lib |
| graceful-fs | 4.2.11 | ISC | bundled in aws-cdk-lib |
| ignore | 5.3.2 | MIT | bundled in aws-cdk-lib |
| jsonfile | 6.2.1 | MIT | bundled in aws-cdk-lib |
| jsonschema | 1.5.0 | MIT | bundled in aws-cdk-lib |
| mime-db | 1.52.0 | MIT | bundled in aws-cdk-lib |
| mime-types | 2.1.35 | MIT | bundled in aws-cdk-lib |
| minimatch | 10.2.5 | BlueOak-1.0.0 | bundled in aws-cdk-lib |
| punycode | 2.3.1 | MIT | bundled in aws-cdk-lib |
| semver | 7.8.5 | ISC | bundled in aws-cdk-lib |
| universalify | 2.0.1 | MIT | bundled in aws-cdk-lib |
| yaml | 1.10.3 | ISC | bundled in aws-cdk-lib |

## npm development dependencies of the CDK app (build and test only, not deployed)

| Package | Version | License | Note |
|---|---|---|---|
| @babel/code-frame | 7.29.7 | MIT |  |
| @babel/compat-data | 7.29.7 | MIT |  |
| @babel/core | 7.29.7 | MIT |  |
| @babel/generator | 7.29.8 | MIT |  |
| @babel/helper-compilation-targets | 7.29.7 | MIT |  |
| @babel/helper-globals | 7.29.7 | MIT |  |
| @babel/helper-module-imports | 7.29.7 | MIT |  |
| @babel/helper-module-transforms | 7.29.7 | MIT |  |
| @babel/helper-plugin-utils | 7.29.7 | MIT |  |
| @babel/helper-string-parser | 7.29.7 | MIT |  |
| @babel/helper-validator-identifier | 7.29.7 | MIT |  |
| @babel/helper-validator-option | 7.29.7 | MIT |  |
| @babel/helpers | 7.29.10 | MIT |  |
| @babel/parser | 7.29.9 | MIT |  |
| @babel/plugin-syntax-async-generators | 7.8.4 | MIT |  |
| @babel/plugin-syntax-bigint | 7.8.3 | MIT |  |
| @babel/plugin-syntax-class-properties | 7.12.13 | MIT |  |
| @babel/plugin-syntax-class-static-block | 7.14.5 | MIT |  |
| @babel/plugin-syntax-import-attributes | 7.29.7 | MIT |  |
| @babel/plugin-syntax-import-meta | 7.10.4 | MIT |  |
| @babel/plugin-syntax-json-strings | 7.8.3 | MIT |  |
| @babel/plugin-syntax-jsx | 7.29.7 | MIT |  |
| @babel/plugin-syntax-logical-assignment-operators | 7.10.4 | MIT |  |
| @babel/plugin-syntax-nullish-coalescing-operator | 7.8.3 | MIT |  |
| @babel/plugin-syntax-numeric-separator | 7.10.4 | MIT |  |
| @babel/plugin-syntax-object-rest-spread | 7.8.3 | MIT |  |
| @babel/plugin-syntax-optional-catch-binding | 7.8.3 | MIT |  |
| @babel/plugin-syntax-optional-chaining | 7.8.3 | MIT |  |
| @babel/plugin-syntax-private-property-in-object | 7.14.5 | MIT |  |
| @babel/plugin-syntax-top-level-await | 7.14.5 | MIT |  |
| @babel/plugin-syntax-typescript | 7.29.7 | MIT |  |
| @babel/template | 7.29.7 | MIT |  |
| @babel/traverse | 7.29.10 | MIT |  |
| @babel/types | 7.29.8 | MIT |  |
| @bcoe/v8-coverage | 0.2.3 | MIT |  |
| @cspotcode/source-map-support | 0.8.1 | MIT |  |
| @emnapi/core | 1.10.0 | MIT |  |
| @emnapi/runtime | 1.10.0 | MIT |  |
| @emnapi/wasi-threads | 1.2.1 | MIT |  |
| @isaacs/cliui | 8.0.2 | ISC |  |
| @istanbuljs/load-nyc-config | 1.1.0 | ISC |  |
| @istanbuljs/schema | 0.1.6 | MIT |  |
| @jest/console | 30.5.2 | MIT |  |
| @jest/core | 30.5.2 | MIT |  |
| @jest/diff-sequences | 30.5.0 | MIT |  |
| @jest/environment | 30.5.2 | MIT |  |
| @jest/expect | 30.5.2 | MIT |  |
| @jest/expect-utils | 30.5.2 | MIT |  |
| @jest/fake-timers | 30.5.2 | MIT |  |
| @jest/get-type | 30.5.0 | MIT |  |
| @jest/globals | 30.5.2 | MIT |  |
| @jest/pattern | 30.5.0 | MIT |  |
| @jest/react-is-18 | 18.3.1 | MIT |  |
| @jest/react-is-19 | 19.3.0 | MIT |  |
| @jest/reporters | 30.5.2 | MIT |  |
| @jest/schemas | 30.5.0 | MIT |  |
| @jest/snapshot-utils | 30.5.1 | MIT |  |
| @jest/source-map | 30.5.2 | MIT |  |
| @jest/test-result | 30.5.2 | MIT |  |
| @jest/test-sequencer | 30.5.2 | MIT |  |
| @jest/transform | 30.5.2 | MIT |  |
| @jest/types | 30.5.1 | MIT |  |
| @jridgewell/gen-mapping | 0.3.13 | MIT |  |
| @jridgewell/remapping | 2.3.5 | MIT |  |
| @jridgewell/resolve-uri | 3.1.2 | MIT |  |
| @jridgewell/sourcemap-codec | 1.6.0 | MIT |  |
| @jridgewell/trace-mapping | 0.3.31 | MIT |  |
| @jridgewell/trace-mapping | 0.3.9 | MIT |  |
| @napi-rs/wasm-runtime | 1.2.5 | MIT |  |
| @parcel/watcher | 2.6.0 | MIT |  |
| @parcel/watcher-android-arm64 | 2.6.0 | MIT |  |
| @parcel/watcher-darwin-arm64 | 2.6.0 | MIT |  |
| @parcel/watcher-darwin-x64 | 2.6.0 | MIT |  |
| @parcel/watcher-freebsd-x64 | 2.6.0 | MIT |  |
| @parcel/watcher-linux-arm-glibc | 2.6.0 | MIT |  |
| @parcel/watcher-linux-arm-musl | 2.6.0 | MIT |  |
| @parcel/watcher-linux-arm64-glibc | 2.6.0 | MIT |  |
| @parcel/watcher-linux-arm64-musl | 2.6.0 | MIT |  |
| @parcel/watcher-linux-x64-glibc | 2.6.0 | MIT |  |
| @parcel/watcher-linux-x64-musl | 2.6.0 | MIT |  |
| @parcel/watcher-win32-arm64 | 2.6.0 | MIT |  |
| @parcel/watcher-win32-x64 | 2.6.0 | MIT |  |
| @pkgjs/parseargs | 0.11.0 | MIT |  |
| @pkgr/core | 0.3.6 | MIT |  |
| @sinclair/typebox | 0.34.52 | MIT |  |
| @sinonjs/commons | 3.0.1 | BSD-3-Clause |  |
| @sinonjs/fake-timers | 15.4.0 | BSD-3-Clause |  |
| @tsconfig/node10 | 1.0.13 | MIT |  |
| @tsconfig/node12 | 1.0.11 | MIT |  |
| @tsconfig/node14 | 1.0.3 | MIT |  |
| @tsconfig/node16 | 1.0.4 | MIT |  |
| @tybys/wasm-util | 0.10.4 | MIT |  |
| @types/babel__core | 7.20.5 | MIT |  |
| @types/babel__generator | 7.27.0 | MIT |  |
| @types/babel__template | 7.4.4 | MIT |  |
| @types/babel__traverse | 7.28.0 | MIT |  |
| @types/istanbul-lib-coverage | 2.0.6 | MIT |  |
| @types/istanbul-lib-report | 3.0.3 | MIT |  |
| @types/istanbul-reports | 3.0.4 | MIT |  |
| @types/jest | 30.0.0 | MIT |  |
| @types/node | 24.19.2 | MIT |  |
| @types/stack-utils | 2.0.3 | MIT |  |
| @types/yargs | 17.0.35 | MIT |  |
| @types/yargs-parser | 21.0.3 | MIT |  |
| @ungap/structured-clone | 1.4.0 | ISC |  |
| @unrs/resolver-binding-android-arm-eabi | 1.12.2 | MIT |  |
| @unrs/resolver-binding-android-arm64 | 1.12.2 | MIT |  |
| @unrs/resolver-binding-darwin-arm64 | 1.12.2 | MIT |  |
| @unrs/resolver-binding-darwin-x64 | 1.12.2 | MIT |  |
| @unrs/resolver-binding-freebsd-x64 | 1.12.2 | MIT |  |
| @unrs/resolver-binding-linux-arm-gnueabihf | 1.12.2 | MIT |  |
| @unrs/resolver-binding-linux-arm-musleabihf | 1.12.2 | MIT |  |
| @unrs/resolver-binding-linux-arm64-gnu | 1.12.2 | MIT |  |
| @unrs/resolver-binding-linux-arm64-musl | 1.12.2 | MIT |  |
| @unrs/resolver-binding-linux-loong64-gnu | 1.12.2 | MIT |  |
| @unrs/resolver-binding-linux-loong64-musl | 1.12.2 | MIT |  |
| @unrs/resolver-binding-linux-ppc64-gnu | 1.12.2 | MIT |  |
| @unrs/resolver-binding-linux-riscv64-gnu | 1.12.2 | MIT |  |
| @unrs/resolver-binding-linux-riscv64-musl | 1.12.2 | MIT |  |
| @unrs/resolver-binding-linux-s390x-gnu | 1.12.2 | MIT |  |
| @unrs/resolver-binding-linux-x64-gnu | 1.12.2 | MIT |  |
| @unrs/resolver-binding-linux-x64-musl | 1.12.2 | MIT |  |
| @unrs/resolver-binding-openharmony-arm64 | 1.12.2 | MIT |  |
| @unrs/resolver-binding-wasm32-wasi | 1.12.2 | MIT |  |
| @unrs/resolver-binding-win32-arm64-msvc | 1.12.2 | MIT |  |
| @unrs/resolver-binding-win32-ia32-msvc | 1.12.2 | MIT |  |
| @unrs/resolver-binding-win32-x64-msvc | 1.12.2 | MIT |  |
| acorn | 8.19.0 | MIT |  |
| acorn-walk | 8.3.5 | MIT |  |
| ansi-escapes | 4.3.2 | MIT |  |
| ansi-regex | 5.0.1 | MIT |  |
| ansi-regex | 6.4.0 | MIT |  |
| ansi-styles | 4.3.0 | MIT |  |
| ansi-styles | 5.2.0 | MIT |  |
| ansi-styles | 6.2.3 | MIT |  |
| anymatch | 3.1.3 | ISC |  |
| arg | 4.1.3 | MIT |  |
| argparse | 1.0.10 | MIT |  |
| aws-cdk | 2.1128.0 | Apache-2.0 |  |
| babel-jest | 30.5.2 | MIT |  |
| babel-plugin-istanbul | 8.0.0 | BSD-3-Clause |  |
| babel-plugin-jest-hoist | 30.5.0 | MIT |  |
| babel-preset-current-node-syntax | 1.2.0 | MIT |  |
| babel-preset-jest | 30.5.0 | MIT |  |
| balanced-match | 1.0.2 | MIT |  |
| balanced-match | 4.0.4 | MIT |  |
| baseline-browser-mapping | 2.11.28 | Apache-2.0 |  |
| brace-expansion | 2.1.7 | MIT |  |
| brace-expansion | 5.0.12 | MIT |  |
| browserslist | 4.29.3 | MIT |  |
| bs-logger | 0.2.6 | MIT |  |
| bser | 2.1.2 | MIT |  |
| callsites | 3.1.0 | MIT |  |
| camelcase | 5.3.1 | MIT |  |
| camelcase | 6.3.0 | MIT |  |
| caniuse-lite | 1.0.30001815 | CC-BY-4.0 |  |
| chalk | 4.1.2 | MIT |  |
| char-regex | 1.0.2 | MIT |  |
| ci-info | 4.4.0 | MIT |  |
| cjs-module-lexer | 2.3.0 | MIT |  |
| cliui | 8.0.1 | ISC |  |
| co | 4.6.0 | MIT |  |
| collect-v8-coverage | 1.0.3 | MIT |  |
| color-convert | 2.0.1 | MIT |  |
| color-name | 1.1.4 | MIT |  |
| convert-source-map | 2.0.0 | MIT |  |
| create-require | 1.1.1 | MIT |  |
| cross-spawn | 7.0.6 | MIT |  |
| debug | 4.4.3 | MIT |  |
| dedent | 1.7.2 | MIT |  |
| deepmerge | 4.3.1 | MIT |  |
| detect-libc | 2.1.2 | Apache-2.0 |  |
| detect-newline | 3.1.0 | MIT |  |
| diff | 4.0.4 | BSD-3-Clause |  |
| eastasianwidth | 0.2.0 | MIT |  |
| electron-to-chromium | 1.5.453 | ISC |  |
| emittery | 0.13.1 | MIT |  |
| emoji-regex | 8.0.0 | MIT |  |
| emoji-regex | 9.2.2 | MIT |  |
| error-ex | 1.3.4 | MIT |  |
| es-module-lexer | 2.3.2 | MIT |  |
| escalade | 3.2.0 | MIT |  |
| escape-string-regexp | 2.0.0 | MIT |  |
| esprima | 4.0.1 | BSD-2-Clause |  |
| execa | 5.1.1 | MIT |  |
| exit-x | 0.2.2 | MIT |  |
| expect | 30.5.2 | MIT |  |
| fast-json-stable-stringify | 2.1.0 | MIT |  |
| fb-watchman | 2.0.4 | MIT |  |
| fdir | 6.5.0 | MIT |  |
| find-up | 4.1.0 | MIT |  |
| foreground-child | 3.3.1 | ISC |  |
| gensync | 1.0.0-beta.2 | MIT |  |
| get-caller-file | 2.0.5 | ISC |  |
| get-package-type | 0.1.0 | MIT |  |
| get-stream | 6.0.1 | MIT |  |
| glob | 10.5.0 | ISC |  |
| glob | 13.0.6 | BlueOak-1.0.0 |  |
| graceful-fs | 4.2.11 | ISC |  |
| handlebars | 4.7.10 | MIT |  |
| has-flag | 4.0.0 | MIT |  |
| html-escaper | 2.0.2 | MIT |  |
| human-signals | 2.1.0 | Apache-2.0 |  |
| import-local | 3.2.0 | MIT |  |
| imurmurhash | 0.1.4 | MIT |  |
| is-arrayish | 0.2.1 | MIT |  |
| is-extglob | 2.1.1 | MIT |  |
| is-fullwidth-code-point | 3.0.0 | MIT |  |
| is-generator-fn | 2.1.0 | MIT |  |
| is-glob | 4.0.3 | MIT |  |
| is-stream | 2.0.1 | MIT |  |
| isexe | 2.0.0 | ISC |  |
| istanbul-lib-coverage | 3.2.2 | BSD-3-Clause |  |
| istanbul-lib-instrument | 6.0.3 | BSD-3-Clause |  |
| istanbul-lib-report | 3.0.1 | BSD-3-Clause |  |
| istanbul-lib-source-maps | 5.0.6 | BSD-3-Clause |  |
| istanbul-reports | 3.2.0 | BSD-3-Clause |  |
| jackspeak | 3.4.3 | BlueOak-1.0.0 |  |
| jest | 30.5.2 | MIT |  |
| jest-changed-files | 30.5.1 | MIT |  |
| jest-circus | 30.5.2 | MIT |  |
| jest-cli | 30.5.2 | MIT |  |
| jest-config | 30.5.2 | MIT |  |
| jest-diff | 30.5.2 | MIT |  |
| jest-docblock | 30.5.0 | MIT |  |
| jest-each | 30.5.2 | MIT |  |
| jest-environment-node | 30.5.2 | MIT |  |
| jest-haste-map | 30.5.1 | MIT |  |
| jest-leak-detector | 30.5.1 | MIT |  |
| jest-matcher-utils | 30.5.2 | MIT |  |
| jest-message-util | 30.5.1 | MIT |  |
| jest-mock | 30.5.2 | MIT |  |
| jest-regex-util | 30.5.0 | MIT |  |
| jest-resolve | 30.5.1 | MIT |  |
| jest-resolve-dependencies | 30.5.2 | MIT |  |
| jest-runner | 30.5.2 | MIT |  |
| jest-runtime | 30.5.2 | MIT |  |
| jest-snapshot | 30.5.2 | MIT |  |
| jest-util | 30.5.1 | MIT |  |
| jest-validate | 30.5.1 | MIT |  |
| jest-watcher | 30.5.2 | MIT |  |
| jest-worker | 30.5.1 | MIT |  |
| js-tokens | 4.0.0 | MIT |  |
| js-yaml | 3.15.2 | MIT |  |
| jsesc | 3.1.0 | MIT |  |
| json-parse-even-better-errors | 2.3.1 | MIT |  |
| json5 | 2.2.3 | MIT |  |
| leven | 3.1.0 | MIT |  |
| lines-and-columns | 1.2.4 | MIT |  |
| locate-path | 5.0.0 | MIT |  |
| lodash.memoize | 4.1.2 | MIT |  |
| lru-cache | 10.4.3 | ISC |  |
| lru-cache | 11.5.3 | BlueOak-1.0.0 |  |
| lru-cache | 5.1.1 | ISC |  |
| make-dir | 4.0.0 | MIT |  |
| make-error | 1.3.6 | ISC |  |
| merge-stream | 2.0.0 | MIT |  |
| mimic-fn | 2.1.0 | MIT |  |
| minimatch | 10.2.6 | BlueOak-1.0.0 |  |
| minimatch | 9.0.9 | ISC |  |
| minimist | 1.2.8 | MIT |  |
| minipass | 7.1.3 | BlueOak-1.0.0 |  |
| ms | 2.1.3 | MIT |  |
| napi-postinstall | 0.3.4 | MIT |  |
| natural-compare | 1.4.0 | MIT |  |
| neo-async | 2.6.2 | MIT |  |
| node-addon-api | 7.1.1 | MIT |  |
| node-int64 | 0.4.0 | MIT |  |
| node-releases | 2.0.58 | MIT |  |
| normalize-path | 3.0.0 | MIT |  |
| npm-run-path | 4.0.1 | MIT |  |
| onetime | 5.1.2 | MIT |  |
| p-limit | 2.3.0 | MIT |  |
| p-limit | 3.1.0 | MIT |  |
| p-locate | 4.1.0 | MIT |  |
| p-try | 2.2.0 | MIT |  |
| package-json-from-dist | 1.0.1 | BlueOak-1.0.0 |  |
| parse-json | 5.2.0 | MIT |  |
| path-exists | 4.0.0 | MIT |  |
| path-key | 3.1.1 | MIT |  |
| path-scurry | 1.11.1 | BlueOak-1.0.0 |  |
| path-scurry | 2.0.2 | BlueOak-1.0.0 |  |
| picocolors | 1.1.1 | ISC |  |
| picomatch | 2.3.2 | MIT |  |
| picomatch | 4.0.7 | MIT |  |
| pirates | 4.0.7 | MIT |  |
| pkg-dir | 4.2.0 | MIT |  |
| pretty-format | 30.5.1 | MIT |  |
| pure-rand | 7.0.1 | MIT |  |
| require-directory | 2.1.1 | MIT |  |
| resolve-cwd | 3.0.0 | MIT |  |
| resolve-from | 5.0.0 | MIT |  |
| semver | 6.3.1 | ISC |  |
| semver | 7.8.5 | ISC |  |
| shebang-command | 2.0.0 | MIT |  |
| shebang-regex | 3.0.0 | MIT |  |
| signal-exit | 3.0.7 | ISC |  |
| signal-exit | 4.1.0 | ISC |  |
| slash | 3.0.0 | MIT |  |
| source-map | 0.6.1 | BSD-3-Clause |  |
| sprintf-js | 1.0.3 | BSD-3-Clause |  |
| stack-utils | 2.0.6 | MIT |  |
| string-length | 4.0.2 | MIT |  |
| string-width | 4.2.3 | MIT |  |
| string-width | 5.1.2 | MIT |  |
| string-width-cjs | 4.2.3 | MIT |  |
| strip-ansi | 6.0.1 | MIT |  |
| strip-ansi | 7.2.0 | MIT |  |
| strip-ansi-cjs | 6.0.1 | MIT |  |
| strip-bom | 4.0.0 | MIT |  |
| strip-final-newline | 2.0.0 | MIT |  |
| strip-json-comments | 3.1.1 | MIT |  |
| supports-color | 7.2.0 | MIT |  |
| supports-color | 8.1.1 | MIT |  |
| synckit | 0.11.13 | MIT |  |
| test-exclude | 7.0.2 | ISC |  |
| ts-jest | 29.4.14 | MIT |  |
| ts-node | 10.9.2 | MIT |  |
| tslib | 2.8.1 | 0BSD |  |
| type-detect | 4.0.8 | MIT |  |
| type-fest | 0.21.3 | (MIT OR CC0-1.0) |  |
| type-fest | 4.41.0 | (MIT OR CC0-1.0) |  |
| typescript | 5.9.3 | Apache-2.0 |  |
| uglify-js | 3.19.3 | BSD-2-Clause |  |
| undici-types | 7.24.6 | MIT |  |
| unrs-resolver | 1.12.2 | MIT |  |
| update-browserslist-db | 1.3.4 | MIT |  |
| v8-compile-cache-lib | 3.0.1 | MIT |  |
| v8-to-istanbul | 9.3.0 | ISC |  |
| which | 2.0.2 | ISC |  |
| wordwrap | 1.0.0 | MIT |  |
| wrap-ansi | 7.0.0 | MIT |  |
| wrap-ansi | 8.1.0 | MIT |  |
| wrap-ansi-cjs | 7.0.0 | MIT |  |
| write-file-atomic | 5.0.1 | ISC |  |
| y18n | 5.0.8 | ISC |  |
| yallist | 3.1.1 | ISC |  |
| yargs | 17.7.3 | MIT |  |
| yargs-parser | 21.1.1 | ISC |  |
| yn | 3.1.1 | MIT |  |
| yocto-queue | 0.1.0 | MIT |  |
