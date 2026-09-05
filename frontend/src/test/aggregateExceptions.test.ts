import { describe, expect, it } from "vitest";
import { countByCategory } from "../lib/aggregateExceptions";
import { mockExceptionListItem } from "./fixtures";

describe("countByCategory", () => {
  it("labels records without an exception category as clean exact matches", () => {
    const items = [
      { ...mockExceptionListItem, exception_id: "EXC-clean-a", category: null },
      { ...mockExceptionListItem, exception_id: "EXC-clean-b", category: null },
      { ...mockExceptionListItem, exception_id: "EXC-fee", category: "fee_mismatch" },
    ];

    expect(countByCategory(items)).toEqual([
      { category: "clean / exact match", count: 2 },
      { category: "fee_mismatch", count: 1 },
    ]);
  });
});
