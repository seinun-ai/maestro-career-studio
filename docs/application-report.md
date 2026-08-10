# Maestro CS Application Report

> **Superseded 2026-07-15.** This report describes the fit-score/suggestion-cards workflow,
> which has been deleted. It was replaced by the deterministic ATS gap workflow — see
> SYSTEM.md §5 for the current workflow and §10 for the decision lineage. Kept for
> history; do not treat anything below as current behavior.

Generated on: 2026-06-09

## Executive Summary

Maestro CS is a local, single-user job application assistant. It helps a candidate turn pasted job descriptions into structured job records, compare those roles against multiple base resumes, generate AI-powered tailoring suggestions, apply selected edits, and render customized resume PDFs. The application also supports cover letter and Q&A generation, referral tracking, resume library management, and analytics across saved jobs.

The product is designed for a candidate who is actively applying to many roles and wants a repeatable workflow for choosing the best resume variant, tailoring it to a job, tracking application status, and learning which skills appear most often in target job descriptions.

## Main Purpose

The application is about making job applications faster, more consistent, and more data-informed. Instead of manually reading every job description, choosing a resume, editing bullets, and rebuilding PDFs, Maestro CS centralizes the process:

- Ingest a job description.
- Extract company, title, location, salary, work authorization, skills, responsibilities, and qualifications.
- Score how well each base resume fits the job.
- Generate concrete resume-edit suggestions.
- Accept, edit, or remove suggestions.
- Materialize the customized resume data.
- Render a LaTeX-backed PDF.
- Track the job, application status, notes, referrals, and generated artifacts.

## Primary Users

The app appears built for an individual job seeker, especially someone applying to technical or data-focused roles. The seeded resume variants and files indicate support for profiles such as:

- Data Analyst
- Data Scientist
- Data Engineer
- AI/ML Engineer
- Hybrid or general technical resume
- Master Profile as a canonical source of resume content

Because it is local-first and single-user, it prioritizes personal workflow control over multi-user collaboration, account management, or hosted SaaS features.

## Core Workflow

1. The user opens **New Application** and pastes a full job description, optionally with a source URL.
2. The backend creates or reuses a job record by hashing the raw job text.
3. An LLM extracts structured job data and normalizes it into the job schema.
4. The user can score fit across all base resumes or a selected base resume.
5. The app stores fit scores with an overall score, verdict, category breakdown, and gap summary.
6. The user generates tailoring suggestions for a selected or automatically chosen best-fit base resume.
7. The app creates an application draft containing the job, base resume, suggestions, optional user prompt, and status fields.
8. The user reviews suggestions, edits or deletes them, and records accept/reject decisions.
9. The backend applies accepted decisions to the base resume JSON and stores a customized resume JSON.
10. The app renders the customized resume with Jinja2 LaTeX templates and compiles it to PDF using `pdflatex`.
11. The application can be tracked with status, notes, applied date, referral, generated PDF, Q&A answers, and cover letter outputs.

## Major Features

### Job Description Ingestion

The job ingestion system accepts raw job text and stores it as a deduplicated job record. It extracts structured fields such as company, title, role category, seniority level, employment type, work mode, location, salary range, work authorization, OPT acceptance, required years of experience, skills, responsibilities, and qualifications.

Skill extraction feeds a `job_skills` table, which powers Explore analytics and skill frequency reports.

### Fit Scoring

The fit scoring system compares a job against base resume JSON files. It can score one resume or all supported base resumes. Scores include:

- Overall score
- Verdict
- Category-level analysis
- Gap summary
- Model used

When creating an application without a specified base resume, the backend can pick the best available base resume based on fit score.

### AI Resume Suggestions

The suggestions system generates tailored edits for the selected base resume. Suggestions can target resume paths, sections, priorities, original text, suggested text, and reasoning. The application supports an optional user prompt, allowing the candidate to guide the suggestion run with extra preferences.

Suggestions are not blindly applied. They become reviewable decisions, and the user can edit or delete individual suggestions before materializing the resume.

### Resume Editing and Rendering

Base resumes are stored as structured JSON and rendered to LaTeX/PDF. The backend validates resume data with Pydantic schemas and uses Jinja2 templates for the resume layout.

The app supports:

- Listing seeded base resumes
- Creating new base resumes
- Duplicating base resumes
- Editing structured resume content
- Rendering base resume PDFs
- Managing project inclusion with an `enabled` flag
- Porting projects between resumes
- Importing content from the Master Profile

Customized application resumes are stored separately under `applications/` as generated `.tex` and `.pdf` artifacts.

### Master Profile

The Master Profile is a special reserved base resume (`master`) used as a broad source of canonical experience, project, skill, education, and certification content. It cannot be created or deleted like a normal base resume. Other resumes can import selected content from it.

### Application and Job Tracking

The **Jobs** screen is the main tracking surface. It shows application-linked jobs and jobs that have been ingested but not yet turned into applications. The backend supports status filtering, not-applied filtering, role category filtering, date filtering, notes, applied timestamps, deletion, and source URL updates.

The older application detail URL redirects to the newer job detail page, suggesting the product has moved toward a consolidated job-centric workflow.

### Q&A and Cover Letters

The Q&A feature can answer user-provided questions in the context of an application or job. It can also generate cover letters with a chosen tone. Cover letters are stored as Q&A entries and can be rendered to PDF through a separate LaTeX cover letter template.

