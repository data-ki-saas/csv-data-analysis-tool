import type { Metadata } from "next";

// Generated with backend/scripts/generate_seo.py --route /login
export const metadata: Metadata = {
  title: "Sign In",
  description:
    "Sign in to your CSV Data Analysis Tool account to upload datasets, run SQL queries, and build interactive charts from your data.",
  alternates: { canonical: "/login" },
};

export default function LoginLayout({ children }: { children: React.ReactNode }) {
  return children;
}
