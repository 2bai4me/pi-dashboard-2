// DevSettingsContext.tsx — Provider für Dev-Settings (FIX 23.06.2026: Modul fehlte)
// Minimal-Stub: aktuell nur ein leerer Context, da die App nicht alle Felder nutzt.

import { createContext, useContext, ReactNode } from "react"

export interface DevSettings {
  enableDebugMode: boolean
  showAdvancedFields: boolean
  enableBetaFeatures: boolean
  // === FIX 23.06.2026: Alle Felder, die in GatewayStatusBar/Layout verwendet werden ===
  showTaskButton: boolean
  showVariableNames: boolean
  showElementRollover: boolean
}

const defaultSettings: DevSettings = {
  enableDebugMode: false,
  showAdvancedFields: false,
  enableBetaFeatures: false,
  showTaskButton: true,
  showVariableNames: false,
  showElementRollover: true,
}

// === FIX 23.06.2026: useDevSettings gibt die Werte GEFLATTET zurueck, damit Aufrufer
// `dev.showTaskButton` direkt schreiben koennen ohne `dev.settings.showTaskButton`. ===
export type DevSettingsContextValue = DevSettings & {
  update: (patch: Partial<DevSettings>) => void
  setDevSetting: <K extends keyof DevSettings>(key: K, value: DevSettings[K]) => void
  resetDevSettings: () => void
}

const DevSettingsContext = createContext<DevSettingsContextValue>({
  ...defaultSettings,
  update: () => {},
  setDevSetting: () => {},
  resetDevSettings: () => {},
})

export function DevSettingsProvider({ children }: { children: ReactNode }) {
  return (
    <DevSettingsContext.Provider
      value={{
        ...defaultSettings,
        update: () => {},
        setDevSetting: () => {},
        resetDevSettings: () => {},
      }}
    >
      {children}
    </DevSettingsContext.Provider>
  )
}

export function useDevSettings() {
  return useContext(DevSettingsContext)
}
