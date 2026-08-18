"use client";

import Link from "next/link";
import { usePathname, useParams, useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { HomeIcon } from "@/components/IconButton";
import { cn } from "@/lib/utils";

const GLOBAL_LINKS = [{ href: "/dashboard", label: "Datasets" }, { href: "/settings", label: "Settings" }];

function datasetLinks(datasetId: string) {
  return [
    { href: `/dashboard/${datasetId}/types`, label: "Column Types" },
    { href: `/dashboard/${datasetId}/reports`, label: "Visual Reports" },
    { href: `/dashboard/${datasetId}/presentation`, label: "Presentation" },
  ];
}

// Responsive via layout direction, not a hamburger drawer: a left column on
// md: and up, collapsing to a horizontal top bar of the same links on small
// screens -- this codebase has no mobile-drawer pattern to extend, and a
// full drawer is a bigger investment than the ask here.
export function DashboardSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const params = useParams<{ datasetId?: string }>();

  async function handleSignOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/login");
    router.refresh();
  }

  const contextualLinks = params.datasetId ? datasetLinks(params.datasetId) : [];

  return (
    <nav className="flex shrink-0 flex-row flex-wrap items-center gap-1 border-b border-border p-3 text-sm md:h-screen md:w-56 md:flex-col md:items-stretch md:gap-4 md:overflow-y-auto md:border-b-0 md:border-r md:p-4">
      <Link href="/dashboard" title="CSV Data Analysis Tool" aria-label="CSV Data Analysis Tool">
        <span className="block h-7 w-7">
          <HomeIcon />
        </span>
      </Link>

      <div className="flex flex-row flex-wrap gap-1 md:flex-col md:gap-1">
        {GLOBAL_LINKS.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={cn(
              "rounded px-2 py-1.5 hover:bg-accent/10",
              pathname === link.href && "bg-accent/10 font-medium"
            )}
          >
            {link.label}
          </Link>
        ))}
      </div>

      {contextualLinks.length > 0 && (
        <div className="flex flex-row flex-wrap gap-1 border-border md:mt-2 md:flex-col md:gap-1 md:border-t md:pt-2">
          <span className="hidden px-2 text-xs uppercase tracking-wide opacity-50 md:block">This dataset</span>
          {contextualLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={cn(
                "rounded px-2 py-1.5 hover:bg-accent/10",
                pathname === link.href && "bg-accent/10 font-medium"
              )}
            >
              {link.label}
            </Link>
          ))}
        </div>
      )}

      <button
        type="button"
        onClick={handleSignOut}
        className="rounded px-2 py-1.5 text-left hover:bg-accent/10 md:mt-auto"
      >
        Sign out
      </button>
    </nav>
  );
}
