import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Trash2, Plus, Building2 } from "lucide-react";

const PLACEHOLDERS = [
  "https://images.unsplash.com/photo-1613490493576-7fde63acd811?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMzN8MHwxfHNlYXJjaHwxfHxsdXh1cnklMjBtb2Rlcm4lMjB2aWxsYSUyMGFyY2hpdGVjdHVyZXxlbnwwfHx8fDE3ODA3MDgxMTB8MA&ixlib=rb-4.1.0&q=85",
  "https://images.unsplash.com/photo-1706808849780-7a04fbac83ef?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMzN8MHwxfHNlYXJjaHwzfHxsdXh1cnklMjBtb2Rlcm4lMjB2aWxsYSUyMGFyY2hpdGVjdHVyZXxlbnwwfHx8fDE3ODA3MDgxMTB8MA&ixlib=rb-4.1.0&q=85",
];

export default function Properties() {
  const [items, setItems] = useState([]);
  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api.get("/properties").then((r) => {
      if (cancelled) return;
      setItems(r.data.items || []);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [version]);

  const refresh = useCallback(() => setVersion((v) => v + 1), []);

  const add = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      await api.post("/properties", { name: name.trim(), notes });
      toast.success("Property added");
      setName("");
      setNotes("");
      refresh();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not add property");
    }
  };

  const remove = async (id) => {
    try {
      await api.delete(`/properties/${id}`);
      toast.success("Removed");
      refresh();
    } catch {
      toast.error("Could not remove");
    }
  };

  return (
    <div data-testid="properties-page" className="space-y-8 max-w-5xl">
      <header>
        <div className="text-[11px] uppercase tracking-[0.22em] text-dim">Properties</div>
        <h1 className="font-display text-3xl tracking-tight mt-1">Managed properties</h1>
        <p className="text-sm text-dim mt-2">
          Add the properties you operate. Used as the canonical list for filtering and future stages.
        </p>
      </header>

      <form
        onSubmit={add}
        data-testid="add-property-form"
        className="surface rounded-md p-6 grid sm:grid-cols-[1fr_1fr_auto] gap-3"
      >
        <Input
          data-testid="property-name-input"
          placeholder="Property name (e.g. Coral Bay 12B)"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="bg-transparent border-[#22252F] focus-visible:ring-1 focus-visible:ring-[#D9A05B]"
        />
        <Input
          data-testid="property-notes-input"
          placeholder="Notes (optional)"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          className="bg-transparent border-[#22252F]"
        />
        <button
          data-testid="add-property-button"
          type="submit"
          className="bg-brand text-black px-4 py-2 rounded-md text-sm font-medium hover:opacity-90 inline-flex items-center gap-2"
        >
          <Plus className="w-4 h-4" /> Add
        </button>
      </form>

      {loading ? (
        <div className="text-dim text-sm">Loading…</div>
      ) : items.length === 0 ? (
        <div className="surface rounded-md p-12 text-center">
          <Building2 className="w-8 h-8 text-[#D9A05B] mx-auto" />
          <div className="text-sm text-dim mt-3">No properties yet. Add your first above.</div>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="property-list">
          {items.map((p, i) => (
            <div key={p.id} className="surface rounded-md overflow-hidden group">
              <div
                className="h-32 bg-cover bg-center"
                style={{
                  backgroundImage: `url(${PLACEHOLDERS[i % PLACEHOLDERS.length]})`,
                }}
              />
              <div className="p-4 flex items-start justify-between">
                <div className="min-w-0">
                  <div className="font-display text-base text-white truncate">{p.name}</div>
                  {p.notes && <div className="text-xs text-dim mt-1 truncate">{p.notes}</div>}
                </div>
                <button
                  data-testid={`delete-property-${p.id}`}
                  onClick={() => remove(p.id)}
                  className="text-dim hover:text-[#E05A50] opacity-0 group-hover:opacity-100 transition p-1"
                  title="Remove"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
