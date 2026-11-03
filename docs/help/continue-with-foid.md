# Continue with FOID

Some banks and apps have a **Continue with FOID** button — like "Sign in with Google", except you arrive already verified, so you don't repeat KYC.

## What happens when you press it

1. **A FOID window opens.** Enter your email and press **Send code** — no password needed.
2. **Enter the 6-digit code** we email you. (If you've turned on two-factor authentication, you'll also enter the code from your authenticator app.)
3. **Check what's being shared.** The screen shows *"\<App\> wants to see:"* and a list, for example your name, your NIN/BVN check results, liveness, or your email and phone.
4. **The first time you share with a business**, FOID asks for a 5-second face check (**Confirm it's you**). This stops someone who can read your email from sharing your identity. Next time with the same business, you skip it.
5. Press **Allow** to share, or **Cancel** to share nothing (*"Cancelled — nothing was shared."*).

The window closes and you're signed in to the app.

## What the business gets

Only what you approved. They get **confirmations** — for example *"NIN verified, last 4 digits 8901"* — **never your full NIN or BVN**. You can revoke access any time in **Consent Requests** (see [Connected apps](./connected-apps)).

| They ask for | They get |
|---|---|
| Your name (always) | First, middle and last name |
| Identity | NIN / BVN check results and the name and date of birth on record |
| Liveness | That your face check passed, and when |
| Contact | Your email address and phone number |
| Financial | Your credential state and trust report (FOID account holders only) |

## "Test app — not checked by FOID"

You'll see this label when an app is still being built and tested. A test app gets your **real first and last name only** — everything else it receives is made-up sample data. FOID hasn't reviewed test apps, so only use them if you trust who sent you.

## No FOID yet?

You can still continue. The window says *"You don't have FOID yet — let's verify you for \<App\>."* You enter your name exactly as on your NIN, then do the NIN check and face check right there.

At the end you'll see **Save this to FOID**:

- **Save this to FOID** creates your FOID with the email you just confirmed, so next time any app using FOID takes seconds. Set a password later with **Forgot password**.
- **No thanks, just continue** finishes the sign-in for that app only. Nothing is saved to a FOID account.

Saving is always your choice — it's never ticked for you.

## Something went wrong?

- *"This sign-in has already finished. Start again from the app."* — go back to the app and press the button again.
- *"Approved, but the app's window was closed."* — the app was closed while you were approving. Go back and try again.
- The window didn't open — your browser may have blocked the popup. Allow popups for that site.