### Referrals

The referrals feature stores companies, careers URLs, contact names, notes, and counts of linked applications. Applications can reference a referral, making it possible to track which opportunities came through referral channels.

### Explore Analytics

The Explore area analyzes the saved job corpus. It includes endpoints and frontend charts for:

- Top skills
- Required, preferred, and mentioned skill frequency
- Skill heatmaps by role category
- Fit score distribution
- Role mix over time

This turns accumulated job descriptions into market intelligence for the candidate.

### Settings, Prompts, and Model Selection

The Settings area exposes operational controls for:

- Persistent memory used in AI prompts
- Editable prompt templates
- Resetting prompts to file defaults
- Fast and smart model selection
- OpenAI and Gemini API key configuration status

The backend separates fast-model tasks, such as extraction and scoring, from smart-model tasks, such as suggestions, Q&A, and cover letters.

## Technical Architecture

Maestro CS is a Docker Compose application with three main services:

- **Frontend:** Next.js App Router, React, TypeScript, Tailwind CSS, shadcn-style UI primitives, TanStack Query, Recharts, and Lucide icons.
- **Backend:** FastAPI, SQLAlchemy, Alembic, Pydantic, OpenAI/Gemini model routing, Jinja2 templates, and LaTeX PDF rendering.
- **Database:** PostgreSQL 16.

The frontend talks to the backend through same-origin `/api` proxy routing in Next.js. In Compose, the backend is reachable from the frontend container through `API_PROXY_BACKEND=http://backend:8000`.

The backend starts with a lifespan hook that runs migrations, seeds base resumes, seeds prompt defaults, and ensures memory exists.

## Data Model

The main persistent entities are:

- `jobs`: raw job descriptions plus normalized extracted fields.
- `job_skills`: normalized skills attached to jobs for analytics.
- `fit_scores`: per-job, per-base-resume scoring results.
- `applications`: draft and tracked applications, including suggestions, decisions, customized resume data, rendered paths, status, notes, referral link, and user prompt.
- `base_resumes`: structured resume variants and rendered artifact paths.
- `qa_entries`: generated Q&A answers and cover letters.
- `referrals`: referral companies, career URLs, contacts, and notes.
- `settings`: memory, prompt overrides, and model preferences.

File-backed artifacts are also important:

- `base_resumes/*.json`: seed resume data.
- `base_resumes/tex/`: rendered base resume LaTeX.
- `base_resumes/pdfs/`: rendered base resume PDFs.
- `applications/`: generated application-specific resume and cover letter artifacts.
- `settings/memory.md`: editable memory outside the committed database seed flow.
- `backend/app/prompts/*.txt`: default prompt templates.

## AI Usage

The app uses LLM calls for several parts of the workflow:

- Job description extraction
- Reduced-field re-extraction/backfill
- Resume fit scoring
- Tailored resume suggestions
- Q&A answer generation
- Cover letter generation

Prompts are stored as editable templates, and the runtime can choose between OpenAI and Gemini model options. The default configured model roles are:

- Fast model: `gpt-4o-mini`
- Smart model: `gpt-4o`

The design keeps AI outputs structured where possible and validates extracted job and resume data through Pydantic schemas before storing or rendering.

## Current Product Shape

The application currently presents these primary navigation areas:

- **New Application:** Ingest a job description, score fit, and generate an application draft.
- **Jobs:** Review tracked jobs and applications, filter/search, and open job detail workflows.
- **Referrals:** Maintain referral sources and contacts.
- **Base Resumes:** Create, duplicate, delete, render, and edit resume variants.
- **Master Profile:** Maintain the canonical source profile.
- **Explore:** Analyze job trends, skill frequency, and fit distributions.
- **Q&A:** Generate application/job answers and cover letters.
- **Settings:** Edit memory, prompt templates, and model choices.

## Notable Strengths

- The workflow is practical and end-to-end: ingestion, scoring, suggestion generation, editing, rendering, and tracking all live in one app.
- Resume data is structured, making suggestions and rendering more reliable than free-form document editing.
- The app keeps generated artifacts local and reproducible through LaTeX templates.
- Prompt and model settings are user-editable, which is useful for experimentation.
- Explore analytics make the tool more valuable over time as more jobs are ingested.
- The Master Profile concept helps prevent resume variants from becoming disconnected copies.

## Key Risks and Limitations

- The app depends on external LLM APIs for core value, so API keys, model availability, rate limits, and output quality directly affect the experience.
- LaTeX rendering adds high-quality PDF output but increases setup complexity and image size.
- The system is local and single-user; it does not include authentication, cloud sync, or collaboration features.
- AI-generated suggestions still require human review, especially because resume content must remain truthful and role-specific.
- Some base-resume handling still references a fixed supported slug list for fit scoring, so newly created resumes may need extra backend support before they can participate everywhere.

## Overall Assessment

Maestro CS is best understood as a local AI-assisted job application workbench. It combines applicant tracking, resume variant management, LLM-based job analysis, tailored resume generation, cover letter support, and job-market analytics into a single personal tool.

Its strongest idea is that every job description becomes reusable structured data. That data improves resume selection, guides tailoring, creates application artifacts, and accumulates into analytics about the roles the user is targeting. The result is not just a resume generator; it is a focused system for managing and learning from the whole application pipeline.
