import { type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { Layers } from "lucide-react";

const NAV_ITEMS = [
  { label: "My Decks", path: "/decks" },
  { label: "New Deck", path: "/" },
];

export function TopNav({ right }: { right?: ReactNode }) {
  const location = useLocation();

  function isActive(path: string) {
    if (path === "/") return location.pathname === "/";
    return location.pathname.startsWith(path);
  }

  return (
    <header className="h-16 flex-shrink-0 bg-nav border-b border-line flex items-center justify-between px-8">
      <div className="flex items-center gap-9">
        <Link to="/" className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-accent flex items-center justify-center">
            <Layers size={14} className="text-white" aria-hidden />
          </div>
          <span className="font-heading font-bold text-[15px] text-ink">
            Teacher Content Gen
          </span>
        </Link>
        <nav className="flex gap-7" aria-label="Primary">
          {NAV_ITEMS.map((item) => {
            const active = isActive(item.path);
            return (
              <Link
                key={item.path}
                to={item.path}
                aria-current={active ? "page" : undefined}
                className={`font-body text-sm py-[19px] border-b-[2.5px] transition-colors
                  ${
                    active
                      ? "text-ink font-bold border-accent"
                      : "text-ink2 font-medium border-transparent hover:text-ink"
                  }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
      <div className="flex items-center gap-3.5">{right}</div>
    </header>
  );
}
