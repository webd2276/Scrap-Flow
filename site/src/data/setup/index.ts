import { CONFIGURATION_SECTIONS } from "./configuration";
import { GETTING_STARTED } from "./gettingStarted";
import { OPERATION_SECTIONS } from "./operations";
import type { SetupSubsection } from "./types";

export const SETUP_SUBSECTIONS: SetupSubsection[] = [
  ...GETTING_STARTED,
  ...CONFIGURATION_SECTIONS,
  ...OPERATION_SECTIONS,
];

export { SETUP_INTRO } from "./types";
export type { SetupSubsection };
