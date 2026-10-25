import { useEffect, useMemo, useState } from 'react'
import { AccountContext, loadAccount, saveAccount } from './account.js'

/** Holds the demo account for the whole app and keeps it in localStorage. */
export function AccountProvider({ children }) {
  const [account, setAccount] = useState(loadAccount)
  const [onboarding, setOnboarding] = useState(false)

  useEffect(() => {
    saveAccount(account)
  }, [account])

  const value = useMemo(
    () => ({
      account,
      update: (patch) => setAccount((a) => ({ ...a, ...patch })),
      onboarding,
      startOnboarding: () => setOnboarding(true),
      closeOnboarding: () => setOnboarding(false),
    }),
    [account, onboarding],
  )

  return <AccountContext.Provider value={value}>{children}</AccountContext.Provider>
}
