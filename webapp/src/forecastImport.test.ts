import { expect, test } from "vitest";

import {
  metadataFromPreview,
  parseForecastImportText,
} from "./forecastImport";

test("parses forecast CSV import previews with required columns and ignored extras", () => {
  const preview = parseForecastImportText(
    "curve.csv",
    [
      "interval_start,price,comment",
      "2026-01-01T00:00:00+08:00,100.5,first",
      "2026-01-01T00:15:00+08:00,101.0,second",
    ].join("\n"),
  );

  expect(preview.errors).toEqual([]);
  expect(preview.point_count).toBe(2);
  expect(preview.date_range).toBe("2026-01-01 to 2026-01-01");
  expect(preview.ignored_columns).toEqual(["comment"]);
  expect(preview.warnings).toContain("One or more trade dates do not contain exactly 96 intervals.");
  expect(preview.points[0]).toEqual({
    interval_start: "2026-01-01T00:00:00+08:00",
    price: "100.5",
  });
});

test("parses forecast JSON import previews and extracts dataset metadata", () => {
  const preview = parseForecastImportText(
    "curve.json",
    JSON.stringify({
      name: "Uploaded day-ahead curve",
      source_name: "Operator notebook",
      source_url: "https://example.invalid/forecast-source",
      region_code: "GD",
      region_name: "Example Province research sample",
      market_scope: "manual_research",
      market_stage: "day_ahead",
      price_scope: "clearing_price",
      timezone: "Asia/Shanghai",
      currency: "CNY",
      price_unit: "CNY_per_MWh",
      data_mode: "user_uploaded",
      notes: "Local research import.",
      points: [
        { interval_start: "2026-01-01T00:00:00+08:00", price: "100" },
      ],
    }),
  );

  const metadata = metadataFromPreview(preview);

  expect(preview.errors).toEqual([]);
  expect(preview.points).toEqual([
    { interval_start: "2026-01-01T00:00:00+08:00", price: "100" },
  ]);
  expect(metadata.name).toBe("Uploaded day-ahead curve");
  expect(metadata.source_name).toBe("Operator notebook");
  expect(metadata.usage_scope).toBe("research_only");
  expect(metadata.interval_minutes).toBe(15);
});

test("rejects empty forecast import files", () => {
  const preview = parseForecastImportText("empty.csv", "");

  expect(preview.errors).toContain("Import file is empty.");
  expect(preview.point_count).toBe(0);
});

test("rejects forecast CSV imports without required columns", () => {
  const preview = parseForecastImportText(
    "bad.csv",
    "timestamp,value\n2026-01-01T00:00:00+08:00,100",
  );

  expect(preview.errors).toContain("CSV import is missing required column 'interval_start'.");
  expect(preview.errors).toContain("CSV import is missing required column 'price'.");
  expect(preview.points).toEqual([]);
});

test("rejects forecast import points without timezone offsets or numeric prices", () => {
  const preview = parseForecastImportText(
    "bad.csv",
    "interval_start,price\n2026-01-01T00:00:00,not-a-price",
  );

  expect(preview.timezone_issue_count).toBe(1);
  expect(preview.invalid_price_count).toBe(1);
  expect(preview.errors).toContain("Every interval_start must include a timezone offset such as +08:00 or Z.");
  expect(preview.errors).toContain("Every price must be numeric.");
});
