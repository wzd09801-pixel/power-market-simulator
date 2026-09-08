import type {
  ForecastImportPreviewPoint,
  ForecastImportPreview,
  ManualForecastDatasetPayload,
} from "./types";

type ForecastImportMetadata = Omit<ManualForecastDatasetPayload, "points">;

const REQUIRED_CSV_COLUMNS = ["interval_start", "price"] as const;
const TIMEZONE_OFFSET_PATTERN = /(Z|[+-]\d{2}:\d{2})$/i;
const DATA_MODES = new Set<ManualForecastDatasetPayload["data_mode"]>([
  "public_observed",
  "public_derived",
  "scenario_simulated",
  "user_uploaded",
]);
const MARKET_STAGES = new Set<ManualForecastDatasetPayload["market_stage"]>([
  "day_ahead",
  "real_time",
  "other",
]);

const METADATA_KEYS = [
  "name",
  "source_name",
  "source_url",
  "region_code",
  "region_name",
  "market_scope",
  "market_stage",
  "price_scope",
  "timezone",
  "currency",
  "price_unit",
  "data_mode",
  "notes",
] as const;

export const defaultManualForecastMetadata: ForecastImportMetadata = {
  name: "Local forecast research curve",
  source_name: "Local file upload",
  source_url: "https://example.invalid/local-forecast-research",
  region_code: "LOCAL",
  region_name: "Local research dataset",
  market_scope: "manual_forecast_research",
  market_stage: "day_ahead",
  price_scope: "regional_reference_price",
  interval_minutes: 15,
  timezone: "Asia/Shanghai",
  currency: "CNY",
  price_unit: "CNY_per_MWh",
  data_mode: "user_uploaded",
  usage_scope: "research_only",
  notes: "Imported from a local file for personal forecast research. This dataset is research_only and is not recommendation evidence.",
};

export function metadataFromPreview(
  preview: ForecastImportPreview | null,
  current: ForecastImportMetadata = defaultManualForecastMetadata,
): ForecastImportMetadata {
  if (preview === null) return current;
  return {
    ...current,
    ...preview.metadata,
    name: preview.metadata.name || nameFromFile(preview.file_name),
    interval_minutes: 15,
    usage_scope: "research_only",
    market_stage: MARKET_STAGES.has(preview.metadata.market_stage ?? "day_ahead")
      ? (preview.metadata.market_stage ?? current.market_stage)
      : current.market_stage,
    data_mode: DATA_MODES.has(preview.metadata.data_mode ?? "user_uploaded")
      ? (preview.metadata.data_mode ?? current.data_mode)
      : current.data_mode,
  };
}

export function parseForecastImportText(fileName: string, rawText: string): ForecastImportPreview {
  const text = rawText.replace(/^\uFEFF/, "").trim();
  if (text.length === 0) {
    return buildPreview({
      fileName,
      points: [],
      metadata: {},
      ignoredColumns: [],
      errors: ["Import file is empty."],
      warnings: [],
    });
  }
  if (looksLikeJson(fileName, text)) {
    return parseJsonForecastImport(fileName, text);
  }
  return parseCsvForecastImport(fileName, text);
}

function parseJsonForecastImport(fileName: string, text: string): ForecastImportPreview {
  const errors: string[] = [];
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return buildPreview({
      fileName,
      points: [],
      metadata: {},
      ignoredColumns: [],
      errors: ["JSON import file could not be parsed."],
      warnings: [],
    });
  }

  const source = Array.isArray(parsed) ? { points: parsed } : parsed;
  if (!isRecord(source)) {
    return buildPreview({
      fileName,
      points: [],
      metadata: {},
      ignoredColumns: [],
      errors: ["JSON import must be an array of points or an object with a points array."],
      warnings: [],
    });
  }
  const pointsValue = source.points;
  if (!Array.isArray(pointsValue)) {
    errors.push("JSON import must include a points array.");
  }

  const points = Array.isArray(pointsValue)
    ? pointsValue.map((item, index) => normalizePoint(item, index + 1))
    : [];
  return buildPreview({
    fileName,
    points,
    metadata: extractMetadata(source),
    ignoredColumns: [],
    errors,
    warnings: [],
  });
}

