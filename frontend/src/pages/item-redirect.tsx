import { useEffect, useState } from 'react';
import { useRoute, useLocation } from 'wouter';
import { Loader2, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { getItem } from '../api/itemArtifacts';

/**
 * Resolves `/items/:id` to the canonical `/orders/:orderId/items/:itemId`
 * URL. The item-preview page lives under the order route because it needs
 * the order context (PO number, importer) for the header, but many
 * existing deep links and external references use the bare `/items/{id}`
 * shape — this tiny shim bridges both.
 */
export default function ItemRedirect() {
  const [, params] = useRoute('/items/:id');
  const [, setLocation] = useLocation();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const id = params?.id;
    if (!id) return;
    let cancelled = false;
    (async () => {
      try {
        const item = await getItem(id);
        if (!cancelled) {
          setLocation(`/orders/${item.order_id}/items/${item.id}`, { replace: true });
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Item not found');
        }
      }
    })();
    return () => { cancelled = true; };
  }, [params?.id, setLocation]);

  if (error) {
    return (
      <div className="p-12 text-center space-y-3">
        <div className="flex justify-center">
          <AlertCircle className="w-8 h-8 text-red-500" />
        </div>
        <p className="text-sm font-medium">Item not found</p>
        <p className="text-xs text-muted-foreground max-w-md mx-auto">{error}</p>
        <Button variant="link" onClick={() => setLocation('/orders')}>Back to Orders</Button>
      </div>
    );
  }

  return (
    <div className="p-12 flex flex-col items-center text-muted-foreground">
      <Loader2 className="w-6 h-6 animate-spin" />
      <p className="text-sm mt-3">Looking up item…</p>
    </div>
  );
}
