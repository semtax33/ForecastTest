import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";


const SCRIPT_DIRECTORY = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(SCRIPT_DIRECTORY, "..", "..");
const OUTPUT = path.join(ROOT, "data-lake", "bronze", "industrials", "v1_5", "bls");
const REPORTS = path.join(OUTPUT, "ppi_detailed_reports");
const SCHEDULES = path.join(OUTPUT, "release_schedules");
const ARCHIVE_PAGE = "https://www.bls.gov/ppi/detailed-report/home.htm";
const MONTHS = [
  "january", "february", "march", "april", "may", "june",
  "july", "august", "september", "october", "november", "december",
];


function reportPeriods() {
  const periods = [];
  for (let year = 2022; year <= 2026; year += 1) {
    const finalMonth = year === 2026 ? 6 : 11;
    for (let month = 0; month <= finalMonth; month += 1) {
      if (year === 2025 && month === 9) continue;
      periods.push({ year, month });
    }
  }
  return periods;
}


async function fetchBuffer(url, expectedType) {
  const response = await fetch(url, { headers: { "user-agent": "Arcana-ForecastTest/1.0" } });
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${url}`);
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes(expectedType)) throw new Error(`Unexpected content type ${contentType}: ${url}`);
  return { bytes: Buffer.from(await response.arrayBuffer()), contentType };
}


async function main() {
  await mkdir(REPORTS, { recursive: true });
  await mkdir(SCHEDULES, { recursive: true });
  const downloadedAt = new Date().toISOString();
  const artifacts = [];
  for (const { year, month } of reportPeriods()) {
    const label = `${MONTHS[month]}-${year}`;
    const name = `ppi-detailed-report-${label}.xlsx`;
    const url = `https://www.bls.gov/ppi/detailed-report/${name}`;
    const { bytes, contentType } = await fetchBuffer(url, "spreadsheetml.sheet");
    if (bytes.subarray(0, 2).toString() !== "PK") throw new Error(`Invalid XLSX signature: ${url}`);
    const target = path.join(REPORTS, name);
    await writeFile(target, bytes);
    artifacts.push({
      report_period: `${year}-${String(month + 1).padStart(2, "0")}`,
      source_url: url,
      local_path: path.relative(ROOT, target).replaceAll("\\", "/"),
      content_type: contentType,
      size_bytes: bytes.length,
      sha256: createHash("sha256").update(bytes).digest("hex"),
    });
  }
  const schedules = [];
  for (const year of [2022, 2023, 2024, 2025, 2026]) {
    const url = `https://www.bls.gov/schedule/${year}/`;
    const { bytes, contentType } = await fetchBuffer(url, "text/html");
    const target = path.join(SCHEDULES, `bls-release-schedule-${year}.html`);
    await writeFile(target, bytes);
    schedules.push({
      calendar_year: year,
      source_url: url,
      local_path: path.relative(ROOT, target).replaceAll("\\", "/"),
      content_type: contentType,
      size_bytes: bytes.length,
      sha256: createHash("sha256").update(bytes).digest("hex"),
    });
  }
  const manifest = {
    schema_version: 1,
    provider: "U.S. Bureau of Labor Statistics",
    archive_page: ARCHIVE_PAGE,
    downloaded_at: downloadedAt,
    pdf_parsing_used: false,
    ppi_report_artifacts: artifacts,
    release_schedule_artifacts: schedules,
  };
  const manifestPath = path.join(OUTPUT, "archive_manifest.json");
  await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  console.log(JSON.stringify({ reports: artifacts.length, schedules: schedules.length, manifest: manifestPath }, null, 2));
}


await main();
