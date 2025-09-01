interface ImportMetaEnv {
    readonly DEV: boolean;
    readonly PROD: boolean;
    readonly MODE: string;
    readonly VITE_API_BASE: string;
    readonly VITE_API_WS: string;
    readonly VITE_API_HLS: string;
    readonly VITE_API_WEBRTC: string;
}

interface ImportMeta {
    readonly env: ImportMetaEnv;
}
