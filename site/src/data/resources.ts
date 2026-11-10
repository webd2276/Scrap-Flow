export type ProjectResource = {
  title: string;
  path: string;
  description: string;
};

export const projectResources: ProjectResource[] = [
  {
    title: "Setup guide",
    path: "SETUP.md",
    description: "Repository setup documentation.",
  },
  {
    title: "Final report",
    path: "docs/FINAL_REPORT.md",
    description: "Dated implementation and verification summary, including unverified items.",
  },
  {
    title: "Presentation guide",
    path: "docs/presentation/README.md",
    description: "Presentation contents and artifact notes.",
  },
  {
    title: "Project presentation",
    path: "docs/presentation/ScrapeFlow-Project-Presentation.pdf",
    description: "Existing 37-slide project presentation.",
  },
];

export function repositoryFileUrl(path: string): string {
  const repositoryUrl = import.meta.env.PUBLIC_REPOSITORY_URL;
  if (!repositoryUrl) {
    return `https://github.com/search?q=${encodeURIComponent(path)}&type=code`;
  }

  const branch = import.meta.env.PUBLIC_REPOSITORY_BRANCH || "master";
  return `${repositoryUrl.replace(/\/$/, "")}/blob/${branch}/${path}`;
}
