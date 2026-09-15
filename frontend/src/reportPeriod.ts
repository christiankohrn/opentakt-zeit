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
