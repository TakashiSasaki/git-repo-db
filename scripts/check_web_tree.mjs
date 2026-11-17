// GitHub/AI Studio imports see the tracked branch tree, not dependency caches.
import { execFileSync } from 'node:child_process';
const paths = execFileSync('git', ['ls-files', '-z'], { encoding: 'utf8' }).split('\0').filter(Boolean);
const forbidden = paths.filter(p => /^(src|packages|docs)\//.test(p) || p.includes('node_modules/'));
if (paths.length > 1000 || forbidden.length || !paths.includes('product-source.json')) {
  throw new Error(`Invalid web tree: ${paths.length} tracked files; forbidden=${forbidden.slice(0, 5).join(',')}`);
}
console.log(`Web branch: ${paths.length}/1000 tracked files; canonical product sources stay external.`);
