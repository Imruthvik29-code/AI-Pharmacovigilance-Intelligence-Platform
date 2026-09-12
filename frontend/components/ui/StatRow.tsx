import type { ComponentType } from "react";
import { ChevronRightIcon } from "@/components/icons/Icons";
import { IconChip } from "@/components/ui/IconChip";

/**
 * The reference detail screen's list row: tinted icon chip, a title with an
 * optional second line, and either a trailing slot or a chevron.
 */
export function StatRow({
  Icon,
  surface,
  ink,
  title,
  meta,
  trailing,
  tone,
  titleColor,
}: {
  Icon: ComponentType<{ className?: string }>;
  surface: string;
  ink: string;
  title: string;
  meta?: string;
  /** Replaces the chevron, e.g. a severity pill. */
  trailing?: React.ReactNode;
  /** Background for the whole row, for the tinted findings alert. */
  tone?: string;
  titleColor?: string;
}) {
  return (
    <div
      className={`pv-row ${tone ? "pv-row-tinted" : ""}`}
      style={tone ? { backgroundColor: tone } : undefined}
    >
      <IconChip
        Icon={Icon}
        surface={tone ? "rgb(255 255 255 / 0.7)" : surface}
        ink={ink}
        size="md"
      />
      <div className="min-w-0 flex-1">
        <p className="pv-row-title" style={titleColor ? { color: titleColor } : undefined}>
          {title}
        </p>
        {meta ? <p className="pv-row-meta">{meta}</p> : null}
      </div>
      {trailing ?? (
        <span className="pv-chevron" aria-hidden="true">
          <ChevronRightIcon className="h-[1.125rem] w-[1.125rem]" />
        </span>
      )}
    </div>
  );
}
