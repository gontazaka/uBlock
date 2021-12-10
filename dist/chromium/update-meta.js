const path = require('path');
const fs = require('fs');

let release_url;
let release_version;

let args = process.argv.slice(2);

if (args.length < 2) {
  process.exit(-1);
}

try {
  release_url = new URL(args[0]);
} catch {
  console.error('⚠ Invalid release URL.')
}
release_version = args[1];

if (!release_url && !release_version) {
  console.error('⚠ Invalid args.')
  process.exit(-2);
}

// file path
const xmlTemplate = path.join(__dirname, './update.template.xml');
const xmlOutput = path.join(__dirname, './update.xml');

const template = fs.readFileSync(xmlTemplate, 'utf-8').toString();

const content = template
  .replace('{release_url}', release_url)
  .replace('{release_version}', release_version);

fs.writeFileSync(xmlOutput, content, 'utf8');
