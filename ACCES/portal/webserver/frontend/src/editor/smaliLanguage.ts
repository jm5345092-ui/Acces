import type { Monaco } from "@monaco-editor/react";

/** Minimal Monarch tokenizer for Smali syntax highlighting — directives,
 * registers, type descriptors, and comments. Not a full grammar, but
 * enough to make Smali readable in the editor (spec section 9). */
export function registerSmaliLanguage(monaco: Monaco) {
  if (monaco.languages.getLanguages().some((l: { id: string }) => l.id === "smali")) return;

  monaco.languages.register({ id: "smali" });

  monaco.languages.setMonarchTokensProvider("smali", {
    tokenizer: {
      root: [
        [/#.*$/, "comment"],
        [/\.(class|super|implements|field|method|end method|annotation|end annotation|locals|param|prologue|line|source|registers|catch|catchall)\b/, "keyword"],
        [/\b(public|private|protected|static|final|abstract|synthetic|constructor|bridge|native|interface|enum|annotation)\b/, "keyword"],
        [/\b(move(-wide|-object)?(\/from16|\/16)?|const(-wide|-string|-class)?(\/\w+)?|invoke-(virtual|super|direct|static|interface)(\/range)?|return(-void|-wide|-object)?|if-\w+|goto(\/\d+)?|new-instance|new-array|array-length|aget(-\w+)?|aput(-\w+)?|iget(-\w+)?|iput(-\w+)?|sget(-\w+)?|sput(-\w+)?|add-\w+|sub-\w+|mul-\w+|div-\w+|rem-\w+|and-\w+|or-\w+|xor-\w+|not-\w+|neg-\w+|cmp\w*|throw|monitor-(enter|exit)|check-cast|instance-of|nop)\b/, "keyword.instruction"],
        [/[pv]\d+/, "variable.register"],
        [/L[\w$/]+;/, "type.identifier"],
        [/\[*[ZBCSIJFDV]/, "type"],
        [/"[^"]*"/, "string"],
        [/:\w+/, "label"],
        [/\b0x[0-9a-fA-F]+\b/, "number.hex"],
        [/\b\d+\b/, "number"],
      ],
    },
  });
}
