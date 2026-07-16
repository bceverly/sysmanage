// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Ambient types for `stylis` v4, which ships no bundled `.d.ts` and has no
// `@types/stylis` for the 4.x line.  We consume the `prefixer` middleware
// (passed to Emotion's `stylisPlugins`), and `stylis-plugin-rtl` imports the
// `Middleware` type from here too — so declare both.
declare module "stylis" {
  export interface Element {
    type: string;
    value: string;
    props: string[] | string;
    children: Element[] | string;
    root: Element | null;
    parent: Element | null;
    length: number;
    return: string;
    line: number;
    column: number;
  }
  export type Middleware = (
    element: Element,
    index: number,
    children: Element[],
    callback: Middleware,
  ) => string | void;
  export const prefixer: Middleware;
}
