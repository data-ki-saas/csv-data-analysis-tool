"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { isValidEmail } from "@/lib/validation";
import { cn } from "@/lib/utils";

export default function SignupPage() {
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [emailTouched, setEmailTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const emailError = emailTouched && email.length > 0 && !isValidEmail(email)
    ? "Enter a valid email address"
    : null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setEmailTouched(true);
    setError(null);

    if (!isValidEmail(email)) {
      return;
    }

    setLoading(true);
    const supabase = createClient();
    const { error } = await supabase.auth.signUp({ email: email.trim(), password });
    setLoading(false);

    if (error) {
      setError(error.message);
      return;
    }

    router.push("/dashboard");
    router.refresh();
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 px-4">
      <h1 className="text-2xl font-semibold">Create an account</h1>

      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <input
            type="email"
            required
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onBlur={() => setEmailTouched(true)}
            aria-invalid={emailError ? true : undefined}
            className={cn(
              "rounded border border-black/10 px-3 py-2 dark:border-white/20",
              emailError && "border-red-600 dark:border-red-500"
            )}
          />
          {emailError && <p className="text-sm text-red-600">{emailError}</p>}
        </div>

        <input
          type="password"
          required
          minLength={6}
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="rounded border border-black/10 px-3 py-2 dark:border-white/20"
        />

        {error && <p className="text-sm text-red-600">{error}</p>}

        <button
          type="submit"
          disabled={loading}
          className="rounded bg-foreground px-3 py-2 text-background disabled:opacity-50"
        >
          {loading ? "Please wait…" : "Sign up"}
        </button>
      </form>

      <Link href="/login" className="text-sm underline">
        Already have an account? Sign in
      </Link>
    </main>
  );
}
