/** Central place for size/length limits used across the app's forms and
 * paginated lists -- update here instead of hunting through components.
 * Mirrors backend/src/core/config.py's Settings, which is the source of
 * truth for what the API actually enforces; keep these two in sync by hand
 * when either changes (there's no shared schema between the two apps). */

// How many distinct values/tags the Edit Column dialog's "Current values"
// and "Tags" lists show per page before "Load more" fetches another page.
// Mirrors Settings.column_values_page_size / tag_candidates_page_size.
export const EDIT_COLUMN_VALUES_PAGE_SIZE = 200;

// Free-text "Add custom chart" prompt on the Visual Reports page. Mirrors
// Settings.custom_chart_prompt_max_length -- generous enough for a
// fully-spelled-out parsing instruction (e.g. "parse experience_raw as
// 'min - max yrs', strip 'yrs', split on '-', average the two numbers...").
export const CUSTOM_CHART_PROMPT_MAX_LENGTH = 500;
