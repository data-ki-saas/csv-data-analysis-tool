import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Terms of Use",
  description: "The terms and conditions for using CSV Data Analysis Tool.",
  alternates: { canonical: "/terms" },
};

const EFFECTIVE_DATE = "January 1, 2026";

export default function TermsPage() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-4 py-16">
      <div>
        <h1 className="text-3xl font-semibold">Terms of Use</h1>
        <p className="mt-2 text-sm opacity-60">Effective date: {EFFECTIVE_DATE}</p>
      </div>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">1. Acceptance of Terms</h2>
        <p className="opacity-80">
          By creating an account or otherwise using CSV Data Analysis Tool (the &quot;Service&quot;),
          you agree to be bound by these Terms of Use. If you do not agree to these terms, do not
          use the Service.
        </p>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">2. Description of Service</h2>
        <p className="opacity-80">
          The Service allows you to upload CSV files, automatically infer a schema, run SQL
          queries, generate charts and visual reports, and export or share the resulting content.
          The Service is provided on an &quot;as is&quot; and &quot;as available&quot; basis and may change or
          be discontinued at any time.
        </p>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">3. Your Account</h2>
        <p className="opacity-80">
          You are responsible for maintaining the confidentiality of your account credentials and
          for all activity that occurs under your account. You must provide accurate information
          when creating an account and notify us promptly of any unauthorized use.
        </p>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">4. Your Content</h2>
        <p className="opacity-80">
          You retain ownership of the data and files you upload (&quot;Your Content&quot;). By uploading
          Your Content, you grant us a limited license to store, process, and display it solely
          for the purpose of operating and providing the Service to you. You are solely
          responsible for ensuring you have the right to upload and process Your Content,
          including any personal data it may contain.
        </p>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">5. Acceptable Use</h2>
        <p className="opacity-80">
          You agree not to use the Service to upload unlawful content, infringe on the rights of
          others, attempt to gain unauthorized access to the Service or other users&apos; data, or
          interfere with the Service&apos;s normal operation.
        </p>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">6. Shareable Links</h2>
        <p className="opacity-80">
          Features that generate shareable links produce publicly accessible URLs. You are
          responsible for deciding what to share and may revoke a share link at any time from
          within the Service.
        </p>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">7. Third-Party AI Providers</h2>
        <p className="opacity-80">
          Certain optional features (such as AI-assisted column type suggestions and chart
          insights) send limited, relevant data to third-party large language model providers to
          generate a response. Use of these optional features is at your discretion.
        </p>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">8. Disclaimer of Warranties</h2>
        <p className="opacity-80">
          The Service is provided without warranties of any kind, express or implied, including
          but not limited to warranties of merchantability, fitness for a particular purpose, and
          non-infringement. We do not warrant that the Service will be uninterrupted, error-free,
          or that any analysis, chart, or AI-generated suggestion will be accurate or complete.
        </p>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">9. Limitation of Liability</h2>
        <p className="opacity-80">
          To the maximum extent permitted by law, we will not be liable for any indirect,
          incidental, special, consequential, or punitive damages, or any loss of data, revenue,
          or profits, arising from your use of the Service.
        </p>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">10. Termination</h2>
        <p className="opacity-80">
          You may stop using the Service and delete your account at any time. We may suspend or
          terminate your access to the Service if you violate these Terms of Use.
        </p>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">11. Changes to These Terms</h2>
        <p className="opacity-80">
          We may update these Terms of Use from time to time. We will post the updated terms on
          this page with a revised effective date. Continued use of the Service after changes
          become effective constitutes acceptance of the revised terms.
        </p>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">12. Contact Us</h2>
        <p className="opacity-80">
          If you have questions about these Terms of Use, please reach out via our Contact page.
        </p>
      </section>
    </main>
  );
}
