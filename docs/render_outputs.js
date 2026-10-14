#!/usr/bin/env node
/* Write the same files the page downloads. Used by tests/test_web_parity.py. */
const fs = require("fs");
const path = require("path");
const pipeline = require("./pipeline");

const fixturesDir = process.argv[2];
const outputDir = process.argv[3];
const zipPath = process.argv[4];

if (!fixturesDir || !outputDir) {
  console.error("usage: node docs/render_outputs.js FIXTURES_DIR OUTPUT_DIR [ZIP_PATH]");
  process.exit(2);
}

function read(name) {
  return fs.readFileSync(path.join(fixturesDir, name), "utf8");
}

const result = pipeline.runPipeline({
  rawStatementCsv: read("raw_statement.csv"),
  statementMetaJson: read("statement_meta.json"),
  chartOfAccountsCsv: read("chart_of_accounts.csv"),
  referenceCsv: read("reference.csv"),
  entityMapCsv: read("entity_map.csv"),
});
const files = pipeline.renderOutputs(result);

for (const rel of Object.keys(files)) {
  const dest = path.join(outputDir, rel);
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.writeFileSync(dest, files[rel], "utf8");
}

if (zipPath) {
  fs.mkdirSync(path.dirname(zipPath), { recursive: true });
  fs.writeFileSync(zipPath, Buffer.from(pipeline.buildZip(files)));
}
