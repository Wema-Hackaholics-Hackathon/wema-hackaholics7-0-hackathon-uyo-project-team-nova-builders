/**
 * Passkeys ("Biometric unlock") — WebAuthn with the device's own fingerprint,
 * face or PIN. The server sends options as JSON (base64url); the browser API
 * wants ArrayBuffers, so we convert both ways here.
 */
import { api } from './api'

type Json = Record<string, unknown>

const b64urlToBuf = (s: string): ArrayBuffer => {
  const b64 = s.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((s.length + 3) % 4)
  const bin = atob(b64)
  const out = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i)
  return out.buffer
}

const bufToB64url = (buf: ArrayBuffer): string => {
  let bin = ''
  for (const b of new Uint8Array(buf)) bin += String.fromCharCode(b)
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

/** True when this device has a built-in fingerprint / face / PIN authenticator. */
export async function passkeysSupported(): Promise<boolean> {
  if (!window.PublicKeyCredential?.isUserVerifyingPlatformAuthenticatorAvailable) return false
  try {
    return await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable()
  } catch {
    return false
  }
}

/** Create a passkey on this device and save it to the account. */
export async function registerPasskey(): Promise<void> {
  const { ticket, options } = (await api.post<{ ticket: string; options: Json }>('/auth/me/passkeys/options')).data
  const o = options as Json & { challenge: string; user: Json & { id: string }; excludeCredentials?: { id: string; type: string }[] }
  const cred = await navigator.credentials.create({
    publicKey: {
      ...(o as unknown as PublicKeyCredentialCreationOptions),
      challenge: b64urlToBuf(o.challenge),
      user: { ...(o.user as unknown as PublicKeyCredentialUserEntity), id: b64urlToBuf(o.user.id) },
      excludeCredentials: (o.excludeCredentials ?? []).map(c => ({ type: 'public-key' as const, id: b64urlToBuf(c.id) })),
    },
  }) as PublicKeyCredential | null
  if (!cred) throw new Error('Passkey setup was cancelled')
  const r = cred.response as AuthenticatorAttestationResponse
  await api.post('/auth/me/passkeys', {
    ticket,
    credential: {
      id: cred.id, rawId: bufToB64url(cred.rawId), type: cred.type,
      response: {
        clientDataJSON: bufToB64url(r.clientDataJSON),
        attestationObject: bufToB64url(r.attestationObject),
        transports: r.getTransports?.() ?? [],
      },
      clientExtensionResults: cred.getClientExtensionResults(),
    },
  })
}

/** Sign in with a passkey on this device. Returns the server's tokens. */
export async function passkeyAssertion(deviceId: string): Promise<{ access_token: string; refresh_token: string }> {
  const { ticket, options } = (await api.post<{ ticket: string; options: Json }>('/auth/passkey/options')).data
  const o = options as Json & { challenge: string }
  const cred = await navigator.credentials.get({
    publicKey: { ...(o as unknown as PublicKeyCredentialRequestOptions), challenge: b64urlToBuf(o.challenge), allowCredentials: [] },
  }) as PublicKeyCredential | null
  if (!cred) throw new Error('Passkey sign-in was cancelled')
  const r = cred.response as AuthenticatorAssertionResponse
  return (await api.post<{ access_token: string; refresh_token: string }>('/auth/passkey/login', {
    ticket,
    device_id: deviceId,
    credential: {
      id: cred.id, rawId: bufToB64url(cred.rawId), type: cred.type,
      response: {
        clientDataJSON: bufToB64url(r.clientDataJSON),
        authenticatorData: bufToB64url(r.authenticatorData),
        signature: bufToB64url(r.signature),
        userHandle: r.userHandle ? bufToB64url(r.userHandle) : null,
      },
      clientExtensionResults: cred.getClientExtensionResults(),
    },
  })).data
}
