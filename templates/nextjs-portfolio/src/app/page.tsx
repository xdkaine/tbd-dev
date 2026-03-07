/* =======================================================================
   NEXT.JS PORTFOLIO — STUDENT TEMPLATE
   =====================================================================
   HOW TO CUSTOMIZE:
   1. Edit the data objects below (PROFILE, SKILLS, PROJECTS, etc.)
   2. Swap placeholder text with your own info
   3. Add your own projects, skills, and experience
   4. The layout and styling are ready to go — focus on content!
   ======================================================================= */

// ── Your profile info (edit this!) ─────────────────────────────────────
const PROFILE = {
  name: "Your Name",
  title: "Computer Science Student",
  tagline: "I build things for the web.",
  bio: `I'm a student developer passionate about creating clean, accessible,
and performant web applications. Currently studying computer science
and exploring modern frontend frameworks like React and Next.js.`,
  email: "you@example.com",
  github: "https://github.com/yourusername",
  linkedin: "https://linkedin.com/in/yourusername",
  location: "Your City, ST",
};

// ── Navigation links ───────────────────────────────────────────────────
const NAV_LINKS = [
  { label: "About", href: "#about" },
  { label: "Skills", href: "#skills" },
  { label: "Projects", href: "#projects" },
  { label: "Experience", href: "#experience" },
  { label: "Education", href: "#education" },
  { label: "Contact", href: "#contact" },
];

// ── Skills (group by category) ─────────────────────────────────────────
const SKILLS = [
  {
    category: "Languages",
    items: ["JavaScript", "TypeScript", "Python", "HTML", "CSS"],
  },
  {
    category: "Frameworks",
    items: ["React", "Next.js", "Tailwind CSS", "Node.js"],
  },
  {
    category: "Tools",
    items: ["Git", "VS Code", "Docker", "Figma"],
  },
  {
    category: "Concepts",
    items: ["REST APIs", "Responsive Design", "Accessibility", "Agile"],
  },
];

// ── Projects ───────────────────────────────────────────────────────────
const PROJECTS = [
  {
    title: "Portfolio Website",
    description:
      "A personal portfolio site built with Next.js and Tailwind CSS. Deployed on TBD.",
    tech: ["Next.js", "Tailwind CSS", "TypeScript"],
    link: "#",
    github: "#",
  },
  {
    title: "Task Tracker App",
    description:
      "A full-stack task management app with authentication and real-time updates.",
    tech: ["React", "Node.js", "MongoDB"],
    link: "#",
    github: "#",
  },
  {
    title: "Weather Dashboard",
    description:
      "A responsive weather app that fetches data from a public API and displays forecasts.",
    tech: ["JavaScript", "REST API", "CSS Grid"],
    link: "#",
    github: "#",
  },
];

// ── Experience ─────────────────────────────────────────────────────────
const EXPERIENCE = [
  {
    role: "Web Development Intern",
    company: "Acme Corp",
    period: "Summer 2025",
    bullets: [
      "Built responsive UI components using React and Tailwind CSS",
      "Collaborated with a team of 4 developers using Git and Agile sprints",
      "Improved page load performance by 30% through code splitting",
    ],
  },
  {
    role: "Teaching Assistant — Intro to Web Dev",
    company: "University CS Department",
    period: "Fall 2024 – Spring 2025",
    bullets: [
      "Led weekly lab sessions for 30+ students on HTML, CSS, and JavaScript",
      "Created supplementary exercises and grading rubrics",
      "Held office hours to debug student projects",
    ],
  },
];

// ── Education ──────────────────────────────────────────────────────────
const EDUCATION = [
  {
    degree: "B.S. Computer Science",
    school: "Your University",
    period: "2022 – 2026 (Expected)",
    details: [
      "Relevant coursework: Data Structures, Algorithms, Web Development, Databases",
      "GPA: 3.X / 4.0",
      "Dean's List — Fall 2023, Spring 2024",
    ],
  },
];

// ═══════════════════════════════════════════════════════════════════════
// COMPONENTS — Students can study and modify these to learn React
// ═══════════════════════════════════════════════════════════════════════

// ── Header / Nav ───────────────────────────────────────────────────────
function Header() {
  return (
    <header className="sticky top-0 z-50 border-b border-zinc-800/60 bg-zinc-950/80 backdrop-blur-md">
      <nav className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
        <a href="#" className="text-lg font-bold tracking-tight text-emerald-400">
          {PROFILE.name.split(" ")[0]}
          <span className="text-zinc-500">.</span>
        </a>
        <ul className="hidden gap-6 md:flex">
          {NAV_LINKS.map((link) => (
            <li key={link.href}>
              <a
                href={link.href}
                className="text-sm text-zinc-400 transition-colors hover:text-emerald-400"
              >
                {link.label}
              </a>
            </li>
          ))}
        </ul>
        {/* Mobile: simple fallback — students can upgrade this to a hamburger menu */}
        <a
          href="#contact"
          className="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-medium text-black transition-colors hover:bg-emerald-400 md:hidden"
        >
          Contact
        </a>
      </nav>
    </header>
  );
}