function parseCsvForecastImport(fileName: string, text: string): ForecastImportPreview {
  const rows = parseCsvRows(text);
  if (rows.length === 0) {
    return buildPreview({
      fileName,
      points: [],
      metadata: {},
      ignoredColumns: [],
      errors: ["CSV import file has no rows."],
      warnings: [],
    });
  }

  const headers = rows[0].map((header) => header.trim());
  const normalizedHeaders = headers.map((header) => header.toLowerCase());
  const errors = REQUIRED_CSV_COLUMNS
    .filter((column) => !normalizedHeaders.includes(column))
    .map((column) => `CSV import is missing required column '${column}'.`);
  const ignoredColumns = headers.filter((header) => {
    const normalized = header.toLowerCase();
    return normalized !== "" && !REQUIRED_CSV_COLUMNS.includes(normalized as typeof REQUIRED_CSV_COLUMNS[number]);
  });
  const intervalIndex = normalizedHeaders.indexOf("interval_start");
  const priceIndex = normalizedHeaders.indexOf("price");
  const points = errors.length === 0
    ? rows.slice(1).map((row, index) => ({
      interval_start: (row[intervalIndex] ?? "").trim(),
      price: (row[priceIndex] ?? "").trim(),
      source_row: index + 2,
    }))
    : [];

  return buildPreview({
    fileName,
    points,
    metadata: {},
    ignoredColumns,
    errors,
    warnings: [],
  });
}

function buildPreview({
  fileName,
  points,
  metadata,
  ignoredColumns,
  errors,
  warnings,
}: {
  fileName: string;
  points: ForecastImportPreviewPoint[];
  metadata: Partial<ForecastImportMetadata>;
  ignoredColumns: string[];
  errors: string[];
  warnings: string[];
}): ForecastImportPreview {
  if (points.length === 0 && errors.length === 0) {
    errors.push("No forecast points were found.");
  }
  const intervalCounts = new Map<string, number>();
  const tradeDateCounts = new Map<string, number>();
  let timezoneIssueCount = 0;
  let invalidPriceCount = 0;
  let minPrice: number | null = null;
  let maxPrice: number | null = null;

  for (const point of points) {
    const intervalStart = point.interval_start.trim();
    const priceText = String(point.price).trim();
    if (!TIMEZONE_OFFSET_PATTERN.test(intervalStart)) {
      timezoneIssueCount += 1;
    }
    intervalCounts.set(intervalStart, (intervalCounts.get(intervalStart) ?? 0) + 1);
    const tradeDate = tradeDateFromInterval(intervalStart);
    if (tradeDate !== null) {
      tradeDateCounts.set(tradeDate, (tradeDateCounts.get(tradeDate) ?? 0) + 1);
    }
    const price = Number(priceText);
    if (!Number.isFinite(price)) {
      invalidPriceCount += 1;
      continue;
    }
    minPrice = minPrice === null ? price : Math.min(minPrice, price);
    maxPrice = maxPrice === null ? price : Math.max(maxPrice, price);
  }

  const duplicateIntervalCount = [...intervalCounts.values()]
    .reduce((count, value) => count + Math.max(0, value - 1), 0);
  const incompleteTradeDateCount = [...tradeDateCounts.values()]
    .filter((count) => count !== 96).length;
  const sortedDates = [...tradeDateCounts.keys()].sort();

  if (timezoneIssueCount > 0) {
    errors.push("Every interval_start must include a timezone offset such as +08:00 or Z.");
  }
  if (invalidPriceCount > 0) {
    errors.push("Every price must be numeric.");
  }
  if (duplicateIntervalCount > 0) {
    warnings.push("Duplicate interval_start values were found; backend quality checks may reject the dataset.");
  }
  if (incompleteTradeDateCount > 0) {
    warnings.push("One or more trade dates do not contain exactly 96 intervals.");
  }
  if (ignoredColumns.length > 0) {
    warnings.push(`Ignored CSV columns: ${ignoredColumns.join(", ")}.`);
  }

  return {
    file_name: fileName,
    point_count: points.length,
    date_count: sortedDates.length,
    date_range: sortedDates.length === 0
      ? "-"
      : `${sortedDates[0]} to ${sortedDates[sortedDates.length - 1]}`,
    duplicate_interval_count: duplicateIntervalCount,
    incomplete_trade_date_count: incompleteTradeDateCount,
    timezone_issue_count: timezoneIssueCount,
    invalid_price_count: invalidPriceCount,
    min_price: minPrice,
    max_price: maxPrice,
    ignored_columns: ignoredColumns,
    sample_points: points.slice(0, 5),
    metadata,
    points: points.map((point) => ({
      interval_start: point.interval_start.trim(),
      price: String(point.price).trim(),
    })),
    errors,
    warnings,
  };
}

