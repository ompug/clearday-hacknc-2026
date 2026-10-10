import { io, type Socket } from "socket.io-client";

import type { RealtimeClient } from "./client";
import type { RealtimeEventName, RealtimeEvents } from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const REFUSED_RETRY_MS = 5000;

/**
 * Socket.IO client for the household and user rooms. The server authenticates the connection with
 * the session cookie (`withCredentials`) and picks the rooms; nothing identifying is sent from here.
 * One shared socket, opened on the first subscription and closed when the last one goes away.
 */
let socket: Socket | null = null;
let subscribers = 0;

function connect(): Socket {
  if (!socket) {
    socket = io(BASE_URL || undefined, {
      path: "/socket.io",
      withCredentials: true,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 10000,
    });
    const s = socket;
    s.on("connect_error", () => {
      // A refused handshake (signed out) is not retried by socket.io itself. Retry slowly; the UI
      // still works without push in the meantime.
      if (!s.active)
        setTimeout(() => socket === s && !s.connected && s.connect(), REFUSED_RETRY_MS);
    });
  }
  return socket;
}

export const socketRealtime: RealtimeClient = {
  on<E extends RealtimeEventName>(event: E, handler: (payload: RealtimeEvents[E]) => void) {
    const s = connect();
    subscribers += 1;
    const listener = (payload: RealtimeEvents[E]) => handler(payload);
    // socket.io-client's typed `on` wants its own event map; our names are plain strings.
    s.on(event as string, listener as (...args: unknown[]) => void);
    return () => {
      s.off(event as string, listener as (...args: unknown[]) => void);
      subscribers -= 1;
      if (subscribers === 0 && socket) {
        socket.disconnect();
        socket = null;
      }
    };
  },
};