// ── Hero ────────────────────────────────────────────────────────────────
function Hero() {
  return (
    <section className="relative overflow-hidden px-6 py-24 md:py-32">
      {/* Background glow */}
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
        <div className="h-[500px] w-[500px] rounded-full bg-emerald-500/5 blur-3xl" />
      </div>

      <div className="relative mx-auto max-w-3xl text-center">
        <p className="animate-fade-in text-sm font-medium uppercase tracking-widest text-emerald-400">
          {PROFILE.title}
        </p>
        <h1 className="animate-slide-up mt-4 text-4xl font-bold tracking-tight sm:text-5xl md:text-6xl">
          Hi, I&apos;m{" "}
          <span className="text-emerald-400">{PROFILE.name}</span>
        </h1>
        <p className="animate-slide-up delay-200 mt-6 text-lg text-zinc-400 opacity-0">
          {PROFILE.tagline}
        </p>
        <div className="animate-slide-up delay-300 mt-8 flex justify-center gap-4 opacity-0">
          <a
            href="#projects"
            className="rounded-lg bg-emerald-500 px-6 py-3 text-sm font-semibold text-black transition-colors hover:bg-emerald-400"
          >
            View My Work
          </a>
          <a
            href="#contact"
            className="rounded-lg border border-zinc-700 px-6 py-3 text-sm font-semibold text-zinc-300 transition-colors hover:bg-zinc-800"
          >
            Get in Touch
          </a>
        </div>
      </div>
    </section>
  );
}

// ── About ───────────────────────────────────────────────────────────────
function About() {
  return (
    <section id="about" className="border-t border-zinc-800/60 px-6 py-20">
      <div className="mx-auto max-w-3xl">
        <SectionHeading title="About Me" />
        <p className="mt-6 whitespace-pre-line text-zinc-400 leading-relaxed">
          {PROFILE.bio}
        </p>
        <div className="mt-6 flex flex-wrap gap-4 text-sm text-zinc-500">
          <span className="flex items-center gap-1.5">
            <MapPinIcon /> {PROFILE.location}
          </span>
          <a href={PROFILE.github} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5 transition-colors hover:text-emerald-400">
            <GithubIcon /> GitHub
          </a>
          <a href={PROFILE.linkedin} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5 transition-colors hover:text-emerald-400">
            <LinkedinIcon /> LinkedIn
          </a>
        </div>
      </div>
    </section>
  );
}

