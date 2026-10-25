export type SquareEnvironment = 'sandbox' | 'production';
export type InventoryConnection = { configured: boolean; environment: SquareEnvironment; apiVersion: string };
export type InventoryLocation = { id: string; name: string };
export type InventoryItem = {
  variationId: string;
  itemName: string;
  variationName: string;
  sku: string | null;
  quantity: string | null;
  tracked: boolean;
  locationId: string;
  updatedAt: string | null;
};
export type InventorySnapshot = {
  source: 'square' | 'example';
  environment: SquareEnvironment;
  location: InventoryLocation;
  items: InventoryItem[];
  syncedAt: string;
  warnings: string[];
};
export type InventoryResponse = {
  connection: InventoryConnection;
  locations: InventoryLocation[];
  snapshot?: InventorySnapshot;
};
