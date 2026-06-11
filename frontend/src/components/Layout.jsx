import { NavLink, Outlet } from "react-router-dom";
import { LayoutDashboard, Upload, Table2, Building2, History, Users, AlertTriangle, Sparkles, Settings, FileDown, Mail, Megaphone, Tag } from "lucide-react";
import { Toaster } from "sonner";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, testid: "nav-dashboard", end: true },
  { to: "/reservations", label: "Reservations", icon: Table2, testid: "nav-reservations" },
  { to: "/segments", label: "Segments", icon: Users, testid: "nav-segments" },
  { to: "/scores", label: "Scores", icon: Sparkles, testid: "nav-scores" },
  { to: "/cancellations", label: "Cancellations", icon: AlertTriangle, testid: "nav-cancellations" },
  { to: "/campaigns", label: "Campaigns", icon: Megaphone, testid: "nav-campaigns" },
  { to: "/reports", label: "Reports", icon: FileDown, testid: "nav-reports" },
  { to: "/import", label: "Import", icon: Upload, testid: "nav-import" },
  { to: "/properties", label: "Properties", icon: Building2, testid: "nav-properties" },
  { to: "/history", label: "Import History", icon: History, testid: "nav-history" },
];

const ADMIN_NAV = [
  { to: "/settings/commissions", label: "Commissions", icon: Settings, testid: "nav-settings-commissions" },
  { to: "/settings/offers", label: "Offer library", icon: Tag, testid: "nav-settings-offers" },
  { to: "/settings/digest", label: "Weekly digest", icon: Mail, testid: "nav-settings-digest" },
];

export default function Layout() {
  return (
    <div className="min-h-screen bg-[#090A0E] text-[#F2F3F5] bg-grid">
      <Toaster theme="dark" position="bottom-right" richColors />
      <div className="flex">
        {/* Sidebar */}
        <aside className="hidden lg:flex flex-col w-60 min-h-screen border-r divider bg-[#0B0C11] sticky top-0 h-screen">
          <div className="px-6 py-7 border-b divider">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-md bg-brand flex items-center justify-center">
                <span className="text-black font-display text-base font-bold">S</span>
              </div>
              <div className="leading-tight">
                <div className="font-display text-[15px] font-medium">Sourcebench</div>
                <div className="text-[10px] uppercase tracking-[0.18em] text-dim">STR Analytics</div>
              </div>
            </div>
          </div>
          <nav className="px-3 py-5 flex-1 space-y-1">
            {NAV.map(({ to, label, icon: Icon, testid, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                data-testid={testid}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                    isActive
                      ? "bg-[#1A1D24] text-white"
                      : "text-[#8F95A3] hover:text-white hover:bg-[#14161D]"
                  }`
                }
              >
                <Icon className="w-4 h-4" />
                <span>{label}</span>
              </NavLink>
            ))}

            <div className="pt-4 mt-2 border-t divider">
              <div className="px-3 pb-2 text-[10px] uppercase tracking-[0.18em] text-[#5B606B]">Admin</div>
              {ADMIN_NAV.map(({ to, label, icon: Icon, testid }) => (
                <NavLink
                  key={to}
                  to={to}
                  data-testid={testid}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                      isActive
                        ? "bg-[#1A1D24] text-white"
                        : "text-[#8F95A3] hover:text-white hover:bg-[#14161D]"
                    }`
                  }
                >
                  <Icon className="w-4 h-4" />
                  <span>{label}</span>
                </NavLink>
              ))}
            </div>
          </nav>
          <div className="px-5 py-4 text-[11px] text-dim border-t divider">
            Stage 5 · Campaign engine
          </div>
        </aside>

        {/* Main */}
        <main className="flex-1 min-w-0">
          {/* Mobile top nav */}
          <div className="lg:hidden border-b divider bg-[#0B0C11] px-4 py-3 sticky top-0 z-10">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded bg-brand flex items-center justify-center">
                  <span className="text-black font-display text-xs font-bold">S</span>
                </div>
                <span className="font-display text-sm">Sourcebench</span>
              </div>
            </div>
            <div className="flex gap-1 mt-3 overflow-x-auto -mx-1 px-1">
              {[...NAV, ...ADMIN_NAV].map(({ to, label, testid, end }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  data-testid={`m-${testid}`}
                  className={({ isActive }) =>
                    `px-3 py-1.5 text-xs rounded-full whitespace-nowrap border ${
                      isActive
                        ? "bg-[#1A1D24] text-white border-[#22252F]"
                        : "text-[#8F95A3] border-transparent hover:text-white"
                    }`
                  }
                >
                  {label}
                </NavLink>
              ))}
            </div>
          </div>

          <div className="px-4 sm:px-8 py-8 max-w-[1600px] mx-auto">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
