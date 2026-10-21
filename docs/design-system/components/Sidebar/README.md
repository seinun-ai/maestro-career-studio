The sidebar is the app's navigation drawer: the brand, one create action, the main pages, a More tools disclosure and the account links.

**You provide:** nothing per page. The shell renders it once in `app/layout.tsx`; a new destination is one entry in `MAIN_ITEMS` or `MORE_TOOLS` (`components/app-sidebar.tsx`) with an icon from the register and a canonical name.

- 256px wide on `sidebar` with a `sidebar-border` edge. The top-left corner belongs to the reveal pill; pages never pad for it.
- **Add job** is the only FAB in the app: `primary-container`, 40px, `radius-corner-lg`. There is one create action here and no second one in a page header for the same thing.
- The main pages, in order, with no group labels: Today, Jobs, Agent inbox, Base resumes, Career history, Analytics.
- **More tools** is a disclosure row in `muted-foreground` with a chevron that turns a quarter when open (`aria-expanded`, `aria-controls`; the closed list is `hidden`). It holds Automations, Referrals, Templates and the Assistant. Until it is pressed it is open on a page it holds, so the current page is always in view.
- Profile and Settings sit at the bottom, in the footer's own `nav`.
- A row is 32px, `radius-full`, `body-medium`, icon 16px. Hover is `sidebar-accent`.
- The current row is `secondary-container` / `on-secondary-container`, weight 600 and `aria-current="page"`, with no Check.
- The Today row carries the Needs you count as an `attention-container` pill; its meaning is also in the link's `aria-label` ("Today, 3 need you").
- The focus ring is the same `ring` as the rest of the app.

Source: `frontend/components/app-sidebar.tsx`, `ui/sidebar.tsx`.
