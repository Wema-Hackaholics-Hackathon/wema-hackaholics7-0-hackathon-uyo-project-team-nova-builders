#!/usr/bin/env node
// npx @foid/node keygen — key pair for private_key_jwt
import { writeFileSync } from 'node:fs'
import { generateKeyPair } from '../src/index.js'

if (process.argv[2] !== 'keygen') {
  console.error('usage: foid keygen')
  process.exit(2)
}
const { privateKeyPem, publicJwk } = generateKeyPair()
writeFileSync('foid_private_key.pem', privateKeyPem, { flag: 'wx', mode: 0o600 })
console.log('Private key written to foid_private_key.pem — keep it on your server, never commit it.\n')
console.log('Public key (paste into FOID Console → Sign-in apps → Edit → Key pair):\n')
console.log(JSON.stringify(publicJwk, null, 2))
