import path from 'node:path';
import { pathToFileURL } from 'node:url';

// Keep module-relative file URL suffixes while replacing the build machine root.
export function remapClientBuildPaths(source, sourceRoot) {
  const prefix = pathToFileURL(path.resolve(sourceRoot) + path.sep).href;
  return source.split(prefix).join('file:///build/readest/');
}

export function createClientBuildPathRemapPlugin(webpack, sourceRoot) {
  const name = 'BookOasisClientBuildPathRemap';
  return {
    apply(compiler) {
      compiler.hooks.thisCompilation.tap(name, (compilation) => {
        compilation.hooks.processAssets.tap(
          { name, stage: webpack.Compilation.PROCESS_ASSETS_STAGE_OPTIMIZE_SIZE + 10 },
          (assets) => {
            for (const [filename, asset] of Object.entries(assets)) {
              if (!filename.endsWith('.js')) continue;
              const original = asset.source().toString();
              const cleaned = remapClientBuildPaths(original, sourceRoot);
              if (cleaned !== original) {
                compilation.updateAsset(filename, new webpack.sources.RawSource(cleaned));
              }
            }
          },
        );
      });
    },
  };
}
