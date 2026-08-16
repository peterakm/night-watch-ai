import type { ShiftInfo } from "../types";

export function ShiftClock({ shift }: { shift: ShiftInfo }) {
  const simTime = new Date(shift.sim_time);
  const timeLabel = simTime.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const startedLabel = new Date(shift.start_time).toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });

  return (
    <div className="shift-clock">
      <div className="shift-clock__row">
        <span className={`shift-clock__dot${shift.running ? " shift-clock__dot--live" : ""}`} aria-hidden="true" />
        <span className="shift-clock__time">{timeLabel}</span>
      </div>
      <span className="muted muted--small">
        {shift.running
          ? `On since ${startedLabel}`
          : `Stopped ${
              shift.stopped_at
                ? new Date(shift.stopped_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
                : ""
            }`}
      </span>
    </div>
  );
}
