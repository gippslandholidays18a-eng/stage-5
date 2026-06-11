import { useEffect, useState } from "react";
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
import { Plus, Trash2, Save, Tag } from "lucide-react";

const TYPES = [
  { value: "percentage", label: "% off" },
  { value: "fixed", label: "Fixed $" },
  { value: "none", label: "No discount" },
];

const CATEGORIES = ["Direct booking incentive", "Loyalty", "Win-back", "Seasonal", "Custom"];

const BLANK = {
  code: "",
  name: "",
  description: "",
  discount_type: "percentage",
  discount_value: 10,
  applies_to: "all",
  active: true,
  expires_at: "",
  category: "Custom",
};

export default function OffersSettings() {
  const [offers, setOffers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);
  const [draft, setDraft] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api.get("/settings/offers").then((r) => {
      if (cancelled) return;
      setOffers(r.data.offers || []);
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, [version]);

  const save = async (offer) => {
    try {
      const payload = { ...offer, code: (offer.code || "").trim().toUpperCase() };
      if (!payload.code) {
        toast.error("Code is required");
        return;
      }
      await api.post("/settings/offers", payload);
      toast.success(`Offer ${payload.code} saved`);
      setDraft(null);
      setVersion((v) => v + 1);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    }
  };

  const remove = async (code) => {
    if (!window.confirm(`Delete ${code}?`)) return;
    try {
      await api.delete(`/settings/offers/${encodeURIComponent(code)}`);
      toast.success("Offer removed");
      setVersion((v) => v + 1);
    } catch {
      toast.error("Delete failed");
    }
  };

  const toggleActive = async (offer) => {
    await save({ ...offer, active: !offer.active });
  };

  if (loading) return <div className="text-dim text-sm">Loading…</div>;

  const grouped = {};
  for (const o of offers) {
    const k = o.category || "Custom";
    grouped[k] = grouped[k] || [];
    grouped[k].push(o);
  }

  return (
    <div data-testid="offers-settings-page" className="space-y-8 max-w-5xl">
      <header>
        <div className="text-[11px] uppercase tracking-[0.22em] text-dim">Settings · Admin</div>
        <h1 className="font-display text-3xl tracking-tight mt-1">Offer library</h1>
        <p className="text-sm text-dim mt-2 max-w-2xl">
          Recommended offers used by the campaign engine. Codes are referenced from /campaigns audience cards and exported into CSV briefs.
        </p>
      </header>

      <button
        data-testid="add-offer-button"
        onClick={() => setDraft({ ...BLANK })}
        className="inline-flex items-center gap-2 bg-brand text-black text-sm font-medium px-4 py-2 rounded-md hover:opacity-90"
      >
        <Plus className="w-4 h-4" /> New offer
      </button>

      {draft && (
        <OfferEditor
          offer={draft}
          onChange={setDraft}
          onSave={() => save(draft)}
          onCancel={() => setDraft(null)}
        />
      )}

      {CATEGORIES.map((cat) => grouped[cat]?.length > 0 && (
        <section key={cat}>
          <h2 className="font-display text-base text-white mb-3">{cat}</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {grouped[cat].map((o) => (
              <OfferRow
                key={o.code}
                offer={o}
                onToggle={() => toggleActive(o)}
                onEdit={() => setDraft({ ...o, expires_at: o.expires_at || "" })}
                onDelete={() => remove(o.code)}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function OfferRow({ offer, onToggle, onEdit, onDelete }) {
  return (
    <div
      data-testid={`offer-row-${offer.code}`}
      className={`surface rounded-md p-4 flex items-start gap-3 ${!offer.active ? "opacity-50" : ""}`}
    >
      <div className="w-9 h-9 rounded-md bg-[#1A1D24] border divider flex items-center justify-center shrink-0">
        <Tag className="w-4 h-4 text-[#D9A05B]" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[#D9A05B] text-sm">{offer.code}</span>
          <span className="text-white text-sm">·</span>
          <span className="text-white text-sm truncate">{offer.name}</span>
        </div>
        <div className="text-xs text-dim mt-1">{offer.description}</div>
        <div className="text-[10px] text-dim mt-2 uppercase tracking-[0.15em]">
          {offer.discount_type === "percentage" && `${offer.discount_value}% off`}
          {offer.discount_type === "fixed" && `$${offer.discount_value} off`}
          {offer.discount_type === "none" && "Non-discount offer"}
        </div>
      </div>
      <div className="flex flex-col items-end gap-2 shrink-0">
        <Switch
          checked={offer.active}
          onCheckedChange={onToggle}
          data-testid={`offer-active-${offer.code}`}
        />
        <div className="flex gap-1">
          <button
            onClick={onEdit}
            data-testid={`offer-edit-${offer.code}`}
            className="text-xs text-dim hover:text-white px-2"
          >
            Edit
          </button>
          <button
            onClick={onDelete}
            data-testid={`offer-delete-${offer.code}`}
            className="text-dim hover:text-[#E05A50]"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}

function OfferEditor({ offer, onChange, onSave, onCancel }) {
  const set = (patch) => onChange({ ...offer, ...patch });
  return (
    <div className="surface rounded-md p-6 space-y-4" data-testid="offer-editor">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="text-[10px] uppercase tracking-[0.15em] text-dim">Code</label>
          <Input
            placeholder="DIRECT20"
            value={offer.code}
            data-testid="offer-code-input"
            onChange={(e) => set({ code: e.target.value.toUpperCase() })}
            className="mt-1 bg-transparent border-[#22252F]"
          />
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-[0.15em] text-dim">Name</label>
          <Input
            value={offer.name}
            data-testid="offer-name-input"
            onChange={(e) => set({ name: e.target.value })}
            className="mt-1 bg-transparent border-[#22252F]"
          />
        </div>
        <div className="sm:col-span-2">
          <label className="text-[10px] uppercase tracking-[0.15em] text-dim">Description</label>
          <Input
            value={offer.description}
            data-testid="offer-description-input"
            onChange={(e) => set({ description: e.target.value })}
            className="mt-1 bg-transparent border-[#22252F]"
          />
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-[0.15em] text-dim">Discount type</label>
          <Select value={offer.discount_type} onValueChange={(v) => set({ discount_type: v })}>
            <SelectTrigger data-testid="offer-type-select" className="mt-1 bg-transparent border-[#22252F]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-[#12141A] border-[#22252F] text-white">
              {TYPES.map((t) => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-[0.15em] text-dim">Discount value</label>
          <Input
            type="number"
            value={offer.discount_value}
            data-testid="offer-value-input"
            onChange={(e) => set({ discount_value: parseFloat(e.target.value) || 0 })}
            className="mt-1 bg-transparent border-[#22252F]"
          />
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-[0.15em] text-dim">Category</label>
          <Select value={offer.category} onValueChange={(v) => set({ category: v })}>
            <SelectTrigger className="mt-1 bg-transparent border-[#22252F]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-[#12141A] border-[#22252F] text-white">
              {CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-[0.15em] text-dim">Expires (optional)</label>
          <input
            type="date"
            value={offer.expires_at || ""}
            onChange={(e) => set({ expires_at: e.target.value })}
            className="mt-1 bg-transparent border border-[#22252F] rounded-md px-3 py-2 text-sm text-white w-full"
          />
        </div>
      </div>

      <div className="flex justify-end gap-2">
        <button onClick={onCancel} className="px-4 py-2 text-sm text-dim hover:text-white">Cancel</button>
        <button
          onClick={onSave}
          data-testid="save-offer-button"
          className="inline-flex items-center gap-2 bg-brand text-black text-sm font-medium px-4 py-2 rounded-md hover:opacity-90"
        >
          <Save className="w-4 h-4" /> Save offer
        </button>
      </div>
    </div>
  );
}
