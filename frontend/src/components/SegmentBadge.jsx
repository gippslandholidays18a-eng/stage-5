/**
 * Visual badge + color helper for guest segments.
 * Colors are derived from the segment family — green for direct, blue for OTA,
 * red for cancellation — so the eye can scan a guest table at a glance.
 */

export function segmentColor(name) {
  if (!name) return "#6B7280";
  if (name.startsWith("Cancelled")) {
    // gradient by intent
    if (name.includes("High Intent")) return "#E05A50";
    if (name.includes("OTA Winback")) return "#F0894A";
    if (name.includes("Repeat Canceller")) return "#B83A30";
    if (name.includes("Recovered")) return "#419B72";
    return "#E05A50";
  }
  if (name.startsWith("Direct Loyal")) return "#D9A05B";
  if (name.startsWith("OTA Loyal")) return "#4B6BF5";
  if (name.startsWith("OTA First-Time")) return "#7B9CFF";
  if (name.startsWith("OTA Repeat")) return "#4B6BF5";
  if (name.startsWith("High Value Direct")) return "#E8B873";
  if (name.startsWith("High Value OTA")) return "#6B8DFF";
  if (name.includes("Most Likely to Convert")) return "#419B72";
  if (name.includes("Risk of Churning")) return "#E89A4B";
  return "#8F95A3";
}

export function SegmentBadge({ name }) {
  const c = segmentColor(name);
  return (
    <span
      className="text-[10px] px-2 py-0.5 rounded border tabular-nums"
      style={{ color: c, borderColor: `${c}44`, backgroundColor: `${c}14` }}
    >
      {name}
    </span>
  );
}
