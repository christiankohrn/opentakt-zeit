const KEY = "ze-offline-queue";

export type QueuedPunch = {
  kind: "in" | "out" | "break_start" | "break_end";
  client_event_id: string;
  device_time: string;
};

export function newEventId(): string {
  if (crypto.randomUUID) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function readQueue(): QueuedPunch[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) || "[]") as QueuedPunch[];
  } catch {
    return [];
  }
}

export function enqueue(item: QueuedPunch): void {
  const q = readQueue();
  q.push(item);
  localStorage.setItem(KEY, JSON.stringify(q));
}

export function writeQueue(items: QueuedPunch[]): void {
  localStorage.setItem(KEY, JSON.stringify(items));
}