// ── Skills ──────────────────────────────────────────────────────────────
function Skills() {
  return (
    <section id="skills" className="border-t border-zinc-800/60 px-6 py-20">
      <div className="mx-auto max-w-3xl">
        <SectionHeading title="Skills" />
        <div className="mt-8 grid gap-6 sm:grid-cols-2">
          {SKILLS.map((group) => (
            <div key={group.category} className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-emerald-400">
                {group.category}
              </h3>
              <div className="mt-3 flex flex-wrap gap-2">
                {group.items.map((skill) => (
                  <span
                    key={skill}
                    className="rounded-md bg-zinc-800 px-2.5 py-1 text-xs text-zinc-300"
                  >
                    {skill}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ── Projects ────────────────────────────────────────────────────────────
function Projects() {
  return (
    <section id="projects" className="border-t border-zinc-800/60 px-6 py-20">
      <div className="mx-auto max-w-3xl">
        <SectionHeading title="Projects" />
        <div className="mt-8 grid gap-6">
          {PROJECTS.map((project) => (
            <div
              key={project.title}
              className="card-hover rounded-xl border border-zinc-800 bg-zinc-900/50 p-6"
            >
              <div className="flex items-start justify-between gap-4">
                <h3 className="text-lg font-semibold">{project.title}</h3>
                <div className="flex shrink-0 gap-2">
                  {project.github !== "#" && (
                    <a href={project.github} target="_blank" rel="noopener noreferrer" className="text-zinc-500 transition-colors hover:text-emerald-400" aria-label="Source code">
                      <GithubIcon />
                    </a>
                  )}
                  {project.link !== "#" && (
                    <a href={project.link} target="_blank" rel="noopener noreferrer" className="text-zinc-500 transition-colors hover:text-emerald-400" aria-label="Live demo">
                      <ExternalLinkIcon />
                    </a>
                  )}
                </div>
              </div>
              <p className="mt-2 text-sm text-zinc-400">{project.description}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                {project.tech.map((t) => (
                  <span
                    key={t}
                    className="rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-medium text-emerald-400"
                  >
                    {t}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ── Experience ──────────────────────────────────────────────────────────
function Experience() {
  return (
    <section id="experience" className="border-t border-zinc-800/60 px-6 py-20">
      <div className="mx-auto max-w-3xl">
        <SectionHeading title="Experience" />
        <div className="mt-8 space-y-8">
          {EXPERIENCE.map((job) => (
            <div key={job.role + job.company} className="relative pl-6 before:absolute before:left-0 before:top-2 before:h-2 before:w-2 before:rounded-full before:bg-emerald-400">
              <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                <h3 className="font-semibold">{job.role}</h3>
                <span className="text-sm text-zinc-500">{job.period}</span>
              </div>
              <p className="text-sm text-emerald-400">{job.company}</p>
              <ul className="mt-3 space-y-1.5">
                {job.bullets.map((b, i) => (
                  <li key={i} className="text-sm text-zinc-400">
                    <span className="mr-2 text-zinc-600">&#8250;</span>
                    {b}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ── Education ───────────────────────────────────────────────────────────
function Education() {
  return (
    <section id="education" className="border-t border-zinc-800/60 px-6 py-20">
      <div className="mx-auto max-w-3xl">
        <SectionHeading title="Education" />
        <div className="mt-8 space-y-8">
          {EDUCATION.map((edu) => (
            <div key={edu.degree + edu.school} className="relative pl-6 before:absolute before:left-0 before:top-2 before:h-2 before:w-2 before:rounded-full before:bg-emerald-400">
              <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                <h3 className="font-semibold">{edu.degree}</h3>
                <span className="text-sm text-zinc-500">{edu.period}</span>
              </div>
              <p className="text-sm text-emerald-400">{edu.school}</p>
              <ul className="mt-3 space-y-1.5">
                {edu.details.map((d, i) => (
                  <li key={i} className="text-sm text-zinc-400">
                    <span className="mr-2 text-zinc-600">&#8250;</span>
                    {d}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ── Contact ─────────────────────────────────────────────────────────────
function Contact() {
  return (
    <section id="contact" className="border-t border-zinc-800/60 px-6 py-20">
      <div className="mx-auto max-w-xl text-center">
        <SectionHeading title="Get in Touch" centered />
        <p className="mt-4 text-zinc-400">
          I&apos;m always open to new opportunities, collaborations, or just a
          friendly chat about web development.
        </p>
        <a
          href={`mailto:${PROFILE.email}`}
          className="glow-accent mt-8 inline-block rounded-lg bg-emerald-500 px-8 py-3 text-sm font-semibold text-black transition-colors hover:bg-emerald-400"
        >
          Say Hello
        </a>
        <div className="mt-6 flex justify-center gap-4">
          <a href={PROFILE.github} target="_blank" rel="noopener noreferrer" className="text-zinc-500 transition-colors hover:text-emerald-400">
            <GithubIcon />
          </a>
          <a href={PROFILE.linkedin} target="_blank" rel="noopener noreferrer" className="text-zinc-500 transition-colors hover:text-emerald-400">
            <LinkedinIcon />
          </a>
        </div>
      </div>
    </section>
  );
}

// ── Footer ──────────────────────────────────────────────────────────────
function Footer() {
  return (
    <footer className="border-t border-zinc-800/60 px-6 py-8">
      <div className="mx-auto flex max-w-5xl flex-col items-center justify-between gap-4 sm:flex-row">
        <p className="text-sm text-zinc-500">
          &copy; {new Date().getFullYear()} {PROFILE.name}. Built with{" "}
          <a href="https://nextjs.org" target="_blank" rel="noopener noreferrer" className="text-zinc-400 underline decoration-zinc-700 underline-offset-2 hover:text-emerald-400">
            Next.js
          </a>{" "}
          &amp;{" "}
          <a href="https://tailwindcss.com" target="_blank" rel="noopener noreferrer" className="text-zinc-400 underline decoration-zinc-700 underline-offset-2 hover:text-emerald-400">
            Tailwind CSS
          </a>
          .
        </p>
        <p className="text-sm text-zinc-600">
          Deployed on TBD
        </p>
      </div>
    </footer>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// SHARED COMPONENTS
// ═══════════════════════════════════════════════════════════════════════

function SectionHeading({ title, centered }: { title: string; centered?: boolean }) {
  return (
    <h2 className={`text-2xl font-bold tracking-tight ${centered ? "text-center" : ""}`}>
      <span className="text-emerald-400">#</span> {title}
    </h2>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// ICONS (inline SVG — no external dependencies needed)
// ═══════════════════════════════════════════════════════════════════════

function GithubIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4" />
      <path d="M9 18c-4.51 2-5-2-7-2" />
    </svg>
  );
}

function LinkedinIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z" />
      <rect width="4" height="12" x="2" y="9" />
      <circle cx="4" cy="4" r="2" />
    </svg>
  );
}

function MapPinIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" />
      <circle cx="12" cy="10" r="3" />
    </svg>
  );
}

function ExternalLinkIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
      <polyline points="15 3 21 3 21 9" />
      <line x1="10" y1="14" x2="21" y2="3" />
    </svg>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// PAGE — Assembles all sections
// ═══════════════════════════════════════════════════════════════════════

export default function Home() {
  return (
    <>
      <Header />
      <main>
        <Hero />
        <About />
        <Skills />
        <Projects />
        <Experience />
        <Education />
        <Contact />
      </main>
      <Footer />
    </>
  );
}
