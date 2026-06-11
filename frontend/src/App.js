import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Layout from "@/components/Layout";
import AnalyticsDashboard from "@/pages/AnalyticsDashboard";
import Import from "@/pages/Import";
import Reservations from "@/pages/Reservations";
import Properties from "@/pages/Properties";
import History from "@/pages/History";
import Segments from "@/pages/Segments";
import GuestProfile from "@/pages/GuestProfile";
import Cancellations from "@/pages/Cancellations";
import Scores from "@/pages/Scores";
import CommissionSettings from "@/pages/CommissionSettings";
import Reports from "@/pages/Reports";

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<AnalyticsDashboard />} />
            <Route path="reservations" element={<Reservations />} />
            <Route path="import" element={<Import />} />
            <Route path="properties" element={<Properties />} />
            <Route path="history" element={<History />} />
            <Route path="segments" element={<Segments />} />
            <Route path="guests/:id" element={<GuestProfile />} />
            <Route path="cancellations" element={<Cancellations />} />
            <Route path="scores" element={<Scores />} />
            <Route path="reports" element={<Reports />} />
            <Route path="settings/commissions" element={<CommissionSettings />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;
