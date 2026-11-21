export class ApiError extends Error {
  readonly status: number;
  /** Seconds from the Retry-After header (429/503), when the server sent a valid one. */
  readonly retryAfterSeconds: number | null;
  constructor(status: number, message: string, retryAfterSeconds: number | null = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

/** 429: too many attempts. Message is deliberately generic (never reveals whether a user exists). */
export class RateLimitError extends ApiError {
  constructor(retryAfterSeconds: number | null) {
    super(429, 'Muitas tentativas. Aguarde um pouco e tente novamente.', retryAfterSeconds);
    this.name = 'RateLimitError';
  }
}

export class NetworkError extends Error {
  constructor() {
    super('Não foi possível conectar ao servidor.');
    this.name = 'NetworkError';
  }
}
