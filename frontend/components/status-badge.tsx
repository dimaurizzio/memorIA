import type { DocStatus } from "@/lib/types";

const MAP: Record<DocStatus, { label: string; cls: string }> = {
  approved: { label: "Aprobado", cls: "bg-[#dcfce7] text-[#15803d]" },
  draft:    { label: "Borrador", cls: "bg-[#fef3c7] text-[#92400e]" },
  rejected: { label: "Rechazado", cls: "bg-[#fee2e2] text-[#991b1b]" },
};

export function StatusBadge({ status }: { status: DocStatus }) {
  const { label, cls } = MAP[status] ?? MAP.draft;
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide uppercase ${cls}`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {label}
    </span>
  );
}
