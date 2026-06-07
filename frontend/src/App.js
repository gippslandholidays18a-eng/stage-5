import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Layout from "@/components/Layout";
import Dashboard from "@/pages/Dashboard";
import Import from "@/pages/Import";
import Reservations from "@/pages/Reservations";
import Properties from "@/pages/Properties";
import History from "@/pages/History";
import Segments from "@/pages/Segments";
import GuestProfile from "@/pages/GuestProfile";
import Cancellations from "@/pages/Cancellations";

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="reservations" element={<Reservations />} />
            <Route path="import" element={<Import />} />
            <Route path="properties" element={<Properties />} />
            <Route path="history" element={<History />} />
            <Route path="segments" element={<Segments />} />
            <Route path="guests/:id" element={<GuestProfile />} />
            <Route path="cancellations" element={<Cancellations />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;
