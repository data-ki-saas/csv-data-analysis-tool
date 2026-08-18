import type { Metadata } from "next";
import siteContent from "@/content/siteContent.json";

export const metadata: Metadata = {
  title: siteContent.contact.title,
  description: siteContent.contact.sections[0]?.body,
  alternates: { canonical: "/contact" },
};

export default function ContactPage() {
  const { title, email, sections } = siteContent.contact;

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-4 py-16">
      <h1 className="text-3xl font-semibold">{title}</h1>
      <p className="text-lg">
        Email us at{" "}
        <a href={`mailto:${email}`} className="underline">
          {email}
        </a>
      </p>
      {sections.map((section) => (
        <section key={section.heading} className="flex flex-col gap-2">
          <h2 className="text-lg font-medium">{section.heading}</h2>
          <p className="opacity-80">{section.body}</p>
        </section>
      ))}
    </main>
  );
}
