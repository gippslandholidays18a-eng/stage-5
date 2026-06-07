import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Layout from "@/components/Layout";
import Dashboard from "@/pages/Dashboard";
import Import from "@/pages/Import";
import Reservations from "@/pages/Reservations";
import Properties from "@/pages/Properties";
import History from "@/pages/History";

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
          </Route>
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;
