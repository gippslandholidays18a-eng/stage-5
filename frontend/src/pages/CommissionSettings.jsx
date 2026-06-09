import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { RotateCcw, Save, Percent } from "lucide-react";

export default function CommissionSettings() {
  const [rates, setRates] = useState({});
  const [defaults, setDefaults] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.get("/settings/commissions").then((r) => {
      if (cancelled) return;
      setRates({ ...r.data.rates });
      setDefaults({ ...r.data.defaults });
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const updateRate = (k, v) => {
    setRates((prev) => ({ ...prev, [k]: v }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      // coerce all values to floats
      const cleaned = {};
      for (const [k, v] of Object.entries(rates)) {
        const n = parseFloat(v);
        if (!isNaN(n) && n >= 0 && n <= 100) cleaned[k] = n;
      }
      const r = await api.put("/settings/commissions", { rates: cleaned });
      setRates({ ...r.data.rates });
      toast.success("Rates saved. Historical commission costs recalculated.");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save");
    } finally {
      setSaving(false);
    }
  };

  const resetDefaults = () => {
    setRates({ ...defaults });
    toast.info("Reset to defaults. Click Save to apply.");
  };

  if (loading) return <div className="text-dim text-sm">Loading…</div>;

  const keys = Object.keys(defaults);

  return (
    <div data-testid="commission-settings-page" className="space-y-8 max-w-3xl">
      <header>
        <div className="text-[11px] uppercase tracking-[0.22em] text-dim">Settings · Admin</div>
        <h1 className="font-display text-3xl tracking-tight mt-1">OTA commission rates</h1>
        <p className="text-sm text-dim mt-2 max-w-2xl">
          These rates are used to estimate commission costs per booking. Saving recalculates every historical OTA reservation immediately.
        </p>
      </header>

      <div className="surface rounded-md p-6 space-y-4">
        {keys.map((k) => (
          <div key={k} className="grid grid-cols-1 sm:grid-cols-[1fr_180px_120px] gap-3 items-center">
            <div>
              <div className="text-sm text-white">{k}</div>
              <div className="text-[11px] text-dim">Default: {defaults[k]}%</div>
            </div>
            <div className="relative">
              <Input
                type="number"
                step="0.1"
                min="0"
                max="100"
                value={rates[k] ?? ""}
                onChange={(e) => updateRate(k, e.target.value)}
                data-testid={`commission-rate-${k.replace(/[^a-z0-9]+/gi,'-').toLowerCase()}`}
                className="bg-transparent border-[#22252F] focus-visible:ring-1 focus-visible:ring-[#D9A05B] pr-9"
              />
              <Percent className="w-3.5 h-3.5 absolute right-3 top-1/2 -translate-y-1/2 text-dim pointer-events-none" />
            </div>
            <div className="text-right">
              {parseFloat(rates[k]) !== defaults[k] && (
                <span className="text-[10px] text-[#D9A05B] uppercase tracking-wider">Modified</span>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="flex flex-col-reverse sm:flex-row gap-3 sm:items-center sm:justify-end">
        <button
          data-testid="reset-defaults-button"
          onClick={resetDefaults}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-md text-sm border border-[#22252F] text-dim hover:text-white hover:bg-[#14161D]"
        >
          <RotateCcw className="w-3.5 h-3.5" /> Reset to defaults
        </button>
        <button
          data-testid="save-rates-button"
          onClick={handleSave}
          disabled={saving}
          className="inline-flex items-center gap-2 bg-brand text-black text-sm font-medium px-5 py-2.5 rounded-md hover:opacity-90 disabled:opacity-50"
        >
          <Save className="w-4 h-4" /> {saving ? "Saving…" : "Save rates"}
        </button>
      </div>
    </div>
  );
}
