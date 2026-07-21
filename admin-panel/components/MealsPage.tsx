"use client";

import ConfigEditor from "@/components/ConfigEditor";

export default function MealsPage({ toast }: { toast: (message: string) => void }) {
  return (
    <>
      <div className="page-title compact">
        <div>
          <span className="eyebrow">MEALS LIBRARY</span>
          <h1>Alternative meals</h1>
          <p>Meal swap options shown when users replace breakfast, lunch, or dinner.</p>
        </div>
      </div>

      <ConfigEditor
        configKey="alternative-meals"
        title="Alternative meals"
        subtitle="Organized by goal category (loss / gain / general) and meal type."
        toast={toast}
      />
    </>
  );
}
