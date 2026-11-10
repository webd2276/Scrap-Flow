import { defineConfig } from "astro/config";

const [owner, repository] = (process.env.GITHUB_REPOSITORY ?? "").split("/");
const repositoryName = repository || "web-scrapping-tool";
const isUserOrOrganizationSite =
  owner && repositoryName.toLowerCase() === `${owner}.github.io`.toLowerCase();

export default defineConfig({
  site: owner ? `https://${owner}.github.io` : "https://example.github.io",
  base: isUserOrOrganizationSite ? "/" : `/${repositoryName}`,
});
