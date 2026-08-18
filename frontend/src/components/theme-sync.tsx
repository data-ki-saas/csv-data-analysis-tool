"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { getSettings } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";
import { useTheme } from "@/components/theme-provider";

// Pulls the signed-in user's saved theme settings from the backend once and
// applies them, so preferences follow the user across browsers/devices.
// Only queries once a Supabase session exists, so the login page never hits
// the (auth-gated) settings endpoint.
export function ThemeSync() {
  const [hasSession, setHasSession] = useState(false);
  const { applyRemote } = useTheme();

  useEffect(() => {
    const supabase = createClient();
    supabase.auth.getSession().then(({ data }) => setHasSession(!!data.session));
    const { data: subscription } = supabase.auth.onAuthStateChange((_event, session) => {
      setHasSession(!!session);
    });
    return () => subscription.subscription.unsubscribe();
  }, []);

  const { data } = useQuery({
    queryKey: ["settings"],
    queryFn: getSettings,
    enabled: hasSession,
  });

  useEffect(() => {
    if (data) applyRemote(data);
  }, [data, applyRemote]);

  return null;
}
