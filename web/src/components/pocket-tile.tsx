import { Bus, PiggyBank, Receipt, ShoppingBag, Ticket, Utensils, Wallet, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import type { PocketKind } from "@/components/action-card/types";

const pocketStyles: Record<PocketKind, { tile: string; bar: string; Icon: LucideIcon }> = {
  food: { tile: "bg-food-tile text-food-ic", bar: "bg-food-ic", Icon: Utensils },
  shopping: { tile: "bg-shop-tile text-shop-ic", bar: "bg-shop-ic", Icon: ShoppingBag },
  transport: { tile: "bg-transport-tile text-transport-ic", bar: "bg-transport-ic", Icon: Bus },
  leisure: { tile: "bg-mint-soft text-mint-text", bar: "bg-mint-text", Icon: Ticket },
  bills: { tile: "bg-mint-soft text-mint-text", bar: "bg-mint-text", Icon: Receipt },
  savings: { tile: "bg-mint-soft text-mint-text", bar: "bg-mint-text", Icon: PiggyBank },
  other: { tile: "bg-mint-soft text-mint-text", bar: "bg-mint-text", Icon: Wallet },
};

export function pocketBarColor(kind: PocketKind): string {
  return pocketStyles[kind].bar;
}

export function PocketTile({ kind, size = 34, className }: { kind: PocketKind; size?: number; className?: string }) {
  const { tile, Icon } = pocketStyles[kind];
  return (
    <span
      className={cn("grid shrink-0 place-items-center", size >= 48 ? "rounded-[14px]" : "rounded-[10px]", tile, className)}
      style={{ width: size, height: size }}
    >
      <Icon className={size >= 48 ? "size-6" : "size-4"} aria-hidden />
    </span>
  );
}
