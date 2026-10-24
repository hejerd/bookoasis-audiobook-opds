import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { remapClientBuildPaths, createClientBuildPathRemapPlugin } from './remap-client-build-paths.mjs';

const root = path.resolve('build-fixture/readest');
const prefix = pathToFileURL(root + path.sep).href;

test('remaps all build module URLs and retains their relative suffix', () => {
  const input = `${prefix}node_modules/zip/lib.js ${prefix}packages/pdf/pdf.mjs`;
  assert.equal(remapClientBuildPaths(input, root), 'file:///build/readest/node_modules/zip/lib.js file:///build/readest/packages/pdf/pdf.mjs');
});
test('preserves network URLs, sibling roots and runtime expressions', () => {
  const input = `${pathToFileURL(root + '-other/lib.js').href} https://example.org/a.js document.baseURI`;
  assert.equal(remapClientBuildPaths(input, root), input);
});
test('handles URL-encoded source roots', () => {
  const spaced = path.resolve('build fixture/readest');
  assert.equal(remapClientBuildPaths(pathToFileURL(path.join(spaced, 'lib.js')).href, spaced), 'file:///build/readest/lib.js');
});
test('updates only JavaScript assets before content hashing', () => {
  let processAssets; const updates=[];
  const webpack={Compilation:{PROCESS_ASSETS_STAGE_OPTIMIZE_SIZE:400},sources:{RawSource:class { constructor(value){this.value=value;} }}};
  const compilation={hooks:{processAssets:{tap(options,callback){assert.equal(options.stage,410);processAssets=callback;}}},updateAsset(name,value){updates.push([name,value.value]);}};
  createClientBuildPathRemapPlugin(webpack,root).apply({hooks:{thisCompilation:{tap(_name,callback){callback(compilation);}}}});
  processAssets({'a.js':{source:()=>`${prefix}lib.js`},'b.css':{source:()=>`${prefix}lib.js`},'c.js':{source:()=> 'https://example.org/lib.js'}});
  assert.deepEqual(updates,[['a.js','file:///build/readest/lib.js']]);
});
