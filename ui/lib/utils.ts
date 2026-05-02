import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(date: Date | string): string {
  return new Date(date).toLocaleDateString("fr-TN", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatMonthYear(yyyyMM: string): string {
  const [year, month] = yyyyMM.split("-");
  const d = new Date(Number(year), Number(month) - 1);
  return d.toLocaleDateString("fr-TN", { year: "numeric", month: "long" });
}

export function formatKwh(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)} GWh`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)} MWh`;
  return `${value.toFixed(0)} kWh`;
}

export function formatTnd(value: number): string {
  return `${value.toLocaleString("fr-TN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} TND`;
}

export function getDocumentTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    steg_bill: "Facture STEG",
    steg_meter_reading: "Relevé Compteur",
    excel_report: "Rapport Mensuel",
    pdf_report: "Rapport PDF",
    pdf_invoice: "Facture PDF",
    image_invoice: "Facture (Photo)",
    unknown: "Document",
  };
  return labels[type] ?? type;
}

export function getEnergyTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    electricity: "Électricité",
    gas: "Gaz Naturel",
    natural_gas: "Gaz Naturel",
    steam: "Vapeur",
    hot_water: "Eau Chaude",
    chilled_water: "Eau Glacée",
    compressed_air: "Air Comprimé",
  };
  return labels[type] ?? type;
}

export function getAnomalyColor(type: string): string {
  const colors: Record<string, string> = {
    RECONCILIATION: "text-red-400",
    SPIKE: "text-amber-400",
    DROPOUT: "text-orange-400",
    DRIFT: "text-yellow-400",
  };
  return colors[type] ?? "text-gray-400";
}

export function confidenceColor(score: number): string {
  if (score >= 0.9) return "text-green-400";
  if (score >= 0.7) return "text-amber-400";
  return "text-red-400";
}
