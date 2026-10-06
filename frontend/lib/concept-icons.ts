// The ONE map from a concept to its Lucide icon (visual-language plan, Task 1). An icon only replaces a
// word if it means one thing, so a concept here owns its glyph app-wide and no two concepts share one
// (backend/tests/test_frontend_concept_icons.py). An icon is never the only carrier of meaning: a word sits
// beside it or in its accessible name (docs/design-system/README.md, Iconography).
import {
  Ban, BarChart3, BookOpen, BookPlus, Bot, BriefcaseBusiness, CalendarClock, CircleCheck, CircleDashed,
  CircleHelp, CircleX, Ellipsis, FileInput, FileOutput, FilePen, FileText, FolderGit2, Handshake,
  HeartPulse, IdCard, Inbox, LayoutTemplate, Layers, Lock, Merge, MessageSquare, Minus, Paperclip,
  Mail, RefreshCw, RotateCcw, ScanSearch, School, ScrollText, SendHorizontal, Settings, SkipForward, Sparkles, Tags, TextQuote,
  ThumbsUp, TrendingDown, TrendingUp, TriangleAlert, UserRound, Wand2, Workflow,
  type LucideIcon,
} from "lucide-react";

export const CONCEPT_ICONS = {
  // Sections (the sidebar's icons win: they were learned first).
  jobs: Inbox,
  // Bot means "agents" (D1): the Agent inbox and connected agents share it; never add a second Bot key.
  agentInbox: Bot,
  automations: Workflow,
  referrals: Handshake,
  careerHistory: BriefcaseBusiness,
  baseResume: FileText,
  templates: LayoutTemplate,
  assistant: MessageSquare,
  analytics: BarChart3,
  settings: Settings,
  // Things and actors.
  attachment: Paperclip,
  drafts: FilePen,
  you: UserRound,
  ai: Sparkles,
  jobWords: TextQuote,
  fromResume: FileInput,
  merged: Merge,
  project: FolderGit2,
  health: HeartPulse,
  skills: Tags,
  jobFacts: Layers,
  workAuthorization: IdCard,
  studentPermit: School,
  docs: BookOpen,
  // Mail is an email address; ScrollText is a cover letter (never swap them).
  email: Mail,
  coverLetter: ScrollText,
  // States.
  done: CircleCheck,
  notRun: CircleDashed,
  warning: TriangleAlert,
  fails: CircleX,
  unknown: CircleHelp,
  // Ban: can't — I can't confirm / they can't / never. CircleHelp stays "unknown" only.
  cannot: Ban,
  // Minus: "nothing here / no change" (not listed, not stated, same, flat, not needed)
  none: Minus,
  locked: Lock,
  scheduled: CalendarClock,
  increase: TrendingUp,
  decrease: TrendingDown,
  // Actions.
  createPdf: FileOutput,
  addToCareerHistory: BookPlus,
  refresh: RefreshCw,
  restore: RotateCcw,
  queue: SendHorizontal,
  approve: ThumbsUp,
  skip: SkipForward,
  analyzeGaps: ScanSearch,
  tailor: Wand2,
  more: Ellipsis,
} as const satisfies Record<string, LucideIcon>;

export type Concept = keyof typeof CONCEPT_ICONS;
