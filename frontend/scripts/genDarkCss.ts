// Writes src/darkTheme.generated.css (usability phase U-1). Run from the frontend folder after a colour class is added:
//   node_modules/.bin/vite-node scripts/genDarkCss.ts
import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { buildDarkCss, colourClassesIn } from '../src/theme/darkMap';

const root = join(__dirname, '..', 'src');

function sources(dir: string): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) {
      if (entry !== 'theme' && entry !== 'audit') files.push(...sources(path));
    } else if (/\.(ts|tsx)$/.test(entry) && !/\.test\.(ts|tsx)$/.test(entry)) {
      files.push(path);
    }
  }
  return files;
}

const classes = sources(root).flatMap((file) => colourClassesIn(readFileSync(file, 'utf8')));
writeFileSync(join(root, 'darkTheme.generated.css'), buildDarkCss(classes));
console.log(`darkTheme.generated.css: ${new Set(classes.map((c) => c.name)).size} classes`);