function looksLikeJson(fileName: string, text: string): boolean {
  const lowerName = fileName.toLowerCase();
  return lowerName.endsWith(".json") || text.startsWith("{") || text.startsWith("[");
}

function parseCsvRows(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let inQuotes = false;

  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    const next = text[index + 1];
    if (character === "\"") {
      if (inQuotes && next === "\"") {
        cell += "\"";
        index += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }
    if (character === "," && !inQuotes) {
      row.push(cell);
      cell = "";
      continue;
    }
    if ((character === "\n" || character === "\r") && !inQuotes) {
      if (character === "\r" && next === "\n") {
        index += 1;
      }
      row.push(cell);
      pushNonEmptyRow(rows, row);
      row = [];
      cell = "";
      continue;
    }
    cell += character;
  }

  row.push(cell);
  pushNonEmptyRow(rows, row);
  return rows;
}

function pushNonEmptyRow(rows: string[][], row: string[]): void {
  if (row.some((cell) => cell.trim() !== "")) {
    rows.push(row);
  }
}

function normalizePoint(item: unknown, sourceRow: number): ForecastImportPreviewPoint {
  if (!isRecord(item)) {
    return { interval_start: "", price: "" };
  }
  return {
    interval_start: String(item.interval_start ?? "").trim(),
    price: String(item.price ?? "").trim(),
    source_row: sourceRow,
  };
}

function extractMetadata(source: Record<string, unknown>): Partial<ForecastImportMetadata> {
  const metadata: Partial<ForecastImportMetadata> = {};
  for (const key of METADATA_KEYS) {
    const value = source[key];
    if (typeof value !== "string" || value.trim() === "") continue;
    if (key === "data_mode") {
      if (DATA_MODES.has(value as ManualForecastDatasetPayload["data_mode"])) {
        metadata.data_mode = value as ManualForecastDatasetPayload["data_mode"];
      }
      continue;
    }
    if (key === "market_stage") {
      if (MARKET_STAGES.has(value as ManualForecastDatasetPayload["market_stage"])) {
        metadata.market_stage = value as ManualForecastDatasetPayload["market_stage"];
      }
      continue;
    }
    metadata[key] = value.trim() as never;
  }
  return metadata;
}

function tradeDateFromInterval(intervalStart: string): string | null {
  const match = /^(\d{4}-\d{2}-\d{2})T/.exec(intervalStart);
  return match?.[1] ?? null;
}

function nameFromFile(fileName: string): string {
  const withoutPath = fileName.split(/[\\/]/).pop() ?? fileName;
  return withoutPath.replace(/\.[^.]+$/, "") || "Local forecast research curve";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
