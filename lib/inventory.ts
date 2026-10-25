import type { InventoryItem, InventorySnapshot } from './inventory-types';

export type InventoryStatus = 'in-stock' | 'low' | 'out' | 'unknown' | 'untracked';
export function inventoryStatus(item: InventoryItem, threshold = 5): InventoryStatus {
  if (!item.tracked) return 'untracked';
  if (item.quantity === null || !item.quantity.trim()) return 'unknown';
  const quantity = Number(item.quantity);
  if (!Number.isFinite(quantity)) return 'unknown';
  if (quantity <= 0) return 'out';
  const limit = Number.isFinite(threshold) && threshold >= 0 && threshold <= 1000000 ? threshold : 5;
  return quantity <= limit ? 'low' : 'in-stock';
}

export function thresholdKey(snapshot: InventorySnapshot, item: InventoryItem): string {
  return JSON.stringify([snapshot.source, snapshot.environment, snapshot.location.id, item.variationId]);
}

function csvCell(value: string): string {
  // Treat names, SKUs, and other imported strings as data in spreadsheet apps.
  const safe = /^[\t\r\n]|^\s*[=+@-]/.test(value) ? `'${value}` : value;
  return `"${safe.replace(/"/g, '""')}"`;
}

export function inventoryCsv(snapshot: InventorySnapshot, thresholds: Record<string, number>): string {
  const rows = [
    ['Item', 'Variation', 'SKU', 'Location', 'Inventory tracking', 'In-stock quantity', 'Low-stock threshold', 'Stock flag', 'Count updated', 'Snapshot refreshed', 'Data source'],
    ...snapshot.items.map(item => {
      const threshold = thresholds[item.variationId] ?? 5;
      return [item.itemName, item.variationName, item.sku ?? '', snapshot.location.name, item.tracked ? 'Tracked' : 'Not tracked', item.tracked ? item.quantity ?? '' : '', String(threshold), inventoryStatus(item, threshold), item.updatedAt ?? '', snapshot.syncedAt, snapshot.source === 'example' ? 'Fictional example' : `Square ${snapshot.environment}`];
    }),
  ];
  return rows.map(row => row.map(csvCell).join(',')).join('\r\n');
}
