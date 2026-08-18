import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description: "How CSV Data Analysis Tool collects, uses, and protects your data.",
  alternates: { canonical: "/privacy" },
};

const EFFECTIVE_DATE = "January 1, 2026";

export default function PrivacyPage() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-4 py-16">
      <div>
        <h1 className="text-3xl font-semibold">Privacy Policy</h1>
        <p className="mt-2 text-sm opacity-60">Effective date: {EFFECTIVE_DATE}</p>
      </div>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">1. Information We Collect</h2>
        <p className="opacity-80">
          We collect information you provide directly, such as your email address and password
          when you create an account, and the CSV files and dataset content you upload for
          analysis. We also collect limited technical information automatically, such as log
          data (IP address, browser type, timestamps) generated when you use the service.
        </p>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">2. How We Use Your Information</h2>
        <p className="opacity-80">
          We use your information to provide and operate the service: authenticating your
          account, processing and storing the datasets you upload, generating schema previews,
          charts, and AI-assisted suggestions, and communicating with you about your account. We
          do not sell your personal information or uploaded data to third parties.
        </p>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">3. Data Storage and Security</h2>
        <p className="opacity-80">
          Uploaded files and derived data are stored using reputable third-party infrastructure
          providers (including our database, authentication, and object storage providers) under
          agreements that require appropriate security safeguards. Access to your datasets is
          scoped to your account. No method of transmission or storage is completely secure, and
          we cannot guarantee absolute security.
        </p>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">4. Third-Party Services</h2>
        <p className="opacity-80">
          We rely on third-party providers to deliver the service, including cloud hosting,
          database, authentication, file storage, and (for certain optional AI-assisted features)
          large language model providers. Data sent to these providers is limited to what is
          necessary to perform the requested function.
        </p>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">5. Sharing and Public Links</h2>
        <p className="opacity-80">
          If you choose to create a shareable chart link, anyone with that link can view the
          shared chart and its data without signing in. You can revoke a share link at any time,
          which immediately disables access via that link.
        </p>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">6. Your Rights and Choices</h2>
        <p className="opacity-80">
          You may access, update, or delete your account and uploaded datasets at any time from
          within the application. Depending on your jurisdiction, you may have additional rights
          regarding your personal data, including the right to request a copy of your data or its
          deletion. Contact us using the details on our Contact page to exercise these rights.
        </p>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">7. Data Retention</h2>
        <p className="opacity-80">
          We retain your account information and uploaded datasets for as long as your account is
          active, or as needed to provide the service. If you delete a dataset or your account, we
          remove the associated data from active storage within a reasonable period, subject to
          any legal or backup retention requirements.
        </p>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">8. Changes to This Policy</h2>
        <p className="opacity-80">
          We may update this Privacy Policy from time to time. We will post the updated policy on
          this page with a revised effective date. Continued use of the service after changes
          become effective constitutes acceptance of the revised policy.
        </p>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">9. Contact Us</h2>
        <p className="opacity-80">
          If you have questions about this Privacy Policy or how we handle your data, please
          reach out via our Contact page.
        </p>
      </section>
    </main>
  );
}
