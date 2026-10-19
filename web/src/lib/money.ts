/** Whole-baht amount, e.g. 1800 → "฿1,800". The sign is dropped; callers word it ("over", "−"). */
export function baht(amount: number): string {
  return `฿${Math.abs(amount).toLocaleString("en-US")}`;
}

/** Signed change, e.g. 600 → "+฿600", -200 → "−฿200". */
export function signedBaht(amount: number): string {
  return `${amount > 0 ? "+" : "−"}${baht(amount)}`;
}

/** Share of a total, to one decimal place when needed: (1200, 6000) → "20%", (2850, 6000) → "47.5%". */
export function percentOf(part: number, total: number): string {
  return `${Math.round((part / total) * 1000) / 10}%`;
}
