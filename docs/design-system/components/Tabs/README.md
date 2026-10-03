Tabs divide one page into sections; they are the line style, with a `primary` indicator under the current tab.

**You provide:** a few short labels, optionally a plain count after each, and the panels. `TabsList` is the line style; it takes no variant.

- 40px tall, labels in `title-small`; the current tab is `foreground` with a 2px `primary` underline, the rest `muted-foreground`.
- A hairline `border` runs under the whole list.
- Counts are plain numbers in `muted-foreground`, never a badge.
- Every panel stays mounted (`keepMounted`), so a draft survives a switch.
- A tab panel draws its focus ring as an overlay above its content.
- Do not use the filled pill strip for page sections: it looks like the SegmentedToggle beside it.

Source: `frontend/components/ui/tabs.tsx`. There is one style: the filled pill strip is gone, and a two- or three-way view switch of one list or chart is a SegmentedToggle. A row never wraps; with more labels than fit it scrolls sideways inside itself, and a click on a partly hidden tab scrolls it into view.
