import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Trash2, Plus, Building2, Pencil, Save, X } from "lucide-react";

const TYPES = ["Apartment", "House", "Townhouse", "Studio", "Villa", "Cabin", "Other"];

const BLANK = {
  name: "",
  property_name: "",
  unit_number: "",
  complex: "",
  property_type: "Apartment",
  bedrooms: "",
  bathrooms: "",
  active: true,
  notes: "",
};

export default function Properties() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);
  const [draft, setDraft] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [editDraft, setEditDraft] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api.get("/properties").then((r) => {
      if (cancelled) return;
      setItems(r.data.items || []);
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, [version]);

  const refresh = useCallback(() => setVersion((v) => v + 1), []);

  const createOne = async () => {
    if (!draft.name.trim()) {
      toast.error("Display name is required");
      return;
    }
    try {
      const payload = {
        ...draft,
        bedrooms: draft.bedrooms === "" ? null : parseInt(draft.bedrooms),
        bathrooms: draft.bathrooms === "" ? null : parseInt(draft.bathrooms),
      };
      await api.post("/properties", payload);
      toast.success("Property added");
      setDraft(null);
      refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not add property");
    }
  };

  const startEdit = (p) => {
    setEditingId(p.id);
    setEditDraft({
      name: p.name || "",
      property_name: p.property_name || "",
      unit_number: p.unit_number || "",
      complex: p.complex || "",
      property_type: p.property_type || "Apartment",
      bedrooms: p.bedrooms ?? "",
      bathrooms: p.bathrooms ?? "",
      active: p.active !== false,
      notes: p.notes || "",
    });
  };

  const saveEdit = async (id) => {
    try {
      const payload = {
        ...editDraft,
        bedrooms: editDraft.bedrooms === "" ? null : parseInt(editDraft.bedrooms),
        bathrooms: editDraft.bathrooms === "" ? null : parseInt(editDraft.bathrooms),
      };
      await api.put(`/properties/${id}`, payload);
      toast.success("Property updated");
      setEditingId(null);
      setEditDraft(null);
      refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    }
  };

  const toggleActive = async (p) => {
    try {
      await api.put(`/properties/${p.id}`, { active: !p.active });
      refresh();
    } catch {
      toast.error("Could not toggle");
    }
  };

  const remove = async (p) => {
    if (!window.confirm(`Delete "${p.name}"?`)) return;
    try {
      await api.delete(`/properties/${p.id}`);
      toast.success("Removed");
      refresh();
    } catch {
      toast.error("Could not remove");
    }
  };

  if (loading) return <div className="text-dim text-sm">Loading…</div>;

  const byComplex = {};
  for (const p of items) {
    const k = p.complex || "(Unassigned)";
    byComplex[k] = byComplex[k] || [];
    byComplex[k].push(p);
  }

  return (
    <div data-testid="properties-page" className="space-y-8 max-w-6xl">
      <header className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-[0.22em] text-dim">Properties</div>
          <h1 className="font-display text-3xl tracking-tight mt-1">Managed properties</h1>
          <p className="text-sm text-dim mt-2 max-w-2xl">
            {items.length} properties. Edit name, complex, unit, type, bedroom and bathroom counts, active status, and notes inline — no code changes needed.
          </p>
        </div>
        <button
          data-testid="add-property-button"
          onClick={() => setDraft({ ...BLANK })}
          className="inline-flex items-center gap-2 bg-brand text-black text-sm font-medium px-4 py-2 rounded-md hover:opacity-90"
        >
          <Plus className="w-4 h-4" /> Add property
        </button>
      </header>

      {draft && (
        <PropertyEditor
          draft={draft}
          setDraft={setDraft}
          onSave={createOne}
          onCancel={() => setDraft(null)}
          mode="create"
        />
      )}

      {Object.entries(byComplex).map(([complexName, group]) => (
        <section key={complexName}>
          <h2 className="font-display text-base text-white mb-3 flex items-center gap-2">
            <Building2 className="w-4 h-4 text-[#D9A05B]" /> {complexName}
            <span className="text-xs text-dim">· {group.length}</span>
          </h2>
          <div className="surface rounded-md overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-[#0E1015]">
                <tr className="text-[10px] uppercase tracking-[0.15em] text-[#6B7280]">
                  <th className="text-left px-4 py-3 font-semibold">Property</th>
                  <th className="text-left px-4 py-3 font-semibold">Unit</th>
                  <th className="text-left px-4 py-3 font-semibold">Type</th>
                  <th className="text-center px-4 py-3 font-semibold">Bed / Bath</th>
                  <th className="text-center px-4 py-3 font-semibold">Active</th>
                  <th className="text-right px-4 py-3 font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody>
                {group.map((p) =>
                  editingId === p.id ? (
                    <tr key={p.id} className="bg-[#15181F]">
                      <td colSpan={6} className="p-4">
                        <PropertyEditor
                          draft={editDraft}
                          setDraft={setEditDraft}
                          onSave={() => saveEdit(p.id)}
                          onCancel={() => { setEditingId(null); setEditDraft(null); }}
                          mode="edit"
                        />
                      </td>
                    </tr>
                  ) : (
                    <tr key={p.id} className={`tbl-row ${!p.active ? "opacity-50" : ""}`} data-testid={`property-row-${p.id}`}>
                      <td className="px-4 py-3">
                        <div className="text-white">{p.name}</div>
                        {p.notes && <div className="text-[11px] text-dim mt-0.5">{p.notes}</div>}
                      </td>
                      <td className="px-4 py-3 text-dim font-mono">{p.unit_number || "—"}</td>
                      <td className="px-4 py-3 text-dim">{p.property_type || "—"}</td>
                      <td className="px-4 py-3 text-center text-dim tabular-nums">
                        {(p.bedrooms ?? "—")} / {(p.bathrooms ?? "—")}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <Switch
                          checked={p.active !== false}
                          onCheckedChange={() => toggleActive(p)}
                          data-testid={`active-${p.id}`}
                        />
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => startEdit(p)}
                          data-testid={`edit-${p.id}`}
                          className="text-dim hover:text-white mr-2"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => remove(p)}
                          data-testid={`delete-${p.id}`}
                          className="text-dim hover:text-[#E05A50]"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    </tr>
                  )
                )}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </div>
  );
}

function PropertyEditor({ draft, setDraft, onSave, onCancel, mode }) {
  const set = (patch) => setDraft({ ...draft, ...patch });
  return (
    <div className="surface rounded-md p-5 space-y-3" data-testid={`property-editor-${mode}`}>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="sm:col-span-2">
          <label className="text-[10px] uppercase tracking-[0.15em] text-dim">Display name *</label>
          <Input
            placeholder="e.g. Ground Floor Apartment — Unit 29"
            value={draft.name}
            onChange={(e) => set({ name: e.target.value })}
            data-testid="prop-name"
            className="mt-1 bg-transparent border-[#22252F] focus-visible:ring-1 focus-visible:ring-[#D9A05B]"
          />
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-[0.15em] text-dim">Property name</label>
          <Input
            value={draft.property_name}
            onChange={(e) => set({ property_name: e.target.value })}
            data-testid="prop-property-name"
            className="mt-1 bg-transparent border-[#22252F]"
          />
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-[0.15em] text-dim">Unit number</label>
          <Input
            value={draft.unit_number}
            onChange={(e) => set({ unit_number: e.target.value })}
            data-testid="prop-unit"
            className="mt-1 bg-transparent border-[#22252F]"
          />
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-[0.15em] text-dim">Complex</label>
          <Input
            value={draft.complex}
            onChange={(e) => set({ complex: e.target.value })}
            data-testid="prop-complex"
            className="mt-1 bg-transparent border-[#22252F]"
          />
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-[0.15em] text-dim">Type</label>
          <Select value={draft.property_type} onValueChange={(v) => set({ property_type: v })}>
            <SelectTrigger data-testid="prop-type" className="mt-1 bg-transparent border-[#22252F]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-[#12141A] border-[#22252F] text-white">
              {TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-[0.15em] text-dim">Bedrooms</label>
          <Input
            type="number"
            min="0"
            value={draft.bedrooms}
            onChange={(e) => set({ bedrooms: e.target.value })}
            data-testid="prop-bedrooms"
            className="mt-1 bg-transparent border-[#22252F]"
          />
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-[0.15em] text-dim">Bathrooms</label>
          <Input
            type="number"
            min="0"
            value={draft.bathrooms}
            onChange={(e) => set({ bathrooms: e.target.value })}
            data-testid="prop-bathrooms"
            className="mt-1 bg-transparent border-[#22252F]"
          />
        </div>
        <div className="sm:col-span-2">
          <label className="text-[10px] uppercase tracking-[0.15em] text-dim">Notes</label>
          <Input
            value={draft.notes}
            onChange={(e) => set({ notes: e.target.value })}
            data-testid="prop-notes"
            className="mt-1 bg-transparent border-[#22252F]"
          />
        </div>
        <div className="flex items-center gap-3">
          <Switch
            checked={draft.active}
            onCheckedChange={(v) => set({ active: v })}
            data-testid="prop-active"
          />
          <span className="text-sm text-white">{draft.active ? "Active" : "Inactive"}</span>
        </div>
      </div>
      <div className="flex justify-end gap-2 pt-2">
        <button
          onClick={onCancel}
          className="inline-flex items-center gap-1.5 text-sm text-dim hover:text-white px-3 py-2"
        >
          <X className="w-3.5 h-3.5" /> Cancel
        </button>
        <button
          onClick={onSave}
          data-testid="prop-save"
          className="inline-flex items-center gap-2 bg-brand text-black text-sm font-medium px-4 py-2 rounded-md hover:opacity-90"
        >
          <Save className="w-4 h-4" /> {mode === "edit" ? "Save changes" : "Add property"}
        </button>
      </div>
    </div>
  );
}
