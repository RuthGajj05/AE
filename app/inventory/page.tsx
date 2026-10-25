"use client";

import { useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, ArrowRight, Boxes, Check, ChevronDown, Download, Link2, LoaderCircle, MapPin, Package, RefreshCw, Search, ShieldCheck, Store, TriangleAlert } from 'lucide-react';
import type { InventoryConnection, InventoryItem, InventoryLocation, InventoryResponse, InventorySnapshot } from '@/lib/inventory-types';
import { inventoryCsv, inventoryStatus, thresholdKey } from '@/lib/inventory';
import { exampleInventory } from '@/lib/inventory-example';
import './inventory.css';

const THRESHOLDS_KEY = 'nearby-inventory-thresholds-v1';
const DEFAULT_THRESHOLD = 5;
type StockFilter = 'all' | 'low' | 'out' | 'unknown' | 'untracked';
const statusLabels = { 'in-stock': 'In stock', low: 'Running low', out: 'Out of stock', unknown: 'Count unavailable', untracked: 'Not tracked' };

function timestamp(value: string) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? 'Time unavailable' : parsed.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}
function formatQuantity(value: string | null) {
  if (value === null || !/^-?\d+(?:\.\d+)?$/.test(value)) return '—';
  return value;
}
function isInventoryResponse(value: unknown): value is InventoryResponse {
  if (!value || typeof value !== 'object') return false;
  const data = value as InventoryResponse;
  if (!data.connection || typeof data.connection.configured !== 'boolean' || !['sandbox', 'production'].includes(data.connection.environment) || typeof data.connection.apiVersion !== 'string' || !Array.isArray(data.locations) || !data.locations.every(item => item && typeof item.id === 'string' && typeof item.name === 'string')) return false;
  if (!data.snapshot) return true;
  const snapshot = data.snapshot;
  return snapshot.source === 'square' && ['sandbox', 'production'].includes(snapshot.environment) && typeof snapshot.location?.id === 'string' && typeof snapshot.location?.name === 'string' && typeof snapshot.syncedAt === 'string' && Array.isArray(snapshot.warnings) && snapshot.warnings.every(item => typeof item === 'string') && Array.isArray(snapshot.items) && snapshot.items.every(item => item && [item.variationId, item.itemName, item.variationName, item.locationId].every(value => typeof value === 'string') && (item.sku === null || typeof item.sku === 'string') && (item.quantity === null || typeof item.quantity === 'string') && typeof item.tracked === 'boolean' && (item.updatedAt === null || typeof item.updatedAt === 'string'));
}

function ThresholdInput({ item, value, onSave }: { item: InventoryItem; value: number; onSave: (value: number) => void }) {
  const [draft, setDraft] = useState(String(value));
  const [invalid, setInvalid] = useState(false);
  useEffect(() => { setDraft(String(value)); setInvalid(false); }, [value]);
  function commit() {
    const number = Number(draft);
    if (!draft.trim() || !Number.isFinite(number) || number < 0 || number > 1000000) { setInvalid(true); return; }
    setInvalid(false); onSave(number);
  }
  return <div className="inventory-threshold"><input type="number" min="0" max="1000000" step="any" inputMode="decimal" aria-label={`Low-stock threshold for ${item.itemName}, ${item.variationName}`} aria-invalid={invalid} value={draft} onChange={event => { setDraft(event.target.value); setInvalid(false); }} onBlur={commit} onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); commit(); } }} /><span>or fewer</span>{invalid && <small role="alert">Enter 0–1,000,000.</small>}</div>;
}

