The sidebar is the app's navigation drawer: the brand, one create action, three labelled groups and the account links.

**You provide:** nothing per page. The shell renders it once in `app/layout.tsx`; a new destination is one entry in `NAV_GROUPS` with a Lucide icon and a canonical name.

- 256px wide on `sidebar` with a `sidebar-border` edge. The top-left corner belongs to the reveal pill; pages never pad for it.
- **Add job** is the only FAB in the app: `primary-container`, 40px, `radius-corner-lg`. There is one create action here and no second one in a page header for the same thing.
- Group labels are `label-medium` at 70% `sidebar-foreground`: Job search, Career library, Tools.
- A row is 32px, `radius-full`, `body-medium`, icon 16px. Hover is `sidebar-accent`.
- The current row is `secondary-container` / `on-secondary-container`, weight 600 and `aria-current="page"`, with no Check.
- The Agent inbox count is an `attention-container` pill; its meaning is also in the link's `aria-label`.
- The focus ring is the same `ring` as the rest of the app.

Source: `frontend/components/app-sidebar.tsx`, `ui/sidebar.tsx`. Changed from source: the row corner goes from 8px to a full pill.
