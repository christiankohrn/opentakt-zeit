export function payrollMonth() {
  const d = new Date();
  if (d.getDate() <= 15) {
    d.setDate(1);
    d.setMonth(d.getMonth() - 1);
  }
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function payrollYear() {
  return Number(payrollMonth().slice(0, 4));
}

export function payrollHalf(): 1 | 2 {
  const month = Number(payrollMonth().slice(5, 7));
  return month <= 6 ? 1 : 2;
}

export function yearRange(year: number) {
  return { from: `${year}-01-01`, to: `${year}-12-31` };
}

export function lastDayOfMonth(month: string) {
  const [year, mon] = month.split("-").map(Number);
  const day = new Date(year, mon, 0).getDate();
  return `${year}-${String(mon).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

export function defaultStichtag(month: string) {
  const today = new Date();
  const iso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
  const last = lastDayOfMonth(month);
  if (iso < `${month}-01`) return iso;
  if (iso > last) return last;
  return iso;
}

export function formatDeDate(iso: string) {
  const [year, month, day] = iso.split("-");
  if (!year || !month || !day) return iso;
  return `${day}.${month}.${year}`;
}

export function monthLabel(month: string) {
  const d = new Date(`${month}-01T12:00:00`);
  if (Number.isNaN(d.getTime())) return month;
  return d.toLocaleDateString("de-DE", { month: "long", year: "numeric" });
}
