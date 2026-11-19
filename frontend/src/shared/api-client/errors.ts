export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/** 429: too many attempts. Message is deliberately generic (never reveals whether a user exists). */
export class RateLimitError extends ApiError {
  readonly retryAfterSeconds: number | null;
  constructor(retryAfterSeconds: number | null) {
    super(429, 'Muitas tentativas. Aguarde um pouco e tente novamente.');
    this.name = 'RateLimitError';
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

export class NetworkError extends Error {
  constructor() {
    super('Não foi possível conectar ao servidor.');
    this.name = 'NetworkError';
  }
}
