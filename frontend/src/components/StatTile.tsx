export function StatTile({
  label,
  value,
  unit,
  abnormal,
}: {
  label: string;
  value: number | string;
  unit?: string;
  abnormal?: boolean;
}) {
  return (
    <div className={`stat-tile${abnormal ? " stat-tile--abnormal" : ""}`}>
      <div className="stat-tile__label">{label}</div>
      <div className="stat-tile__value">
        {value}
        {unit && <span className="stat-tile__unit">{unit}</span>}
      </div>
    </div>
  );
}
