import { createContext, useContext } from "react";
import { useTTS } from "./TTSControl";

type TTSContextType = ReturnType<typeof useTTS>;

const TTSContext = createContext<TTSContextType | null>(null);

export function TTSProvider({ children }: { children: React.ReactNode }) {
  const tts = useTTS();
  return <TTSContext.Provider value={tts}>{children}</TTSContext.Provider>;
}

export function useTTSContext() {
  const ctx = useContext(TTSContext);
  if (!ctx) throw new Error("useTTSContext must be used within TTSProvider");
  return ctx;
}
