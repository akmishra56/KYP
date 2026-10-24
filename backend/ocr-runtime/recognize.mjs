import { createWorker, PSM } from 'tesseract.js';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const models = fileURLToPath(new URL('./models/', import.meta.url));
let worker;
try {
  worker = await createWorker('eng', 1, { langPath: models, gzip: false, cacheMethod: 'none', logger: () => {} });
  await worker.setParameters({ tessedit_pageseg_mode: PSM.SINGLE_BLOCK, user_defined_dpi: '300' });
  const results = [];
  for (const image of process.argv.slice(2)) {
    const { data } = await worker.recognize(image, {}, { text: true, tsv: true });
    results.push({ text: data.text, tsv: data.tsv });
  }
  process.stdout.write(JSON.stringify(results.length === 1 ? results[0] : results));
} catch (error) {
  process.stderr.write('Local OCR failed. Check the runtime and English model installation.');
  process.exitCode = 1;
} finally {
  if (worker) await worker.terminate();
}
