export class ListingCache {
  private readonly seen = new Map<string, number>();
  private readonly ttlMs: number;

  constructor(ttlHours = 4) {
    this.ttlMs = ttlHours * 3_600_000;
  }

  isSeen(pairAddress: string): boolean {
    const ts = this.seen.get(pairAddress);
    if (ts === undefined) return false;
    if (Date.now() - ts > this.ttlMs) {
      this.seen.delete(pairAddress);
      return false;
    }
    return true;
  }

  markSeen(pairAddress: string): void {
    this.seen.set(pairAddress, Date.now());
  }

  cleanup(): number {
    const now = Date.now();
    let removed = 0;
    for (const [key, ts] of this.seen) {
      if (now - ts > this.ttlMs) {
        this.seen.delete(key);
        removed++;
      }
    }
    return removed;
  }

  get size(): number {
    return this.seen.size;
  }
}
