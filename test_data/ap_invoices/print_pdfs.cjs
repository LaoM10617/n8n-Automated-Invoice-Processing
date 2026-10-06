// Chromium replaces WeasyPrint because this Windows runtime lacks Pango/GObject.
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require('C:/Users/13020/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async () => {
  const data = JSON.parse(fs.readFileSync(path.join(__dirname, 'input.json'), 'utf8'));
  const browser = await chromium.launch({headless: true, channel: 'msedge'});
  try {
    const page = await browser.newPage();
    for (const item of data.cases) {
      const output = path.join(__dirname, item.file_name);
      if (item.copy_from) {
        fs.copyFileSync(path.join(__dirname, item.copy_from), output);
      } else {
        await page.goto(pathToFileURL(output.replace(/\.pdf$/, '.html')).href);
        await page.pdf({path: output, printBackground: true, preferCSSPageSize: true});
      }
      console.log(item.file_name);
    }
  } finally { await browser.close(); }
})();
