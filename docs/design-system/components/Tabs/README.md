Tabs divide one page into sections; they are the line style, with a `primary` indicator under the current tab.

**You provide:** two to six short labels, optionally a plain count after each, and the panels. Use `TabsList variant="line"`.

- 40px tall, labels in `title-small`; the current tab is `foreground` with a 2px `primary` underline, the rest `muted-foreground`.
- A hairline `border` runs under the whole list.
- Counts are plain numbers in `muted-foreground`, never a badge.
- Every panel stays mounted (`keepMounted`), so a draft survives a switch.
- A tab panel draws its focus ring as an overlay above its content.
- Do not use the filled pill strip for page sections: it looks like the SegmentedToggle beside it.

Source: `frontend/components/ui/tabs.tsx` (`line` variant). The default filled variant is still used by the resume studios' section tabs, the template editor and four dialogs and drawers, which are not page sections; whether they follow is an open owner decision.
