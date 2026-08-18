import type { Metadata } from "next";

// Generated with backend/scripts/generate_seo.py --route /signup
export const metadata: Metadata = {
  title: "Sign Up",
  description:
    "Create a free account to turn CSV files into instant business intelligence — schema previews, SQL queries, and interactive charts, no setup required.",
  alternates: { canonical: "/signup" },
};

export default function SignupLayout({ children }: { children: React.ReactNode }) {
  return children;
}
