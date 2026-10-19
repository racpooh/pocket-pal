"use client";

import { List, MessageCircle, Target, Wallet } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

// Activity and Goal routes come later; their tabs point at the routes they will use.
const TABS = [
  { label: "Chat", href: "/", Icon: MessageCircle },
  { label: "Pockets", href: "/pockets", Icon: Wallet },
  { label: "Activity", href: "/activity", Icon: List },
  { label: "Goal", href: "/goal", Icon: Target },
];

export function TabBar() {
  const pathname = usePathname();
  return (
    <nav aria-label="Main" className="grid grid-cols-4 border-t border-line bg-card px-2 pt-1.5 pb-[max(10px,env(safe-area-inset-bottom))]">
      {TABS.map(({ label, href, Icon }) => {
        const current = pathname === href;
        return (
          <Link
            key={label}
            href={href}
            aria-current={current ? "page" : undefined}
            className={cn(
              "flex min-h-[58px] flex-col items-center justify-center gap-0.5 rounded-[14px] text-xs font-semibold",
              current ? "bg-mint-soft text-mint-text" : "text-muted-foreground",
            )}
          >
            <Icon className="size-[22px]" aria-hidden />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
