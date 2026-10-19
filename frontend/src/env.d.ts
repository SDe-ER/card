declare global {
  interface Window {
    /** Boot data from card/www/cdms.py (production build only). */
    csrf_token?: string
    lang?: string
    dir?: 'rtl' | 'ltr'
    __messages?: Record<string, string>
  }
}

declare module 'vue' {
  interface ComponentCustomProperties {
    __: (text: string, args?: unknown[], context?: string) => string
  }
}

export {}
