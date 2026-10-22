declare module '@mono.co/connect.js' {
  interface MonoConnectOptions {
    key: string
    onSuccess: (data: { code: string }) => void
    onClose?: () => void
    onLoad?: () => void
  }
  export default class MonoConnect {
    constructor(options: MonoConnectOptions)
    setup(): void
    open(): void
    reauthorise(accountId: string): void
  }
}
