const configuredBase = import.meta.env.BASE_URL;

export const siteBase = configuredBase.endsWith("/")
  ? configuredBase
  : `${configuredBase}/`;
