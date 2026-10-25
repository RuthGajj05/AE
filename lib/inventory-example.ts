import type { InventorySnapshot } from './inventory-types';

// Fictional fixture: never a fallback for a failed Square request.
export const exampleInventory: InventorySnapshot = {
  source: 'example',
  environment: 'sandbox',
  location: { id: 'example-shop', name: 'Sample bakery' },
  syncedAt: '2026-10-25T12:00:00.000Z',
  warnings: ['Fictional sample inventory. These quantities do not come from a Square account.', 'Stock counts do not include reservations or a separate sold-out setting. Confirm sellable availability in Square.'],
  items: [
    { variationId: 'sample-sourdough', itemName: 'Sourdough loaf', variationName: 'Regular', sku: 'BREAD-001', quantity: '24', tracked: true, locationId: 'example-shop', updatedAt: '2026-10-25T11:52:00.000Z' },
    { variationId: 'sample-croissant', itemName: 'Butter croissant', variationName: 'Single', sku: 'PASTRY-001', quantity: '4', tracked: true, locationId: 'example-shop', updatedAt: '2026-10-25T11:58:00.000Z' },
    { variationId: 'sample-roll', itemName: 'Cinnamon roll', variationName: 'Single', sku: 'PASTRY-002', quantity: '0', tracked: true, locationId: 'example-shop', updatedAt: '2026-10-25T11:56:00.000Z' },
    { variationId: 'sample-baguette', itemName: 'Baguette', variationName: 'Regular', sku: 'BREAD-002', quantity: '5', tracked: true, locationId: 'example-shop', updatedAt: '2026-10-25T11:50:00.000Z' },
    { variationId: 'sample-granola', itemName: 'Granola by weight', variationName: 'Bulk', sku: 'PANTRY-001', quantity: '7.5', tracked: true, locationId: 'example-shop', updatedAt: '2026-10-25T11:40:00.000Z' },
    { variationId: 'sample-cookie', itemName: 'Chocolate chip cookie', variationName: 'Single', sku: 'PASTRY-003', quantity: '-2', tracked: true, locationId: 'example-shop', updatedAt: '2026-10-25T11:59:00.000Z' },
    { variationId: 'sample-tart', itemName: 'Seasonal tart', variationName: 'Whole', sku: null, quantity: null, tracked: true, locationId: 'example-shop', updatedAt: null },
    { variationId: 'sample-coffee', itemName: 'Drip coffee', variationName: 'Small', sku: 'COFFEE-001', quantity: null, tracked: false, locationId: 'example-shop', updatedAt: null },
  ],
};
