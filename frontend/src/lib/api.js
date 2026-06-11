import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API,
  headers: { "Content-Type": "application/json" },
});

export const SOURCE_COLORS = {
  Airbnb: "#FF5A5F",
  "Booking.com": "#003580",
  Stayz: "#34A853",
  VRBO: "#16B5C6",
  Expedia: "#FFC107",
  "Other OTA": "#6B7280",
  "Direct — Website": "#007786",
  "Direct — Phone": "#0A8895",
  "Direct — Email": "#16959D",
  "Direct — Repeat Guest": "#1E9FA6",
  Unknown: "#6B7280",
};

export const CHANNEL_COLORS = {
  Direct: "#007786",
  OTA: "#4B6BF5",
};

export const fmtAUD = (n) =>
  new Intl.NumberFormat("en-AU", {
    style: "currency",
    currency: "AUD",
    maximumFractionDigits: 0,
  }).format(Number(n || 0));

export const fmtPct = (n) =>
  `${(Math.round(Number(n || 0) * 10) / 10).toFixed(1)}%`;

export const ALL_SOURCES = [
  "Airbnb",
  "Booking.com",
  "Stayz",
  "VRBO",
  "Expedia",
  "Other OTA",
  "Direct — Website",
  "Direct — Phone",
  "Direct — Email",
  "Direct — Repeat Guest",
  "Unknown",
];

export const fmtMoney = (n) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(Number(n || 0));

export const fmtNumber = (n) =>
  new Intl.NumberFormat("en-US").format(Number(n || 0));

export const fmtDate = (iso) => {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "—";
    return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "2-digit" });
  } catch {
    return "—";
  }
};
