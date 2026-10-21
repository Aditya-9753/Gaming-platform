/** The built-in artwork spells RUN WIN, so it is only used while the brand name matches. */
export const isBuiltInBrand = (name: string) => /^run\s*win$/i.test(name.trim())
