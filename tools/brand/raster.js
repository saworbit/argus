// Argus brand - the PNGs that platforms insist on. Everything derives from
// the SVGs dist.py writes to docs/brand; run that first.
//
//   node tools/brand/raster.js
const { Resvg } = require('@resvg/resvg-js');
const fs = require('fs'), path = require('path');
const DIR = path.resolve(__dirname, '..', '..', 'docs', 'brand');
const made = [];
const png = (src, width, name) => {
  const svg = fs.readFileSync(path.join(DIR, src), 'utf8');
  const buf = new Resvg(svg, { fitTo: { mode: 'width', value: width } })
    .render().asPng();
  fs.writeFileSync(path.join(DIR, name), buf);
  made.push(name);
};

// GitHub's repository social preview takes a raster image, 1280 x 640.
png('social-preview.svg', 1280, 'social-preview.png');
// Avatars (GitHub, Discord and friends) take a raster square.
png('argus-icon-tile.svg', 512, 'argus-icon-tile-512.png');

console.log('wrote', made.length, 'pngs to', DIR);
