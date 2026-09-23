// Line codes, names and colours. The codes are lineorder_line_stops.line_code
// and mrtguessr_stations.lines; names and colours must match LINES in
// scripts/seed_supabase.py.

export const LINES = {
  NS: { name: "North-South Line", color: "#d42e12" },
  EW: { name: "East-West Line", color: "#009645" },
  NE: { name: "North East Line", color: "#9900aa" },
  CC: { name: "Circle Line", color: "#fa9e0d" },
  DT: { name: "Downtown Line", color: "#005ec4" },
  TE: { name: "Thomson-East Coast Line", color: "#9d5b25" },
  BP: { name: "Bukit Panjang LRT", color: "#748477" },
  SK: { name: "Sengkang LRT", color: "#748477" },
  PG: { name: "Punggol LRT", color: "#748477" },
};

export const lineName = (code) => LINES[code]?.name ?? code;
