export interface FairnessVerificationInput {
  serverSeed: string
  clientSeed: string
  nonce: number
  gameId: string
}

export interface FairnessVerificationResult {
  combinedHash: string
  calculatedResult: number | string
  expectedResult: number | string
  isValid: boolean
}
