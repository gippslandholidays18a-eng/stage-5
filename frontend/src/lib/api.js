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
  Stayz: "#7B4FE6",
  VRBO: "#1D4ED8",
  Expedia: "#FCE300",
  "Other OTA": "#4B6BF5",
  "Direct — Website": "#D9A05B",
  "Direct — Phone": "#E89A4B",
  "Direct — Email": "#C58D52",
  "Direct — Repeat Guest": "#A8763E",
  Unknown: "#6B7280",
};

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