export default function InventoryPage() {
  const [connection, setConnection] = useState<InventoryConnection | null>(null);
  const [locations, setLocations] = useState<InventoryLocation[]>([]);
  const [selectedLocation, setSelectedLocation] = useState('');
  const [snapshot, setSnapshot] = useState<InventorySnapshot | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<StockFilter>('all');
  const [thresholds, setThresholds] = useState<Record<string, number>>({});
  const [storageReady, setStorageReady] = useState(false);
  const [storageAvailable, setStorageAvailable] = useState(true);
  const controller = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const snapshotRef = useRef<InventorySnapshot | null>(null);

  useEffect(() => { snapshotRef.current = snapshot; }, [snapshot]);
  useEffect(() => {
    try {
      const raw = localStorage.getItem(THRESHOLDS_KEY);
      if (raw) {
        const saved = JSON.parse(raw);
        if (saved && typeof saved === 'object' && !Array.isArray(saved)) setThresholds(Object.fromEntries(Object.entries(saved).filter(([, value]) => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1000000)) as Record<string, number>);
      }
    } catch { setStorageAvailable(false); }
    setStorageReady(true);
    void loadSquare();
    return () => { generation.current++; controller.current?.abort(); };
  }, []);
  useEffect(() => {
    if (!storageReady) return;
    try { localStorage.setItem(THRESHOLDS_KEY, JSON.stringify(thresholds)); setStorageAvailable(true); } catch { setStorageAvailable(false); }
  }, [thresholds, storageReady]);

  async function loadSquare(locationId?: string) {
    controller.current?.abort();
    const abort = new AbortController(); controller.current = abort;
    const run = ++generation.current;
    const previous = snapshotRef.current;
    if (previous?.source === 'example' || (locationId && previous?.location.id !== locationId)) { setSnapshot(null); snapshotRef.current = null; }
    if (locationId) setSelectedLocation(locationId);
    setBusy(true); setError('');
    async function request(id?: string) {
      const response = await fetch(`/api/inventory/square${id ? `?locationId=${encodeURIComponent(id)}` : ''}`, { signal: abort.signal, cache: 'no-store' });
      const data: unknown = await response.json().catch(() => null);
      if (!response.ok) {
        const error = data && typeof data === 'object' && 'error' in data ? data.error : null;
        throw new Error(typeof error === 'string' ? error : 'Square inventory could not be loaded. Please try again.');
      }
      if (!isInventoryResponse(data)) throw new Error('The inventory response could not be read. Please try again.');
      return data;
    }
    try {
      let data = await request(locationId);
      if (run !== generation.current) return;
      setConnection(data.connection); setLocations(data.locations);
      if (!data.connection.configured) { setSnapshot(null); snapshotRef.current = null; setSelectedLocation(''); return; }
      const requested = locationId || data.locations[0]?.id;
      if (!requested) { setSnapshot(null); snapshotRef.current = null; setSelectedLocation(''); return; }
      setSelectedLocation(requested);
      if (!data.snapshot) data = await request(requested);
      if (run !== generation.current) return;
      if (!data.snapshot || data.snapshot.location.id !== requested) throw new Error('Square returned a different location. Refresh to try again.');
      setConnection(data.connection); setLocations(data.locations); setSnapshot(data.snapshot); snapshotRef.current = data.snapshot;
    } catch (cause) {
      if (run !== generation.current || abort.signal.aborted) return;
      const message = cause instanceof Error ? cause.message : 'Square inventory could not be loaded. Please try again.';
      setError(message);
    } finally {
      if (run === generation.current) { setBusy(false); controller.current = null; }
    }
  }
  function showSample() {
    controller.current?.abort(); generation.current++;
    setBusy(false); setError(''); setSnapshot(exampleInventory); snapshotRef.current = exampleInventory;
    setSelectedLocation(exampleInventory.location.id); setFilter('all'); setQuery('');
  }
  const thresholdFor = (item: InventoryItem) => snapshot ? thresholds[thresholdKey(snapshot, item)] ?? DEFAULT_THRESHOLD : DEFAULT_THRESHOLD;
  const counts = useMemo(() => {
    const summary = { 'in-stock': 0, low: 0, out: 0, unknown: 0, untracked: 0 };
    for (const item of snapshot?.items || []) summary[inventoryStatus(item, thresholds[thresholdKey(snapshot!, item)] ?? DEFAULT_THRESHOLD)]++;
    return summary;
  }, [snapshot, thresholds]);
  const visibleItems = snapshot?.items.filter(item => {
    const status = inventoryStatus(item, thresholdFor(item));
    return (filter === 'all' || filter === status) && `${item.itemName} ${item.variationName} ${item.sku || ''}`.toLowerCase().includes(query.trim().toLowerCase());
  }) || [];
  function exportCsv() {
    if (!snapshot) return;
    const perItem = Object.fromEntries(snapshot.items.map(item => [item.variationId, thresholdFor(item)]));
    const blob = new Blob(['\uFEFF', inventoryCsv(snapshot, perItem)], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob); const anchor = document.createElement('a');
    anchor.href = url; anchor.download = `nearby-${snapshot.source === 'example' ? 'sample-' : ''}inventory-${snapshot.location.id.replace(/[^a-zA-Z0-9_-]/g, '_')}.csv`; anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return <div className="inventory-shell">
    <header className="site-header inventory-header"><div className="header-inner"><a className="brand" href="/" aria-label="Nearby home"><span className="brand-mark"><MapPin size={21} /></span>nearby<span className="brand-period">.</span></a><nav className="inventory-nav" aria-label="Main navigation"><a href="/">Business research</a><a href="/inventory" aria-current="page">Inventory</a></nav><span className="private-label"><ShieldCheck size={13} />Private prototype</span></div></header>
    <main className="inventory-main">
      <section className="inventory-hero"><div><div className="eyebrow"><span className="eyebrow-line" /> A CLEARER VIEW OF YOUR SHELVES</div><h1>Know what’s on hand.<br /><em>Know what needs attention.</em></h1><p>Your Square items and stock counts, in one place. Set a low-stock threshold and see where to look next.</p></div><div className="inventory-hero-mark" aria-hidden="true"><Boxes size={52} strokeWidth={1.2} /><span>SMALL BUSINESS.<br />A LITTLE MORE CLARITY.</span></div></section>

      <section className={`inventory-connection ${snapshot?.source === 'example' ? 'is-sample' : ''}`} aria-label="Square connection">
        <div className="inventory-connection-icon"><Link2 size={20} /></div><div className="inventory-connection-copy"><strong>{snapshot?.source === 'example' ? 'You’re exploring sample inventory' : connection?.configured ? `Square ${connection.environment === 'sandbox' ? 'Sandbox' : 'Production'}` : busy ? 'Checking Square connection…' : 'Connect your Square inventory'}</strong><p>{snapshot?.source === 'example' ? 'Fictional items and quantities. Try the filters and thresholds; these are not your Square records.' : connection?.configured ? 'Read-only connection. Counts update when you refresh this page’s inventory.' : 'No live Square data is connected yet. The site owner can configure the account in server settings. Explore the sample below.'}</p></div>
        <div className="inventory-connection-actions">{snapshot?.source === 'example' ? <button className="button button-outline button-small" onClick={() => void loadSquare()} disabled={busy}>Check Square connection <ArrowRight size={14} /></button> : !connection?.configured && <button className="button button-primary button-small" onClick={showSample} disabled={!storageReady}>Explore sample inventory <ArrowRight size={14} /></button>}{!snapshot && !busy && <button className="text-button" onClick={() => void loadSquare()}>Check connection <RefreshCw size={13} /></button>}</div>
      </section>

      {error && <div className="inventory-error" role="alert"><AlertCircle size={18} /><div><strong>{snapshot?.source === 'square' ? 'Refresh failed — showing the last successful snapshot.' : 'Inventory could not be loaded.'}</strong><p>{error}</p>{snapshot?.source === 'square' && <p>These counts were last refreshed {timestamp(snapshot.syncedAt)} and may be out of date.</p>}</div></div>}

      {snapshot ? <>
        <div className="inventory-toolbar"><div className="inventory-location"><MapPin size={17} /><div><label htmlFor="inventory-location">LOCATION</label>{snapshot.source === 'example' ? <strong>{snapshot.location.name}</strong> : <div className="inventory-select-wrap"><select id="inventory-location" value={selectedLocation} disabled={busy} onChange={event => void loadSquare(event.target.value)}>{locations.map(location => <option key={location.id} value={location.id}>{location.name}</option>)}</select><ChevronDown size={14} /></div>}</div></div><div className="inventory-toolbar-actions"><span className="inventory-sync-status" role="status">{busy ? <><LoaderCircle size={13} className="spin" />Refreshing… showing previous counts</> : snapshot.source === 'example' ? <><Store size={13} />Sample data</> : error ? <><AlertCircle size={13} />Last successful refresh {timestamp(snapshot.syncedAt)}</> : <><Check size={13} />Last refreshed {timestamp(snapshot.syncedAt)}</>}</span>{snapshot.source === 'square' && <button className="button button-outline button-small" disabled={busy} onClick={() => void loadSquare(snapshot.location.id)}><RefreshCw size={14} className={busy ? 'spin' : ''} />Refresh</button>}<button className="button button-outline button-small" onClick={exportCsv} disabled={busy}><Download size={14} />Export CSV</button></div></div>

        <section className="inventory-summary" aria-label="Inventory summary"><div><span>Item variations</span><strong>{snapshot.items.length.toLocaleString()}</strong><small>At this location</small></div><div className="summary-low"><span><TriangleAlert size={13} />Running low</span><strong>{counts.low.toLocaleString()}</strong><small>At or below your threshold</small></div><div className="summary-out"><span>Out of stock</span><strong>{counts.out.toLocaleString()}</strong><small>Zero or negative count</small></div><div><span>Counts to check</span><strong>{(counts.unknown + counts.untracked).toLocaleString()}</strong><small>{counts.unknown} unavailable · {counts.untracked} not tracked</small></div></section>

        <section className="inventory-stock" aria-labelledby="inventory-stock-heading"><div className="inventory-stock-heading"><div><h2 id="inventory-stock-heading">A look at your stock.</h2><p>{snapshot.source === 'example' ? 'Fictional sample counts. Try setting a threshold for each item.' : 'Set a threshold for each item. Square remains the source of your counts.'}</p></div><span className={`inventory-mode-badge ${snapshot.source === 'example' ? 'sample' : ''}`}>{snapshot.source === 'example' ? 'SAMPLE DATA' : snapshot.environment === 'sandbox' ? 'SQUARE SANDBOX' : 'SQUARE PRODUCTION'}</span></div><div className="inventory-filters"><div className="inventory-search"><Search size={16} /><input aria-label="Search inventory by item or SKU" value={query} placeholder="Search items or SKU…" onChange={event => setQuery(event.target.value)} /></div><div className="inventory-filter-select"><label htmlFor="inventory-filter">Show</label><select id="inventory-filter" value={filter} onChange={event => setFilter(event.target.value as StockFilter)}><option value="all">All stock statuses</option><option value="low">Running low</option><option value="out">Out of stock</option><option value="unknown">Count unavailable</option><option value="untracked">Not tracked</option></select></div></div>
          <div className="inventory-table-scroll"><table className="inventory-table"><caption className="inventory-sr-only">Inventory at {snapshot.location.name}. Threshold edits are saved only in this browser.</caption><thead><tr><th scope="col">ITEM / VARIATION</th><th scope="col">SKU</th><th scope="col">ON HAND</th><th scope="col">STATUS</th><th scope="col">LOW-STOCK THRESHOLD</th></tr></thead><tbody>{visibleItems.map(item => {
            const status = inventoryStatus(item, thresholdFor(item));
            return <tr key={item.variationId}><th scope="row"><strong>{item.itemName}</strong><span>{item.variationName || 'Standard variation'}</span></th><td className="inventory-sku">{item.sku || '—'}</td><td className={`inventory-quantity ${status === 'out' ? 'out' : ''}`}><strong>{item.tracked ? formatQuantity(item.quantity) : '—'}</strong>{item.updatedAt && <small>Updated {timestamp(item.updatedAt)}</small>}</td><td><span className={`stock-badge stock-${status}`}><span />{statusLabels[status]}</span></td><td>{item.tracked ? <ThresholdInput key={thresholdKey(snapshot, item)} item={item} value={thresholdFor(item)} onSave={value => setThresholds(previous => ({ ...previous, [thresholdKey(snapshot, item)]: value }))} /> : <span className="inventory-untracked-note">Enable tracking in Square</span>}</td></tr>;
          })}</tbody></table></div>
          {!visibleItems.length && <div className="inventory-empty"><Package size={30} /><h3>{snapshot.items.length ? 'No items match this view.' : 'No items at this location yet.'}</h3><p>{snapshot.items.length ? 'Try a different search or stock status.' : 'Add item variations in Square and refresh to see them here.'}</p>{snapshot.items.length > 0 && <button className="text-button" onClick={() => { setQuery(''); setFilter('all'); }}>Show all items <ArrowRight size={13} /></button>}</div>}
          <div className="inventory-table-footer"><span>Showing {visibleItems.length} of {snapshot.items.length} item variations</span><span><ShieldCheck size={12} />{storageAvailable ? 'Thresholds save in this browser only' : 'Browser storage unavailable — thresholds will not persist'}</span></div>
        </section>
        <aside className="inventory-notes"><AlertCircle size={18} /><div><h3>A snapshot, not a live stock counter.</h3><p>Refresh to retrieve the latest Square counts. A missing count is shown as unavailable, never assumed to be zero. Thresholds flag items for your review; they do not place orders or change Square.</p>{snapshot.warnings.length > 0 && <ul>{snapshot.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>}</div></aside>
      </> : busy ? <div className="inventory-loading" role="status"><LoaderCircle size={25} className="spin" /><h2>Bringing your inventory into view.</h2><p>Reading the Square catalog and stock counts.</p></div> : connection?.configured && !locations.length && !error ? <div className="inventory-start-card"><Store size={32} /><h2>No Square locations found.</h2><p>Check that your connected Square account has an active location, then check the connection again.</p><button className="button button-outline" onClick={() => void loadSquare()}>Check connection <RefreshCw size={14} /></button></div> : <section className="inventory-start-card"><div className="inventory-start-icon"><Boxes size={40} strokeWidth={1.3} /></div><h2>Start with what you already have.</h2><p>Connect Square to bring in your item variations and their current counts. You can explore an example now, without connecting an account.</p><div className="inventory-start-steps"><span><span>01</span>Choose a location</span><span><span>02</span>Check low stock</span><span><span>03</span>Set your thresholds</span></div><button className="button button-primary" onClick={showSample} disabled={!storageReady}>Explore sample inventory <ArrowRight size={15} /></button><a className="inventory-setup-link" href="https://github.com/jaggerbaldevia-star/AE/blob/main/SQUARE.md" target="_blank" rel="noopener noreferrer">Square setup instructions <ArrowRight size={12} /></a></section>}
    </main><footer className="site-footer inventory-footer"><div><span className="brand">nearby<span className="brand-period">.</span></span><span>Small business. Clearer direction.</span></div><span>Stock counts from Square. Decisions by you.</span></footer>
  </div>;
}
